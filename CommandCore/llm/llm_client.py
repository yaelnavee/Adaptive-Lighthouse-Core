import os
from dotenv import load_dotenv
from groq import Groq

# טעינה מפורשת של הקובץ מהתיקייה הנוכחית
load_dotenv()

class LLMClient:
    def __init__(self):
        # משיכת המפתח עם ערך ברירת מחדל לבדיקה
        api_key = os.getenv("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in .env file. Please check the file location.")
            
        self.client = Groq(api_key=api_key)

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=300
        )
        return response.choices[0].message.content.strip()