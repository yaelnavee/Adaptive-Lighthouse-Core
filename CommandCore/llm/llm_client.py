"""
LLM client — wraps Groq API (llama-3.3-70b-versatile).

The groq package import is deferred inside __init__ so that tests that mock
LLMClient can import this module without groq being installed.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        try:
            from groq import Groq
        except ImportError as exc:
            raise ImportError("The 'groq' package is required.") from exc

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found in .env file.")

        self.client = Groq(api_key=api_key)

    def generate(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,  # Lowered to 0.2 for maximum precision and rule adherence
            max_tokens=500,   # Increased for stable Hebrew responses
        )
        return response.choices[0].message.content.strip()