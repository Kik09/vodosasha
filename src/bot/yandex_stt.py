import logging
import httpx

from src.config import settings

logger = logging.getLogger(__name__)

YANDEX_STT_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"


class YandexSTT:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None

    async def init(self):
        """Initialize HTTP client."""
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Api-Key {settings.yandex_api_key}",
            },
            timeout=30.0,
        )
        logger.info("Yandex STT initialized")

    async def close(self):
        """Close HTTP client."""
        if self.client:
            await self.client.aclose()

    async def recognize(self, audio_data: bytes) -> str:
        """Recognize speech from OGG audio."""
        if not self.client:
            raise RuntimeError("YandexSTT not initialized")

        params = {
            "folderId": settings.yandex_folder_id,
            "lang": "ru-RU",
            "format": "oggopus",
        }

        response = await self.client.post(
            YANDEX_STT_URL,
            params=params,
            content=audio_data,
            headers={"Content-Type": "application/octet-stream"},
        )
        response.raise_for_status()

        result = response.json()
        return result.get("result", "")


yandex_stt = YandexSTT()
