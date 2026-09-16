"""Spacetime-grounded, multimodal relations for Eran.

The central rule is deliberately different from a vanilla neural edge:
a relationship is an object (or hyper-edge), not a scalar.  Images, prompts,
sound, memories, named dimensions and physical observations are preserved as
first-class evidence.  A numeric value exists only as a temporary,
context-specific *projection* used by one computation.

This module is stdlib-only and does not interpret media by itself.  In
particular, an image is not silently converted into a claim or a score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable


class ProjectionRequired(ValueError):
    """Raised when a rich relation has no honest numeric projection."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("times must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SpacetimeStamp:
    """Where and when an observation belongs, including uncertainty.

    ``frame`` names the coordinate frame (room, camera, GPS, simulation...).
    ``position_m`` may be absent: unknown is better than invented precision.
    """

    observed_at: datetime
    frame: str = "unknown"
    position_m: tuple[float, float, float] | None = None
    time_uncertainty_s: float = 0.0
    position_uncertainty_m: float | None = None
    source_clock: str = "system"

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _as_utc(self.observed_at))
        if self.time_uncertainty_s < 0:
            raise ValueError("time uncertainty cannot be negative")
        if self.position_uncertainty_m is not None and self.position_uncertainty_m < 0:
            raise ValueError("position uncertainty cannot be negative")


@dataclass(frozen=True)
class RelationArtifact:
    """A first-class part of a relation: image, prompt, audio, memory, etc.

    ``payload`` can genuinely be any Python object.  For durable storage,
    ``reference`` should point to the original file/object and ``digest`` can
    hold a content hash.  Interpretation remains explicit and revisable.
    """

    kind: str
    payload: object | None = None
    reference: str | None = None
    description: str = ""
    spacetime: SpacetimeStamp | None = None
    provenance: str = "unknown"
    digest: str | None = None

    def __post_init__(self) -> None:
        if self.payload is None and self.reference is None:
            raise ValueError("artifact needs a payload or a reference")


@dataclass(frozen=True)
class ProjectionContext:
    """The current embodied question asked of a relationship."""

    now: datetime = field(default_factory=_utc_now)
    purpose: str = "transmit"
    observer_frame: str = "unknown"
    observer_position_m: tuple[float, float, float] | None = None
    body_state: dict[str, float] = field(default_factory=dict)
    query: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "now", _as_utc(self.now))


@dataclass(frozen=True)
class Projection:
    """A disposable scalar view; never the relationship itself."""

    value: float
    confidence: float
    rationale: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError("projection value must be finite")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("projection confidence must be in [0, 1]")


@dataclass
class RelationState:
    """Multiple timescales instead of one permanently overwritten weight."""

    fast: float = 0.0
    slow: float = 0.0
    eligibility: float = 0.0
    uncertainty: float = 1.0
    updates: int = 0
    last_event_at: datetime | None = None

    def advance(self, dt_s: float, fast_tau_s: float = 30.0,
                eligibility_tau_s: float = 5.0) -> None:
        if dt_s < 0:
            raise ValueError("time cannot run backward")
        if fast_tau_s <= 0 or eligibility_tau_s <= 0:
            raise ValueError("time constants must be positive")
        self.fast *= math.exp(-dt_s / fast_tau_s)
        self.eligibility *= math.exp(-dt_s / eligibility_tau_s)

    def observe(self, strength: float, occurred_at: datetime,
                modulator: float = 1.0, consolidation: float = 0.02) -> None:
        occurred_at = _as_utc(occurred_at)
        if self.last_event_at is not None and occurred_at < self.last_event_at:
            raise ValueError("out-of-order event requires explicit replay")
        delta = float(strength) * float(modulator)
        self.fast += delta
        self.eligibility += abs(float(strength))
        self.slow += consolidation * delta
        self.uncertainty = max(0.0, self.uncertainty * 0.98)
        self.updates += 1
        self.last_event_at = occurred_at


Projector = Callable[["SpacetimeRelation", ProjectionContext], Projection]


@dataclass
class SpacetimeRelation:
    """A multimodal, high-dimensional hyper-edge between 2+ participants."""

    relation_id: str
    participants: tuple[str, ...]
    prompt: str = ""
    dimensions: dict[str, object] = field(default_factory=dict)
    artifacts: list[RelationArtifact] = field(default_factory=list)
    state: RelationState = field(default_factory=RelationState)
    projector: Projector | None = None
    vanilla_weight: float | None = None

    def __post_init__(self) -> None:
        if len(set(self.participants)) < 2:
            raise ValueError("a relation needs at least two distinct participants")
        if self.vanilla_weight is not None and not math.isfinite(self.vanilla_weight):
            raise ValueError("vanilla weight must be finite")

    def project(self, context: ProjectionContext) -> Projection:
        if self.projector is not None:
            return self.projector(self, context)
        if self.vanilla_weight is not None:
            return Projection(
                value=float(self.vanilla_weight),
                confidence=1.0,
                rationale="explicit vanilla baseline",
            )
        raise ProjectionRequired(
            f"relation '{self.relation_id}' contains rich meaning; "
            "provide a context-specific projector instead of inventing a scalar"
        )

    def transmit(self, signal: float, context: ProjectionContext) -> tuple[float, Projection]:
        projection = self.project(context)
        return float(signal) * projection.value, projection


class RelationGraph:
    """An indexed hypergraph with many relations per entity."""

    def __init__(self) -> None:
        self._relations: dict[str, SpacetimeRelation] = {}
        self._by_participant: dict[str, set[str]] = {}

    def add(self, relation: SpacetimeRelation) -> None:
        if relation.relation_id in self._relations:
            raise ValueError(f"duplicate relation id '{relation.relation_id}'")
        self._relations[relation.relation_id] = relation
        for participant in relation.participants:
            self._by_participant.setdefault(participant, set()).add(relation.relation_id)

    def relations_for(self, participant: str) -> tuple[SpacetimeRelation, ...]:
        ids = sorted(self._by_participant.get(participant, ()))
        return tuple(self._relations[rid] for rid in ids)

    def neighbors(self, participant: str) -> set[str]:
        connected: set[str] = set()
        for relation in self.relations_for(participant):
            connected.update(relation.participants)
        connected.discard(participant)
        return connected

    def walk(self, starts: Iterable[str], max_hops: int) -> set[str]:
        """Return entities reachable within ``max_hops`` hyper-relations."""
        if max_hops < 0:
            raise ValueError("max_hops cannot be negative")
        seen = set(starts)
        frontier = set(starts)
        for _ in range(max_hops):
            nxt: set[str] = set()
            for entity in frontier:
                nxt.update(self.neighbors(entity))
            frontier = nxt - seen
            seen.update(frontier)
            if not frontier:
                break
        return seen

