"""
orchestrator/commander.py
=========================
Backwards-compatibility shim.

CommanderAgent has been promoted to agents/commander_agent.py so it can be
imported alongside the other agents. This module re-exports it so any existing
code that imports from orchestrator.commander continues to work.
"""

from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS

__all__ = ["CommanderAgent", "CONSTITUTION", "VETO_TRIGGERS"]
