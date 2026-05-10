"""
orchestrator/commander.py
=========================
Backwards-compatibility shim.

CommanderAgent has been promoted to agents/commander_agent.py so it can be
imported alongside the other agents. This module re-exports it so any existing
code that imports from orchestrator.commander continues to work.
"""

from agents.commander_agent import CommanderAgent

class IncidentOrchestrator:
    def __init__(self, llm_client):
        self.commander = CommanderAgent(llm_client)

    def get_final_decision(self, situation, agent_outputs):
        """
        Receives the parallel outputs from all agents and sends them 
        to the Commander for final constitutional synthesis.
        """
        # Format agent outputs for the commander[cite: 3]
        formatted_responses = {res['name']: res['response'] for res in agent_outputs}
        
        # Call the correct method name from CommanderAgent
        result = self.commander.review_and_synthesize(formatted_responses)
        return result["final_plan"][cite: 5]
    
    