import os
import sys
from groq import Groq
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
print(f"Testing Groq API with key: {api_key[:10]}... and model: {model}")

try:
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Hello, just a test.",
            }
        ],
        model=model,
    )
    print("Success! Response:")
    print(chat_completion.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
