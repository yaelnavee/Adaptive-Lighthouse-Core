# from abc import ABC

# class BaseAgent(ABC):
#     def __init__(self, name, role, persona, protocol_path, llm_client):
#         self.name = name
#         self.role = role
#         self.persona = persona
#         self.llm = llm_client
#         # טעינת הפרוטוקול מקובץ חיצוני (הבסיס ל-RAG)
#         self.protocol = self._load_protocol(protocol_path)

#     def _load_protocol(self, path):
#         import os
#         if os.path.exists(path):
#             with open(path, 'r', encoding='utf-8') as f:
#                 return f.read()
#         return "Standard operational protocols apply."

#     def build_prompt(self, user_input):
#         return f"""
# You are {self.name}.
# Role: {self.role}

# PERSONA:
# {self.persona}

# OPERATIONAL PROTOCOL (MANDATORY):
# {self.protocol}

# INSTRUCTIONS:
# - Respond ONLY within your protocol.
# - Do NOT invent actions outside your authority.
# - Focus strictly on your domain.

# SITUATION:
# {user_input}

# Provide a professional recommendation.
# """

#     def analyze(self, user_input):
#         return self.llm.generate(self.build_prompt(user_input))


from abc import ABC
import os

class BaseAgent(ABC):
    def __init__(self, name, role, persona, protocol_path, llm_client):
        self.name = name
        self.role = role
        self.persona = persona
        self.llm = llm_client
        self.protocol = self._load_protocol(protocol_path)

    def _load_protocol(self, path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return "Standard operational protocols apply."

    def build_prompt(self, user_input, previous_findings=""):
        return f"""
You are {self.name}, an emergency specialist. 

ROLE: {self.role}
PROTOCOL: {self.protocol}

COORDINATION CONTEXT (Mandatory constraint):
{previous_findings if previous_findings else "You are the FIRST responder. Set the baseline."}

INSTRUCTIONS for Collaborative Response:
1. DO NOT repeat the situation description.
2. DO NOT use generic phrases like "I will coordinate with...".
3. ACTIVE REACTION: Look at what the previous agents decided. If Fire set a 500m zone, YOU must use that 500m zone in your plan.
4. BUILD UPON: Use the previous findings as facts. Your job is to fill the gaps left by others within your domain.
5. BE BREIF: 2-3 direct bullet points maximum.
6. LANGUAGE MATCHING (Critical): Detect the language of the SITUATION. 
       - If the user input is in HEBREW, your entire response MUST be in HEBREW.
       - If the user input is in ENGLISH, your entire response MUST be in ENGLISH.
       - Use professional terminology appropriate for the chosen language.

SITUATION:
{user_input}

ACTIONABLE COLLABORATION PLAN:
"""

    def analyze(self, user_input, previous_findings=""):
        # עדכון הפונקציה לקבלת ההקשר המשותף
        return self.llm.generate(self.build_prompt(user_input, previous_findings))