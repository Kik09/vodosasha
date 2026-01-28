import logging
from pathlib import Path

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

# Database schema for the agent
DB_SCHEMA = """
## Database Schema: AQUADOKS

### products
- id SERIAL PRIMARY KEY
- sku VARCHAR(20) UNIQUE NOT NULL -- '0_5L', '1L', '5L', '19L'
- name VARCHAR(255) NOT NULL
- volume VARCHAR(50) NOT NULL
- pack_size INTEGER NOT NULL
- price_per_pack INTEGER NOT NULL (в рублях)
- description TEXT
- created_at, updated_at TIMESTAMP

### inventory
- id SERIAL PRIMARY KEY
- product_id INTEGER REFERENCES products(id)
- stock_packs INTEGER NOT NULL DEFAULT 0
- reserved_packs INTEGER NOT NULL DEFAULT 0
- updated_at TIMESTAMP

### customers
- id SERIAL PRIMARY KEY
- name VARCHAR(255) NOT NULL
- phone VARCHAR(20) UNIQUE NOT NULL
- email VARCHAR(255)
- city VARCHAR(100)
- created_at TIMESTAMP

### orders
- id SERIAL PRIMARY KEY
- customer_id INTEGER REFERENCES customers(id)
- channel VARCHAR(50) NOT NULL -- 'telegram', 'web', 'max', 'marketplace'
- status VARCHAR(50) NOT NULL DEFAULT 'pending' -- 'pending', 'paid', 'processing', 'delivering', 'completed', 'cancelled'
- city VARCHAR(100)
- address TEXT
- total_amount INTEGER NOT NULL (в рублях)
- discount_amount INTEGER DEFAULT 0
- final_amount INTEGER NOT NULL
- payment_status VARCHAR(50) DEFAULT 'pending' -- 'pending', 'paid', 'failed'
- payment_link TEXT
- robokassa_order_id VARCHAR(100)
- created_at, updated_at TIMESTAMP

### order_items
- id SERIAL PRIMARY KEY
- order_id INTEGER REFERENCES orders(id)
- product_id INTEGER REFERENCES products(id)
- sku VARCHAR(20) NOT NULL
- qty_packs INTEGER NOT NULL
- price_per_pack INTEGER NOT NULL
- subtotal INTEGER NOT NULL

### deliveries
- id SERIAL PRIMARY KEY
- order_id INTEGER REFERENCES orders(id)
- provider VARCHAR(50) -- 'yandex', 'dpd', etc
- tracking_number VARCHAR(100)
- status VARCHAR(50) DEFAULT 'pending'
- delivery_cost INTEGER
- created_at, updated_at TIMESTAMP

### chat_sessions
- id SERIAL PRIMARY KEY
- customer_id INTEGER REFERENCES customers(id)
- channel VARCHAR(50) NOT NULL
- external_chat_id VARCHAR(100)
- started_at, ended_at TIMESTAMP

### chat_messages
- id SERIAL PRIMARY KEY
- session_id INTEGER REFERENCES chat_sessions(id)
- role VARCHAR(20) NOT NULL -- 'user', 'assistant', 'tool', 'system'
- content TEXT
- tool_name VARCHAR(100)
- tool_args JSONB
- created_at TIMESTAMP

### knowledge_base (RAG)
- id SERIAL PRIMARY KEY
- content TEXT NOT NULL
- metadata JSONB
- embedding vector(1536)
- created_at TIMESTAMP
"""

SYSTEM_PROMPT = f"""Ты — SQL-агент для базы данных AQUADOKS. Твоя задача — генерировать корректные PostgreSQL запросы на основе запросов пользователя.

{DB_SCHEMA}

## Правила:

1. Генерируй ТОЛЬКО валидный PostgreSQL SQL.
2. Отвечай ТОЛЬКО SQL-запросом, без объяснений и markdown-форматирования.
3. Если нужно несколько запросов, разделяй их точкой с запятой.
4. Для SELECT используй понятные alias'ы.
5. При UPDATE/DELETE всегда используй WHERE.
6. Не используй DROP TABLE, TRUNCATE, или другие опасные операции.
7. Цены хранятся в рублях (INTEGER).

## Примеры:

Пользователь: "покажи все товары"
SQL: SELECT sku, name, volume, pack_size, price_per_pack FROM products ORDER BY id;

Пользователь: "сколько заказов за сегодня"
SQL: SELECT COUNT(*) as orders_today FROM orders WHERE created_at::date = CURRENT_DATE;

Пользователь: "обнови цену 0.5л на 1100"
SQL: UPDATE products SET price_per_pack = 1100, updated_at = NOW() WHERE sku = '0_5L';

Пользователь: "топ 5 клиентов по сумме заказов"
SQL: SELECT c.name, c.phone, SUM(o.final_amount) as total_spent FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.status != 'cancelled' GROUP BY c.id ORDER BY total_spent DESC LIMIT 5;
"""


class SQLAgent:
    def __init__(self):
        self.client: httpx.AsyncClient | None = None
        self.model_uri = f"gpt://{settings.yandex_folder_id}/yandexgpt/latest"

    async def init(self):
        """Initialize Yandex GPT client."""
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Api-Key {settings.yandex_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        logger.info(f"SQL Agent initialized (model: {self.model_uri})")

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()

    async def generate_sql(self, user_request: str) -> str:
        """Generate SQL query from natural language request."""
        if not self.client:
            raise RuntimeError("SQLAgent not initialized. Call init() first.")

        messages = [
            {"role": "system", "text": SYSTEM_PROMPT},
            {"role": "user", "text": user_request},
        ]

        payload = {
            "modelUri": self.model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": 0.1,  # Low temperature for precise SQL
                "maxTokens": "500",
            },
            "messages": messages,
        }

        try:
            response = await self.client.post(YANDEX_GPT_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            sql = data["result"]["alternatives"][0]["message"]["text"]
            # Clean up the response
            sql = sql.strip()
            if sql.startswith("```"):
                sql = sql.split("\n", 1)[1] if "\n" in sql else sql[3:]
            if sql.endswith("```"):
                sql = sql[:-3]
            return sql.strip()
        except httpx.HTTPStatusError as e:
            logger.error(f"Yandex GPT HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Yandex GPT error: {e}")
            raise


sql_agent = SQLAgent()
