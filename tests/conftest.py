"""Shared test fixtures."""

from __future__ import annotations

import pytest

from asm import models
from asm.services import pricing


@pytest.fixture(autouse=True)
def _isolated_app_data(monkeypatch, tmp_path_factory):
    """Point ~/.asm-backed state (usage ledger, pricing cache) at a fresh tmp
    dir so tests never read or write the real app data."""
    monkeypatch.setattr(models, "APP_DATA_DIR", tmp_path_factory.mktemp("asm-app-data"))


@pytest.fixture(autouse=True)
def _no_live_pricing(monkeypatch):
    """Keep every test offline: pre-set live-rates state so load_live_rates()
    never fetches LiteLLM or touches the real ~/.asm pricing cache.
    Live-pricing tests opt back in by resetting ``_live_db`` to None."""
    monkeypatch.setattr(pricing, "_live_db", {})
    monkeypatch.setattr(pricing, "_rates_source", "bundled table")
