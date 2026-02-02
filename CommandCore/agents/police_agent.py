from agents.base_agent import BaseAgent

class PoliceAgent(BaseAgent):
    def __init__(self, llm_client):
        super().__init__(
            name="Police_Bot",
            role="Law Enforcement Expert",
            persona="Methodical, evidence-oriented, crowd control focused",
            protocol_path="protocols/police_protocol..md",
            llm_client=llm_client
        )
