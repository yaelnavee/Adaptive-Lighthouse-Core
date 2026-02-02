from abc import ABC

class BaseAgent(ABC):
    def __init__(self, name, role, persona, protocol_path, llm_client):
        self.name = name
        self.role = role
        self.persona = persona
        self.llm = llm_client
        # טעינת הפרוטוקול מקובץ חיצוני (הבסיס ל-RAG)
        self.protocol = self._load_protocol(protocol_path)

    def _load_protocol(self, path):
        import os
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return "Standard operational protocols apply."

    def build_prompt(self, user_input):
        return f"""
You are {self.name}.
Role: {self.role}

PERSONA:
{self.persona}

OPERATIONAL PROTOCOL (MANDATORY):
{self.protocol}

INSTRUCTIONS:
- Respond ONLY within your protocol.
- Do NOT invent actions outside your authority.
- Focus strictly on your domain.

SITUATION:
{user_input}

Provide a professional recommendation.
"""

    def analyze(self, user_input):
        return self.llm.generate(self.build_prompt(user_input))
