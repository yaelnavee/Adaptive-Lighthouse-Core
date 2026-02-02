from agents.base_agent import BaseAgent

class MedicalAgent(BaseAgent):
    def __init__(self, llm_client):
        super().__init__(
            name="Med_Bot",
            role="Medical Response Expert",
            persona="Calm, triage-focused, life-preservation driven",
            protocol_path="protocols/med_protocol.md",
            llm_client=llm_client
        )
