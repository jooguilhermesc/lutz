"""Tests for lutz/agent/orchestrator.py and lutz/agent/conversation.py — Sprint 3.

All LLM interactions are mocked. No real API calls are made.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lutz.agent.conversation import (
    AgentPlan,
    ConversationContext,
    ConversationManager,
    ConversationState,
)
from lutz.agent.orchestrator import (
    AgentOrchestrator,
    ExecutionEngine,
    GoalManager,
    TaskPlanner,
    _load_prompt,
)
from lutz.agent.tools import ToolRegistry, get_tool_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm(response: str = "{}") -> MagicMock:
    """Return a mock LLMClient whose .complete() returns (response, {})."""
    llm = MagicMock()
    llm.complete.return_value = (response, {})
    return llm


def _make_tool_registry() -> MagicMock:
    registry = MagicMock(spec=ToolRegistry)
    registry.list_tools.return_value = [
        {"name": "inspect_corpus", "description": "...", "parameters": {}}
    ]
    registry.execute.return_value = {"article_count": 5}
    return registry


def _make_model_router() -> MagicMock:
    router = MagicMock()
    router.route.return_value = {
        "tier": 0,
        "model": "gpt-4o-mini",
        "provider": "openai",
        "base_url": "",
        "adapted_prompt": "",
        "temperature": 0.2,
        "profile": {},
    }
    return router


# ---------------------------------------------------------------------------
# 1. ConversationManager — creates session
# ---------------------------------------------------------------------------


def test_conversation_manager_creates_session():
    """get_or_create deve criar sessão nova com state=IDLE."""
    manager = ConversationManager()
    ctx = manager.get_or_create("sess-001")

    assert isinstance(ctx, ConversationContext)
    assert ctx.session_id == "sess-001"
    assert ctx.state == ConversationState.IDLE


# ---------------------------------------------------------------------------
# 2. ConversationManager — transition
# ---------------------------------------------------------------------------


def test_conversation_manager_transition():
    """transition deve alterar o state do contexto correto."""
    manager = ConversationManager()
    manager.get_or_create("sess-002")
    manager.transition("sess-002", ConversationState.PLANNING)

    ctx = manager.get_or_create("sess-002")
    assert ctx.state == ConversationState.PLANNING


# ---------------------------------------------------------------------------
# 3. ConversationManager — advance_step increments
# ---------------------------------------------------------------------------


def test_conversation_manager_advance_step():
    """advance_step deve incrementar current_step e retornar True quando há próximo."""
    manager = ConversationManager()
    manager.get_or_create("sess-003")
    plan = AgentPlan(
        steps=[
            {"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "a"},
            {"step": 2, "tool": "search_corpus", "arguments": {}, "rationale": "b"},
        ],
        current_step=0,
        goal="test",
    )
    manager.set_plan("sess-003", plan)

    result = manager.advance_step("sess-003")
    ctx = manager.get_or_create("sess-003")

    assert result is True
    assert ctx.plan.current_step == 1


# ---------------------------------------------------------------------------
# 4. ConversationManager — advance_step returns False at end
# ---------------------------------------------------------------------------


def test_conversation_manager_advance_step_returns_false_at_end():
    """advance_step deve retornar False quando não há mais passos."""
    manager = ConversationManager()
    manager.get_or_create("sess-004")
    plan = AgentPlan(
        steps=[{"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "a"}],
        current_step=0,
        goal="test",
    )
    manager.set_plan("sess-004", plan)

    result = manager.advance_step("sess-004")

    assert result is False


# ---------------------------------------------------------------------------
# 5. GoalManager — extract returns dict with "goal"
# ---------------------------------------------------------------------------


def test_goal_manager_extract_returns_dict():
    """GoalManager.extract deve chamar LLM e retornar dict com chave 'goal'."""
    payload = json.dumps({
        "goal": "revisão sobre IA na educação",
        "inclusion_criterion": "estudos empíricos",
        "preferred_model": None,
        "is_ambiguous": False,
    })
    llm = _make_llm(payload)
    gm = GoalManager(llm)

    result = gm.extract("Quero fazer uma revisão sobre IA na educação")

    assert isinstance(result, dict)
    assert result["goal"] == "revisão sobre IA na educação"
    assert result["is_ambiguous"] is False
    llm.complete.assert_called_once()


# ---------------------------------------------------------------------------
# 6. GoalManager — handles LLM failure with fallback
# ---------------------------------------------------------------------------


def test_goal_manager_handles_llm_failure():
    """Quando LLM lança exceção, GoalManager deve retornar fallback com goal=user_message."""
    llm = MagicMock()
    llm.complete.side_effect = RuntimeError("connection error")
    gm = GoalManager(llm)

    msg = "Quero analisar artigos sobre machine learning"
    result = gm.extract(msg)

    assert result["goal"] == msg
    assert result["is_ambiguous"] is False


# ---------------------------------------------------------------------------
# 7. GoalManager — handles invalid JSON from LLM
# ---------------------------------------------------------------------------


def test_goal_manager_handles_invalid_json():
    """Quando LLM retorna JSON inválido, GoalManager deve retornar fallback."""
    llm = _make_llm("não é um JSON válido!!!")
    gm = GoalManager(llm)

    msg = "Faça uma análise do corpus"
    result = gm.extract(msg)

    assert result["goal"] == msg
    assert result["is_ambiguous"] is False


# ---------------------------------------------------------------------------
# 8. TaskPlanner — returns AgentPlan with steps
# ---------------------------------------------------------------------------


def test_task_planner_returns_agent_plan():
    """TaskPlanner.plan deve chamar LLM e retornar AgentPlan com steps preenchidos."""
    payload = json.dumps({
        "steps": [
            {"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "primeiro"},
            {"step": 2, "tool": "analyze_corpus", "arguments": {"prompt": "IA"}, "rationale": "segundo"},
        ],
        "clarification_needed": False,
        "clarification_question": None,
    })
    llm = _make_llm(payload)
    registry = _make_tool_registry()
    planner = TaskPlanner(llm, registry)

    plan = planner.plan("revisão sobre IA")

    assert isinstance(plan, AgentPlan)
    assert len(plan.steps) == 2
    assert plan.steps[0]["tool"] == "inspect_corpus"
    assert plan.goal == "revisão sobre IA"


# ---------------------------------------------------------------------------
# 9. TaskPlanner — handles clarification_needed=True
# ---------------------------------------------------------------------------


def test_task_planner_handles_clarification_needed():
    """Quando LLM retorna clarification_needed=True, plano deve ter steps=[]."""
    payload = json.dumps({
        "steps": [],
        "clarification_needed": True,
        "clarification_question": "Você quer screening individual ou síntese aberta?",
    })
    llm = _make_llm(payload)
    registry = _make_tool_registry()
    planner = TaskPlanner(llm, registry)

    plan = planner.plan("analisa os artigos")

    assert isinstance(plan, AgentPlan)
    assert plan.steps == []
    # goal deve conter a pergunta de clarificação
    assert "Você quer" in plan.goal or plan.goal == ""


# ---------------------------------------------------------------------------
# 10. TaskPlanner — handles parse failure with fallback plan
# ---------------------------------------------------------------------------


def test_task_planner_handles_parse_failure():
    """Quando LLM retorna lixo, TaskPlanner deve retornar plano mínimo com inspect_corpus."""
    llm = _make_llm("isso não é JSON")
    registry = _make_tool_registry()
    planner = TaskPlanner(llm, registry)

    plan = planner.plan("objetivo qualquer")

    assert isinstance(plan, AgentPlan)
    assert len(plan.steps) >= 1
    assert plan.steps[0]["tool"] == "inspect_corpus"


# ---------------------------------------------------------------------------
# 11. ExecutionEngine — executes tool via ToolRegistry
# ---------------------------------------------------------------------------


def test_execution_engine_executes_tool():
    """ExecutionEngine.execute_step deve chamar ToolRegistry.execute e retornar resultado."""
    registry = _make_tool_registry()
    router = _make_model_router()
    engine = ExecutionEngine(registry, router)

    step = {"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "teste"}
    result = engine.execute_step(step)

    registry.execute.assert_called_once_with(
        "inspect_corpus", {}, vector_store=None, job_manager=None
    )
    assert result == {"article_count": 5}


# ---------------------------------------------------------------------------
# 12. ExecutionEngine — handles tool error
# ---------------------------------------------------------------------------


def test_execution_engine_handles_tool_error():
    """Quando ToolRegistry.execute lança exceção, deve retornar {"error": ..., "tool": ...}."""
    registry = MagicMock(spec=ToolRegistry)
    registry.execute.side_effect = ValueError("tool broke")
    router = _make_model_router()
    engine = ExecutionEngine(registry, router)

    step = {"step": 1, "tool": "analyze_corpus", "arguments": {}, "rationale": "teste"}
    result = engine.execute_step(step)

    assert "error" in result
    assert "tool broke" in result["error"]
    assert result["tool"] == "analyze_corpus"


# ---------------------------------------------------------------------------
# 13. AgentOrchestrator — IDLE → AWAITING_CONFIRMATION
# ---------------------------------------------------------------------------


def test_orchestrator_idle_to_awaiting_confirmation():
    """Mensagem longa em IDLE deve levar ao estado AWAITING_CONFIRMATION."""
    goal_payload = json.dumps({
        "goal": "revisão sistemática sobre IA",
        "inclusion_criterion": None,
        "preferred_model": None,
        "is_ambiguous": False,
    })
    plan_payload = json.dumps({
        "steps": [
            {"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "inspeciona"},
        ],
        "clarification_needed": False,
        "clarification_question": None,
    })
    # LLM é chamado 2x: goal extraction + planning
    llm = MagicMock()
    llm.complete.side_effect = [
        (goal_payload, {}),
        (plan_payload, {}),
    ]
    registry = _make_tool_registry()
    router = _make_model_router()
    conversation = ConversationManager()
    orchestrator = AgentOrchestrator(llm, registry, router, conversation)

    response = orchestrator.process_message(
        "sess-010",
        "Preciso fazer uma revisão sistemática completa sobre IA na educação básica"
    )

    assert response["state"] == ConversationState.AWAITING_CONFIRMATION.value
    assert response["awaiting_confirmation"] is True
    assert response["plan"] is not None


# ---------------------------------------------------------------------------
# 14. AgentOrchestrator — "sim" triggers execution
# ---------------------------------------------------------------------------


def test_orchestrator_confirmation_triggers_execute():
    """'sim' em AWAITING_CONFIRMATION deve executar o passo e retornar resultado."""
    registry = _make_tool_registry()
    router = _make_model_router()
    conversation = ConversationManager()

    # Configurar sessão já em AWAITING_CONFIRMATION com plano
    ctx = conversation.get_or_create("sess-011")
    plan = AgentPlan(
        steps=[{"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "r"}],
        current_step=0,
        goal="teste",
    )
    conversation.set_plan("sess-011", plan)
    conversation.transition("sess-011", ConversationState.AWAITING_CONFIRMATION)

    llm = _make_llm("{}")
    orchestrator = AgentOrchestrator(llm, registry, router, conversation)

    response = orchestrator.process_message("sess-011", "sim")

    assert response["step_result"] is not None
    registry.execute.assert_called_once()


# ---------------------------------------------------------------------------
# 15. AgentOrchestrator — "cancelar" sets state to IDLE
# ---------------------------------------------------------------------------


def test_orchestrator_cancel():
    """'cancelar' em AWAITING_CONFIRMATION deve levar ao estado IDLE."""
    registry = _make_tool_registry()
    router = _make_model_router()
    conversation = ConversationManager()

    ctx = conversation.get_or_create("sess-012")
    plan = AgentPlan(
        steps=[{"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "r"}],
        current_step=0,
        goal="teste",
    )
    conversation.set_plan("sess-012", plan)
    conversation.transition("sess-012", ConversationState.AWAITING_CONFIRMATION)

    llm = _make_llm("{}")
    orchestrator = AgentOrchestrator(llm, registry, router, conversation)

    response = orchestrator.process_message("sess-012", "cancelar")

    assert response["state"] == ConversationState.IDLE.value


# ---------------------------------------------------------------------------
# 16. AgentOrchestrator — adjustment replans
# ---------------------------------------------------------------------------


def test_orchestrator_adjustment_replans():
    """Resposta de ajuste em AWAITING_CONFIRMATION deve replanejamento."""
    plan_payload = json.dumps({
        "steps": [
            {"step": 1, "tool": "analyze_corpus", "arguments": {"prompt": "ajustado"}, "rationale": "novo"},
        ],
        "clarification_needed": False,
        "clarification_question": None,
    })
    llm = MagicMock()
    llm.complete.return_value = (plan_payload, {})

    registry = _make_tool_registry()
    router = _make_model_router()
    conversation = ConversationManager()

    ctx = conversation.get_or_create("sess-013")
    plan = AgentPlan(
        steps=[{"step": 1, "tool": "inspect_corpus", "arguments": {}, "rationale": "r"}],
        current_step=0,
        goal="teste original",
    )
    conversation.set_plan("sess-013", plan)
    conversation.transition("sess-013", ConversationState.AWAITING_CONFIRMATION)

    orchestrator = AgentOrchestrator(llm, registry, router, conversation)

    response = orchestrator.process_message(
        "sess-013",
        "quero usar 8 workers e filtrar só methodology"
    )

    # Deve ter replanejado — estado é AWAITING_CONFIRMATION com novo plano
    assert response["state"] == ConversationState.AWAITING_CONFIRMATION.value
    assert response["plan"] is not None
    llm.complete.assert_called()


# ---------------------------------------------------------------------------
# 17. _load_prompt — returns non-empty string for planner_system.md
# ---------------------------------------------------------------------------


def test_load_prompt_returns_string():
    """_load_prompt('planner_system.md') deve retornar string não vazia."""
    content = _load_prompt("planner_system.md")
    assert isinstance(content, str)
    assert len(content) > 0


# ---------------------------------------------------------------------------
# 18. ConversationManager — cancel() sets state to IDLE
# ---------------------------------------------------------------------------


def test_conversation_manager_cancel_sets_idle():
    """cancel() deve definir state=IDLE independente do estado anterior."""
    manager = ConversationManager()
    manager.get_or_create("sess-014")
    manager.transition("sess-014", ConversationState.EXECUTING)
    manager.cancel("sess-014")

    ctx = manager.get_or_create("sess-014")
    assert ctx.state == ConversationState.IDLE
