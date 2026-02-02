"""Tools for YandexGPT function calling."""
import logging
from src.db.database import db

logger = logging.getLogger(__name__)

# Tool definitions for YandexGPT
TOOLS = [
    {
        "function": {
            "name": "get_products",
            "description": "Получить список всех товаров AQUADOKS с ценами и размерами упаковок",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
    },
    {
        "function": {
            "name": "check_stock",
            "description": "Проверить наличие товара на складе по SKU",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {
                        "type": "string",
                        "description": "SKU товара: 0_5L, 1L, 5L или 19L",
                    }
                },
                "required": ["sku"],
            },
        }
    },
    {
        "function": {
            "name": "calculate_order",
            "description": "Рассчитать стоимость заказа с учётом скидки 10% от 5000 руб",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Список позиций заказа",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string", "description": "SKU товара"},
                                "qty": {"type": "integer", "description": "Количество упаковок"},
                            },
                            "required": ["sku", "qty"],
                        },
                    }
                },
                "required": ["items"],
            },
        }
    },
    {
        "function": {
            "name": "create_order",
            "description": "Создать заказ для клиента из Санкт-Петербурга",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Имя клиента"},
                    "customer_phone": {"type": "string", "description": "Телефон клиента"},
                    "city": {"type": "string", "description": "Город (Санкт-Петербург)"},
                    "address": {"type": "string", "description": "Адрес доставки"},
                    "items": {
                        "type": "array",
                        "description": "Позиции заказа",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sku": {"type": "string"},
                                "qty": {"type": "integer"},
                            },
                            "required": ["sku", "qty"],
                        },
                    },
                },
                "required": ["customer_name", "customer_phone", "city", "address", "items"],
            },
        }
    },
]


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return result as string."""
    logger.info(f"[TOOL] {name} args={arguments}")

    try:
        if name == "get_products":
            return await tool_get_products()
        elif name == "check_stock":
            return await tool_check_stock(arguments.get("sku", ""))
        elif name == "calculate_order":
            return await tool_calculate_order(arguments.get("items", []))
        elif name == "create_order":
            return await tool_create_order(arguments)
        else:
            return f"Неизвестная функция: {name}"
    except Exception as e:
        logger.error(f"[TOOL] Error in {name}: {e}")
        return f"Ошибка: {e}"


async def tool_get_products() -> str:
    """Get all products with prices."""
    sql = """
        SELECT p.sku, p.name, p.volume, p.pack_size, p.price_per_pack,
               i.stock_packs - i.reserved_packs as available
        FROM products p
        JOIN inventory i ON p.id = i.product_id
        ORDER BY p.id
    """
    rows = await db.execute_raw(sql)

    if not rows:
        return "Товары не найдены в базе данных"

    lines = ["Товары AQUADOKS:"]
    for r in rows:
        lines.append(
            f"- {r['sku']}: {r['name']} ({r['volume']}, {r['pack_size']} шт в упаковке) — "
            f"{r['price_per_pack']} руб/упаковка, в наличии: {r['available']} упаковок"
        )
    return "\n".join(lines)


async def tool_check_stock(sku: str) -> str:
    """Check stock for specific SKU."""
    sql = """
        SELECT p.sku, p.name, p.price_per_pack,
               i.stock_packs, i.reserved_packs,
               i.stock_packs - i.reserved_packs as available
        FROM products p
        JOIN inventory i ON p.id = i.product_id
        WHERE p.sku = $1
    """
    rows = await db.execute_raw(sql, sku)

    if not rows:
        return f"Товар с SKU '{sku}' не найден. Доступные SKU: 0_5L, 1L, 5L, 19L"

    r = rows[0]
    return (
        f"Товар {r['sku']} ({r['name']}): цена {r['price_per_pack']} руб/упаковка, "
        f"в наличии {r['available']} упаковок"
    )


async def tool_calculate_order(items: list) -> str:
    """Calculate order total with discount."""
    if not items:
        return "Список товаров пуст"

    # Get prices from DB
    skus = [item.get("sku") for item in items]
    placeholders = ", ".join(f"${i+1}" for i in range(len(skus)))
    sql = f"SELECT sku, price_per_pack FROM products WHERE sku IN ({placeholders})"
    rows = await db.execute_raw(sql, *skus)

    prices = {r["sku"]: r["price_per_pack"] for r in rows}

    lines = ["Расчёт заказа:"]
    subtotal = 0

    for item in items:
        sku = item.get("sku")
        qty = item.get("qty", 0)
        price = prices.get(sku)

        if not price:
            lines.append(f"- {sku}: товар не найден")
            continue

        item_total = price * qty
        subtotal += item_total
        lines.append(f"- {sku} x {qty} упаковок = {item_total} руб")

    lines.append(f"\nСумма: {subtotal} руб")

    if subtotal >= 5000:
        discount = int(subtotal * 0.1)
        final = subtotal - discount
        lines.append(f"Скидка 10%: -{discount} руб")
        lines.append(f"Итого: {final} руб")
    else:
        diff = 5000 - subtotal
        lines.append(f"До скидки 10% не хватает {diff} руб")
        lines.append(f"Итого: {subtotal} руб")

    return "\n".join(lines)


async def tool_create_order(args: dict) -> str:
    """Create order in database."""
    name = args.get("customer_name")
    phone = args.get("customer_phone")
    city = args.get("city", "")
    address = args.get("address", "")
    items = args.get("items", [])

    if "петербург" not in city.lower() and "спб" not in city.lower():
        return "Заказы через бота доступны только для Санкт-Петербурга. Для других городов используйте маркетплейсы."

    if not items:
        return "Список товаров пуст"

    # Get or create customer
    customer_id = await db.get_or_create_customer(name, phone, city)

    # Calculate totals
    skus = [item.get("sku") for item in items]
    placeholders = ", ".join(f"${i+1}" for i in range(len(skus)))
    sql = f"""
        SELECT p.id, p.sku, p.price_per_pack, i.stock_packs - i.reserved_packs as available
        FROM products p
        JOIN inventory i ON p.id = i.product_id
        WHERE p.sku IN ({placeholders})
    """
    rows = await db.execute_raw(sql, *skus)
    products = {r["sku"]: r for r in rows}

    # Check availability
    order_items = []
    subtotal = 0

    for item in items:
        sku = item.get("sku")
        qty = item.get("qty", 0)
        prod = products.get(sku)

        if not prod:
            return f"Товар {sku} не найден"

        if prod["available"] < qty:
            return f"Недостаточно товара {sku}: доступно {prod['available']}, запрошено {qty}"

        item_total = prod["price_per_pack"] * qty
        subtotal += item_total
        order_items.append({
            "product_id": prod["id"],
            "sku": sku,
            "qty": qty,
            "price": prod["price_per_pack"],
            "subtotal": item_total,
        })

    discount = int(subtotal * 0.1) if subtotal >= 5000 else 0
    final_amount = subtotal - discount

    # Create order
    order_id = await db.create_order(
        customer_id=customer_id,
        channel="telegram",
        city=city,
        address=address,
        total_amount=subtotal,
        discount_amount=discount,
        final_amount=final_amount,
        items=order_items,
    )

    result = f"Заказ #{order_id} создан!\n"
    result += f"Сумма: {subtotal} руб"
    if discount:
        result += f", скидка: {discount} руб"
    result += f"\nИтого к оплате: {final_amount} руб\n"
    result += f"Адрес доставки: {address}, {city}\n"
    result += "Ссылка на оплату будет отправлена отдельно."

    return result
