"""Dashboard screen - usage stats and overview."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from cc_tui.services.claude_data import get_stats, get_usage_data


def _fmt(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class DashboardPane(Container):
    CSS = """
    DashboardPane {
        height: 1fr;
        padding: 1 2;
    }
    #dash-scroll {
        height: 1fr;
    }
    .dash-title {
        text-style: bold;
        color: $accent;
        margin: 1 0 0 0;
    }
    .dash-divider {
        height: 1;
        margin: 1 0;
        color: $primary-background;
    }
    .dash-content {
        height: auto;
        margin: 0 0 0 2;
    }
    .dash-table {
        height: auto;
        margin: 0 0 0 2;
    }
    .bar-container {
        height: auto;
        margin: 0 0 0 2;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="dash-scroll"):
            yield Static("Loading...", id="dash-loading")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        stats = get_stats()
        usage = get_usage_data()
        self.app.call_from_thread(self._build_dashboard, stats, usage)

    def _build_dashboard(self, stats, usage) -> None:
        scroll = self.query_one("#dash-scroll", VerticalScroll)
        scroll.remove_children()

        # === Header ===
        scroll.mount(Static(
            f"[bold]CC-TUI[/]  Claude Code Session Manager\n"
            f"[dim]Since {usage['first_use'][:10] if usage['first_use'] else 'N/A'}  |  "
            f"{usage['num_startups']} startups  |  "
            f"{usage['total_sessions_ever']} total sessions[/]"
        ))
        scroll.mount(Static("─" * 70, classes="dash-divider"))

        # === Cost Summary ===
        scroll.mount(Static("[bold]  Total Cost[/]", classes="dash-title"))
        scroll.mount(Static(
            f"  [bold green]${usage['total_cost']:.2f}[/]",
            classes="dash-content",
        ))

        # === Model Usage ===
        scroll.mount(Static("[bold]  Model Usage[/]", classes="dash-title"))
        model_lines = []
        for model in sorted(usage["model_totals"].keys()):
            t = usage["model_totals"][model]
            short_name = model.replace("claude-", "").split("-2025")[0].split("-2026")[0]
            model_lines.append(
                f"  [cyan]{short_name:20s}[/]  "
                f"${t['costUSD']:>8.2f}  "
                f"In:{_fmt_tokens(t['inputTokens']):>6s}  "
                f"Out:{_fmt_tokens(t['outputTokens']):>6s}  "
                f"Cache:{_fmt_tokens(t['cacheReadInputTokens']):>7s}"
            )
        scroll.mount(Static("\n".join(model_lines), classes="dash-table"))
        scroll.mount(Static("─" * 70, classes="dash-divider"))

        # === Recent Activity (bar chart) ===
        scroll.mount(Static("[bold]  Recent Activity[/]  (sessions/day)", classes="dash-title"))
        days = usage["sessions_by_day"]
        if days:
            max_count = max(days.values()) if days else 1
            bar_lines = []
            for day, count in list(days.items())[:10]:
                bar_len = int(count / max_count * 30) if max_count > 0 else 0
                bar = "█" * bar_len
                weekday = datetime.strptime(day, "%Y-%m-%d").strftime("%a")
                bar_lines.append(f"  {day} {weekday}  {bar} {count}")
            scroll.mount(Static("\n".join(bar_lines), classes="bar-container"))
        scroll.mount(Static("─" * 70, classes="dash-divider"))

        # === Top Projects by Cost ===
        scroll.mount(Static("[bold]  Top Projects by Cost[/]", classes="dash-title"))
        cost_lines = []
        for i, pc in enumerate(usage["project_costs"][:10], 1):
            bar_len = int(pc["cost"] / usage["project_costs"][0]["cost"] * 20) if usage["project_costs"] else 0
            bar = "▓" * bar_len
            cost_lines.append(f"  {i:2d}. ${pc['cost']:>8.2f}  {bar}  {pc['name']}")
        scroll.mount(Static("\n".join(cost_lines), classes="dash-table"))
        scroll.mount(Static("─" * 70, classes="dash-divider"))

        # === Data Overview ===
        scroll.mount(Static("[bold]  Data Overview[/]", classes="dash-title"))
        overview = (
            f"  {'Projects':20s} {stats.total_projects:>6d}\n"
            f"  {'Session Dirs':20s} {stats.total_sessions:>6d}    [dim](orphaned: {stats.orphaned_sessions})[/]\n"
            f"  {'File History':20s} {stats.total_file_history:>6d}    [dim](orphaned: {stats.orphaned_file_history})[/]\n"
            f"  {'Debug Files':20s} {stats.total_debug:>6d}    [dim](orphaned: {stats.orphaned_debug})[/]\n"
            f"  {'Todos':20s} {stats.total_todos:>6d}    [dim](orphaned: {stats.orphaned_todos})[/]\n"
            f"\n"
            f"  {'Disk: .claude/':20s} {_fmt(stats.claude_dir_size):>10s}\n"
            f"  {'Disk: projects/':20s} {_fmt(stats.projects_dir_size):>10s}"
        )
        scroll.mount(Static(overview, classes="dash-table"))
