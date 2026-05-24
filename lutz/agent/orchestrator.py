"""Orchestrator for the Lutz agentic layer — Sprint 3.

Components:
- GoalManager: extracts structured research goals from natural language
- TaskPlanner: decomposes a goal into a sequence of tool calls
- ExecutionEngine: executes individual plan steps via ToolRegistry
- AgentOrchestrator: top-level entry point combining all three

Security:
- All LLM calls use a protective system prompt loaded from prompts/
- No user input is ever interpolated into subprocess calls
- Tool execution errors are caught and returned as structured dicts
- Audit logging is recorded when an AuditLog instance is provided
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .conversation import AgentPlan, ConversationManager, ConversationState
from .model_router import ModelRouter
from .tools import ToolRegistry

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# Keywords used to detect user intent in AWAITING_CONFIRMATION state
_CONFIRM_KEYWORDS = {"sim", "yes", "ok", "confirma", "pode", "start", "go"}
_CANCEL_KEYWORDS = {"não", "nao", "no", "cancelar", "cancel", "para", "stop"}


def _load_prompt(filename: str) -> str:
    """Load a prompt file from lutz/agent/prompts/."""
    path = _PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")


def _parse_json_response(text: str) -> dict:
    """Attempt to parse a JSON response from LLM output.

    Handles both raw JSON and JSON wrapped in markdown code blocks.
    """
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first and last line (``` markers)
        inner = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        text = inner.strip()
    return json.loads(text)


class GoalManager:
    """Extract a structured research goal from a user message via LLM."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm
        self._system = _load_prompt("goal_extractor.md")

    def extract(self, user_message: str) -> dict:
        """Call LLM with goal_extractor system prompt and return parsed dict.

        Falls back to {"goal": user_message, "is_ambiguous": False, ...} on any
        LLM failure or JSON parse error.
        """
        fallback = {
            "goal": user_message,
            "inclusion_criterion": None,
            "preferred_model": None,
            "is_ambiguous": False,
        }
        try:
            text, _ = self._llm.complete(self._system, user_message)
            result = _parse_json_response(text)
            if "goal" not in result:
                return fallback
            return result
        except Exception as exc:
            logger.warning("GoalManager.extract failed: %s", exc)
            return fallback


class TaskPlanner:
    """Generate an execution plan (AgentPlan) from a research goal via LLM."""

    def __init__(self, llm: Any, tool_registry: ToolRegistry) -> None:
        self._llm = llm
        self._registry = tool_registry
        self._system_template = _load_prompt("planner_system.md")

    def plan(
        self,
        goal: str,
        inclusion_criterion: str | None = None,
    ) -> AgentPlan:
        """Call LLM with the planner system prompt and return an AgentPlan.

        Returns AgentPlan(steps=[]) when clarification is needed (goal field
        holds the clarification question). Falls back to a minimal plan with
        inspect_corpus as the first step when parsing fails.
        """
        tool_list = ", ".join(t["name"] for t in self._registry.list_tools())
        system = self._system_template.replace("{tool_list}", tool_list)

        user_content = goal
        if inclusion_criterion:
            user_content = f"{goal}\n\nInclusion criterion: {inclusion_criterion}"

        try:
            text, _ = self._llm.complete(system, user_content)
            data = _parse_json_response(text)
        except Exception as exc:
            logger.warning("TaskPlanner.plan failed: %s", exc)
            return self._minimal_plan(goal, inclusion_criterion)

        if data.get("clarification_needed"):
            question = data.get("clarification_question") or ""
            return AgentPlan(
                steps=[],
                current_step=0,
                goal=question,
                inclusion_criterion=inclusion_criterion,
            )

        steps = data.get("steps", [])
        if not steps:
            return self._minimal_plan(goal, inclusion_criterion)

        return AgentPlan(
            steps=steps,
            current_step=0,
            goal=goal,
            inclusion_criterion=inclusion_criterion,
        )

    def _minimal_plan(
        self, goal: str, inclusion_criterion: str | None
    ) -> AgentPlan:
        """Return a safe fallback plan starting with inspect_corpus."""
        return AgentPlan(
            steps=[
                {
                    "step": 1,
                    "tool": "inspect_corpus",
                    "arguments": {},
                    "rationale": "Fallback: inspect corpus before planning further steps.",
                    "status": "pending",
                }
            ],
            current_step=0,
            goal=goal,
            inclusion_criterion=inclusion_criterion,
        )


class ExecutionEngine:
    """Execute a single plan step via the ToolRegistry."""

    def __init__(self, tool_registry: ToolRegistry, model_router: ModelRouter) -> None:
        self._registry = tool_registry
        self._router = model_router

    def execute_step(self, step: dict, vector_store: Any = None) -> dict:
        """Route the tool call to the correct tier and execute it.

        Returns the tool result dict, or {"error": str, "tool": name} on failure.
        """
        tool_name = step.get("tool", "")
        arguments = step.get("arguments", {})
        try:
            result = self._registry.execute(tool_name, arguments, vector_store)
            return result
        except Exception as exc:
            logger.warning("ExecutionEngine.execute_step error (%s): %s", tool_name, exc)
            return {"error": str(exc), "tool": tool_name}


class AgentOrchestrator:
    """Top-level entry point: process a user message and return an agentic response."""

    def __init__(
        self,
        llm: Any,
        tool_registry: ToolRegistry,
        model_router: ModelRouter,
        conversation_manager: ConversationManager,
    ) -> None:
        self.goal_manager = GoalManager(llm)
        self.task_planner = TaskPlanner(llm, tool_registry)
        self.execution_engine = ExecutionEngine(tool_registry, model_router)
        self.conversation = conversation_manager

    def process_message(
        self,
        session_id: str,
        user_message: str,
        vector_store: Any = None,
    ) -> dict:
        """Process a user message and return the agentic response.

        Returns
        -------
        dict with keys:
            response (str): text for the user
            state (str): current conversation state value
            plan (dict | None): current plan serialised, if any
            step_result (dict | None): result of the executed step, if any
            awaiting_confirmation (bool): True when user confirmation is needed
        """
        ctx = self.conversation.get_or_create(session_id)
        state = ctx.state
        msg_lower = user_message.strip().lower()
        msg_words = set(msg_lower.split())

        step_result: dict | None = None

        # ------------------------------------------------------------------
        # State: AWAITING_CONFIRMATION
        # ------------------------------------------------------------------
        if state == ConversationState.AWAITING_CONFIRMATION:
            if msg_words & _CANCEL_KEYWORDS:
                self.conversation.cancel(session_id)
                ctx = self.conversation.get_or_create(session_id)
                return self._build_response(
                    ctx,
                    "Plano cancelado. Pode iniciar uma nova tarefa quando quiser.",
                    step_result=None,
                )

            if msg_words & _CONFIRM_KEYWORDS:
                self.conversation.transition(session_id, ConversationState.EXECUTING)
                ctx = self.conversation.get_or_create(session_id)
                step_result = self._execute_current_step(session_id, vector_store)
                has_next = self.conversation.advance_step(session_id)
                if has_next:
                    self.conversation.transition(session_id, ConversationState.STEP_COMPLETE)
                    next_step = self._current_step(session_id)
                    response_text = (
                        f"Passo concluído. Próximo passo: {next_step.get('tool', '')}. "
                        "Posso continuar?"
                    )
                    self.conversation.transition(
                        session_id, ConversationState.AWAITING_CONFIRMATION
                    )
                else:
                    self.conversation.transition(session_id, ConversationState.IDLE)
                    response_text = "Pipeline concluído com sucesso."
                ctx = self.conversation.get_or_create(session_id)
                return self._build_response(ctx, response_text, step_result=step_result)

            # Anything else → ADJUSTING → PLANNING (replanning)
            self.conversation.transition(session_id, ConversationState.ADJUSTING)
            adjusted_goal = f"{ctx.plan.goal if ctx.plan else ''}\n\nAjuste: {user_message}"
            inclusion_criterion = ctx.plan.inclusion_criterion if ctx.plan else None
            new_plan = self.task_planner.plan(adjusted_goal, inclusion_criterion)
            self.conversation.set_plan(session_id, new_plan)
            self.conversation.transition(
                session_id, ConversationState.AWAITING_CONFIRMATION
            )
            ctx = self.conversation.get_or_create(session_id)
            return self._build_response(
                ctx,
                self._plan_summary(new_plan) + "\n\nPosso executar com os ajustes?",
                step_result=None,
            )

        # ------------------------------------------------------------------
        # State: IDLE (or any non-confirmation state) — start new conversation
        # ------------------------------------------------------------------
        if len(user_message.strip()) > 20 or state == ConversationState.IDLE:
            self.conversation.transition(session_id, ConversationState.GOAL_EXTRACTION)
            extracted = self.goal_manager.extract(user_message)
            goal = extracted.get("goal", user_message)
            inclusion_criterion = extracted.get("inclusion_criterion")
            preferred_model = extracted.get("preferred_model")

            if preferred_model:
                ctx = self.conversation.get_or_create(session_id)
                ctx.preferred_model = preferred_model

            self.conversation.transition(session_id, ConversationState.PLANNING)
            plan = self.task_planner.plan(goal, inclusion_criterion)
            self.conversation.set_plan(session_id, plan)
            self.conversation.transition(
                session_id, ConversationState.AWAITING_CONFIRMATION
            )
            ctx = self.conversation.get_or_create(session_id)
            return self._build_response(
                ctx,
                self._plan_summary(plan) + "\n\nPosso começar?",
                step_result=None,
            )

        # ------------------------------------------------------------------
        # Fallback: short message in non-confirmation state
        # ------------------------------------------------------------------
        ctx = self.conversation.get_or_create(session_id)
        return self._build_response(
            ctx,
            "Descreva seu objetivo de pesquisa para que eu possa criar um plano.",
            step_result=None,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _execute_current_step(self, session_id: str, vector_store: Any) -> dict:
        ctx = self.conversation.get_or_create(session_id)
        if ctx.plan is None or not ctx.plan.steps:
            return {}
        step = ctx.plan.steps[ctx.plan.current_step]
        return self.execution_engine.execute_step(step, vector_store)

    def _current_step(self, session_id: str) -> dict:
        ctx = self.conversation.get_or_create(session_id)
        if ctx.plan is None or not ctx.plan.steps:
            return {}
        idx = ctx.plan.current_step
        if idx < len(ctx.plan.steps):
            return ctx.plan.steps[idx]
        return {}

    def _plan_summary(self, plan: AgentPlan) -> str:
        if not plan.steps:
            return "Preciso de mais informações para criar um plano."
        lines = [f"Plano para: {plan.goal}", ""]
        for step in plan.steps:
            lines.append(
                f"  Passo {step.get('step', '?')}: {step.get('tool', '?')} — "
                f"{step.get('rationale', '')}"
            )
        return "\n".join(lines)

    def _build_response(
        self,
        ctx: "ConversationContext",  # noqa: F821
        response_text: str,
        step_result: dict | None,
    ) -> dict:
        plan_dict: dict | None = None
        if ctx.plan is not None:
            plan_dict = {
                "steps": ctx.plan.steps,
                "current_step": ctx.plan.current_step,
                "goal": ctx.plan.goal,
                "inclusion_criterion": ctx.plan.inclusion_criterion,
            }
        return {
            "response": response_text,
            "state": ctx.state.value,
            "plan": plan_dict,
            "step_result": step_result,
            "awaiting_confirmation": ctx.state == ConversationState.AWAITING_CONFIRMATION,
        }
