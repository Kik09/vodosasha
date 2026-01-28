import logging
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

AGENT_PROMPT_PATH = Path(__file__).parent.parent.parent / "agent_prompt.md"
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexGPT:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None
        self.system_prompt: str = ""
        self.model_uri = f"gpt://{settings.yandex_folder_id}/yandexgpt/latest"

    async def init(self):
        """Initialize Yandex GPT client and load system prompt."""
        # Load agent prompt
        if AGENT_PROMPT_PATH.exists():
            self.system_prompt = AGENT_PROMPT_PATH.read_text(encoding="utf-8")
            logger.info(
                f"Agent prompt loaded from {AGENT_PROMPT_PATH} "
                f"({len(self.system_prompt)} chars)"
            )
        else:
            logger.warning(f"Agent prompt not found at {AGENT_PROMPT_PATH}")
            self.system_prompt = "Ты — AI-продавец бренда воды AQUADOKS."

        # Initialize httpx client
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Api-Key {settings.yandex_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        logger.info(f"Yandex GPT client initialized (model: {self.model_uri})")

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()

    async def chat(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Send message to Yandex GPT and get response."""
        if not self.client:
            raise RuntimeError("YandexGPT not initialized. Call init() first.")

        # Build messages in Yandex format (uses "text" instead of "content")
        messages = [{"role": "system", "text": self.system_prompt}]

        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "text": msg.get("content", ""),
                })

        messages.append({"role": "user", "text": user_message})

        payload = {
            "modelUri": self.model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": 0.7,
                "maxTokens": "1000",
            },
            "messages": messages,
        }

        try:
            response = await self.client.post(YANDEX_GPT_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["result"]["alternatives"][0]["message"]["text"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Yandex GPT HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Yandex GPT error: {e}")
            raise


yandex_gpt = YandexGPT()
