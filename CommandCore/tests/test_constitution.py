"""
tests/test_constitution.py — Live Constitution & Trigger Editing (Milestone 3 Extra)
======================================================================================
Tests cover:
  1. Adding a new rule to CONSTITUTION is picked up by the prompt builder
  2. Adding a new VETO_TRIGGER phrase causes pre-screen to flag it
  3. Removing a trigger phrase stops it from being flagged
  4. Editing a rule text changes the prompt content
"""

import unittest
from unittest.mock import MagicMock
import agents.commander_agent as ca_module
from agents.commander_agent import CommanderAgent


class TestLiveConstitutionEditing(unittest.TestCase):
    """
    These tests patch the module-level CONSTITUTION and VETO_TRIGGERS to simulate
    the live-editing feature available in the Streamlit sidebar.
    They restore originals in tearDown to avoid test pollution.
    """

    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_llm.generate.return_value = (
            "REVIEW:\nFire_Bot: APPROVED\nPolice_Bot: APPROVED\nMed_Bot: APPROVED\n"
            "FINAL_PLAN:\nAll approved."
        )
        # Save originals
        self._orig_constitution = ca_module.CONSTITUTION
        self._orig_triggers = dict(ca_module.VETO_TRIGGERS)

    def tearDown(self):
        # Always restore to avoid polluting other tests
        ca_module.CONSTITUTION = self._orig_constitution
        ca_module.VETO_TRIGGERS = self._orig_triggers

    # ------------------------------------------------------------------
    # 1. New rule appears in prompt
    # ------------------------------------------------------------------
    def test_new_rule_appears_in_review_prompt(self):
        ca_module.CONSTITUTION = self._orig_constitution + "\nRULE 6: No drones below 50m in a hot zone."
        commander = CommanderAgent(self.mock_llm)
        reports = {"Fire_Bot": "Deploy drone at 30m.", "Police_Bot": "OK.", "Med_Bot": "OK."}
        pre_screen = commander._pre_screen_vetoes(reports)
        prompt = commander._build_review_prompt(reports, pre_screen)
        self.assertIn("RULE 6", prompt)
        self.assertIn("drones", prompt)

    # ------------------------------------------------------------------
    # 2. New trigger phrase causes pre-screen flag
    # ------------------------------------------------------------------
    def test_new_trigger_phrase_is_flagged(self):
        ca_module.VETO_TRIGGERS["deploy drone below"] = "RULE 6 — Drone altitude violation"
        commander = CommanderAgent(self.mock_llm)
        reports = {
            "Fire_Bot": "Deploy drone below 30m for recon.",
            "Police_Bot": "Perimeter clear.",
            "Med_Bot": "Triage ready.",
        }
        pre_screen = commander._pre_screen_vetoes(reports)
        self.assertIsNotNone(pre_screen["Fire_Bot"],
                             "New trigger phrase should flag Fire_Bot")

    # ------------------------------------------------------------------
    # 3. Removed trigger no longer flags
    # ------------------------------------------------------------------
    def test_removed_trigger_no_longer_flags(self):
        # Remove all triggers that could match "enter unstable building"
        ca_module.VETO_TRIGGERS = {
            k: v for k, v in ca_module.VETO_TRIGGERS.items()
            if "enter unstable" not in k and "unstable building" not in k
        }
        commander = CommanderAgent(self.mock_llm)
        reports = {
            "Fire_Bot": "Team should enter unstable building.",
            "Police_Bot": "Clear.",
            "Med_Bot": "Clear.",
        }
        pre_screen = commander._pre_screen_vetoes(reports)
        # After removing the trigger, Fire_Bot should NOT be flagged by pre-screen
        # (it may still be caught by LLM review, but pre_screen result should be None)
        self.assertIsNone(pre_screen.get("Fire_Bot"),
                          "Removed trigger should no longer flag Fire_Bot in pre-screen")

    # ------------------------------------------------------------------
    # 4. Editing a rule text changes the prompt content
    # ------------------------------------------------------------------
    def test_edited_rule_text_reflected_in_prompt(self):
        ca_module.CONSTITUTION = "RULE 1: Human life > Property.\nRULE 2: Updated rule text for testing purposes."
        commander = CommanderAgent(self.mock_llm)
        reports = {"Fire_Bot": "A", "Police_Bot": "B", "Med_Bot": "C"}
        pre_screen = commander._pre_screen_vetoes(reports)
        prompt = commander._build_review_prompt(reports, pre_screen)
        self.assertIn("Updated rule text for testing purposes", prompt)


if __name__ == "__main__":
    unittest.main()
