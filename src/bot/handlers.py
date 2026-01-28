import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.db.database import db
from src.bot.yandex_gpt import yandex_gpt

router = Router()
logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "pending": "Ожидает оплаты",
    "paid": "Оплачен",
    "processing": "В обработке",
    "delivering": "Доставляется",
    "completed": "Завершён",
    "cancelled": "Отменён",
}

PAYMENT_LABELS = {
    "pending": "Не оплачен",
    "paid": "Оплачен",
    "failed": "Ошибка оплаты",
}


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command."""
    telegram_id = str(message.from_user.id)
    username = message.from_user.username or "N/A"

    logger.info(f"[CMD] /start tg_id={telegram_id} username=@{username}")

    session_id = await db.get_or_create_session(telegram_id)
    await db.log_message(session_id, "user", "/start")

    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n"
        "Я — бот-помощник <b>AQUADOKS</b>, щелочной воды для здоровья и энергии.\n\n"
        "Чем могу помочь?\n"
        "• Расскажу о продукции и ценах\n"
        "• Помогу оформить заказ\n"
        "• Отвечу на вопросы о доставке\n\n"
        "Просто напишите, что вас интересует!"
    )

    await db.log_message(session_id, "assistant", "Приветствие отправлено")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    telegram_id = str(message.from_user.id)
    logger.info(f"[CMD] /help tg_id={telegram_id}")

    session_id = await db.get_or_create_session(telegram_id)
    await db.log_message(session_id, "user", "/help")

    await message.answer(
        "<b>Доступные команды:</b>\n\n"
        "/start — начать диалог\n"
        "/help — показать эту справку\n"
        "/status — статус ваших заказов\n\n"
        "<b>Наша продукция:</b>\n"
        "• 0.5л (12 шт) — 1 000 ₽\n"
        "• 1л (9 шт) — 1 250 ₽\n"
        "• 5л (2 шт) — 800 ₽\n"
        "• 19л (1 шт) — 1 000 ₽\n\n"
        "Скидка 10% при заказе от 5 000 ₽!\n\n"
        "<b>Доставка:</b>\n"
        "• Санкт-Петербург — доставка курьером\n"
        "• Другие города — через маркетплейсы (Ozon, Wildberries, Яндекс.Маркет)"
    )

    await db.log_message(session_id, "assistant", "Справка отправлена")


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Handle /status command - show recent orders."""
    telegram_id = str(message.from_user.id)
    logger.info(f"[CMD] /status tg_id={telegram_id}")

    session_id = await db.get_or_create_session(telegram_id)
    await db.log_message(session_id, "user", "/status")

    orders = await db.get_customer_orders(telegram_id, limit=5)

    if not orders:
        await message.answer(
            "У вас пока нет заказов.\n\n"
            "Напишите мне, чтобы оформить первый заказ!"
        )
        await db.log_message(session_id, "assistant", "Заказов нет")
        return

    lines = ["<b>Ваши последние заказы:</b>\n"]

    for order in orders:
        order_id = order["id"]
        status = STATUS_LABELS.get(order["status"], order["status"])
        amount = order["final_amount"]
        created = order["created_at"].strftime("%d.%m.%Y %H:%M")
        payment = PAYMENT_LABELS.get(order["payment_status"], order["payment_status"])

        line = f"\n<b>Заказ #{order_id}</b> от {created}\n"
        line += f"Сумма: {amount:,} ₽\n".replace(",", " ")
        line += f"Статус: {status}\n"
        line += f"Оплата: {payment}"

        if order.get("tracking_number"):
            line += f"\nТрек: <code>{order['tracking_number']}</code>"

        if order.get("delivery_status"):
            delivery = STATUS_LABELS.get(
                order["delivery_status"], order["delivery_status"]
            )
            line += f"\nДоставка: {delivery}"

        lines.append(line)

    await message.answer("\n".join(lines))
    await db.log_message(session_id, "assistant", f"Показано {len(orders)} заказов")


@router.message()
async def handle_message(message: Message):
    """Handle all other messages - send to Yandex GPT."""
    telegram_id = str(message.from_user.id)
    user_text = message.text or ""

    # Get customer info for logging
    customer = await db.get_customer_by_telegram_id(telegram_id)
    phone = customer.get("phone", "N/A") if customer else "N/A"

    # Log incoming message to stdout
    logger.info(
        f"[MSG] tg_id={telegram_id} phone={phone} | {user_text}"
    )

    session_id = await db.get_or_create_session(telegram_id)
    await db.log_message(session_id, "user", user_text)

    # Get conversation history for context
    history = await db.get_session_messages(session_id, limit=10)

    try:
        # Send to Yandex GPT
        response = await yandex_gpt.chat(user_text, history)

        # Log response to stdout
        logger.info(
            f"[GPT] tg_id={telegram_id} | {response[:100]}..."
            if len(response) > 100
            else f"[GPT] tg_id={telegram_id} | {response}"
        )

        await message.answer(response)
        await db.log_message(session_id, "assistant", response)

    except Exception as e:
        logger.error(f"[ERR] tg_id={telegram_id} | Yandex GPT error: {e}")
        await message.answer(
            "Извините, произошла техническая ошибка. Попробуйте позже или напишите /help"
        )
        await db.log_message(session_id, "assistant", f"Error: {e}")
