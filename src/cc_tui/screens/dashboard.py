"""Dashboard screen - usage stats and overview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.widgets import DataTable, Static, TabPane, TabbedContent

from cc_tui.i18n import t
from cc_tui.services.claude_data import get_period_usage, get_stats, get_usage_data
from cc_tui.utils import format_bytes


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class DashboardPane(Container):
    BINDINGS = [
        Binding("tab", "period_next", "Next Period", show=False, priority=True),
        Binding("shift+tab", "period_prev", "Previous Period", show=False, priority=True),
        Binding("1", "period('daily')", "Daily"),
        Binding("2", "period('weekly')", "Weekly"),
        Binding("3", "period('monthly')", "Monthly"),
    ]

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
    .dash-table {
        height: auto;
        margin: 0 0 0 2;
    }
    #period-tabs {
        height: auto;
        margin: 0;
    }
    .period-pane {
        padding: 0;
        height: auto;
    }
    .period-table {
        height: auto;
        margin: 0;
    }
    """

    CONTENT_IDS = (
        "dash-header", "dash-div-1", "dash-cost-title", "dash-model-table",
        "dash-div-2", "period-tabs",
        "dash-div-3", "dash-top-title", "dash-top-projects",
        "dash-div-4", "dash-overview-title", "dash-overview",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._period = "daily"
        self._cached_stats = None
        self._cached_usage = None
        self._cached_periods: dict[str, list] = {}
        self._loading_period: str | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="dash-scroll"):
            yield Static(f"[bold]CC-TUI[/]  {t('dash.loading')}", id="dash-loading")
            yield Static("", id="dash-header")
            yield Static("", id="dash-div-1")
            yield Static("", id="dash-cost-title", classes="dash-title")
            yield Static("", id="dash-model-table", classes="dash-table")
            yield Static("", id="dash-div-2")
            with TabbedContent(initial="period-daily", id="period-tabs"):
                with TabPane("Daily", id="period-daily", classes="period-pane"):
                    yield DataTable(id="period-table-daily", classes="period-table")
                with TabPane("Weekly", id="period-weekly", classes="period-pane"):
                    yield DataTable(id="period-table-weekly", classes="period-table")
                with TabPane("Monthly", id="period-monthly", classes="period-pane"):
                    yield DataTable(id="period-table-monthly", classes="period-table")
            yield Static("", id="dash-div-3")
            yield Static("", id="dash-top-title", classes="dash-title")
            yield Static("", id="dash-top-projects", classes="dash-table")
            yield Static("", id="dash-div-4")
            yield Static("", id="dash-overview-title", classes="dash-title")
            yield Static("", id="dash-overview", classes="dash-table")

    def on_mount(self) -> None:
        for wid in self.CONTENT_IDS:
            self.query_one(f"#{wid}").display = False
        for key in ("daily", "weekly", "monthly"):
            pt = self._get_period_table(key)
            pt.zebra_stripes = True
            pt.show_cursor = False
            pt.add_columns("Period", "Cost", "Messages", "Input", "Output", "Cache")
        self.refresh_data()

    def refresh_data(self) -> None:
        self._cached_periods = {}
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        stats = get_stats()
        usage = get_usage_data()
        daily = get_period_usage("daily")
        self.app.call_from_thread(self._on_data_loaded, stats, usage, {"daily": daily})
        # Load weekly/monthly in background
        for key in ("weekly", "monthly"):
            data = get_period_usage(key)
            self.app.call_from_thread(self._on_bg_period_loaded, key, data)

    def _on_data_loaded(self, stats, usage, periods=None) -> None:
        self._cached_stats = stats
        self._cached_usage = usage
        if periods:
            self._cached_periods.update(periods)
        self.query_one("#dash-loading", Static).display = False
        for wid in self.CONTENT_IDS:
            self.query_one(f"#{wid}").display = True
        self._render_all()

    def _on_bg_period_loaded(self, key: str, data: list) -> None:
        """Callback for background-loaded weekly/monthly data."""
        self._cached_periods[key] = data
        if self._period == key:
            self._render_period_section()

    def _render_all(self) -> None:
        stats = self._cached_stats
        usage = self._cached_usage
        if not stats or not usage:
            return

        title = f"[bold]CC-TUI[/]  [dim]Filter:[/] {self.app.target_path}" if self.app.target_path else "[bold]CC-TUI[/]  Claude Code Session Manager"
        self.query_one("#dash-header", Static).update(
            f"{title}\n"
            f"[dim]Since {usage['first_use'][:10] if usage['first_use'] else 'N/A'}  |  "
            f"{usage['num_startups']} startups  |  "
            f"{usage['total_sessions_ever']} total sessions[/]"
        )
        self.query_one("#dash-div-1", Static).update("─" * 70)

        self.query_one("#dash-cost-title", Static).update(
            f"[bold]  {t('dash.total_cost')}  [green]${usage['total_cost']:.2f}[/][/]"
        )
        model_lines = []
        for model in sorted(usage["model_totals"].keys()):
            mt = usage["model_totals"][model]
            short = model.replace("claude-", "").split("-2025")[0].split("-2026")[0]
            model_lines.append(
                f"  [cyan]{short:20s}[/]  "
                f"${mt['costUSD']:>8.2f}  "
                f"In:{_fmt_tokens(mt['inputTokens']):>6s}  "
                f"Out:{_fmt_tokens(mt['outputTokens']):>6s}  "
                f"Cache:{_fmt_tokens(mt['cacheReadInputTokens']):>7s}"
            )
        self.query_one("#dash-model-table", Static).update("\n".join(model_lines))
        self.query_one("#dash-div-2", Static).update("─" * 70)

        self._render_period_section()

        self.query_one("#dash-div-3", Static).update("─" * 70)

        self.query_one("#dash-top-title", Static).update(
            f"[bold]  {t('dash.top_projects')}[/]  [dim]({t('dash.top10')})[/]"
        )
        cost_lines = []
        for i, pc in enumerate(usage["project_costs"][:10], 1):
            bar_len = int(pc["cost"] / usage["project_costs"][0]["cost"] * 20) if usage["project_costs"] else 0
            bar = "▓" * bar_len
            cost_lines.append(f"  {i:2d}. ${pc['cost']:>8.2f}  {bar}  {pc['name']}")
        self.query_one("#dash-top-projects", Static).update("\n".join(cost_lines))
        self.query_one("#dash-div-4", Static).update("─" * 70)

        self.query_one("#dash-overview-title", Static).update(f"[bold]  {t('dash.data_overview')}[/]")
        overview = (
            f"  {'Projects':20s} {stats.total_projects:>6d}\n"
            f"  {'Session Dirs':20s} {stats.total_sessions:>6d}    [dim](orphaned: {stats.orphaned_sessions})[/]\n"
            f"  {'File History':20s} {stats.total_file_history:>6d}    [dim](orphaned: {stats.orphaned_file_history})[/]\n"
            f"  {'Debug Files':20s} {stats.total_debug:>6d}    [dim](orphaned: {stats.orphaned_debug})[/]\n"
            f"  {'Todos':20s} {stats.total_todos:>6d}    [dim](orphaned: {stats.orphaned_todos})[/]\n"
            f"\n"
            f"  {'Disk: .claude/':20s} {format_bytes(stats.claude_dir_size):>10s}\n"
            f"  {'Disk: projects/':20s} {format_bytes(stats.projects_dir_size):>10s}"
        )
        self.query_one("#dash-overview", Static).update(overview)

    def _render_period_section(self) -> None:
        """Render the period table from cache."""
        self.query_one("#period-tabs", TabbedContent).active = f"period-{self._period}"

        period_loaded = self._period in self._cached_periods
        period_data = self._cached_periods.get(self._period, [])
        pt = self._get_period_table(self._period)
        pt.clear()

        if period_data:
            for p in period_data[:20]:
                pt.add_row(
                    p["period"],
                    f"${p['total_cost']:.2f}",
                    str(p["total_messages"]),
                    _fmt_tokens(p["total_input"]),
                    _fmt_tokens(p["total_output"]),
                    _fmt_tokens(p["total_cache"]),
                )
        elif not period_loaded:
            pt.add_row(t("dash.loading_period"), "", "", "", "", "")
        else:
            pt.add_row(t("dash.no_data"), "", "", "", "", "")

        pt.move_cursor(row=0, column=0, animate=False, scroll=False)
        pt.scroll_home(animate=False, immediate=True, x_axis=False, y_axis=True)

    def _get_period_table(self, key: str) -> DataTable:
        return self.query_one(f"#period-table-{key}", DataTable)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Handle period changes from the nested tabbed content."""
        if event.tabbed_content.id != "period-tabs":
            return
        tab_id = event.tab.id or ""
        if tab_id.startswith("period-"):
            period = tab_id.replace("period-", "", 1)
            if period != self._period:
                self.action_period(period)

    def action_period(self, key: str) -> None:
        """Switch period via keyboard (1/2/3)."""
        self._period = key
        if key in self._cached_periods:
            self._render_period_section()
        else:
            self._render_period_section()
            self.run_worker(lambda k=key: self._load_period(k), thread=True)

    def action_period_next(self) -> None:
        """Cycle to the next dashboard period immediately."""
        order = ["daily", "weekly", "monthly"]
        idx = order.index(self._period)
        self.action_period(order[(idx + 1) % len(order)])

    def action_period_prev(self) -> None:
        """Cycle to the previous dashboard period immediately."""
        order = ["daily", "weekly", "monthly"]
        idx = order.index(self._period)
        self.action_period(order[(idx - 1) % len(order)])

    def _load_period(self, key: str) -> None:
        data = get_period_usage(key)
        self.app.call_from_thread(self._on_period_loaded, key, data)

    def _on_period_loaded(self, key: str, data: list) -> None:
        self._cached_periods[key] = data
        self._loading_period = None
        if self._period == key:
            self._render_period_section()
