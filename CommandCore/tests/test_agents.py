import unittest
from unittest.mock import MagicMock, patch
import os
from agents.agent_factory import SpecialistFactory
from agents.base_agent import BaseAgent

class TestCommandCore(unittest.TestCase):

    def setUp(self):
        # אתחול מדומה של ה-LLM כדי לא לבצע קריאות API אמיתיות
        self.mock_llm = MagicMock()

    # 1. בדיקת ה-Factory (האם נוצר הסוכן הנכון?)
    def test_factory_creation(self):
        fire_agent = SpecialistFactory.create("fire", self.mock_llm)
        self.assertEqual(fire_agent.name, "Fire_Bot") #
        self.assertEqual(fire_agent.role, "Firefighting Expert") #
        
        with self.assertRaises(ValueError):
            SpecialistFactory.create("unknown_type", self.mock_llm) #

    # 2. בדיקת טעינת פרוטוקולים (RAG Resilience)
    def test_protocol_loading(self):
        # בדיקה שסוכן טוען את הקובץ הנכון
        fire_agent = SpecialistFactory.create("fire", self.mock_llm)
        # אם הקובץ קיים, הפרוטוקול לא צריך להיות הודעת ברירת המחדל
        self.assertNotEqual(fire_agent.protocol, "Standard operational protocols apply.") #

    # 3. בדיקת זיהוי שפה (Language Matching)
    def test_language_instruction_injection(self):
        agent = SpecialistFactory.create("medical", self.mock_llm)
        
        # בדיקה שהפרומפט מכיל את הוראת השפה הקריטית
        prompt = agent.build_prompt("עזרה דחופה")
        self.assertIn("LANGUAGE MATCHING (Critical)", prompt) #
        self.assertIn("If the user input is in HEBREW, your entire response MUST be in HEBREW", prompt) #

    # 4. בדיקת מגבלת מילים וקיצור (Brevity Constraint)
    def test_brevity_constraint(self):
        agent = SpecialistFactory.create("police", self.mock_llm)
        prompt = agent.build_prompt("Crowd control needed")
        
        # וידוא שהפרומפט כולל את הדרישה לקיצור
        self.assertIn("BE BREIF: 2-3 direct bullet points maximum", prompt) #
        self.assertIn("DO NOT repeat the situation description", prompt) #

    # 5. בדיקת ההקשר המשותף (The Round Table Feature)
    def test_shared_context_injection(self):
        agent = SpecialistFactory.create("medical", self.mock_llm)
        previous_info = "Fire_Bot established a 500m hot zone."
        
        prompt = agent.build_prompt("Injured person found", previous_findings=previous_info)
        
        # וידוא שהמידע מהסוכנים הקודמים מוזרק למקום הנכון
        self.assertIn("COORDINATION CONTEXT", prompt) #
        self.assertIn(previous_info, prompt) #

    # 6. בדיקת חולשה: טיפול בקלט ריק
    def test_empty_input_handling(self):
        agent = SpecialistFactory.create("fire", self.mock_llm)
        prompt = agent.build_prompt("")
        # המערכת צריכה עדיין לייצר פרומפט תקין גם אם הקלט ריק
        self.assertIn("SITUATION:", prompt) #

if __name__ == '__main__':
    unittest.main()