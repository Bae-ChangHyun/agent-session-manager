"""Internationalization support for cc-tui."""

from __future__ import annotations

import os

_current_lang = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── App ──
    "app.quit": {"en": "Quit", "ko": "종료"},
    "app.refresh": {"en": "Refresh", "ko": "새로고침"},
    "app.refreshed": {"en": "Refreshed", "ko": "새로고침 완료"},
    # Tab names
    "tab.dashboard": {"en": "Dashboard", "ko": "대시보드"},
    "tab.projects": {"en": "Projects", "ko": "프로젝트"},
    "tab.file_history": {"en": "File History", "ko": "파일 히스토리"},
    "tab.orphaned": {"en": "Orphaned", "ko": "고아 데이터"},
    "tab.debug_todos": {"en": "Debug/Todos", "ko": "디버그/Todos"},
    "tab.migrate": {"en": "Migrate", "ko": "마이그레이션"},
    "tab.backups": {"en": "Backups", "ko": "백업"},
    # Confirm dialog
    "confirm.yes": {"en": "Confirm (y)", "ko": "확인 (y)"},
    "confirm.no": {"en": "Cancel (n)", "ko": "취소 (n)"},
    "confirm.bulk_delete": {
        "en": "Delete {count} selected {type}?",
        "ko": "선택한 {count}개 {type}를 삭제하시겠습니까?",
    },
    "confirm.group_delete": {
        "en": "Delete {count} {type} in this group?",
        "ko": "이 그룹의 {count}개 {type}를 삭제하시겠습니까?",
    },
    # ── Dashboard ──
    "dash.loading": {"en": "Loading dashboard data...", "ko": "대시보드 데이터 로딩 중..."},
    "dash.total_cost": {"en": "Total Cost", "ko": "총 비용"},
    "dash.top_projects": {"en": "Top Projects by Cost", "ko": "비용 상위 프로젝트"},
    "dash.top10": {"en": "Top 10", "ko": "상위 10개"},
    "dash.data_overview": {"en": "Data Overview", "ko": "데이터 개요"},
    "dash.no_data": {"en": "(no data)", "ko": "(데이터 없음)"},
    # ── Projects ──
    "proj.info": {
        "en": (
            "[bold]Projects[/] - .claude.json projects + sessions\n"
            "[dim]Expand folder to see sessions. Click session to preview conversation.\n"
            "[green]O[/]=folder exists  [red]X[/]=folder deleted/moved (config only)[/]"
        ),
        "ko": (
            "[bold]Projects[/] - .claude.json 프로젝트 + 세션\n"
            "[dim]폴더를 펼치면 세션 목록이 보입니다. 세션을 클릭하면 대화 내용을 미리봅니다.\n"
            "[green]O[/]=폴더 존재  [red]X[/]=폴더 삭제/이동됨(설정만 남음)[/]"
        ),
    },
    "proj.select_hint": {
        "en": "Select a project or session",
        "ko": "프로젝트 또는 세션을 선택하세요",
    },
    "proj.btn_trash_session": {"en": "Delete Session", "ko": "세션 삭제"},
    "proj.btn_remove_config": {"en": "Remove from Config", "ko": "설정에서 제거"},
    "proj.status_found": {"en": "[green]Found[/]", "ko": "[green]존재[/]"},
    "proj.status_missing": {
        "en": "[red]Missing[/] (folder deleted/moved)",
        "ko": "[red]Missing[/] (폴더 삭제/이동됨)",
    },
    "proj.sessions_hint": {
        "en": "[dim]To delete sessions, expand the project and select individual sessions.[/]",
        "ko": "[dim]세션을 삭제하려면 프로젝트를 펼쳐서 개별 세션을 선택하세요.[/]",
    },
    "proj.no_sessions_hint": {
        "en": "[dim]No sessions. You can remove this from config.[/]",
        "ko": "[dim]세션이 없으므로 설정에서 제거할 수 있습니다.[/]",
    },
    "proj.confirm_trash_session": {
        "en": "Delete this session?\n\nSession: {sid}\n\n[bold]Only this 1 session will be deleted.[/]\n[dim]Moved to trash, recoverable[/]",
        "ko": "이 세션을 삭제하시겠습니까?\n\nSession: {sid}\n\n[bold]이 세션 1개만 삭제됩니다.[/]\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "proj.confirm_remove_config": {
        "en": "Remove project from config?\n\nPath: {path}\n\n[dim]No sessions. Only removes from .claude.json.[/]",
        "ko": "설정에서 프로젝트를 제거하시겠습니까?\n\nPath: {path}\n\n[dim]세션이 없는 프로젝트입니다.\n.claude.json 목록에서만 제거됩니다.[/]",
    },
    "proj.trash_ok": {"en": "Session deleted: {sid}", "ko": "세션 삭제 완료: {sid}"},
    "proj.trash_fail": {"en": "Delete failed", "ko": "삭제 실패"},
    "proj.config_removed": {"en": "Removed from config: {path}", "ko": "설정에서 제거됨: {path}"},
    "proj.config_fail": {"en": "Remove failed", "ko": "제거 실패"},
    "proj.no_dir_info": {"en": "No project directory info", "ko": "프로젝트 디렉토리 정보 없음"},
    "proj.no_messages": {"en": "[dim]No conversation messages found[/]", "ko": "[dim]대화 메시지 없음[/]"},
    "proj.btn_trash_orphaned": {"en": "Trash Orphaned Sessions ({count})", "ko": "Orphaned 세션 삭제 ({count})"},
    "proj.confirm_trash_orphaned": {
        "en": "Delete all orphaned session directories?\n\n{count} dirs with no matching project.\n[dim]Moved to trash, recoverable[/]",
        "ko": "Orphaned 세션 디렉토리를 모두 삭제?\n\n매칭 프로젝트 없는 {count}개.\n[dim]휴지통으로 이동, 복구 가능[/]",
    },
    # ── File History ── detail panel status descriptions
    "fh.status_orphaned_desc": {
        "en": (
            "[yellow bold]Orphaned[/]\n"
            "[dim]Session deleted, no matching project.\n"
            "Safe to delete.[/]"
        ),
        "ko": (
            "[yellow bold]Orphaned[/]\n"
            "[dim]세션이 삭제되어 매칭되지 않습니다.\n"
            "안전하게 삭제 가능합니다.[/]"
        ),
    },
    "fh.status_active_desc": {
        "en": (
            "[green bold]Active[/]\n"
            "[dim]Connected to a current project.\n"
            "Deleting will disable file rollback for this project.[/]"
        ),
        "ko": (
            "[green bold]Active[/]\n"
            "[dim]현재 프로젝트와 연결되어 있습니다.\n"
            "삭제 시 해당 프로젝트의 파일 되돌리기 기능을 사용할 수 없습니다.[/]"
        ),
    },
    # ── File History ──
    "fh.info": {
        "en": (
            "[bold]File History[/] - Version history/snapshots of files edited by Claude\n"
            "[dim]Stored in ~/.claude/file-history/. Used for file rollback; old entries can be cleaned.\n"
            "[yellow]Orphaned[/]=no matching project found[/]"
        ),
        "ko": (
            "[bold]File History[/] - Claude가 편집한 파일의 버전 히스토리/스냅샷\n"
            "[dim]~/.claude/file-history/ 에 저장됩니다. 파일 되돌리기용이므로 오래된 것은 정리해도 됩니다.\n"
            "[yellow]Orphaned[/]=프로젝트가 삭제/이동되어 매칭되지 않는 히스토리[/]"
        ),
    },
    "fh.select_hint": {
        "en": "Select a file history entry to see details",
        "ko": "파일 히스토리를 선택하면 상세 정보가 표시됩니다",
    },
    "fh.btn_trash": {"en": "Trash Selected", "ko": "선택 항목 삭제"},
    "fh.confirm_trash": {
        "en": "Move file history to trash?\n\n{name}\n[dim]Moved to trash, recoverable[/]",
        "ko": "File history를 휴지통으로 이동?\n\n{name}\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "fh.btn_trash_orphaned": {"en": "Trash All Orphaned ({count})", "ko": "Orphaned 전체 삭제 ({count})"},
    "fh.confirm_trash_orphaned": {
        "en": "Delete all orphaned file history?\n\n{count} orphaned entries.\n[dim]Moved to trash, recoverable[/]",
        "ko": "Orphaned 파일 히스토리를 모두 삭제?\n\n{count}개.\n[dim]휴지통으로 이동, 복구 가능[/]",
    },
    # ── Orphaned ──
    "orph.info": {
        "en": (
            "[bold]Orphaned[/] - Leftover data with no matching project in .claude.json\n"
            "[dim]Data remaining after projects were deleted/moved.\n"
            "[bold]Select an item[/] then press the button. Moved to trash, recoverable.[/]"
        ),
        "ko": (
            "[bold]Orphaned[/] - .claude.json에 매칭 프로젝트가 없는 잔여 데이터\n"
            "[dim]프로젝트를 삭제/이동한 뒤 남은 데이터입니다.\n"
            "[bold]삭제는 개별 항목 선택 후[/] 버튼을 눌러주세요. 휴지통으로 이동되며 복구 가능합니다.[/]"
        ),
    },
    "orph.select_first": {"en": "Select an item first", "ko": "삭제할 항목을 선택하세요"},
    "orph.session_header": {
        "en": "[bold yellow]Orphaned Session Dirs[/]  [dim](project dirs not in .claude.json, each may contain multiple sessions)[/]",
        "ko": "[bold yellow]Orphaned Session Dirs[/]  [dim](.claude.json에 없는 프로젝트 디렉토리, 각 디렉토리에 여러 세션 포함)[/]",
    },
    "orph.fh_header": {
        "en": "[bold yellow]Orphaned File History[/]  [dim](file history without matching project)[/]",
        "ko": "[bold yellow]Orphaned File History[/]  [dim](프로젝트 없는 파일 버전 히스토리)[/]",
    },
    "orph.debug_header": {
        "en": "[bold yellow]Orphaned Debug[/]  [dim](debug logs without session)[/]",
        "ko": "[bold yellow]Orphaned Debug[/]  [dim](세션 없는 디버그 로그)[/]",
    },
    "orph.todo_header": {
        "en": "[bold yellow]Orphaned Todos[/]  [dim](todo memos without session)[/]",
        "ko": "[bold yellow]Orphaned Todos[/]  [dim](세션 없는 할일 메모)[/]",
    },
    "orph.confirm_session": {
        "en": "Move this project directory to trash?\n\nPath: {path}\nFiles: {count}\n\n[bold yellow]All sessions in this directory will be deleted![/]\n[dim]Moved to trash, recoverable[/]",
        "ko": "이 프로젝트 디렉토리를 휴지통으로 이동?\n\nPath: {path}\n포함된 파일: {count}개\n\n[bold yellow]이 디렉토리의 모든 세션이 삭제됩니다![/]\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "orph.confirm_fh": {
        "en": "Move file history to trash?\n\nDir: {name}\n[dim]Moved to trash, recoverable[/]",
        "ko": "File history를 휴지통으로 이동?\n\nDir: {name}\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "orph.confirm_debug": {
        "en": "Move debug file to trash?\n\nFile: {name}\n[dim]Moved to trash, recoverable[/]",
        "ko": "Debug file을 휴지통으로 이동?\n\nFile: {name}\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "orph.confirm_todo": {
        "en": "Move todo file to trash?\n\nFile: {name}\n[dim]Moved to trash, recoverable[/]",
        "ko": "Todo file을 휴지통으로 이동?\n\nFile: {name}\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    # ── Debug/Todos ──
    "dt.info": {
        "en": (
            "[bold]Debug / Todos[/] - Claude Code internal file management\n"
            "[dim]Debug: Internal debug logs created on errors (unnecessary except for bug reports)\n"
            "Todos: Internal task memos created during sessions (not user todos, unnecessary after session)\n"
            "[yellow]Orphaned[/]=session deleted → safe to delete\n"
            "Select an item to preview its content on the right.[/]"
        ),
        "ko": (
            "[bold]Debug / Todos[/] - Claude Code 내부 파일 관리\n"
            "[dim]Debug: Claude Code 오류 시 생성되는 [bold]내부 디버그 로그[/dim][dim] (버그 리포트 외 불필요)\n"
            "Todos: Claude가 세션 중 생성하는 [bold]내부 작업 메모[/dim][dim] (사용자 todo 아님, 세션 끝나면 불필요)\n"
            "[yellow]Orphaned[/]=해당 세션이 삭제됨 → 안전하게 삭제 가능\n"
            "항목을 선택하면 오른쪽에 내용 미리보기가 표시됩니다.[/]"
        ),
    },
    "dt.select_file": {"en": "Select a file to preview", "ko": "파일을 선택하세요"},
    "dt.btn_trash_debug": {"en": "Trash Selected Debug", "ko": "선택 디버그 삭제"},
    "dt.btn_trash_todo": {"en": "Trash Selected Todo", "ko": "선택 Todo 삭제"},
    "dt.confirm_debug": {
        "en": "Move debug file to trash?\n\nFile: {name}\n[dim]Moved to trash, recoverable[/]",
        "ko": "Debug file을 휴지통으로 이동?\n\nFile: {name}\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "dt.confirm_todo": {
        "en": "Move todo file to trash?\n\nFile: {name}\n[dim]Moved to trash, recoverable[/]",
        "ko": "Todo file을 휴지통으로 이동?\n\nFile: {name}\n[dim]휴지통으로 이동되며 복구 가능합니다[/]",
    },
    "dt.empty_file": {
        "en": "(Empty file - no content)\nSafe to delete.",
        "ko": "(빈 파일 - 내용 없음)\n안전하게 삭제 가능합니다.",
    },
    "dt.none": {"en": "(none)", "ko": "(없음)"},
    "dt.btn_prune_debug": {"en": "Prune Empty ({count})", "ko": "빈 파일 정리 ({count})"},
    "dt.btn_prune_todo": {"en": "Prune Empty ({count})", "ko": "빈 파일 정리 ({count})"},
    "dt.confirm_prune_debug": {
        "en": "Delete all empty debug files?\n\n{count} empty files found.\n[dim]Moved to trash, recoverable[/]",
        "ko": "빈 디버그 파일을 모두 삭제하시겠습니까?\n\n{count}개의 빈 파일.\n[dim]휴지통으로 이동, 복구 가능[/]",
    },
    "dt.confirm_prune_todo": {
        "en": "Delete all empty todo files?\n\n{count} empty files found.\n[dim]Moved to trash, recoverable[/]",
        "ko": "빈 Todo 파일을 모두 삭제하시겠습니까?\n\n{count}개의 빈 파일.\n[dim]휴지통으로 이동, 복구 가능[/]",
    },
    "dt.prune_ok": {"en": "Pruned {ok} empty files", "ko": "빈 파일 {ok}개 정리 완료"},
    "dt.btn_trash_orphaned_debug": {"en": "Trash Orphaned ({count})", "ko": "Orphaned 삭제 ({count})"},
    "dt.btn_trash_orphaned_todo": {"en": "Trash Orphaned ({count})", "ko": "Orphaned 삭제 ({count})"},
    "dt.confirm_trash_orphaned_debug": {
        "en": "Delete all orphaned debug files?\n\n{count} orphaned files.\n[dim]Moved to trash, recoverable[/]",
        "ko": "Orphaned 디버그 파일 모두 삭제?\n\n{count}개.\n[dim]휴지통으로 이동, 복구 가능[/]",
    },
    "dt.confirm_trash_orphaned_todo": {
        "en": "Delete all orphaned todo files?\n\n{count} orphaned files.\n[dim]Moved to trash, recoverable[/]",
        "ko": "Orphaned Todo 파일 모두 삭제?\n\n{count}개.\n[dim]휴지통으로 이동, 복구 가능[/]",
    },
    # ── Migrate ──
    "mig.info": {
        "en": (
            "[bold]Migrate[/] - Session migration (copy-based, keeps originals)\n"
            "[dim]Select source project on the left, target on the right.\n"
            "Session files and memory are copied from source to target.[/]"
        ),
        "ko": (
            "[bold]Migrate[/] - 세션 마이그레이션 (복사 기반, 원본 유지)\n"
            "[dim]왼쪽에서 소스 프로젝트, 오른쪽에서 대상 프로젝트를 선택하세요.\n"
            "세션 파일과 메모리가 소스에서 대상으로 복사됩니다.[/]"
        ),
    },
    "mig.source_title": {
        "en": "[bold cyan]Source[/] (original to copy) [dim]- only projects with sessions[/]",
        "ko": "[bold cyan]Source[/] (복사할 원본) [dim]- 세션이 있는 프로젝트만 표시[/]",
    },
    "mig.target_title": {"en": "[bold green]Target[/] (destination)", "ko": "[bold green]Target[/] (복사할 대상)"},
    "mig.not_selected": {"en": "[dim]Not selected[/]", "ko": "[dim]선택되지 않음[/]"},
    "mig.append": {"en": "Append (keep existing, skip duplicates)", "ko": "Append (기존 유지, 중복 스킵)"},
    "mig.overwrite": {"en": "Overwrite (delete existing, overwrite)", "ko": "Overwrite (기존 삭제 후 덮어쓰기)"},
    "mig.select_source": {"en": "Select source project on the left", "ko": "왼쪽에서 소스 프로젝트를 선택하세요"},
    "mig.select_target": {"en": "Select target project on the right", "ko": "오른쪽에서 대상 프로젝트를 선택하세요"},
    "mig.same_error": {"en": "Source and target are the same", "ko": "소스와 대상이 같습니다"},
    "mig.confirm": {
        "en": "Migrate sessions?\n\nSource: {src}\nTarget: {tgt}\nMode: {mode}\n\n[dim]Session files will be copied. Originals are kept.[/]",
        "ko": "Migrate sessions?\n\nSource: {src}\nTarget: {tgt}\nMode: {mode}\n\n[dim]세션 파일이 복사됩니다. 원본은 유지됩니다.[/]",
    },
    "mig.complete": {"en": "Migration complete!", "ko": "마이그레이션 완료!"},
    "mig.failed": {"en": "Migration failed", "ko": "마이그레이션 실패"},
    # ── Backups ──
    "bak.info": {
        "en": (
            "[bold]Backups[/] - Create and restore config/full backups\n"
            "[dim]Stored in ~/.cc-tui/backups/. Create backups before risky operations.[/]"
        ),
        "ko": (
            "[bold]Backups[/] - 설정/전체 백업 생성 및 복원\n"
            "[dim]~/.cc-tui/backups/ 에 저장됩니다. 작업 전 백업을 만들어두면 실수해도 복구할 수 있습니다.[/]"
        ),
    },
    "bak.btn_config": {"en": "Create Config Backup", "ko": "설정 백업 생성"},
    "bak.btn_full": {"en": "Create Full Backup", "ko": "전체 백업 생성"},
    "bak.btn_restore": {"en": "Restore Selected", "ko": "선택 항목 복원"},
    "bak.btn_delete": {"en": "Delete Selected", "ko": "선택 항목 삭제"},
    "bak.confirm_full": {
        "en": "Create a full backup of .claude directory?\nThis may take a moment.",
        "ko": ".claude 디렉토리 전체 백업을 생성하시겠습니까?\n시간이 다소 걸릴 수 있습니다.",
    },
    "bak.confirm_restore": {
        "en": "Restore backup '{name}'?\nCurrent config will be backed up first.",
        "ko": "백업 '{name}'을(를) 복원하시겠습니까?\n현재 설정이 먼저 백업됩니다.",
    },
    "bak.confirm_delete": {"en": "Delete backup '{name}'?", "ko": "백업 '{name}'을(를) 삭제하시겠습니까?"},
    # Common
    "common.trashed": {"en": "Trashed: {name}", "ko": "삭제됨: {name}"},
    "common.failed": {"en": "Failed", "ko": "실패"},
    "common.active": {"en": "[green]Active[/]", "ko": "[green]Active[/]"},
    "common.orphaned": {"en": "[yellow]Orphaned[/]", "ko": "[yellow]Orphaned[/]"},
    "common.trash_bulk_ok": {"en": "Deleted {ok} items ({fail} failed)", "ko": "{ok}개 삭제 완료 ({fail}개 실패)"},
    "common.no_items": {"en": "No items to delete", "ko": "삭제할 항목 없음"},
}


def set_lang(lang: str) -> None:
    """Set the current language. Falls back to 'en' if unsupported."""
    global _current_lang
    _current_lang = lang if lang in ("en", "ko") else "en"


def get_lang() -> str:
    return _current_lang


def t(key: str, **kwargs) -> str:
    """Get translated string. Supports {placeholder} formatting."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text


def init_lang(cli_lang: str | None = None) -> None:
    """Initialize language from CLI arg > env var > default (en)."""
    lang = cli_lang or os.environ.get("CC_TUI_LANG", "en")
    set_lang(lang)
