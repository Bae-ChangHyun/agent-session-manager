"""Model pricing for cost estimation.

Per-million-token USD rates, sourced from LiteLLM's pricing database
(https://github.com/BerriAI/litellm — the same source tools like tokscale use).

Rather than guessing a tier from the model name (which silently mispriced newer
Opus releases as the old, 3x-more-expensive Opus 4.0/4.1), we keep an explicit
per-model table and fall back to a tier estimate only for unknown models. New
Opus releases default to the *current* (cheaper) Opus pricing, not the legacy one.
"""

from __future__ import annotations

# Per-1M-token rates: (input, output, cache_read, cache_create) in USD.
_OPUS_LEGACY = (15.0, 75.0, 1.50, 18.75)   # opus 4.0 / 4.1 / opus-3
_OPUS = (5.0, 25.0, 0.50, 6.25)            # opus 4.5+
_SONNET = (3.0, 15.0, 0.30, 3.75)          # sonnet 4.x / 3.x
_HAIKU = (1.0, 5.0, 0.10, 1.25)            # haiku 4.x / 3.5

# Exact per-model rates (keyed by the model id with the date suffix stripped).
_RATES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4-0": _OPUS_LEGACY,
    "claude-opus-4-1": _OPUS_LEGACY,
    "claude-opus-4-5": _OPUS,
    "claude-opus-4-6": _OPUS,
    "claude-opus-4-7": _OPUS,
    "claude-opus-4-8": _OPUS,
    "claude-sonnet-4-5": _SONNET,
    "claude-sonnet-4-6": _SONNET,
    "claude-haiku-4-5": _HAIKU,
}

# Opus releases that still carry the old, expensive pricing.
_LEGACY_OPUS_MARKERS = ("opus-4-0", "opus-4-1", "opus-3")


def _normalize(model: str) -> str:
    """Strip a trailing date / variant suffix from a model id.

    e.g. ``claude-opus-4-8-20260101`` -> ``claude-opus-4-8``,
    ``claude-opus-4-6[1m]`` -> ``claude-opus-4-6``.
    """
    name = model.split("[")[0]
    for marker in ("-2024", "-2025", "-2026", "-2027"):
        name = name.split(marker)[0]
    if not name.startswith("claude-"):
        name = "claude-" + name.lstrip("-")
    return name


def _rates_for(model: str) -> tuple[float, float, float, float]:
    """Return (input, output, cache_read, cache_create) per-1M rates for a model."""
    name = _normalize(model)
    if name in _RATES:
        return _RATES[name]
    # Fallback by family for unknown / future models.
    if "opus" in name:
        return _OPUS_LEGACY if any(m in name for m in _LEGACY_OPUS_MARKERS) else _OPUS
    if "haiku" in name:
        return _HAIKU
    return _SONNET


def calc_cost(usage: dict, model: str) -> float:
    """Estimate USD cost for a single usage record."""
    inp_r, out_r, cr_r, cw_r = _rates_for(model)
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_create = usage.get("cache_creation_input_tokens", 0)
    return (
        inp * inp_r
        + out * out_r
        + cache_read * cr_r
        + cache_create * cw_r
    ) / 1_000_000


# Models that are placeholders, not billable (e.g. Claude Code's synthetic
# "no API call" assistant turns). Skipped entirely in usage aggregation.
NON_BILLABLE_MODELS = frozenset({"<synthetic>", "<synthetic-streaming>", ""})


def is_billable(model: str) -> bool:
    return model not in NON_BILLABLE_MODELS
