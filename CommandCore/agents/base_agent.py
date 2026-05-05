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

    def build_prompt(self, user_input: str, previous_findings: str = "") -> str:
        """
        Assembles the full LLM prompt for this agent.

        Parameters
        ----------
        user_input        : The current incident description
        previous_findings : Aggregated output from agents that ran before this one
                            (empty string if this agent runs first)
        """
        coordination_block = (
            previous_findings
            if previous_findings
            else "You are the FIRST responder. Set the baseline."
        )

        return f"""You are {self.name}, an emergency specialist.

ROLE: {self.role}
PROTOCOL: {self.protocol}

COORDINATION CONTEXT (Mandatory constraint — treat this as ground truth):
{coordination_block}

INSTRUCTIONS for Collaborative Response:
1. DO NOT repeat the situation description.
2. DO NOT use generic phrases like "I will coordinate with...".
3. ACTIVE REACTION: Look at what the previous agents decided. If Fire set a 500m zone,
   YOU must use that 500m zone in your plan.
4. BUILD UPON: Use previous findings as facts. Fill only the gaps left by others within your domain.
5. BE BRIEF: 2-3 direct bullet points maximum.
6. STAY WITHIN BOUNDS: Respond only within your domain.
7. LANGUAGE MATCHING (Critical): Detect the language of the SITUATION.
   - If the user input is in HEBREW, your entire response MUST be in HEBREW.
   - If the user input is in ENGLISH, your entire response MUST be in ENGLISH.
   - Use professional terminology appropriate for the chosen language.

SITUATION:
{user_input}

ACTIONABLE COLLABORATION PLAN:
"""

    def analyze(self, user_input: str, previous_findings: str = "") -> str:
        """Sends the assembled prompt to the LLM and returns the response."""
        return self.llm.generate(self.build_prompt(user_input, previous_findings))
