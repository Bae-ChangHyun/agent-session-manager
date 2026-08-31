from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import DataTable, Input

from asm.app import CCTuiApp
from asm.services.backup import create_config_backup
from tests.async_utils import run_async_test
from tests.test_feature_smoke import _setup_fake_claude


async def _settle(pilot, seconds: float = 0.5) -> None:
    await pilot.pause()
    await asyncio.sleep(seconds)
    await pilot.pause()


def _run_app(monkeypatch, tmp_path: Path, body) -> None:
    _setup_fake_claude(monkeypatch, tmp_path)

    async def run() -> None:
        app = CCTuiApp()
        async with app.run_test(size=(140, 45)) as pilot:
            await _settle(pilot)
            await body(app, pilot)

    run_async_test(run())


def test_backup_selection_tracks_visible_rows_and_confirmed_payload(
    monkeypatch, tmp_path: Path
) -> None:
    async def body(app, pilot) -> None:
        first_path = create_config_backup()
        second_path = create_config_backup()
        assert first_path and second_path

        app.action_tab("tab-backups")
        pane = app.query_one("BackupsPane")
        pane.refresh_data()
        await _settle(pilot)

        table = pane.query_one("#backups-table", DataTable)
        backups_by_path = {backup.path: backup for backup in pane._backups.values()}
        first_name = backups_by_path[first_path].name
        second_name = backups_by_path[second_path].name
        first_row = next(
            index for index, key in enumerate(table.rows) if key.value == first_name
        )
        table.move_cursor(row=first_row)
        table.focus()
        await pilot.pause()
        pane.action_toggle_select()
        assert pane._selected == {first_name}

        pane.query_one("#backups-filter", Input).value = second_name
        await pilot.pause()
        assert pane._selected == set()
        assert set(pane._backups) == {second_name}

        pane.query_one("#backups-filter", Input).value = ""
        await pilot.pause()
        second_row = next(
            index for index, key in enumerate(table.rows) if key.value == second_name
        )
        table.move_cursor(row=second_row)
        table.focus()
        await pilot.pause()
        pane.action_toggle_select()
        selected_backup = pane._backups[second_name]

        pane._handle_action("sort-backups")
        row_key = next(key for key in table.rows if key.value == second_name)
        name_column = next(iter(table.columns))
        assert "●" in str(table.get_cell(row_key, name_column))

        confirmed = []
        monkeypatch.setattr(
            pane,
            "_do_bulk_delete",
            lambda backups: confirmed.extend(backups),
        )
        pane._handle_action("delete")
        await pilot.pause()
        pane._selected.clear()
        pane._backups.clear()
        await pilot.press("y")
        await pilot.pause()
        assert confirmed == [selected_backup]

    _run_app(monkeypatch, tmp_path, body)


def test_global_refresh_includes_agent_import(monkeypatch, tmp_path: Path) -> None:
    async def body(app, pilot) -> None:
        pane = app.query_one("AgentImportPane")
        calls = []
        monkeypatch.setattr(pane, "refresh_data", lambda: calls.append("refresh"))

        app.action_refresh()

        assert calls == ["refresh"]

    _run_app(monkeypatch, tmp_path, body)
