"""Provider registry. One entry per web AI service."""
from __future__ import annotations

from providers.base import Provider
from providers.grok import GrokProvider
from providers.perplexity import PerplexityProvider

REGISTRY: dict[str, type] = {
    PerplexityProvider.name: PerplexityProvider,
    GrokProvider.name: GrokProvider,
}


def get(name: str) -> Provider:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise SystemExit(
            f"unknown provider {name!r}; known: {', '.join(sorted(REGISTRY))}"
        )


__all__ = ["REGISTRY", "get", "Provider"]
