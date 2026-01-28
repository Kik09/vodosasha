import asyncpg
from typing import Optional

from src.config import settings


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
        )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def get_customer_by_telegram_id(self, telegram_id: str) -> Optional[dict]:
        """Find customer by telegram external_chat_id from chat_sessions."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.* FROM customers c
                JOIN chat_sessions cs ON cs.customer_id = c.id
                WHERE cs.external_chat_id = $1 AND cs.channel = 'telegram'
                ORDER BY cs.started_at DESC
                LIMIT 1
                """,
                telegram_id,
            )
            return dict(row) if row else None

    async def get_customer_orders(
        self, telegram_id: str, limit: int = 5
    ) -> list[dict]:
        """Get recent orders for customer by telegram_id."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT o.id, o.status, o.final_amount, o.created_at,
                       o.payment_status, d.tracking_number, d.status as delivery_status
                FROM orders o
                LEFT JOIN deliveries d ON d.order_id = o.id
                JOIN chat_sessions cs ON cs.customer_id = o.customer_id
                WHERE cs.external_chat_id = $1 AND cs.channel = 'telegram'
                ORDER BY o.created_at DESC
                LIMIT $2
                """,
                telegram_id,
                limit,
            )
            return [dict(row) for row in rows]

    async def get_or_create_session(
        self, telegram_id: str, customer_id: Optional[int] = None
    ) -> int:
        """Get active session or create new one."""
        async with self.pool.acquire() as conn:
            # Check for active session (not ended)
            row = await conn.fetchrow(
                """
                SELECT id FROM chat_sessions
                WHERE external_chat_id = $1 AND channel = 'telegram' AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                telegram_id,
            )
            if row:
                return row["id"]

            # Create new session
            row = await conn.fetchrow(
                """
                INSERT INTO chat_sessions (customer_id, channel, external_chat_id)
                VALUES ($1, 'telegram', $2)
                RETURNING id
                """,
                customer_id,
                telegram_id,
            )
            return row["id"]

    async def log_message(
        self,
        session_id: int,
        role: str,
        content: str,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None,
    ):
        """Log a chat message."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, tool_name, tool_args)
                VALUES ($1, $2, $3, $4, $5)
                """,
                session_id,
                role,
                content,
                tool_name,
                tool_args,
            )

    async def get_session_messages(
        self, session_id: int, limit: int = 10
    ) -> list[dict]:
        """Get recent messages for session (for conversation context)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = $1 AND role IN ('user', 'assistant')
                ORDER BY created_at DESC
                LIMIT $2
                """,
                session_id,
                limit,
            )
            # Return in chronological order (oldest first)
            return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    async def execute_raw(self, sql: str):
        """Execute raw SQL query and return results.

        WARNING: Only use with trusted input (admin bot with authentication).
        """
        async with self.pool.acquire() as conn:
            # Determine query type
            sql_upper = sql.strip().upper()

            if sql_upper.startswith("SELECT") or sql_upper.startswith("WITH"):
                # SELECT query - return rows
                rows = await conn.fetch(sql)
                return rows
            else:
                # INSERT/UPDATE/DELETE - execute and return status
                result = await conn.execute(sql)
                return result


db = Database()
