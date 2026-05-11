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
3. ACTIVE REACTION: Look at what previous agents decided and align your zones accordingly.
4. BUILD UPON: Use previous findings as facts. Fill only the gaps left by others.
5. BE BRIEF: 2-3 direct bullet points maximum.
6. STAY WITHIN BOUNDS: Respond only within your domain.
7. LANGUAGE MATCHING (Critical): The SITUATION is in HEBREW. Your entire response MUST be in HEBREW.
8. PROPORTIONALITY: Match the response to the SCALE of the incident. If it's a 'trash fire', do NOT declare an MCI.
9. DATA FIDELITY: Use only distances justified by your expertise. Do not use '500m' as a default if not mentioned.

SITUATION:
{user_input}

ACTIONABLE COLLABORATION PLAN (HEBREW ONLY):
"""

    def analyze(self, user_input: str, previous_findings: str = "") -> str:
        """Sends the assembled prompt to the LLM and returns the response."""
        system_instruction = """
        STRICT DATA RULES:
        1. If the CURRENT SITUATION is gibberish, random characters, or empty, 
           REPLY ONLY WITH: "Incomprehensible input." 
        2. Do NOT establish "baseline" plans or zones (like 500m) if no specific 
           hazards are mentioned in the input.
        3. If the incident is clear but minor, provide initial safety advice only.
        """
        return self.llm.generate(self.build_prompt(user_input, previous_findings))
