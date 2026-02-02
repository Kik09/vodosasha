import json
import logging
from pathlib import Path

import httpx

from src.config import settings
from src.bot.tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)

AGENT_PROMPT_PATH = Path(__file__).parent.parent.parent / "agent_prompt.md"
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
MAX_TOOL_ROUNDS = 5  # Prevent infinite loops


class YandexGPT:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None
        self._system_prompt: str = ""
        self._prompt_mtime: float = 0  # Last modification time
        # yandexgpt без /latest для поддержки function calling
        self.model_uri = f"gpt://{settings.yandex_folder_id}/yandexgpt"

    @property
    def system_prompt(self) -> str:
        """Get system prompt, reloading from file if it changed."""
        self._reload_prompt_if_changed()
        return self._system_prompt

    def _reload_prompt_if_changed(self):
        """Reload prompt from file if it was modified."""
        if not AGENT_PROMPT_PATH.exists():
            return

        current_mtime = AGENT_PROMPT_PATH.stat().st_mtime
        if current_mtime != self._prompt_mtime:
            self._system_prompt = AGENT_PROMPT_PATH.read_text(encoding="utf-8")
            self._prompt_mtime = current_mtime
            logger.info(f"Agent prompt reloaded ({len(self._system_prompt)} chars)")

    async def init(self):
        """Initialize Yandex GPT client and load system prompt."""
        # Load agent prompt
        if AGENT_PROMPT_PATH.exists():
            self._system_prompt = AGENT_PROMPT_PATH.read_text(encoding="utf-8")
            self._prompt_mtime = AGENT_PROMPT_PATH.stat().st_mtime
            logger.info(
                f"Agent prompt loaded from {AGENT_PROMPT_PATH} "
                f"({len(self._system_prompt)} chars)"
            )
        else:
            logger.warning(f"Agent prompt not found at {AGENT_PROMPT_PATH}")
            self._system_prompt = "Ты — AI-продавец бренда воды AQUADOKS."

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
        """Send message to Yandex GPT and get response with function calling."""
        if not self.client:
            raise RuntimeError("YandexGPT not initialized. Call init() first.")

        # Build messages in Yandex format
        messages = [{"role": "system", "text": self.system_prompt}]

        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "text": msg.get("content", ""),
                })

        messages.append({"role": "user", "text": user_message})

        # Process with potential tool calls
        for round_num in range(MAX_TOOL_ROUNDS):
            payload = {
                "modelUri": self.model_uri,
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": "1000",
                },
                "tools": TOOLS,
                "messages": messages,
            }

            try:
                # Debug: log tools count
                if round_num == 0:
                    logger.info(f"[API] Sending request with {len(TOOLS)} tools")

                response = await self.client.post(YANDEX_GPT_URL, json=payload)
                response.raise_for_status()
                data = response.json()

                alternative = data["result"]["alternatives"][0]
                message = alternative["message"]
                status = alternative.get("status", "")

                # Debug logging
                logger.info(f"[API] status={status}, has_toolCallList={'toolCallList' in message}")

                # Check if model wants to call tools
                if "toolCallList" in message:
                    tool_calls = message["toolCallList"].get("toolCalls", [])
                    if not tool_calls:
                        # No actual tool calls, return text if any
                        return message.get("text", "")

                    # Add assistant message with tool calls
                    messages.append({"role": "assistant", "toolCallList": message["toolCallList"]})

                    # Execute each tool and collect results
                    tool_results = []
                    for tc in tool_calls:
                        func_call = tc.get("functionCall", {})
                        func_name = func_call.get("name", "")
                        func_args = func_call.get("arguments", {})

                        # Execute tool
                        result = await execute_tool(func_name, func_args)
                        logger.info(f"[TOOL] {func_name} result: {result[:100]}...")

                        tool_results.append({
                            "functionResult": {
                                "name": func_name,
                                "content": result,
                            }
                        })

                    # Add tool results as user message
                    messages.append({"role": "user", "toolResultList": {"toolResults": tool_results}})

                    # Continue to next round
                    continue

                # No tool calls - return final response
                return message.get("text", "")

            except httpx.HTTPStatusError as e:
                logger.error(f"Yandex GPT HTTP error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Yandex GPT error: {e}")
                raise

        # Max rounds reached
        logger.warning("Max tool call rounds reached")
        return "Извините, не удалось обработать запрос. Попробуйте переформулировать."


yandex_gpt = YandexGPT()
