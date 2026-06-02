"""
CommanderAgent — Milestone 4: The Consensus Engine
===================================================
Extends Milestone 3's Constitutional AI with:
  - ConsensusEngine: deterministic urgency scoring + conflict resolution
  - PRE-SCREEN FLAGGED markers injected into the LLM prompt
  - Conflict resolutions injected as authoritative guidance
  - Structured output: {reviews, final_plan, veto_log, urgency_scores, conflicts}
  - get_veto_log() public accessor for audit log
"""

import re
import os
from typing import Optional
from llm.llm_client import LLMClient
from agents.base_agent import UNCLEAR_RESPONSE_EN, UNCLEAR_RESPONSE_HE
from consensus.consensus_engine import ConsensusEngine


def load_constitution_file():
    """Loads the constitution text from the external markdown file."""
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "protocols", "constitution.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "RULE 1: Life safety first. RULE 2: Maintain input fidelity."


CONSTITUTION = load_constitution_file()

VETO_TRIGGERS: dict = {
    "enter unstable":         "RULE 2 — Team ordered into unstable structure",
    "unstable building":      "RULE 2 — Team ordered into unstable structure",
    "enter the hot zone":     "RULE 5 — Unauthorised hot-zone entry without Fire_Bot clearance",
    "evidence first":         "RULE 3 — Evidence collection before life-safety response",
    "experimental treatment": "RULE 4 — Experimental/invented medical protocol",
    "פינוי מיידי":            "RULE 5 — Unauthorized hot-zone entry before clearance",
    "נכנסים לפינוי":          "RULE 5 — Unauthorized hot-zone entry before clearance",
    "אירוע רב נפגעים":        "RULE 6 — Disproportional response to minor incident",
    "mci":                    "RULE 6 — Disproportional response to minor incident",
    "פינוי של כל השכונה":     "RULE 6 — Disproportional response to minor incident",
}


class CommanderAgent:
    """
    Two-stage Constitutional AI commander with Consensus Engine pre-processing.

    Pipeline:
      1. ConsensusEngine  — urgency scores + deterministic conflict resolution
      2. Pre-screen       — fast keyword veto scan
      3. LLM review       — deep constitutional synthesis → single unified plan
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self._veto_log: list = []
        self._consensus = ConsensusEngine()

    def get_veto_log(self) -> list:
        """Returns the current veto audit log."""
        return self._veto_log

    def review_and_synthesize(self, agent_reports: dict) -> dict:
        self._veto_log = []

        # Stage 1: Consensus Engine — urgency scores + conflict resolution
        consensus = self._consensus.resolve(agent_reports)
        urgency_scores = consensus["urgency_scores"]
        conflicts = consensus["conflicts"]
        consensus_summary = consensus["summary"]

        # Stage 2: Fast deterministic keyword pre-screen
        pre_screen = self._pre_screen_vetoes(agent_reports)

        # Stage 3: Deep constitutional review via LLM
        prompt = self._build_review_prompt(agent_reports, pre_screen, consensus_summary)
        raw_response = self.llm.generate(prompt)

        reviews = self._parse_reviews(raw_response, agent_reports)
        final_plan = self._parse_final_plan(raw_response)

        for agent, review in reviews.items():
            if review["vetoed"]:
                self._veto_log.append({
                    "stage": "llm_review",
                    "agent": agent,
                    "reason": review["reason"],
                })

        return {
            "reviews": reviews,
            "final_plan": final_plan,
            "veto_log": self._veto_log,
            "urgency_scores": urgency_scores,
            "conflicts": conflicts,
        }

    def _pre_screen_vetoes(self, agent_reports: dict) -> dict:
        import agents.commander_agent as _self_module
        triggers = _self_module.VETO_TRIGGERS

        results: dict = {}
        for agent, report in agent_reports.items():
            report_lower = (report or "").lower()
            matched_rule: Optional[str] = None

            for phrase, rule_label in triggers.items():
                if phrase.lower() in report_lower:
                    matched_rule = rule_label
                    break

            results[agent] = matched_rule
            if matched_rule:
                self._veto_log.append({
                    "stage": "pre_screen",
                    "agent": agent,
                    "reason": matched_rule,
                })
        return results

    def _build_review_prompt(
        self,
        agent_reports: dict,
        pre_screen: dict,
        consensus_summary: str = "",
    ) -> str:
        import agents.commander_agent as _self_module
        constitution = _self_module.CONSTITUTION

        # Build reports block with PRE-SCREEN FLAGGED markers where applicable
        report_lines = []
        for agent, text in agent_reports.items():
            flag = pre_screen.get(agent)
            flag_str = f"\n  ⚠️ PRE-SCREEN FLAGGED: {flag}" if flag else ""
            report_lines.append(f"  [{agent}]: {text or '(no report)'}{flag_str}")
        reports_block = "\n".join(report_lines)

        hebrew_chars = len(re.findall(r'[֐-׿]', reports_block))
        english_chars = len(re.findall(r'[a-zA-Z]', reports_block))

        if english_chars >= hebrew_chars or "Incomprehensible input" in reports_block:
            gibberish_target = UNCLEAR_RESPONSE_EN
        else:
            gibberish_target = UNCLEAR_RESPONSE_HE

        consensus_block = f"\n{consensus_summary}\n" if consensus_summary else ""

        return f"""You are the COMMANDER AGENT enforcing Constitutional AI.

CONSTITUTION:
{constitution}
{consensus_block}
SPECIALIST REPORTS:
{reports_block}

### MANDATORY LOGIC:
1. GIBBERISH CHECK (PRIORITY 1): If the specialist reports indicate the input is total nonsense, random characters, or completely unclear, your FINAL_PLAN MUST be EXACTLY the following text — copy it verbatim, do NOT translate, summarize, or alter it in any way:
---
{gibberish_target}
---
2. ANTI-HALLUCINATION: VETO any agent that invents hazards (e.g., "gas leak", "victims") NOT mentioned in the input.
3. TACTICAL EXPERTISE: Do NOT veto specialists for setting safety perimeters (e.g., 50m, 70m) or choosing equipment. This is their EXPERTISE, not a hallucination.
4. RADIUS SYNC: If agents propose different distances, prioritize Fire_Bot's radius and align others to it.
5. HAZMAT SAFETY (RULE 5): VETO any agent attempting to enter a hot zone or perform an immediate evacuation ("פינוי מיידי") before Fire_Bot gives the safe-to-enter signal.
6. SCALE & PROPORTIONALITY: VETO disproportional responses. If a minor trash can fire is reported, VETO declarations of MCI or full neighborhood evacuations.
7. CONFLICT RESOLUTION: Follow the CONSENSUS ANALYSIS conflict resolutions above. They are BINDING.
8. LANGUAGE: If Priority 1 is active, use the exact language of the string provided in Rule 1. Otherwise, detect the dominant language of the specialist reports and respond in the SAME language — Hebrew if reports are predominantly Hebrew, English if predominantly English.

STRICT FORMAT:
REVIEW:
<AgentName>: APPROVED or VETO - <Reason>
...
FINAL_PLAN:
<ONE unified action plan with numbered priorities. Address life-safety first, then tactical, then logistics. Do NOT write three separate agent sub-sections — this must read as a single coherent command order.>
"""

    def _parse_reviews(self, raw_response: str, agent_reports: dict) -> dict:
        reviews: dict = {}
        review_match = re.search(r"REVIEW:(.*?)(?:FINAL_PLAN:|$)", raw_response, re.DOTALL | re.IGNORECASE)
        review_block = review_match.group(1) if review_match else raw_response

        for agent in agent_reports:
            pattern = rf"{re.escape(agent)}\s*:\s*(VETO|APPROVED)(.*?)(?=\n\S|\Z)"
            match = re.search(pattern, review_block, re.IGNORECASE | re.DOTALL)
            if match:
                verdict = match.group(1).upper()
                reviews[agent] = {
                    "vetoed": verdict == "VETO",
                    "reason": match.group(2).strip().lstrip("- "),
                }
            else:
                reviews[agent] = {"vetoed": False, "reason": ""}
        return reviews

    def _parse_final_plan(self, raw_response: str) -> str:
        match = re.search(r"FINAL_PLAN:\s*(.*)", raw_response, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else raw_response.strip()
