"""Reusable action bar widget with clickable Rich markup buttons."""

from rich.cells import cell_len
from textual.widgets import Static


class ActionBar(Static):
    """A bar of clickable Rich-markup buttons."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._click_map: list[tuple[int, int, str]] = []
        self._on_action = None

    def set_actions(self, actions: list[tuple[str, str, str]], on_action=None) -> None:
        """Set action buttons.

        Args:
            actions: list of (action_id, label, color)
            on_action: callback(action_id) when clicked
        """
        self._on_action = on_action
        parts = []
        click_map = []
        x = 0
        for i, (action_id, label, color) in enumerate(actions):
            text = f" {label} "
            width = cell_len(text)
            click_map.append((x, x + width, action_id))
            parts.append(f"[bold white on {color}]{text}[/]")
            x += width
            if i < len(actions) - 1:
                x += 2
        self._click_map = click_map
        self.update("  ".join(parts))

    def on_click(self, event) -> None:
        if self._on_action:
            for start, end, action_id in self._click_map:
                if start <= event.x < end:
                    self._on_action(action_id)
                    break
