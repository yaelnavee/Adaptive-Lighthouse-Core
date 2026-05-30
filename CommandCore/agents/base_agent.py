"""
BaseAgent — Abstract base class for all specialist agents.

Each specialist agent inherits from this class and provides:
  - A unique name, role, and persona
  - A path to its domain protocol (.md file)

The build_prompt() method assembles the full instruction set for the LLM,
including coordination context from previously-run agents (Round Table feature).
"""

from abc import ABC
import os
import re

# Single source of truth for unclear/gibberish responses used by all agents and the commander.
UNCLEAR_RESPONSE_EN = (
    "Event description is unclear. Please provide:\n"
    "• Type of event (fire / accident / hazmat / other)\n"
    "• Location of the event\n"
    "• Estimated number of casualties (if known)"
)

UNCLEAR_RESPONSE_HE = (
    "תיאור האירוע אינו ברור. אנא ספק:\n"
    '• סוג האירוע (שריפה / תאונה / חומ"ס / אחר)\n'
    "• מיקום האירוע\n"
    "• מספר נפגעים משוערים (אם ידוע)"
)


class BaseAgent(ABC):
    def __init__(self, name: str, role: str, persona: str, protocol_path: str, llm_client):
        self.name = name
        self.role = role
        self.persona = persona
        self.llm = llm_client
        self.protocol = self._load_protocol(protocol_path)

    def _load_protocol(self, path: str) -> str:
        """Loads the domain-specific protocol from a markdown file."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return "Standard operational protocols apply."

    @staticmethod
    def _detect_language(text: str) -> str:
        """Returns 'HEBREW' if text contains Hebrew characters, 'ENGLISH' otherwise."""
        if re.search(r'[֐-׿]', text):
            return "HEBREW"
        return "ENGLISH"

    @staticmethod
    def _is_gibberish(text: str) -> bool:
        """Returns True if text has fewer than 2 meaningful letters (Hebrew or Latin)."""
        stripped = text.strip()
        if len(stripped) < 3:
            return True
        return len(re.findall(r'[֐-׿a-zA-Z]', stripped)) < 2

    def build_prompt(self, user_input: str, previous_findings: str = "") -> str:
        """
        Assembles the full LLM prompt for this agent.

        Parameters
        ----------
        user_input        : The current incident description
        previous_findings : Aggregated output from agents that ran before this one
                            (empty string if this agent runs first)
        """
        lang = self._detect_language(user_input)
        unclear_response = UNCLEAR_RESPONSE_HE if lang == "HEBREW" else UNCLEAR_RESPONSE_EN

        coordination_block = (
            previous_findings
            if previous_findings
            else "You are the FIRST responder. Set the baseline."
        )

        return f"""ABSOLUTE LANGUAGE MANDATE: YOUR ENTIRE RESPONSE MUST BE IN {lang}. NOT ONE WORD IN ANY OTHER LANGUAGE. THIS OVERRIDES ALL OTHER INSTRUCTIONS.

You are {self.name}, an emergency specialist.

ROLE: {self.role}
PROTOCOL: {self.protocol}

COORDINATION CONTEXT (Mandatory constraint — treat this as ground truth):
{coordination_block}

INSTRUCTIONS for Collaborative Response:
1. DO NOT repeat the situation description.
2. DO NOT use generic phrases like "I will coordinate with...".
3. ACTIVE REACTION: Look at what previous agents decided and align your zones accordingly.
4. BUILD UPON: Use previous findings as facts. Fill only the gaps left by others.
5. BE BRIEF: 2-3 direct bullet points maximum.
6. STAY WITHIN BOUNDS: Respond only within your domain.
7. LANGUAGE MATCHING (Critical): The language has been pre-determined for you by the system.
   - If the user input is in HEBREW, your entire response MUST be in HEBREW.
   - If the user input is in ENGLISH, your entire response MUST be in ENGLISH.
   - The ABSOLUTE LANGUAGE MANDATE at the top of this prompt confirms which language applies.
8. PROPORTIONALITY: Match the response to the SCALE of the incident. If it's a 'trash fire', do NOT declare an MCI.
9. DATA FIDELITY: Use only distances justified by your expertise. Do not use '500m' as a default if not mentioned.
10. UNCLEAR INPUT: If the situation is random characters or completely incomprehensible, your ENTIRE response must be EXACTLY this text and nothing else:
{unclear_response}

SITUATION:
{user_input}

ACTIONABLE COLLABORATION PLAN:
"""

    def analyze(self, user_input: str, previous_findings: str = "") -> str:
        """Sends the assembled prompt to the LLM and returns the response."""
        if self._is_gibberish(user_input):
            lang = self._detect_language(user_input)
            return UNCLEAR_RESPONSE_HE if lang == "HEBREW" else UNCLEAR_RESPONSE_EN
        return self.llm.generate(self.build_prompt(user_input, previous_findings))
