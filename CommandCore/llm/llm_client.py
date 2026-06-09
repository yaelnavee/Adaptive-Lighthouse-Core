# """
# LLM client — wraps Groq API (llama-3.3-70b-versatile).

# The groq package import is deferred inside __init__ so that tests that mock
# LLMClient can import this module without groq being installed.
# """

# import os
# from dotenv import load_dotenv

# load_dotenv()


# class LLMClient:
#     def __init__(self):
#         try:
#             from groq import Groq
#         except ImportError as exc:
#             raise ImportError("The 'groq' package is required.") from exc

#         api_key = os.getenv("GROQ_API_KEY")
#         if not api_key:
#             raise ValueError("GROQ_API_KEY not found in .env file.")

#         self.client = Groq(api_key=api_key)

#     def generate(self, prompt: str) -> str:
#         response = self.client.chat.completions.create(
#             model="llama-3.3-70b-versatile",
#             # model="llama-3.1-8b-instant", # Using a smaller model for faster responses during development; switch to 70b for production
#             messages=[{"role": "user", "content": prompt}],
#             temperature=0.2,  # Lowered to 0.2 for maximum precision and rule adherence
#             max_tokens=500,   # Increased for stable Hebrew responses
#         )
#         return response.choices[0].message.content.strip()




"""
LLM client — wraps Groq API.
Auto-retries on 429 rate-limit errors with exponential backoff.
"""

import os
import time
from dotenv import load_dotenv

load_dotenv()

MAX_RETRIES = 5
BASE_WAIT   = 35


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
        wait = BASE_WAIT
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=500,
                )
                return response.choices[0].message.content.strip()

            except Exception as exc:
                err = str(exc)
                if "429" in err or "rate_limit" in err.lower():
                    import re
                    m = re.search(r'try again in (\d+(?:\.\d+)?)s', err)
                    sleep_for = float(m.group(1)) + 2 if m else wait
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(sleep_for)
                        wait *= 2
                        continue
                raise