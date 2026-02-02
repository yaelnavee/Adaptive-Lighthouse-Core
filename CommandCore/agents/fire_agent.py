from agents.base_agent import BaseAgent

class FireAgent(BaseAgent):
    def __init__(self, llm_client):
        super().__init__(
            name="Fire_Bot",
            role="Firefighting Expert",
            persona="Decisive, safety-first, rapid risk assessment",
            # הפניה לקובץ החיצוני בתיקיית protocols
            protocol_path="protocols/fire_protocol.md",
            llm_client=llm_client
        )

