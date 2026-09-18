import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_PROVIDER = "groq"
FALLBACK_PROVIDER = "gemini"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

GEMINI_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "openai/gpt-oss-20b"

TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 2048
TIMEOUT_SECONDS = 8
