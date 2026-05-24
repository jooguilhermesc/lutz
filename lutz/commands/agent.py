"""CLI command: lutz agent — interactive agentic session."""
from __future__ import annotations

import json
import uuid

import click
from rich.console import Console

console = Console()


@click.command()
@click.option("--session", "-s", default=None, help="ID de sessão existente")
@click.option(
    "--list-tools",
    "list_tools_flag",
    is_flag=True,
    help="Lista todas as tools disponíveis",
)
@click.option(
    "--model-info",
    default=None,
    metavar="MODEL_ID",
    help="Mostra perfil de um modelo específico",
)
def agent(session: str | None, list_tools_flag: bool, model_info: str | None) -> None:
    """Inicia uma sessão agentiva interativa."""
    from lutz.agent import AgentOrchestrator, get_tool_registry, ModelRouter
    from lutz.agent.conversation import ConversationManager
    from lutz.core.llm_client import LLMClient
    from lutz.utils.project import find_project_root, load_env

    if list_tools_flag:
        registry = get_tool_registry()
        for tool in registry.list_tools():
            console.print(f"[bold]{tool['name']}[/bold] — {tool['description']}")
        return

    if model_info:
        router = ModelRouter()
        profile = router.selector._profiles.get(model_info)
        if not profile:
            console.print(f"[red]Modelo '{model_info}' não encontrado.[/red]")
            return
        console.print_json(json.dumps(profile, indent=2, ensure_ascii=False))
        return

    # Resolve project root and env
    root = find_project_root()
    if root is None:
        console.print(
            "[red]Nenhum projeto lutz encontrado. Execute 'lutz init' primeiro.[/red]"
        )
        raise SystemExit(1)

    env = load_env(root)

    try:
        llm = LLMClient.from_env(env)
    except ValueError as exc:
        console.print(f"[red]Erro de configuração do LLM: {exc}[/red]")
        raise SystemExit(1)

    registry = get_tool_registry()
    router = ModelRouter()
    mgr = ConversationManager()
    orch = AgentOrchestrator(llm, registry, router, mgr)

    session_id = session or str(uuid.uuid4())
    console.print(
        f"[bold teal]Lutz Agent[/bold teal] — sessão [dim]{session_id[:8]}[/dim]"
    )
    console.print(
        "[dim]Digite sua pergunta de pesquisa. 'sair' para encerrar.[/dim]\n"
    )

    while True:
        try:
            user_input = console.input("[bold]Você:[/bold] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Sessão encerrada.[/dim]")
            break

        if user_input.lower() in ("sair", "exit", "quit"):
            break
        if not user_input:
            continue

        result = orch.process_message(session_id, user_input)
        console.print(f"\n[bold green]Lutz:[/bold green] {result['response']}")

        plan = result.get("plan")
        if plan and plan.get("steps"):
            console.print("\n[dim]Plano:[/dim]")
            for step in plan["steps"]:
                status = step.get("status", "pending")
                icon = "✓" if status == "done" else "○"
                rationale = step.get("rationale", "")[:60]
                console.print(
                    f"  {icon} {step['step']}. [bold]{step['tool']}[/bold] — {rationale}"
                )

        console.print()
