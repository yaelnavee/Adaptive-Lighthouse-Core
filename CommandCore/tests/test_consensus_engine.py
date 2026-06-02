"""
tests/test_consensus_engine.py — Milestone 4: The Consensus Engine
===================================================================
Tests cover:
  1. Urgency score calculation — tier base weight, keyword bonuses, score clamping
  2. Tier priority — LIFE_SAFETY agents score higher baseline than EVIDENCE agents
  3. Hebrew keyword detection
  4. Conflict detection — opposing stances across agents
  5. No-conflict path — aligned agents produce empty conflict list
  6. Conflict resolution — priority-based winner selection
  7. Safety-first tie-break — restrictive actions win equal-priority ties
  8. Full resolve() pipeline — returns all required keys
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from consensus.consensus_engine import (
    ConsensusEngine, UrgencyScore, ConflictReport,
    AGENT_TIERS, TIER_BASE_SCORE, TIER_PRIORITY,
)


class TestUrgencyScoreCalculation(unittest.TestCase):

    def setUp(self):
        self.engine = ConsensusEngine()

    def test_life_safety_agents_score_higher_baseline(self):
        """LIFE_SAFETY tier agents (Fire/Med) must outscore EVIDENCE tier (Police) on neutral text."""
        reports = {
            "Fire_Bot": "Stand by at perimeter.",
            "Police_Bot": "Stand by at perimeter.",
        }
        scores = self.engine.calculate_urgency_scores(reports)
        self.assertGreater(scores["Fire_Bot"].score, scores["Police_Bot"].score)

    def test_critical_keywords_boost_score(self):
        """Reports with critical-level keywords must score higher than neutral reports."""
        high = {"Fire_Bot": "Multiple casualties trapped in collapsing structure."}
        low  = {"Fire_Bot": "Minor incident. Situation is contained and clear."}
        score_high = self.engine.calculate_urgency_scores(high)["Fire_Bot"].score
        score_low  = self.engine.calculate_urgency_scores(low)["Fire_Bot"].score
        self.assertGreater(score_high, score_low)

    def test_score_clamped_to_max_10(self):
        """Score must never exceed 10.0 regardless of keyword density."""
        spam = {"Fire_Bot": (
            "trapped casualty casualties dead dying explosion toxic "
            "chemical leak gas leak collapse critical fire injured evacuate "
            "hot zone hazmat rescue emergency urgent danger victim"
        )}
        score = self.engine.calculate_urgency_scores(spam)["Fire_Bot"].score
        self.assertLessEqual(score, 10.0)

    def test_score_clamped_to_min_1(self):
        """Score must never drop below 1.0 even for low-urgency reports."""
        low = {"Police_Bot": "Minor normal small resolved clear contained situation."}
        score = self.engine.calculate_urgency_scores(low)["Police_Bot"].score
        self.assertGreaterEqual(score, 1.0)

    def test_unknown_agent_defaults_to_property_tier(self):
        """Agents not in AGENT_TIERS fall back to the PROPERTY tier."""
        reports = {"Unknown_Bot": "Some report text here."}
        scores = self.engine.calculate_urgency_scores(reports)
        self.assertEqual(scores["Unknown_Bot"].tier, "PROPERTY")

    def test_label_critical_for_high_score(self):
        """Score >= 7.0 must carry the CRITICAL label."""
        us = UrgencyScore(agent="Test", score=8.0, tier="LIFE_SAFETY")
        self.assertEqual(us.label, "CRITICAL")

    def test_label_high_for_mid_score(self):
        """Score in [5.0, 7.0) must carry the HIGH label."""
        us = UrgencyScore(agent="Test", score=6.0, tier="LIFE_SAFETY")
        self.assertEqual(us.label, "HIGH")

    def test_label_medium_for_middle_score(self):
        """Score in [3.0, 5.0) must carry the MEDIUM label."""
        us = UrgencyScore(agent="Test", score=4.0, tier="EVIDENCE")
        self.assertEqual(us.label, "MEDIUM")

    def test_label_low_for_low_score(self):
        """Score < 3.0 must carry the LOW label."""
        us = UrgencyScore(agent="Test", score=2.0, tier="PROPERTY")
        self.assertEqual(us.label, "LOW")

    def test_hebrew_critical_keywords_boost_score(self):
        """Hebrew urgency keywords must be detected and raise the score."""
        high_he = {"Med_Bot": "נפגעים כלואים במבנה קורס."}  # Casualties trapped in collapsing building
        low_he  = {"Med_Bot": "המתנה בפריפריה."}             # Standby at perimeter
        score_high = self.engine.calculate_urgency_scores(high_he)["Med_Bot"].score
        score_low  = self.engine.calculate_urgency_scores(low_he)["Med_Bot"].score
        self.assertGreater(score_high, score_low)

    def test_matched_keywords_recorded(self):
        """Matched keyword terms must be listed in the UrgencyScore."""
        reports = {"Fire_Bot": "There are casualties trapped in the fire."}
        scores = self.engine.calculate_urgency_scores(reports)
        keywords_str = " ".join(scores["Fire_Bot"].matched_keywords).lower()
        self.assertIn("casualties", keywords_str)
        self.assertIn("trapped", keywords_str)


class TestConflictDetection(unittest.TestCase):

    def setUp(self):
        self.engine = ConsensusEngine()

    def test_no_conflicts_when_agents_agree(self):
        """Aligned agents must produce an empty conflict list."""
        reports = {
            "Fire_Bot":   "Perimeter at 100m. Stand by.",
            "Police_Bot": "Road blocked at 100m. No civilians in zone.",
            "Med_Bot":    "Triage in cold zone. Awaiting Fire_Bot clearance.",
        }
        scores = self.engine.calculate_urgency_scores(reports)
        conflicts = self.engine.detect_conflicts(reports, scores)
        self.assertEqual(len(conflicts), 0)

    def test_zone_access_conflict_detected(self):
        """Entry-allowed vs no-entry stance pair must trigger a zone_access conflict."""
        reports = {
            "Fire_Bot": "No entry. Do not enter this area.",
            "Med_Bot":  "Entry authorized. Proceed to enter casualty location.",
        }
        scores = self.engine.calculate_urgency_scores(reports)
        conflicts = self.engine.detect_conflicts(reports, scores)
        topics = [c.topic for c in conflicts]
        self.assertIn("zone_access", topics)

    def test_road_status_conflict_detected(self):
        """Road-open vs road-closed must trigger a road_status conflict."""
        reports = {
            "Fire_Bot":   "Block road immediately. Divert traffic from incident.",
            "Police_Bot": "Road open. Traffic flowing normally near the area.",
        }
        scores = self.engine.calculate_urgency_scores(reports)
        conflicts = self.engine.detect_conflicts(reports, scores)
        topics = [c.topic for c in conflicts]
        self.assertIn("road_status", topics)

    def test_conflict_winner_is_one_of_the_two_agents(self):
        """Every ConflictReport must name one of its two agents as the winner."""
        reports = {
            "Fire_Bot": "Do not enter. Entry forbidden.",
            "Med_Bot":  "Safe to enter. Entry authorized now.",
        }
        scores = self.engine.calculate_urgency_scores(reports)
        conflicts = self.engine.detect_conflicts(reports, scores)
        for c in conflicts:
            self.assertIn(c.winner, [c.agent_a, c.agent_b],
                          "Winner must be one of the two conflicting agents")

    def test_conflict_resolution_reason_is_nonempty(self):
        """Every ConflictReport must provide a non-empty human-readable reason."""
        reports = {
            "Fire_Bot": "Do not enter. Entry denied.",
            "Med_Bot":  "Entry authorized. Proceed to enter.",
        }
        scores = self.engine.calculate_urgency_scores(reports)
        conflicts = self.engine.detect_conflicts(reports, scores)
        for c in conflicts:
            self.assertGreater(len(c.resolution_reason), 5)


class TestConflictResolution(unittest.TestCase):

    def setUp(self):
        self.engine = ConsensusEngine()

    def test_higher_urgency_score_wins(self):
        """Agent with significantly higher urgency score must win the conflict."""
        scores = {
            "Fire_Bot": UrgencyScore("Fire_Bot", 9.0, "LIFE_SAFETY"),
            "Med_Bot":  UrgencyScore("Med_Bot",  4.0, "LIFE_SAFETY"),
        }
        winner, reason = self.engine._pick_winner(
            "Fire_Bot", "deny", "Med_Bot", "allow", scores, "zone_access"
        )
        self.assertEqual(winner, "Fire_Bot")
        self.assertIn("9.0", reason)

    def test_life_safety_wins_over_evidence_on_tier_tiebreak(self):
        """LIFE_SAFETY tier must defeat EVIDENCE tier when urgency scores are equal."""
        scores = {
            "Fire_Bot":   UrgencyScore("Fire_Bot",   5.0, "LIFE_SAFETY"),
            "Police_Bot": UrgencyScore("Police_Bot", 5.0, "EVIDENCE"),
        }
        winner, reason = self.engine._pick_winner(
            "Fire_Bot", "deny", "Police_Bot", "allow", scores, "zone_access"
        )
        self.assertEqual(winner, "Fire_Bot")
        self.assertIn("LIFE_SAFETY", reason)

    def test_safety_first_tiebreak_deny_wins_over_allow(self):
        """When priority and score are equal, the restrictive (deny) stance must win."""
        scores = {
            "Fire_Bot": UrgencyScore("Fire_Bot", 5.0, "LIFE_SAFETY"),
            "Med_Bot":  UrgencyScore("Med_Bot",  5.0, "LIFE_SAFETY"),
        }
        winner, reason = self.engine._pick_winner(
            "Fire_Bot", "deny", "Med_Bot", "allow", scores, "zone_access"
        )
        self.assertEqual(winner, "Fire_Bot")
        self.assertIn("Safety-first", reason)

    def test_safety_first_closed_wins_over_open(self):
        """Closed road stance must beat open road stance on equal priority/score."""
        scores = {
            "Fire_Bot":   UrgencyScore("Fire_Bot",   5.0, "LIFE_SAFETY"),
            "Police_Bot": UrgencyScore("Police_Bot", 5.0, "LIFE_SAFETY"),
        }
        winner, _ = self.engine._pick_winner(
            "Fire_Bot", "closed", "Police_Bot", "open", scores, "road_status"
        )
        self.assertEqual(winner, "Fire_Bot")

    def test_life_safety_wins_conflict_against_evidence(self):
        """End-to-end: LIFE_SAFETY agent beats EVIDENCE agent in a detected conflict."""
        reports = {
            "Fire_Bot":   "No entry. Entry forbidden until decontamination.",
            "Police_Bot": "Entry authorized. Officers can enter the zone.",
        }
        scores = {
            "Fire_Bot":   UrgencyScore("Fire_Bot",   5.0, "LIFE_SAFETY"),
            "Police_Bot": UrgencyScore("Police_Bot", 5.0, "EVIDENCE"),
        }
        conflicts = self.engine.detect_conflicts(reports, scores)
        zone_conflicts = [c for c in conflicts if c.topic == "zone_access"]
        self.assertTrue(len(zone_conflicts) > 0, "Expected a zone_access conflict")
        self.assertEqual(zone_conflicts[0].winner, "Fire_Bot",
                         "LIFE_SAFETY tier must win over EVIDENCE tier when scores are tied")


class TestResolveIntegration(unittest.TestCase):

    def setUp(self):
        self.engine = ConsensusEngine()

    def test_resolve_returns_all_required_keys(self):
        """resolve() must return urgency_scores, conflicts, and summary."""
        reports = {
            "Fire_Bot":   "Perimeter set. Stand by.",
            "Police_Bot": "Traffic diverted.",
            "Med_Bot":    "Triage ready in cold zone.",
        }
        result = self.engine.resolve(reports)
        self.assertIn("urgency_scores", result)
        self.assertIn("conflicts", result)
        self.assertIn("summary", result)

    def test_resolve_scores_every_agent(self):
        """Every agent in the input must receive an urgency score."""
        reports = {"Fire_Bot": "A", "Police_Bot": "B", "Med_Bot": "C"}
        result = self.engine.resolve(reports)
        for agent in reports:
            self.assertIn(agent, result["urgency_scores"])

    def test_summary_contains_all_agent_names(self):
        """The consensus summary string must mention every agent name."""
        reports = {
            "Fire_Bot":   "Perimeter set.",
            "Police_Bot": "Traffic diverted.",
            "Med_Bot":    "Triage ready.",
        }
        result = self.engine.resolve(reports)
        for agent in reports:
            self.assertIn(agent, result["summary"])

    def test_no_conflict_summary_message(self):
        """Summary must contain 'NO CONFLICTS DETECTED' when agents are aligned."""
        reports = {
            "Fire_Bot":   "Perimeter at 100m.",
            "Police_Bot": "Traffic blocked at 100m.",
            "Med_Bot":    "Triage ready.",
        }
        result = self.engine.resolve(reports)
        if not result["conflicts"]:
            self.assertIn("NO CONFLICTS DETECTED", result["summary"])

    def test_conflict_in_summary_when_present(self):
        """Summary must contain 'CONFLICT RESOLUTIONS' when at least one conflict exists."""
        reports = {
            "Fire_Bot": "Do not enter. No entry allowed.",
            "Med_Bot":  "Entry authorized. Proceed to enter now.",
        }
        result = self.engine.resolve(reports)
        if result["conflicts"]:
            self.assertIn("CONFLICT RESOLUTIONS", result["summary"])

    def test_urgency_scores_are_urgencyscore_instances(self):
        """Values in urgency_scores dict must be UrgencyScore instances."""
        reports = {"Fire_Bot": "Rescue team on standby."}
        result = self.engine.resolve(reports)
        for agent, score in result["urgency_scores"].items():
            self.assertIsInstance(score, UrgencyScore)

    def test_conflicts_are_conflictreport_instances(self):
        """Items in conflicts list must be ConflictReport instances."""
        reports = {
            "Fire_Bot": "No entry. Entry forbidden.",
            "Med_Bot":  "Entry authorized. Proceed to enter.",
        }
        result = self.engine.resolve(reports)
        for c in result["conflicts"]:
            self.assertIsInstance(c, ConflictReport)


if __name__ == "__main__":
    unittest.main(verbosity=2)
