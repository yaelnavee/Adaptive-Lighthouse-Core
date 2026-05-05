"""
Tests for Milestone 3: The Commander Agent & Constitutional AI
=============================================================
Tests cover:
  1. Constitutional rule enforcement (pre-screen)
  2. Veto mechanism for each rule
  3. APPROVED path (valid reports pass through)
  4. Synthesis: APPROVED reports appear in final plan
  5. Veto audit log integrity
  6. Edge cases: empty reports, all vetoed
"""

import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.commander_agent import CommanderAgent, VETO_TRIGGERS, CONSTITUTION


class TestCommanderAgentPreScreen(unittest.TestCase):
    """Tests the fast keyword-based pre-screening (no LLM)."""

    def setUp(self):
        self.mock_llm = MagicMock()
        # Prevent LLM calls from breaking tests
        self.mock_llm.generate.return_value = (
            "REVIEW:\nFire_Bot: APPROVED\nPolice_Bot: APPROVED\nMed_Bot: APPROVED\n"
            "FINAL_PLAN:\nAll units proceed with the approved plan."
        )
        self.commander = CommanderAgent(self.mock_llm)

    def test_veto_trigger_unstable_entry(self):
        """Rule 2: A plan ordering entry into unstable zone must be pre-screen flagged."""
        reports = {
            "Fire_Bot": "Team should enter unstable building to rescue victim.",
            "Police_Bot": "Secure the perimeter.",
            "Med_Bot": "Triage in the cold zone."
        }
        pre_screen = self.commander._pre_screen_vetoes(reports)
        # Fire_Bot triggered "enter unstable"
        self.assertIsNotNone(pre_screen["Fire_Bot"],
                             "Fire_Bot should be flagged for 'enter unstable'")
        # Others should pass
        self.assertIsNone(pre_screen["Police_Bot"])
        self.assertIsNone(pre_screen["Med_Bot"])

    def test_veto_trigger_evidence_before_rescue(self):
        """Rule 3: Evidence work before rescue must be flagged."""
        reports = {
            "Fire_Bot": "Establish 200m perimeter.",
            "Police_Bot": "Collect evidence first, then allow fire crew in.",
            "Med_Bot": "Triage ready."
        }
        pre_screen = self.commander._pre_screen_vetoes(reports)
        self.assertIsNotNone(pre_screen["Police_Bot"])
        self.assertIsNone(pre_screen["Fire_Bot"])

    def test_veto_trigger_experimental_treatment(self):
        """Rule 4: Invented medical protocol must be flagged."""
        reports = {
            "Fire_Bot": "Hot zone secured.",
            "Police_Bot": "Traffic diverted.",
            "Med_Bot": "Administer experimental treatment X-47 to stabilize patient."
        }
        pre_screen = self.commander._pre_screen_vetoes(reports)
        self.assertIsNotNone(pre_screen["Med_Bot"])

    def test_clean_reports_pass_prescreening(self):
        """All clean reports should return None (no pre-screen veto)."""
        reports = {
            "Fire_Bot": "Establish 300m hot zone. Foam applied. Rescue team on standby.",
            "Police_Bot": "Traffic redirected. 300m perimeter set. No civilians in zone.",
            "Med_Bot": "Triage area in cold zone. 2 red, 1 yellow patients being treated."
        }
        pre_screen = self.commander._pre_screen_vetoes(reports)
        for agent, result in pre_screen.items():
            self.assertIsNone(result, f"{agent} should pass pre-screening but got: {result}")

    def test_veto_log_records_prescreens(self):
        """Veto log should capture pre-screen events."""
        reports = {
            "Fire_Bot": "Enter the hot zone immediately.",
            "Police_Bot": "All clear.",
            "Med_Bot": "All clear."
        }
        self.commander._pre_screen_vetoes(reports)
        log = self.commander.get_veto_log()
        self.assertTrue(len(log) > 0, "Veto log should not be empty after a flagged pre-screen")
        self.assertEqual(log[0]["stage"], "pre_screen")
        self.assertEqual(log[0]["agent"], "Fire_Bot")


class TestCommanderAgentLLMReview(unittest.TestCase):
    """Tests the LLM-based constitutional review and response parsing."""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.commander = CommanderAgent(self.mock_llm)

    def test_veto_is_parsed_correctly(self):
        """Parser must correctly identify a VETO in LLM response."""
        self.mock_llm.generate.return_value = (
            "REVIEW:\n"
            "Fire_Bot: VETO - Rule 2: Orders team into confirmed unstable structure.\n"
            "Police_Bot: APPROVED\n"
            "Med_Bot: APPROVED\n"
            "FINAL_PLAN:\n"
            "Police and Medical proceed. Fire team holds at perimeter."
        )
        result = self.commander.review_and_synthesize({
            "Fire_Bot": "Enter the building now.",
            "Police_Bot": "Perimeter secured.",
            "Med_Bot": "Triage ready."
        })
        self.assertTrue(result["reviews"]["Fire_Bot"]["vetoed"],
                        "Fire_Bot must be marked as vetoed")
        self.assertFalse(result["reviews"]["Police_Bot"]["vetoed"])
        self.assertFalse(result["reviews"]["Med_Bot"]["vetoed"])

    def test_approved_appears_in_final_plan(self):
        """Approved content must appear in the final synthesized plan."""
        self.mock_llm.generate.return_value = (
            "REVIEW:\n"
            "Fire_Bot: APPROVED\n"
            "Police_Bot: APPROVED\n"
            "Med_Bot: APPROVED\n"
            "FINAL_PLAN:\n"
            "All units proceed. Perimeter at 300m. Triage active in cold zone."
        )
        result = self.commander.review_and_synthesize({
            "Fire_Bot": "300m perimeter.",
            "Police_Bot": "Traffic diverted.",
            "Med_Bot": "Triage active."
        })
        self.assertIn("300m", result["final_plan"])
        self.assertIn("Triage", result["final_plan"])

    def test_all_vetoed_still_returns_final_plan(self):
        """Even if all agents are vetoed, a final plan must still be returned."""
        self.mock_llm.generate.return_value = (
            "REVIEW:\n"
            "Fire_Bot: VETO - Rule 2: Unsafe entry.\n"
            "Police_Bot: VETO - Rule 3: Evidence before rescue.\n"
            "Med_Bot: VETO - Rule 4: Invented medication.\n"
            "FINAL_PLAN:\n"
            "All specialist plans have been vetoed. Stand by for re-assessment."
        )
        result = self.commander.review_and_synthesize({
            "Fire_Bot": "Enter unstable building.",
            "Police_Bot": "Collect evidence first.",
            "Med_Bot": "Use new experimental drug X."
        })
        self.assertTrue(len(result["final_plan"]) > 0,
                        "final_plan must not be empty even when all vetoed")
        self.assertTrue(result["reviews"]["Fire_Bot"]["vetoed"])
        self.assertTrue(result["reviews"]["Police_Bot"]["vetoed"])
        self.assertTrue(result["reviews"]["Med_Bot"]["vetoed"])

    def test_empty_reports_handled_gracefully(self):
        """Empty reports should not crash the commander."""
        self.mock_llm.generate.return_value = (
            "REVIEW:\n"
            "Fire_Bot: APPROVED\n"
            "Police_Bot: APPROVED\n"
            "Med_Bot: APPROVED\n"
            "FINAL_PLAN:\n"
            "No data received. Awaiting field reports."
        )
        try:
            result = self.commander.review_and_synthesize({
                "Fire_Bot": "",
                "Police_Bot": "",
                "Med_Bot": ""
            })
            self.assertIn("final_plan", result)
        except Exception as e:
            self.fail(f"Commander crashed on empty input: {e}")

    def test_veto_log_llm_stage(self):
        """LLM-detected vetoes must appear in veto_log with stage='llm_review'."""
        self.mock_llm.generate.return_value = (
            "REVIEW:\n"
            "Fire_Bot: APPROVED\n"
            "Police_Bot: VETO - Rule 3: Evidence before evacuation.\n"
            "Med_Bot: APPROVED\n"
            "FINAL_PLAN:\n"
            "Fire and Medical proceed without Police delay."
        )
        result = self.commander.review_and_synthesize({
            "Fire_Bot": "Safe perimeter set.",
            "Police_Bot": "Collect evidence first before evacuation.",  # will be flagged
            "Med_Bot": "Triage ready."
        })
        llm_vetoes = [v for v in result["veto_log"] if v.get("stage") == "llm_review"]
        self.assertTrue(len(llm_vetoes) > 0, "Should have at least one llm_review veto")
        self.assertEqual(llm_vetoes[0]["agent"], "Police_Bot")


class TestConstitution(unittest.TestCase):
    """Sanity checks on the Constitution itself."""

    def test_constitution_contains_all_rules(self):
        for rule_num in range(1, 6):
            self.assertIn(f"RULE {rule_num}", CONSTITUTION,
                          f"RULE {rule_num} must exist in CONSTITUTION")

    def test_veto_triggers_not_empty(self):
        self.assertTrue(len(VETO_TRIGGERS) >= 5,
                        "There must be at least 5 veto trigger phrases")

    def test_life_safety_rule_exists(self):
        self.assertIn("Human life", CONSTITUTION)

    def test_responder_safety_rule_exists(self):
        self.assertIn("structurally unstable", CONSTITUTION)

    def test_medical_integrity_rule_exists(self):
        self.assertIn("approved treatments", CONSTITUTION)


class TestReviewPromptStructure(unittest.TestCase):
    """Ensures the prompt sent to LLM is well-formed."""

    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_llm.generate.return_value = (
            "REVIEW:\nFire_Bot: APPROVED\nPolice_Bot: APPROVED\nMed_Bot: APPROVED\n"
            "FINAL_PLAN:\nAll approved."
        )
        self.commander = CommanderAgent(self.mock_llm)

    def test_prompt_contains_constitution(self):
        reports = {"Fire_Bot": "A", "Police_Bot": "B", "Med_Bot": "C"}
        pre_screen = self.commander._pre_screen_vetoes(reports)
        prompt = self.commander._build_review_prompt(reports, pre_screen)
        self.assertIn("CONSTITUTION", prompt)
        self.assertIn("RULE 1", prompt)

    def test_prompt_contains_all_agent_names(self):
        reports = {"Fire_Bot": "report1", "Police_Bot": "report2", "Med_Bot": "report3"}
        pre_screen = self.commander._pre_screen_vetoes(reports)
        prompt = self.commander._build_review_prompt(reports, pre_screen)
        self.assertIn("Fire_Bot", prompt)
        self.assertIn("Police_Bot", prompt)
        self.assertIn("Med_Bot", prompt)

    def test_prompt_contains_output_format(self):
        reports = {"Fire_Bot": "A", "Police_Bot": "B", "Med_Bot": "C"}
        pre_screen = self.commander._pre_screen_vetoes(reports)
        prompt = self.commander._build_review_prompt(reports, pre_screen)
        self.assertIn("FINAL_PLAN:", prompt)
        self.assertIn("REVIEW:", prompt)

    def test_flagged_agent_marked_in_prompt(self):
        """Pre-screen flagged agents should be visually marked in the LLM prompt."""
        reports = {
            "Fire_Bot": "Enter the hot zone immediately.",
            "Police_Bot": "Perimeter clear.",
            "Med_Bot": "Triage active."
        }
        pre_screen = self.commander._pre_screen_vetoes(reports)
        prompt = self.commander._build_review_prompt(reports, pre_screen)
        self.assertIn("PRE-SCREEN FLAGGED", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)