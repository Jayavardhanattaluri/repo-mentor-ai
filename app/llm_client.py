from openai import OpenAI

from app.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL


class LLMClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=NVIDIA_API_KEY,
            base_url=NVIDIA_BASE_URL,
            timeout=120.0,
        )

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 3000) -> str:
        response = self.client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=120.0,
        )
        return response.choices[0].message.content