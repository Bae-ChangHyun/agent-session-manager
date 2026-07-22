"""Shared test fixtures."""

from __future__ import annotations

import pytest

from asm.services import pricing


@pytest.fixture(autouse=True)
def _no_live_pricing(monkeypatch):
    """Keep every test offline: pre-set live-rates state so load_live_rates()
    never fetches LiteLLM or touches the real ~/.asm pricing cache.
    Live-pricing tests opt back in by resetting ``_live_db`` to None."""
    monkeypatch.setattr(pricing, "_live_db", {})
    monkeypatch.setattr(pricing, "_rates_source", "bundled table")
