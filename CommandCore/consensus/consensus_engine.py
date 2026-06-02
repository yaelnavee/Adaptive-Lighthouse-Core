"""
ConsensusEngine — Milestone 4: The Consensus Engine
====================================================
Deterministic (non-LLM) pre-processing that runs before the Commander's LLM call.

Three stages:
  1. calculate_urgency_scores() — keyword + tier-weight scoring per agent (1–10)
  2. detect_conflicts()         — opposing-recommendation detection across agents
  3. resolve()                  — full pipeline; returns scores, conflicts, and a
                                  summary string ready to inject into the LLM prompt
"""

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Priority tiers — add new agents here
# ---------------------------------------------------------------------------
AGENT_TIERS: dict[str, str] = {
    "Fire_Bot":   "LIFE_SAFETY",
    "Med_Bot":    "LIFE_SAFETY",
    "Police_Bot": "EVIDENCE",
}

TIER_BASE_SCORE: dict[str, float] = {
    "LIFE_SAFETY": 5.0,
    "EVIDENCE":    3.0,
    "PROPERTY":    1.0,
}

TIER_PRIORITY: dict[str, int] = {
    "LIFE_SAFETY": 3,
    "EVIDENCE":    2,
    "PROPERTY":    1,
}

# ---------------------------------------------------------------------------
# Urgency keyword catalog (English + Hebrew)
# ---------------------------------------------------------------------------
_URGENCY_KEYWORDS: dict[str, dict] = {
    "CRITICAL": {
        "weight": 2.0,
        "terms": [
            "trapped", "casualty", "casualties", "dead", "dying", "explosion",
            "toxic", "chemical leak", "gas leak", "collapse", "critical",
            "נפגע", "נפגעים", "כלוא", "מת", "פיצוץ", "דליפה", "קריסה", "קריטי",
        ],
    },
    "HIGH": {
        "weight": 1.0,
        "terms": [
            "fire", "injured", "evacuate", "hot zone", "hazmat", "rescue",
            "emergency", "urgent", "danger", "victim",
            "שריפה", "פצוע", "פינוי", "אזור חם", "חירום", "דחוף", "סכנה", "קורבן",
        ],
    },
    "MEDIUM": {
        "weight": 0.3,
        "terms": [
            "perimeter", "secure", "control", "standby", "monitor", "contain",
            "קורדון", "אבטחה", "שליטה", "המתנה", "ניטור",
        ],
    },
    "LOW": {
        "weight": -0.5,
        "terms": [
            "minor", "small", "contained", "resolved", "clear", "normal",
            "קטן", "שולי", "נשלט", "תקין", "רגיל",
        ],
    },
}

# ---------------------------------------------------------------------------
# Conflict patterns — each topic maps two opposing stances to phrase lists.
# Case-insensitive substring matching is used.
# ---------------------------------------------------------------------------
_CONFLICT_PATTERNS: dict[str, dict[str, list[str]]] = {
    "zone_access": {
        "allow": [
            "safe to enter", "authorized to enter", "entry authorized",
            "proceed to enter", "can enter", "cleared to enter", "entry approved",
            "כניסה מאושרת", "ניתן להיכנס", "מאושר כניסה",
        ],
        "deny": [
            "no entry", "hold position", "do not enter", "wait for clearance",
            "entry forbidden", "entry denied", "no access",
            "כניסה אסורה", "לא להיכנס", "המתן לאישור", "אסור כניסה", "אין כניסה",
        ],
    },
    "road_status": {
        "open": [
            "road open", "open the road", "allow traffic", "traffic flowing",
            "כביש פתוח", "תנועה חופשית", "פתח כביש",
        ],
        "closed": [
            "road closed", "block road", "close the road", "divert traffic",
            "חסימת כביש", "סגור כביש", "הסטת תנועה",
        ],
    },
    "evacuation": {
        "proceed": [
            "immediate evacuation", "full evacuation", "exit the area",
            "פינוי מיידי", "פינוי מלא", "פנה מהאזור",
        ],
        "hold": [
            "shelter in place", "stay inside", "do not evacuate", "remain indoors",
            "שהה במקום", "הישאר בפנים", "אין לפנות", "אל תפנה",
        ],
    },
}

# Stances that represent a restrictive/safety-conservative choice
_SAFETY_STANCES = {"deny", "closed", "hold"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class UrgencyScore:
    agent: str
    score: float                              # 1.0 – 10.0
    tier: str
    matched_keywords: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.score >= 7.0:
            return "CRITICAL"
        if self.score >= 5.0:
            return "HIGH"
        if self.score >= 3.0:
            return "MEDIUM"
        return "LOW"


@dataclass
class ConflictReport:
    topic: str            # e.g. "zone_access"
    agent_a: str
    stance_a: str         # e.g. "allow"
    agent_b: str
    stance_b: str         # e.g. "deny"
    score_a: float
    score_b: float
    winner: str           # agent whose recommendation takes precedence
    resolution_reason: str


# ---------------------------------------------------------------------------
# ConsensusEngine
# ---------------------------------------------------------------------------
class ConsensusEngine:
    """
    Deterministic pre-processing layer for the Commander.
    All logic is keyword + priority based — no LLM calls.
    """

    def calculate_urgency_scores(
        self, agent_reports: dict[str, str]
    ) -> dict[str, UrgencyScore]:
        scores: dict[str, UrgencyScore] = {}
        for agent, report in agent_reports.items():
            tier = AGENT_TIERS.get(agent, "PROPERTY")
            base = TIER_BASE_SCORE[tier]
            report_lower = (report or "").lower()

            bonus = 0.0
            matched: list[str] = []
            for level, cfg in _URGENCY_KEYWORDS.items():
                for term in cfg["terms"]:
                    if term.lower() in report_lower:
                        bonus += cfg["weight"]
                        matched.append(f"{term}({level})")

            raw = base + bonus
            scores[agent] = UrgencyScore(
                agent=agent,
                score=round(max(1.0, min(10.0, raw)), 1),
                tier=tier,
                matched_keywords=matched,
            )
        return scores

    def detect_conflicts(
        self,
        agent_reports: dict[str, str],
        urgency_scores: dict[str, UrgencyScore],
    ) -> list[ConflictReport]:
        agents = list(agent_reports.keys())
        conflicts: list[ConflictReport] = []

        for topic, sides in _CONFLICT_PATTERNS.items():
            # Map each agent to the stance it expresses (first match wins)
            agent_stances: dict[str, str] = {}
            for agent in agents:
                report_lower = (agent_reports.get(agent) or "").lower()
                for stance_name, phrases in sides.items():
                    if any(phrase.lower() in report_lower for phrase in phrases):
                        agent_stances[agent] = stance_name
                        break

            # Group agents by stance
            stance_agents: dict[str, list[str]] = {}
            for agent, stance in agent_stances.items():
                stance_agents.setdefault(stance, []).append(agent)

            # Cross-product: agents on opposing stances conflict
            all_stances = list(stance_agents.keys())
            for i in range(len(all_stances)):
                for j in range(i + 1, len(all_stances)):
                    s_a, s_b = all_stances[i], all_stances[j]
                    for a_agent in stance_agents[s_a]:
                        for b_agent in stance_agents[s_b]:
                            winner, reason = self._pick_winner(
                                a_agent, s_a, b_agent, s_b, urgency_scores, topic
                            )
                            us_a = urgency_scores.get(a_agent)
                            us_b = urgency_scores.get(b_agent)
                            conflicts.append(ConflictReport(
                                topic=topic,
                                agent_a=a_agent,
                                stance_a=s_a,
                                agent_b=b_agent,
                                stance_b=s_b,
                                score_a=us_a.score if us_a else 0.0,
                                score_b=us_b.score if us_b else 0.0,
                                winner=winner,
                                resolution_reason=reason,
                            ))
        return conflicts

    def _pick_winner(
        self,
        agent_a: str, stance_a: str,
        agent_b: str, stance_b: str,
        urgency_scores: dict[str, UrgencyScore],
        topic: str,
    ) -> tuple[str, str]:
        us_a = urgency_scores.get(agent_a)
        us_b = urgency_scores.get(agent_b)
        score_a = us_a.score if us_a else 1.0
        score_b = us_b.score if us_b else 1.0
        tier_a = us_a.tier if us_a else "PROPERTY"
        tier_b = us_b.tier if us_b else "PROPERTY"
        pri_a = TIER_PRIORITY.get(tier_a, 0)
        pri_b = TIER_PRIORITY.get(tier_b, 0)

        # 1. Higher urgency score wins (gap > 0.5 to avoid floating-point noise)
        if abs(score_a - score_b) > 0.5:
            if score_a > score_b:
                return agent_a, f"Higher urgency score ({score_a:.1f} vs {score_b:.1f})"
            return agent_b, f"Higher urgency score ({score_b:.1f} vs {score_a:.1f})"

        # 2. Higher priority tier wins
        if pri_a != pri_b:
            if pri_a > pri_b:
                return agent_a, f"Higher priority tier ({tier_a} > {tier_b})"
            return agent_b, f"Higher priority tier ({tier_b} > {tier_a})"

        # 3. Safety-first: restrictive action wins
        if stance_a in _SAFETY_STANCES and stance_b not in _SAFETY_STANCES:
            return agent_a, "Safety-first principle: restrictive action preferred on equal priority and score"
        if stance_b in _SAFETY_STANCES and stance_a not in _SAFETY_STANCES:
            return agent_b, "Safety-first principle: restrictive action preferred on equal priority and score"

        # 4. Complete tie — return first agent
        return agent_a, "Equal priority and score — defaulting to first agent"

    def resolve(self, agent_reports: dict[str, str]) -> dict:
        """
        Full consensus pipeline. Returns urgency_scores, conflicts, and a
        summary string ready for injection into the Commander's LLM prompt.
        """
        urgency_scores = self.calculate_urgency_scores(agent_reports)
        conflicts = self.detect_conflicts(agent_reports, urgency_scores)
        summary = self._build_summary(urgency_scores, conflicts)
        return {
            "urgency_scores": urgency_scores,
            "conflicts": conflicts,
            "summary": summary,
        }

    def _build_summary(
        self,
        urgency_scores: dict[str, UrgencyScore],
        conflicts: list[ConflictReport],
    ) -> str:
        lines = ["CONSENSUS ANALYSIS (pre-computed — treat as authoritative):"]

        lines.append("\nURGENCY SCORES:")
        for agent, us in urgency_scores.items():
            lines.append(
                f"  {agent}: {us.score:.1f}/10 [{us.label}] (tier: {us.tier})"
            )

        if conflicts:
            lines.append("\nCONFLICT RESOLUTIONS (BINDING — follow these exactly):")
            for c in conflicts:
                lines.append(
                    f"  [{c.topic.upper()}] {c.agent_a}({c.stance_a}) vs "
                    f"{c.agent_b}({c.stance_b}) → WINNER: {c.winner} "
                    f"— {c.resolution_reason}"
                )
        else:
            lines.append("\nNO CONFLICTS DETECTED — agents are aligned.")

        return "\n".join(lines)
