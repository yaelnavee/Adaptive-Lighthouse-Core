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
from typing import Optional
from llm.llm_client import LLMClient

# ---------------------------------------------------------------------------
# THE CONSTITUTION — plain-English rules. Keep the "RULE N:" prefix so tests
# can verify each rule by number. Add new rules at the bottom.
# ---------------------------------------------------------------------------
CONSTITUTION = """
RULE 1: Human life > Property. Any plan that risks human life to protect property is forbidden.
RULE 2: No response team enters a structurally unstable zone without clearance. Danger threshold > 70% = automatic hold.
RULE 3: Life-safety operations (rescue, evacuation) take priority over evidence collection. Any plan delaying rescue for evidence is forbidden.
RULE 4: Medical personnel must use approved treatments only. Experimental or invented protocols are forbidden.
RULE 5: Fire_Bot clearance is required before any unit enters a hot zone. No unit self-authorises entry.
""".strip()

# ---------------------------------------------------------------------------
# VETO_TRIGGERS — extend this dict to add new pre-screen checks.
# Keys   : phrase to detect (case-insensitive substring match)
# Values : rule label shown in the audit log
# ---------------------------------------------------------------------------
VETO_TRIGGERS: dict = {
    "enter unstable":         "RULE 2 — Team ordered into unstable structure",
    "unstable building":      "RULE 2 — Team ordered into unstable structure",
    "enter the hot zone":     "RULE 5 — Unauthorised hot-zone entry without Fire_Bot clearance",
    "evidence first":         "RULE 3 — Evidence collection before life-safety response",
    "collect evidence first": "RULE 3 — Evidence collection before life-safety response",
    "experimental treatment": "RULE 4 — Experimental/invented medical protocol",
    "experimental drug":      "RULE 4 — Experimental/invented medical protocol",
    "new drug":               "RULE 4 — Experimental/invented medical protocol",
    "life for property":      "RULE 1 — Plan risks life to protect property",
}


class CommanderAgent:
    """
    Two-stage Constitutional AI commander.

    Stage 1 — _pre_screen_vetoes():  fast, deterministic keyword scan.
    Stage 2 — review_and_synthesize(): LLM deep review using CONSTITUTION.

    Both stages read module-level CONSTITUTION and VETO_TRIGGERS at call time,
    so live edits (e.g. from the Streamlit sidebar) take effect immediately.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self._veto_log: list = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review_and_synthesize(self, agent_reports: dict) -> dict:
        """
        Full two-stage constitutional review.

        Parameters
        ----------
        agent_reports : dict  {agent_name: report_text}

        Returns
        -------
        dict with keys:
          reviews   — {agent_name: {vetoed: bool, reason: str}}
          final_plan — str
          veto_log  — list of audit entries [{stage, agent, reason}]
        """
        self._veto_log = []

        # Stage 1: keyword pre-screen (no LLM cost, instant)
        pre_screen = self._pre_screen_vetoes(agent_reports)

        # Stage 2: LLM deep constitutional review
        prompt = self._build_review_prompt(agent_reports, pre_screen)
        raw_response = self.llm.generate(prompt)

        # Parse structured LLM output into a dict
        reviews = self._parse_reviews(raw_response, agent_reports)
        final_plan = self._parse_final_plan(raw_response)

        # Append LLM-detected vetoes to the audit log.
        # If the LLM vetoes an agent, always record it as 'llm_review' stage,
        # even if it was also caught by pre-screen (both stages can fire independently).
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

    def get_veto_log(self) -> list:
        """Returns the audit log from the most recent review_and_synthesize call."""
        return self._veto_log

    # ------------------------------------------------------------------
    # Internal helpers — read module globals at call time for live editing
    # ------------------------------------------------------------------

    def _pre_screen_vetoes(self, agent_reports: dict) -> dict:
        """
        Fast keyword scan using the current module-level VETO_TRIGGERS.
        Populates the veto log with stage='pre_screen' for each match.

        Returns
        -------
        dict {agent_name: veto_reason_str | None}
        """
        import agents.commander_agent as _self_module
        triggers = _self_module.VETO_TRIGGERS

        results: dict = {}
        for agent, report in agent_reports.items():
            report_lower = report.lower()
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
        """Constructs the structured LLM review prompt using the current CONSTITUTION."""
        import agents.commander_agent as _self_module
        constitution = _self_module.CONSTITUTION

        # Pre-screen summary block
        flagged_lines = [
            f"  ⚠ {agent}: PRE-SCREEN FLAGGED — {reason}"
            for agent, reason in pre_screen.items()
            if reason
        ]
        flagged_block = "\n".join(flagged_lines) if flagged_lines else "  ✓ No pre-screen flags."

        reports_block = "\n".join(
            f"  [{agent}]: {text or '(no report submitted)'}"
            for agent, text in agent_reports.items()
        )

        # Detect the language of the incident from the reports context
        # (use the first non-empty report as language sample)
        sample_text = next((v for v in agent_reports.values() if v), "")

        return f"""You are the COMMANDER AGENT responsible for Constitutional AI enforcement.

CONSTITUTION (non-negotiable):
{constitution}

PRE-SCREEN RESULTS (keyword scan already performed):
{flagged_block}

SPECIALIST REPORTS:
{reports_block}

YOUR TASK:
1. Review every report against the CONSTITUTION — treat pre-screen results as confirmed hints.
2. For each agent output exactly one of:
     <AgentName>: APPROVED
     <AgentName>: VETO - <RULE reference> - <brief reason>
3. Write a FINAL_PLAN synthesising only APPROVED recommendations into one concise
   unified tactical plan. If all are vetoed, issue a safe default hold order.

LANGUAGE RULE (critical): Detect the language used in the SPECIALIST REPORTS.
- If the reports are in HEBREW → write FINAL_PLAN entirely in HEBREW.
- If the reports are in ENGLISH → write FINAL_PLAN entirely in ENGLISH.
- The REVIEW lines (APPROVED/VETO) must always be in ENGLISH for parsing.

STRICT OUTPUT FORMAT (do not deviate):
REVIEW:
<AgentName>: APPROVED or VETO - <reason>
...
FINAL_PLAN:
<unified plan in the detected language>
"""

    def _parse_reviews(self, raw_response: str, agent_reports: dict) -> dict:
        """
        Parses the REVIEW block from the LLM response.
        Defaults to APPROVED if an agent name is missing from the response.
        """
        reviews: dict = {}

        review_match = re.search(
            r"REVIEW:(.*?)(?:FINAL_PLAN:|$)", raw_response, re.DOTALL | re.IGNORECASE
        )
        review_block = review_match.group(1) if review_match else ""

        for agent in agent_reports:
            pattern = rf"{re.escape(agent)}\s*:\s*(VETO|APPROVED)(.*?)(?=\n\S|\Z)"
            match = re.search(pattern, review_block, re.IGNORECASE | re.DOTALL)

            if match:
                verdict = match.group(1).upper()
                reason = match.group(2).strip().lstrip("- ").strip()
                reviews[agent] = {
                    "vetoed": verdict == "VETO",
                    "reason": reason if reason else ("Constitutional violation" if verdict == "VETO" else ""),
                }
            else:
                # Agent absent from response — default to APPROVED (fail-open for display,
                # but the audit log preserves any pre-screen flag)
                reviews[agent] = {"vetoed": False, "reason": ""}

        return reviews

    def _parse_final_plan(self, raw_response: str) -> str:
        """Extracts the FINAL_PLAN section from the LLM response."""
        match = re.search(r"FINAL_PLAN:\s*(.*)", raw_response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return raw_response.strip()
