from agents.fire_agent import FireAgent
from agents.police_agent import PoliceAgent
from agents.medical_agent import MedicalAgent

class SpecialistFactory:
    @staticmethod
    def create(agent_type, llm_client):
        agent_type = agent_type.lower()

        if agent_type == "fire":
            return FireAgent(llm_client)
        elif agent_type == "police":
            return PoliceAgent(llm_client)
        elif agent_type == "medical":
            return MedicalAgent(llm_client)
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")
