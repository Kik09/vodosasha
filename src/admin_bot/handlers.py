import logging
from pathlib import Path

from aiogram import Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

from src.config import settings
from src.db.database import db
from src.admin_bot.sql_agent import sql_agent

logger = logging.getLogger(__name__)
router = Router()

AGENT_PROMPT_PATH = Path(__file__).parent.parent.parent / "agent_prompt.md"

# In-memory storage for authenticated users
authenticated_users: set[int] = set()

# Main keyboard
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📦 Заказы"), KeyboardButton(text="📊 Склад")],
        [KeyboardButton(text="👥 Клиенты"), KeyboardButton(text="📋 Схема БД")],
    ],
    resize_keyboard=True,
)


def is_authenticated(user_id: int) -> bool:
    """Check if user is authenticated."""
    return user_id in authenticated_users


async def execute_and_format(sql: str, message: Message) -> None:
    """Execute SQL and send formatted result."""
    try:
        result = await db.execute_raw(sql)
        if not result:
            await message.answer("Нет данных.")
            return

        lines = []
        if hasattr(result[0], 'keys'):
            cols = list(result[0].keys())
            lines.append(" | ".join(cols))
            lines.append("-" * len(lines[0]))

        for row in result[:50]:
            vals = [str(v) if v is not None else "-" for v in (row.values() if hasattr(row, 'values') else row)]
            lines.append(" | ".join(vals))

        if len(result) > 50:
            lines.append(f"\n... ещё {len(result) - 50}")

        output = "\n".join(lines)
        if len(output) > 4000:
            output = output[:4000] + "\n... (обрезано)"

        await message.answer(f"```\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@router.message(Command("start"))
async def handle_start(message: Message):
    """Handle /start command."""
    user_id = message.from_user.id

    if is_authenticated(user_id):
        await message.answer(
            "AQUADOKS Admin Bot\n\n"
            "Используйте кнопки или отправьте запрос на естественном языке.\n\n"
            "Команды:\n"
            "/orders - заказы\n"
            "/stock - склад\n"
            "/clients - клиенты\n"
            "/schema - схема БД\n"
            "/prompt - промпт sales-бота\n"
            "/setprompt - обновить промпт\n"
            "/logout - выйти",
            reply_markup=main_keyboard,
        )
    else:
        await message.answer("Введите пароль для доступа:")


@router.message(Command("logout"))
async def handle_logout(message: Message):
    """Handle /logout command."""
    user_id = message.from_user.id
    if user_id in authenticated_users:
        authenticated_users.discard(user_id)
        await message.answer("Вы вышли из системы.")
    else:
        await message.answer("Вы не авторизованы.")


@router.message(Command("schema"))
async def handle_schema(message: Message):
    """Show database schema."""
    user_id = message.from_user.id

    if not is_authenticated(user_id):
        await message.answer("Введите пароль для доступа:")
        return

    schema_text = """
**products**: sku, name, volume, pack_size, price_per_pack
**inventory**: product_id, stock_packs, reserved_packs
**customers**: name, phone, email, city
**orders**: customer_id, channel, status, city, address, total_amount, discount_amount, final_amount, payment_status
**order_items**: order_id, product_id, sku, qty_packs, price_per_pack, subtotal
**deliveries**: order_id, provider, tracking_number, status, delivery_cost
**chat_sessions**: customer_id, channel, external_chat_id
**chat_messages**: session_id, role, content, tool_name, tool_args
**knowledge_base**: content, metadata, embedding
"""
    await message.answer(schema_text, parse_mode="Markdown")


@router.message(Command("prompt"))
async def handle_prompt(message: Message):
    """Show current agent prompt."""
    user_id = message.from_user.id

    if not is_authenticated(user_id):
        await message.answer("Введите пароль для доступа:")
        return

    if AGENT_PROMPT_PATH.exists():
        prompt_text = AGENT_PROMPT_PATH.read_text(encoding="utf-8")
        # Telegram message limit is 4096 chars
        if len(prompt_text) > 4000:
            # Send in chunks
            await message.answer(f"Промпт ({len(prompt_text)} символов):\n\n")
            for i in range(0, len(prompt_text), 4000):
                chunk = prompt_text[i:i+4000]
                await message.answer(chunk)
        else:
            await message.answer(f"Текущий промпт:\n\n{prompt_text}")
    else:
        await message.answer("Файл agent_prompt.md не найден.")


@router.message(Command("setprompt"))
async def handle_setprompt(message: Message):
    """Set new agent prompt - show instructions."""
    user_id = message.from_user.id

    if not is_authenticated(user_id):
        await message.answer("Введите пароль для доступа:")
        return

    await message.answer(
        "Чтобы обновить промпт, отправьте текстовый файл (.txt или .md).\n\n"
        "Файл заменит текущий agent_prompt.md."
    )


@router.message(Command("orders"))
async def handle_orders(message: Message):
    """Show recent orders."""
    if not is_authenticated(message.from_user.id):
        await message.answer("Введите пароль для доступа:")
        return

    sql = """
        SELECT o.id, c.name, o.status, o.final_amount, o.created_at::date
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.id
        ORDER BY o.created_at DESC
        LIMIT 20
    """
    await execute_and_format(sql, message)


@router.message(Command("stock"))
async def handle_stock(message: Message):
    """Show inventory status."""
    if not is_authenticated(message.from_user.id):
        await message.answer("Введите пароль для доступа:")
        return

    sql = """
        SELECT p.sku, p.name, p.price_per_pack, i.stock_packs, i.reserved_packs,
               (i.stock_packs - i.reserved_packs) as available
        FROM products p
        JOIN inventory i ON p.id = i.product_id
        ORDER BY p.id
    """
    await execute_and_format(sql, message)


@router.message(Command("clients"))
async def handle_clients(message: Message):
    """Show customers."""
    if not is_authenticated(message.from_user.id):
        await message.answer("Введите пароль для доступа:")
        return

    sql = """
        SELECT c.id, c.name, c.phone, c.city, COUNT(o.id) as orders_count
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        LIMIT 30
    """
    await execute_and_format(sql, message)


@router.message(lambda m: m.document is not None)
async def handle_document(message: Message):
    """Handle file upload for prompt update."""
    user_id = message.from_user.id

    if not is_authenticated(user_id):
        await message.answer("Введите пароль для доступа:")
        return

    doc = message.document
    if not doc.file_name.endswith(('.txt', '.md')):
        await message.answer("Поддерживаются только .txt и .md файлы.")
        return

    try:
        file = await message.bot.get_file(doc.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        new_prompt = file_bytes.read().decode('utf-8')

        AGENT_PROMPT_PATH.write_text(new_prompt, encoding="utf-8")
        logger.info(f"Agent prompt updated by user {user_id} via file ({len(new_prompt)} chars)")
        await message.answer(
            f"Промпт обновлён ({len(new_prompt)} символов).\n"
            "Sales-бот подхватит изменения автоматически."
        )
    except Exception as e:
        logger.error(f"Error updating prompt from file: {e}")
        await message.answer(f"Ошибка: {e}")


@router.message()
async def handle_message(message: Message):
    """Handle all messages."""
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""

    if not text:
        return

    # Check authentication
    if not is_authenticated(user_id):
        # Try to authenticate with password
        if text == settings.admin_bot_password:
            authenticated_users.add(user_id)
            logger.info(f"User {user_id} authenticated successfully")
            await message.answer(
                "Доступ разрешён.\n\n"
                "Используйте кнопки или отправьте запрос на естественном языке.",
                reply_markup=main_keyboard,
            )
        else:
            logger.warning(f"Failed auth attempt from user {user_id}")
            await message.answer("Неверный пароль.")
        return

    # Handle keyboard buttons
    if text == "📦 Заказы":
        return await handle_orders(message)
    elif text == "📊 Склад":
        return await handle_stock(message)
    elif text == "👥 Клиенты":
        return await handle_clients(message)
    elif text == "📋 Схема БД":
        return await handle_schema(message)

    # User is authenticated - process SQL request
    try:
        # Generate SQL from natural language
        await message.answer("Генерирую SQL...")
        sql_query = await sql_agent.generate_sql(text)

        # Show generated SQL
        await message.answer(f"```sql\n{sql_query}\n```", parse_mode="Markdown")

        # Execute SQL
        await message.answer("Выполняю...")
        result = await db.execute_raw(sql_query)

        # Format result
        if result is None:
            await message.answer("Запрос выполнен успешно (нет данных для отображения).")
        elif isinstance(result, list):
            if len(result) == 0:
                await message.answer("Пустой результат (0 строк).")
            else:
                # Format as table
                output_lines = []

                # Get column names from first row
                if result and hasattr(result[0], 'keys'):
                    columns = list(result[0].keys())
                    output_lines.append(" | ".join(columns))
                    output_lines.append("-" * len(output_lines[0]))

                for row in result[:50]:  # Limit to 50 rows
                    if hasattr(row, 'values'):
                        values = [str(v) if v is not None else "NULL" for v in row.values()]
                    else:
                        values = [str(v) if v is not None else "NULL" for v in row]
                    output_lines.append(" | ".join(values))

                if len(result) > 50:
                    output_lines.append(f"\n... и ещё {len(result) - 50} строк")

                output = "\n".join(output_lines)

                # Truncate if too long
                if len(output) > 4000:
                    output = output[:4000] + "\n\n... (обрезано)"

                await message.answer(f"```\n{output}\n```", parse_mode="Markdown")
        else:
            await message.answer(f"Результат: {result}")

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        await message.answer(f"Ошибка: {e}")
