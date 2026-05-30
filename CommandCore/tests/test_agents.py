"""
tests/test_agents.py — Milestone 1 & 2: Specialist Agents
==========================================================
Tests cover:
  1. Factory creates the correct agent type
  2. Protocol files are loaded (RAG resilience)
  3. Language-matching instruction is injected into every prompt
  4. Brevity constraint is present in every prompt
  5. Round Table: shared coordination context is injected correctly
  6. Edge case: empty input does not crash prompt builder
"""

import unittest
from unittest.mock import MagicMock
import os
from agents.agent_factory import SpecialistFactory
from agents.base_agent import BaseAgent


class TestSpecialistAgents(unittest.TestCase):

    def setUp(self):
        # Use a mock LLM to avoid real API calls in unit tests
        self.mock_llm = MagicMock()

    # ------------------------------------------------------------------
    # 1. Factory creation
    # ------------------------------------------------------------------
    def test_factory_creates_fire_agent(self):
        fire_agent = SpecialistFactory.create("fire", self.mock_llm)
        self.assertEqual(fire_agent.name, "Fire_Bot")
        self.assertEqual(fire_agent.role, "Firefighting Expert")

    def test_factory_raises_on_unknown_type(self):
        with self.assertRaises(ValueError):
            SpecialistFactory.create("unknown_type", self.mock_llm)

    # ------------------------------------------------------------------
    # 2. Protocol loading (RAG resilience)
    # ------------------------------------------------------------------
    def test_protocol_loaded_from_file(self):
        """Agent should load its markdown protocol, not the fallback string."""
        fire_agent = SpecialistFactory.create("fire", self.mock_llm)
        self.assertNotEqual(fire_agent.protocol, "Standard operational protocols apply.")

    # ------------------------------------------------------------------
    # 3. Language-matching instruction injected into prompt
    # ------------------------------------------------------------------
    def test_language_instruction_in_prompt(self):
        agent = SpecialistFactory.create("medical", self.mock_llm)
        hebrew_prompt = agent.build_prompt("עזרה דחופה")
        # Hard mandate at the top (deterministic — Python-detected, not LLM-inferred)
        self.assertIn("ABSOLUTE LANGUAGE MANDATE", hebrew_prompt)
        self.assertIn("YOUR ENTIRE RESPONSE MUST BE IN HEBREW", hebrew_prompt)
        # Fallback instruction block still present
        self.assertIn("LANGUAGE MATCHING (Critical)", hebrew_prompt)
        self.assertIn("If the user input is in HEBREW, your entire response MUST be in HEBREW", hebrew_prompt)
        # English input must mandate ENGLISH
        english_prompt = agent.build_prompt("Help needed")
        self.assertIn("YOUR ENTIRE RESPONSE MUST BE IN ENGLISH", english_prompt)

    # ------------------------------------------------------------------
    # 4. Brevity constraint in prompt
    # ------------------------------------------------------------------
    def test_brevity_constraint_in_prompt(self):
        agent = SpecialistFactory.create("police", self.mock_llm)
        prompt = agent.build_prompt("Crowd control needed")
        self.assertIn("BE BRIEF: 2-3 direct bullet points maximum", prompt)
        self.assertIn("DO NOT repeat the situation description", prompt)

    # ------------------------------------------------------------------
    # 5. Round Table: shared context injected correctly
    # ------------------------------------------------------------------
    def test_shared_context_injected(self):
        agent = SpecialistFactory.create("medical", self.mock_llm)
        previous_info = "Fire_Bot established a 500m hot zone."
        prompt = agent.build_prompt("Injured person found", previous_findings=previous_info)
        self.assertIn("COORDINATION CONTEXT", prompt)
        self.assertIn(previous_info, prompt)

    # ------------------------------------------------------------------
    # 6. Edge case: empty input
    # ------------------------------------------------------------------
    def test_empty_input_builds_valid_prompt(self):
        """Empty user input must not crash the prompt builder."""
        agent = SpecialistFactory.create("fire", self.mock_llm)
        prompt = agent.build_prompt("")
        self.assertIn("SITUATION:", prompt)
        self.assertIn("ACTIONABLE COLLABORATION PLAN:", prompt)

    # ------------------------------------------------------------------
    # 7. Gibberish detection — valid Hebrew must never be rejected
    # ------------------------------------------------------------------
    def test_gibberish_accepts_valid_hebrew_sentence(self):
        """A well-formed Hebrew incident description must not be flagged as gibberish."""
        valid_hebrew = "התפוצץ צינור גז ברחוב עמוס בתל אביב, טרם דווח על נפגעים"
        self.assertFalse(BaseAgent._is_gibberish(valid_hebrew))

    def test_gibberish_accepts_short_hebrew_word(self):
        """Two-character Hebrew words are valid inputs and must not be rejected."""
        self.assertFalse(BaseAgent._is_gibberish("אש"))

    def test_gibberish_rejects_symbols_only(self):
        self.assertTrue(BaseAgent._is_gibberish("!!!"))

    def test_gibberish_rejects_empty_and_whitespace(self):
        self.assertTrue(BaseAgent._is_gibberish(""))
        self.assertTrue(BaseAgent._is_gibberish("   "))

    def test_gibberish_rejects_digits_only(self):
        self.assertTrue(BaseAgent._is_gibberish("12345"))

    def test_gibberish_accepts_valid_english_sentence(self):
        self.assertFalse(BaseAgent._is_gibberish("Gas pipe explosion on Main Street"))


if __name__ == "__main__":
    unittest.main()
