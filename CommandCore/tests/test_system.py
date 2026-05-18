"""
tests/test_system.py
====================
Integration tests for Milestone 3: The Constitution.
Testing Gibberish Rejection, Radius Conflicts, Language Consistency, and Context.
"""

import pytest
import re
from agents.commander_agent import CommanderAgent
from agents.base_agent import BaseAgent
from llm.llm_client import LLMClient

# Since BaseAgent is an ABC, we create a concrete dummy for testing
class SpecialistAgent(BaseAgent):
    def __init__(self, name, role, llm_client):
        super().__init__(
            name=name, 
            role=role, 
            persona="Professional expert", 
            protocol_path="protocols/fire_protocol.md", # Dummy path
            llm_client=llm_client
        )

@pytest.fixture
def system_setup():
    """Initializes the LLM client and the Commander."""
    client = LLMClient()
    commander = CommanderAgent(client)
    return client, commander

# ---------------------------------------------------------------------------
# TEST 1: Gibberish & Trash Input Rejection
# ---------------------------------------------------------------------------
def test_gibberish_rejection(system_setup):
    """
    Checks if random characters trigger the mandatory error message 
    without any tactical hallucinations.
    """
    client, commander = system_setup
    
    # Simulating specialist responses to gibberish input (e.g., "סבז בסזס")
    reports = {
        "Fire_Bot": "Incomprehensible input.",
        "Med_Bot": "Incomprehensible input.",
        "Police_Bot": "Incomprehensible input."
    }
    
    result = commander.review_and_synthesize(reports)
    
    # Assert that the mandatory error string is returned
    expected_error = "The event description is unclear. Please provide a clearer description of the incident."
    assert result["final_plan"] == expected_error
    assert result["reviews"]["Fire_Bot"]["vetoed"] in [True, False]

# ---------------------------------------------------------------------------
# TEST 2: Radius Conflict & Fire_Bot Authority
# ---------------------------------------------------------------------------
def test_radius_conflict_resolution(system_setup):
    """
    Checks if the Commander VETOs specialists who exceed the Fire_Bot's expert radius.
    """
    client, commander = system_setup
    
    reports = {
        "Fire_Bot": "מקור האש זוהה. קובע אזור חם ברדיוס 50 מטר.",
        "Med_Bot": "מקים אזור טיפול במרחק בטוח של 500 מטר מהאש.", # Potential Hallucination
        "Police_Bot": "חוסם צירים ברדיוס 100 מטר."
    }
    
    result = commander.review_and_synthesize(reports)
    
    # Commander should VETO Med_Bot for the disproportional 500m radius
    assert result["reviews"]["Med_Bot"]["vetoed"] is True
    assert "500" not in result["final_plan"]
    # Final plan should align with Fire_Bot's 50m
    assert "50" in result["final_plan"]

# ---------------------------------------------------------------------------
# TEST 3: Language Consistency (Hebrew Input)
# ---------------------------------------------------------------------------
def test_language_consistency_hebrew(system_setup):
    """
    Ensures that when input is in Hebrew, the final plan is entirely in Hebrew.
    """
    client, commander = system_setup
    
    reports = {
        "Fire_Bot": "פח בוער ברחוב הרצל. כיבוי ראשוני בוצע.",
        "Med_Bot": "אין נפגעים במקום.",
        "Police_Bot": "התנועה זורמת כסדרה."
    }
    
    result = commander.review_and_synthesize(reports)
    
    # Checking for Hebrew characters in the final plan
    hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
    assert bool(hebrew_pattern.search(result["final_plan"]))
    # Ensure no English "hallucinations" in the synthesized text
    assert "Final Plan" not in result["final_plan"]

# ---------------------------------------------------------------------------
# TEST 4: State Persistence (Contextual Update)
# ---------------------------------------------------------------------------
def test_context_persistence(system_setup):
    """
    Simulates a 2-step incident to see if context is preserved.
    """
    client, _ = system_setup
    fire_agent = SpecialistAgent("Fire_Bot", "Fire Specialist", client)
    
    # Step 1: Initial situation
    situation_1 = "פח בוער ברחוב הרצל."
    finding_1 = fire_agent.analyze(situation_1)
    
    # Step 2: Escalation - fire spread to a car
    situation_2 = "האש התפשטה לרכב חונה סמוך."
    # We pass finding_1 as previous context
    finding_2 = fire_agent.analyze(situation_2, previous_findings=finding_1)
    
    # Assert that Fire_Bot acknowledges the previous trash fire context
    assert "רכב" in finding_2 and "אזור" in finding_2
    # assert "רכב" in finding_2

# ---------------------------------------------------------------------------
# TEST 5: Minor Incident Proportionality
# ---------------------------------------------------------------------------
def test_minor_incident_proportionality(system_setup):
    """
    Verify that small incidents do not trigger MCI declarations.
    """
    client, commander = system_setup
    
    reports = {
        "Fire_Bot": "פח אשפה קטן בוער. שליטה מלאה.",
        "Med_Bot": "מכריז על אירוע רב נפגעים MCI.", # Disproportional!
        "Police_Bot": "פינוי של כל השכונה." # Disproportional!
    }
    
    result = commander.review_and_synthesize(reports)
    
    # Commander must VETO the disproportional responses
    assert result["reviews"]["Med_Bot"]["vetoed"] is True
    assert result["reviews"]["Police_Bot"]["vetoed"] is True
    assert "MCI" not in result["final_plan"]

 # ---------------------------------------------------------------------------
# TEST 6: Complex Hazmat Scenario (Constitutional Enforcement)
# ---------------------------------------------------------------------------
def test_hazmat_incident_coordination(system_setup):
    """
    Checks if the Commander enforces Rule 5 (Fire_Bot clearance) during 
    a toxic leak, even when Med_Bot attempts an immediate rescue.
    """
    client, commander = system_setup
    
    reports = {
        "Fire_Bot": "דליפת כלור במפעל. האזור מוגדר כ-Hot Zone. נדרש טיהור לפני כניסה.",
        "Med_Bot": "מזהה 2 פצועים בתוך המבנה. נכנסים לפינוי מיידי.", # Violation of Rule 5
        "Police_Bot": "סגירת כבישים ברדיוס 200 מטר מהמפעל."
    }
    
    result = commander.review_and_synthesize(reports)
    
    # Commander must VETO Med_Bot for unauthorized entry into a Hot Zone
    assert result["reviews"]["Med_Bot"]["vetoed"] is True
    reason_lower = result["reviews"]["Med_Bot"]["reason"].lower()
    assert any(kw in reason_lower for kw in ["rule 5", "clearance", "hot zone", "decontamination", "טיהור"])
    
    # Final plan must prioritize Fire_Bot's "Safe-to-Enter" signal
    assert any(kw in result["final_plan"] for kw in ["אישור", "Safe-to-Enter", "לפני כניסה"])