import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
print(f"Testing Groq API with key: {api_key[:10]}...")

try:
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Hello, just a test.",
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    print("Success! Response:")
    print(chat_completion.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
