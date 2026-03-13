"""Dashboard screen showing overall statistics and guide."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from cc_tui.services.claude_data import get_stats


def _format_bytes(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class StatCard(Static):
    CSS = """
    StatCard {
        width: 1fr;
        height: 5;
        border: round $primary;
        padding: 0 2;
        content-align: center middle;
        text-align: center;
        margin: 0 1;
    }
    StatCard.warning {
        border: round $error;
        color: $error;
    }
    """


class DashboardPane(Container):
    CSS = """
    DashboardPane {
        height: 1fr;
        padding: 1;
    }
    .dash-section-title {
        text-style: bold;
        margin: 1 0 0 0;
        color: $accent;
    }
    .stat-row {
        height: auto;
        margin: 1 0;
    }
    #guide-section {
        height: auto;
        margin-top: 1;
        padding: 1;
        border: round $primary-background;
    }
    .guide-item {
        height: auto;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]Claude Code Data Overview[/]", classes="dash-section-title")
        yield Static("Loading...", id="loading-msg")
        yield Horizontal(id="row-counts", classes="stat-row")
        yield Static("[bold]Orphaned (정리 가능)[/]", classes="dash-section-title")
        yield Horizontal(id="row-orphaned", classes="stat-row")
        yield Static("[bold]Disk Usage[/]", classes="dash-section-title")
        yield Horizontal(id="row-size", classes="stat-row")

        with VerticalScroll(id="guide-section"):
            yield Static("[bold underline]탭 가이드[/]\n", classes="guide-item")
            yield Static(
                "[bold cyan]Projects[/]  .claude.json에 등록된 프로젝트 목록\n"
                "  Claude Code를 사용한 모든 프로젝트 경로와 설정이 여기 저장됩니다.\n"
                "  [green]Found[/] = 프로젝트 폴더가 디스크에 존재  "
                "[red]Missing[/] = 폴더가 삭제/이동됨 (설정만 남음)\n"
                "  트리 구조로 상위 폴더별 그룹핑됩니다.",
                classes="guide-item",
            )
            yield Static(
                "[bold cyan]Sessions[/]  실제 대화 기록 파일 (JSONL)\n"
                "  ~/.claude/projects/ 아래에 프로젝트별로 세션 파일이 저장됩니다.\n"
                "  세션을 선택하면 대화 내용을 미리볼 수 있습니다.",
                classes="guide-item",
            )
            yield Static(
                "[bold cyan]File History[/]  Claude가 편집한 파일의 버전 히스토리\n"
                "  되돌리기용 스냅샷입니다. 시간이 지나면 쌓이므로 정리해도 됩니다.",
                classes="guide-item",
            )
            yield Static(
                "[bold cyan]Orphaned[/]  .claude.json에 매칭 프로젝트가 없는 고아 데이터\n"
                "  프로젝트를 삭제/이동한 뒤 남은 잔여 데이터입니다. 정리해도 안전합니다.",
                classes="guide-item",
            )
            yield Static(
                "[bold cyan]Debug/Todos[/]  세션별 디버그 로그와 할일 메모\n"
                "  임시 데이터이므로 디스크 절약을 위해 정리 가능합니다.",
                classes="guide-item",
            )
            yield Static(
                "[bold cyan]Migrate[/]  세션 마이그레이션 (복사 기반)\n"
                "  프로젝트 경로를 변경했을 때, 기존 세션을 새 경로로 옮깁니다.",
                classes="guide-item",
            )
            yield Static(
                "[bold cyan]Backups[/]  설정/전체 백업 생성 및 복원\n"
                "  작업 전 백업을 만들어두면 실수해도 복구할 수 있습니다.",
                classes="guide-item",
            )

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        self.run_worker(self._load_stats, thread=True)

    def _load_stats(self) -> None:
        stats = get_stats()
        self.app.call_from_thread(self._update_display, stats)

    def _update_display(self, stats) -> None:
        loading = self.query_one("#loading-msg", Static)
        loading.display = False

        row = self.query_one("#row-counts")
        row.remove_children()
        row.mount(StatCard(f"Projects\n[bold]{stats.total_projects}[/]"))
        row.mount(StatCard(f"Sessions\n[bold]{stats.total_sessions}[/]"))
        row.mount(StatCard(f"File History\n[bold]{stats.total_file_history}[/]"))
        row.mount(StatCard(f"Debug\n[bold]{stats.total_debug}[/]"))
        row.mount(StatCard(f"Todos\n[bold]{stats.total_todos}[/]"))

        row_o = self.query_one("#row-orphaned")
        row_o.remove_children()
        total_orphaned = stats.orphaned_sessions + stats.orphaned_file_history + stats.orphaned_debug + stats.orphaned_todos
        row_o.mount(StatCard(
            f"Sessions\n[bold]{stats.orphaned_sessions}[/]",
            classes="warning" if stats.orphaned_sessions else "",
        ))
        row_o.mount(StatCard(
            f"File History\n[bold]{stats.orphaned_file_history}[/]",
            classes="warning" if stats.orphaned_file_history else "",
        ))
        row_o.mount(StatCard(
            f"Debug\n[bold]{stats.orphaned_debug}[/]",
            classes="warning" if stats.orphaned_debug else "",
        ))
        row_o.mount(StatCard(
            f"Todos\n[bold]{stats.orphaned_todos}[/]",
            classes="warning" if stats.orphaned_todos else "",
        ))
        row_o.mount(StatCard(
            f"Total\n[bold]{total_orphaned}[/]",
            classes="warning" if total_orphaned else "",
        ))

        row_s = self.query_one("#row-size")
        row_s.remove_children()
        row_s.mount(StatCard(f".claude/\n[bold]{_format_bytes(stats.claude_dir_size)}[/]"))
        row_s.mount(StatCard(f"projects/\n[bold]{_format_bytes(stats.projects_dir_size)}[/]"))
