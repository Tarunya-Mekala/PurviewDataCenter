from openai import OpenAI
from app.core.config import settings

client = OpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)

response = client.chat.completions.create(
    model=settings.LLM_MODEL,
    messages=[
        {
            "role": "user",
            "content": "Explain what a BOM is in a data center in 3 sentences."
        }
    ],
    temperature=0.0,
)

print(response.choices[0].message.content)