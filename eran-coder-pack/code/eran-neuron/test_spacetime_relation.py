"""Tests for Eran's grounded multimodal relation object."""

import unittest
from datetime import datetime, timedelta, timezone

from spacetime_relation import (
    Projection,
    ProjectionContext,
    ProjectionRequired,
    RelationArtifact,
    RelationGraph,
    RelationState,
    SpacetimeRelation,
    SpacetimeStamp,
)


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestRichRelationship(unittest.TestCase):
    def test_image_and_prompt_remain_first_class_objects(self):
        photo = RelationArtifact(
            kind="image",
            reference="private://family/hug.jpg",
            description="a remembered embrace; interpretation belongs to its people",
            spacetime=SpacetimeStamp(T0, frame="family-memory"),
            provenance="owner supplied",
        )
        relation = SpacetimeRelation(
            relation_id="family-bond",
            participants=("person-a", "person-b", "shared-memory"),
            prompt="Treat this as a relationship with history, not a score.",
            dimensions={"care": "deep", "roles": ("sibling", "witness")},
            artifacts=[photo],
        )
        self.assertIs(relation.artifacts[0], photo)
        self.assertIn("history", relation.prompt)
        self.assertEqual(len(relation.participants), 3)

    def test_rich_meaning_is_never_silently_reduced_to_number(self):
        relation = SpacetimeRelation("r", ("a", "b"), prompt="complex")
        with self.assertRaises(ProjectionRequired):
            relation.transmit(1.0, ProjectionContext(now=T0))

    def test_vanilla_weight_exists_only_as_explicit_baseline(self):
        relation = SpacetimeRelation("baseline", ("a", "b"), vanilla_weight=0.25)
        output, projection = relation.transmit(8.0, ProjectionContext(now=T0))
        self.assertEqual(output, 2.0)
        self.assertEqual(projection.rationale, "explicit vanilla baseline")

    def test_projection_can_depend_on_time_space_body_and_purpose(self):
        observed = SpacetimeStamp(T0, frame="room", position_m=(0.0, 0.0, 0.0))

        def grounded(rel, ctx):
            age_h = (ctx.now - rel.artifacts[0].spacetime.observed_at).total_seconds() / 3600
            distance = abs(ctx.observer_position_m[0])
            body_gate = ctx.body_state.get("attention", 0.0)
            value = body_gate / (1.0 + age_h + distance)
            return Projection(value, 0.8, "explicit age + distance + body-state projection")

        relation = SpacetimeRelation(
            "grounded",
            ("observer", "object"),
            artifacts=[RelationArtifact("observation", payload={"shape": "ball"}, spacetime=observed)],
            projector=grounded,
        )
        ctx = ProjectionContext(
            now=T0 + timedelta(hours=1),
            observer_frame="room",
            observer_position_m=(2.0, 0.0, 0.0),
            body_state={"attention": 1.0},
        )
        output, projection = relation.transmit(4.0, ctx)
        self.assertAlmostEqual(output, 1.0)
        self.assertEqual(projection.confidence, 0.8)

    def test_multiple_timescales_decay_differently(self):
        state = RelationState()
        state.observe(1.0, T0)
        slow_before = state.slow
        state.advance(30.0, fast_tau_s=30.0, eligibility_tau_s=5.0)
        self.assertAlmostEqual(state.fast, 0.367879441, places=6)
        self.assertLess(state.eligibility, 0.01)
        self.assertEqual(state.slow, slow_before)


class TestConnectivity(unittest.TestCase):
    def test_hyperedges_create_high_connectivity_without_pairwise_duplication(self):
        graph = RelationGraph()
        graph.add(SpacetimeRelation("family-event", ("a", "b", "place", "photo"), vanilla_weight=1))
        graph.add(SpacetimeRelation("place-story", ("place", "story", "era"), vanilla_weight=1))
        self.assertEqual(graph.neighbors("a"), {"b", "place", "photo"})
        self.assertEqual(graph.walk(["a"], max_hops=2), {"a", "b", "place", "photo", "story", "era"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
