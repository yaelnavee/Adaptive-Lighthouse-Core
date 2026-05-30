"""
CommanderAgent — Milestone 3: The Constitution
===============================================
Implements Constitutional AI with:
  - CONSTITUTION: human-readable rules string (edit directly — no JSON file needed)
  - VETO_TRIGGERS: keyword phrases for fast pre-screening (edit as a plain dict)
  - Two-stage review: keyword pre-screen then LLM deep review
  - Structured output: {reviews, final_plan, veto_log}
  - Veto audit log for full traceability

To add or modify rules:
  1. Edit the CONSTITUTION string below (plain English, one "RULE N:" per line).
  2. Add matching keyword phrases to VETO_TRIGGERS.
  No other code changes are needed.
  In the Streamlit UI, both can be edited live from the sidebar.
"""

import re
import os
from typing import Optional
from llm.llm_client import LLMClient
from agents.base_agent import UNCLEAR_RESPONSE_EN, UNCLEAR_RESPONSE_HE

# # ---------------------------------------------------------------------------
# # THE CONSTITUTION — plain-English rules. Keep the "RULE N:" prefix so tests
# # can verify each rule by number. Add new rules at the bottom.
# # ---------------------------------------------------------------------------
# CONSTITUTION = """
# RULE 1: Human life > Property. Any plan that risks human life to protect property is forbidden.
# RULE 2: No response team enters a structurally unstable zone without clearance. Danger threshold > 70% = automatic hold.
# RULE 3: Life-safety operations (rescue, evacuation) take priority over evidence collection. Any plan delaying rescue for evidence is forbidden.
# RULE 4: Medical personnel must use approved treatments only. Experimental or invented protocols are forbidden.
# RULE 5: Fire_Bot clearance is required before any unit enters a hot zone. No unit self-authorises entry.
# """.strip()

# # ---------------------------------------------------------------------------
# # VETO_TRIGGERS — extend this dict to add new pre-screen checks.
# # Keys   : phrase to detect (case-insensitive substring match)
# # Values : rule label shown in the audit log
# # ---------------------------------------------------------------------------
# VETO_TRIGGERS: dict = {
#     "enter unstable":         "RULE 2 — Team ordered into unstable structure",
#     "unstable building":      "RULE 2 — Team ordered into unstable structure",
#     "enter the hot zone":     "RULE 5 — Unauthorised hot-zone entry without Fire_Bot clearance",
#     "evidence first":         "RULE 3 — Evidence collection before life-safety response",
#     "collect evidence first": "RULE 3 — Evidence collection before life-safety response",
#     "experimental treatment": "RULE 4 — Experimental/invented medical protocol",
#     "experimental drug":      "RULE 4 — Experimental/invented medical protocol",
#     "new drug":               "RULE 4 — Experimental/invented medical protocol",
#     "life for property":      "RULE 1 — Plan risks life to protect property",
#     "נכנסים לאזור חם":        "RULE 5 — Unauthorized hot-zone entry", #
#     "כניסה מיידית":           "RULE 5 — Unauthorized hot-zone entry", #
# }
# """
# ### MANDATORY VALIDATION:
# ...
# 5. HAZMAT SAFETY (RULE 5): If Fire_Bot defines a "Hot Zone" or says "Decontamination/טיהור required", 
#    you MUST VETO any other agent attempting to ENTER before Fire_Bot gives the "Safe-to-Enter" signal. 
#    Human life protection (Rule 1) does NOT justify ignoring Rule 5 safety protocols.
# """


# Function to load the constitution from the protocols folder
def load_constitution_file():
    """
    Loads the constitution text from the external markdown file.
    Ensures that administrative rules are separated from logic.
    """
    # Path relative to the agent file location
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "protocols", "constitution.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        # Fallback if the file is missing
        return "RULE 1: Life safety first. RULE 2: Maintain input fidelity."

# Initializing global variables for Streamlit compatibility
CONSTITUTION = load_constitution_file()

# Triggers for fast keyword pre-screening
VETO_TRIGGERS: dict = {
    "enter unstable":         "RULE 2 — Team ordered into unstable structure",
    "unstable building":      "RULE 2 — Team ordered into unstable structure",
    "enter the hot zone":     "RULE 5 — Unauthorised hot-zone entry without Fire_Bot clearance",
    "evidence first":         "RULE 3 — Evidence collection before life-safety response",
    "experimental treatment": "RULE 4 — Experimental/invented medical protocol",
    # Hebrew active triggers for test compliance
    "פינוי מיידי":            "RULE 5 — Unauthorized hot-zone entry before clearance",
    "נכנסים לפינוי":          "RULE 5 — Unauthorized hot-zone entry before clearance",
    "אירוע רב נפגעים":        "RULE 6 — Disproportional response to minor incident",
    "mci":                    "RULE 6 — Disproportional response to minor incident",
    "פינוי של כל השכונה":     "RULE 6 — Disproportional response to minor incident",
}

class CommanderAgent:
    """
    Two-stage Constitutional AI commander.
    Validates specialist outputs against the external Constitution.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self._veto_log: list = []

    def review_and_synthesize(self, agent_reports: dict) -> dict:
        self._veto_log = []

        # Stage 1: Fast deterministic keyword scan
        pre_screen = self._pre_screen_vetoes(agent_reports)

        # Stage 2: Deep constitutional review via LLM
        prompt = self._build_review_prompt(agent_reports, pre_screen)
        raw_response = self.llm.generate(prompt)

        reviews = self._parse_reviews(raw_response, agent_reports)
        final_plan = self._parse_final_plan(raw_response)

        # Append LLM findings to the audit log
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

    def _build_review_prompt(self, agent_reports: dict, pre_screen: dict) -> str:
        import agents.commander_agent as _self_module

        constitution = _self_module.CONSTITUTION
        reports_block = "\n".join(
            f"  [{agent}]: {text or '(no report)'}"
            for agent, text in agent_reports.items()
        )

        hebrew_chars = len(re.findall(r'[\u0590-\u05FF]', reports_block))
        english_chars = len(re.findall(r'[a-zA-Z]', reports_block))

        if english_chars >= hebrew_chars or "Incomprehensible input" in reports_block:
            gibberish_target = UNCLEAR_RESPONSE_EN
        else:
            gibberish_target = UNCLEAR_RESPONSE_HE

        return f"""You are the COMMANDER AGENT enforcing Constitutional AI.

CONSTITUTION:
{constitution}

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
7. LANGUAGE: If Priority 1 is active, use the exact language of the string provided in Rule 1. Otherwise, detect the dominant language of the specialist reports and respond in the SAME language — Hebrew if reports are predominantly Hebrew, English if predominantly English.

STRICT FORMAT:
REVIEW:
<AgentName>: APPROVED or VETO - <Reason>
...
FINAL_PLAN:
<The unified plan OR the mandatory error message>
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
                    "reason": match.group(2).strip().lstrip("- ")
                }
            else:
                reviews[agent] = {"vetoed": False, "reason": ""}
        return reviews

    def _parse_final_plan(self, raw_response: str) -> str:
        match = re.search(r"FINAL_PLAN:\s*(.*)", raw_response, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else raw_response.strip()