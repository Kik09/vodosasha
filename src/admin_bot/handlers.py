import logging
from pathlib import Path

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from src.config import settings
from src.db.database import db
from src.admin_bot.sql_agent import sql_agent

logger = logging.getLogger(__name__)
router = Router()

AGENT_PROMPT_PATH = Path(__file__).parent.parent.parent / "agent_prompt.md"

# In-memory storage for authenticated users
authenticated_users: set[int] = set()

# Users waiting to input new prompt
awaiting_prompt: set[int] = set()


def is_authenticated(user_id: int) -> bool:
    """Check if user is authenticated."""
    return user_id in authenticated_users


@router.message(Command("start"))
async def handle_start(message: Message):
    """Handle /start command."""
    user_id = message.from_user.id

    if is_authenticated(user_id):
        await message.answer(
            "AQUADOKS Admin Bot\n\n"
            "Отправь запрос на естественном языке, я сгенерирую и выполню SQL.\n\n"
            "Примеры:\n"
            "- покажи все товары\n"
            "- сколько заказов за сегодня\n"
            "- топ 5 клиентов по сумме\n"
            "- обнови остаток 0.5л на 50 упаковок\n\n"
            "Команды:\n"
            "/schema - показать схему БД\n"
            "/prompt - показать системный промпт sales-бота\n"
            "/setprompt - обновить системный промпт\n"
            "/logout - выйти"
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
    """Set new agent prompt."""
    user_id = message.from_user.id

    if not is_authenticated(user_id):
        await message.answer("Введите пароль для доступа:")
        return

    # Check if prompt text is provided with command
    command_text = message.text or ""
    parts = command_text.split(maxsplit=1)

    if len(parts) > 1:
        # Prompt text provided inline
        new_prompt = parts[1]
        AGENT_PROMPT_PATH.write_text(new_prompt, encoding="utf-8")
        logger.info(f"Agent prompt updated by user {user_id} ({len(new_prompt)} chars)")
        await message.answer(
            f"Промпт обновлён ({len(new_prompt)} символов).\n"
            "Sales-бот подхватит изменения автоматически."
        )
    else:
        # Enter prompt editing mode
        awaiting_prompt.add(user_id)
        await message.answer(
            "Отправьте новый текст промпта следующим сообщением.\n"
            "Отправьте /cancel для отмены."
        )


@router.message(Command("cancel"))
async def handle_cancel(message: Message):
    """Cancel current operation."""
    user_id = message.from_user.id
    if user_id in awaiting_prompt:
        awaiting_prompt.discard(user_id)
        await message.answer("Операция отменена.")
    else:
        await message.answer("Нет активной операции.")


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
                "Отправь запрос на естественном языке, я сгенерирую и выполню SQL.\n\n"
                "Примеры:\n"
                "- покажи все товары\n"
                "- сколько заказов за сегодня\n"
                "- топ 5 клиентов по сумме"
            )
        else:
            logger.warning(f"Failed auth attempt from user {user_id}")
            await message.answer("Неверный пароль.")
        return

    # Check if user is in prompt editing mode
    if user_id in awaiting_prompt:
        awaiting_prompt.discard(user_id)
        new_prompt = message.text  # Use raw text, not stripped
        AGENT_PROMPT_PATH.write_text(new_prompt, encoding="utf-8")
        logger.info(f"Agent prompt updated by user {user_id} ({len(new_prompt)} chars)")
        await message.answer(
            f"Промпт обновлён ({len(new_prompt)} символов).\n"
            "Sales-бот подхватит изменения автоматически."
        )
        return

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
