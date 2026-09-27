import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
model = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Hello"}]
    )
    print(f"SUCCESS with {model}")
except Exception as e:
    print(f"ERROR: {type(e).__name__} - {e}")
