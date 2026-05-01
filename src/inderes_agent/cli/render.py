"""rich-based output formatting."""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from ..orchestration.workflows import WorkflowResult

console = Console()


def render_answer(text: str) -> None:
    console.print(Markdown(text))


def render_routing(classification, *, dim: bool = True) -> None:
    style = "dim" if dim else None
    summary = (
        f"→ domains: {[d.value for d in classification.domains]}"
        + (f"  · companies: {classification.companies}" if classification.companies else "")
        + (f"  · comparison" if classification.is_comparison else "")
    )
    console.print(summary, style=style)


def render_trace(query: str, workflow: WorkflowResult, lead_model: str) -> None:
    table = Table(title=f"Trace — {query[:60]}")
    table.add_column("Step")
    table.add_column("Domain")
    table.add_column("Company")
    table.add_column("Model")
    table.add_column("Status")

    for i, sr in enumerate(workflow.subagent_results, 1):
        status = "ERROR" if sr.error else "ok"
        table.add_row(
            str(i),
            sr.domain.value,
            sr.company or "-",
            sr.model_used,
            status,
        )
    table.add_row("synth", "lead", "-", lead_model, "ok")

    console.print(table)
    if workflow.fallback_events:
        console.print(
            f"[yellow]ℹ {workflow.fallback_events} subagent(s) used fallback model[/yellow]"
        )


def render_error(msg: str) -> None:
    console.print(Panel(msg, title="Error", border_style="red"))


def render_info(msg: str) -> None:
    console.print(f"[cyan]{msg}[/cyan]")


def render_trace_compact(workflow: WorkflowResult, lead_model: str) -> None:
    """Print per-subagent outcome with output preview — for debugging in one-shot mode."""
    console.print()
    console.rule("[dim]subagent trace[/dim]")
    for sr in workflow.subagent_results:
        status = "[red]ERROR[/red]" if sr.error else "[green]ok[/green]"
        head = f"[bold]{sr.domain.value}[/bold]"
        if sr.company:
            head += f" — {sr.company}"
        head += f"  ({sr.model_used}) {status}"
        console.print(head)
        if sr.error:
            console.print(f"  [red]{sr.error}[/red]")
        else:
            preview = (sr.text or "").strip()
            if not preview:
                console.print("  [yellow](empty response)[/yellow]")
            else:
                snippet = preview if len(preview) <= 600 else preview[:600] + "…"
                console.print(f"  [dim]{snippet}[/dim]")
    console.print(f"[dim]synthesis model: {lead_model}[/dim]")
