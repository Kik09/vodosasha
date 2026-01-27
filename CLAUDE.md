# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-агент продавец для бренда щелочной воды **AQUADOKS**. Агент работает через OpenAI-совместимый интерфейс (OpenAI, YandexGPT) и использует function calling для выполнения операций.

**Основной промпт агента**: см. `agent_prompt.md`

**Продукты**:
- 0.5л (12 шт) — 1000₽
- 1л (9 шт) — 1250₽
- 5л (2 шт) — 800₽
- 19л (1 шт) — 1000₽

Скидка 10% при заказе ≥5000₽.

## Development Commands

```bash
# Start PostgreSQL with pgvector
docker-compose up -d

# Stop database
docker-compose down

# View logs
docker-compose logs -f postgres

# Connect to database
psql postgresql://aquadoks_user:aquadoks_pass_change_in_prod@localhost:5432/aquadoks

# Install dependencies (when requirements.txt exists)
pip install -r requirements.txt

# Run tests
pytest
pytest tests/test_agent.py -v
```

## Architecture

### Database (PostgreSQL + pgvector)

**Core tables**:
- `products` — каталог товаров (SKU: 0_5L, 1L, 5L, 19L)
- `inventory` — складской учет (stock_packs, reserved_packs)
- `customers` — клиентская база (name, phone, city)
- `orders` — заказы с статусами (pending → paid → processing → delivering → completed)
- `order_items` — позиции заказа
- `deliveries` — информация о доставках
- `knowledge_base` — embeddings для RAG (vector dimension: 1536)

Схема инициализируется автоматически при первом запуске из `db/init/01_schema.sql`.

### AI Agent Tools

Агент использует OpenAI function calling. Требуемые tools:

**Catalog & Inventory**:
- `check_stock_price(sku, qty_packs)` — проверка цены и наличия
- `get_products()` — список всех товаров

**Order Management**:
- `create_order(items, customer_id, city, address, channel)` — создание заказа
- `calculate_discount(total_amount)` — расчет скидки (≥5000₽ → 10%)

**Payment**:
- `create_robokassa_link(order_id, amount)` — генерация ссылки на оплату (только СПб)

**Delivery**:
- `check_delivery_availability(city, address)` — проверка доставки (СПб или маркетплейс)
- `calculate_delivery_cost(city, address, items)` — расчет стоимости доставки

**Customer Data**:
- `create_or_get_customer(name, phone, city)` — создание/поиск клиента
- `yandexdoc_append_row(table_id, row)` — запись заявки в Yandex Documents

**Storage**:
- `read_yc_file(bucket, key)` — чтение файлов из Yandex Cloud Storage
- `list_yc_files(bucket, prefix)` — список файлов

**RAG/Knowledge Base**:
- `search_knowledge(query, top_k)` — semantic search по FAQ/документации

### Integrations

**Платежи**: Robokassa (только для заказов по СПб через сайт/Telegram/MAX)
**Доставка**: Яндекс.Доставка API (СПб), маркетплейсы (остальная РФ)
**Хранилище**: Yandex Cloud Storage (прайс-листы, изображения)
**Уведомления**: Telegram, Email, MAX

### Channels

- **Telegram bot** (aiogram) — основной канал
- **Web chatbot** — виджет на сайте
- **MAX** — мессенджер

### Geography Rules

**Санкт-Петербург**: прямая доставка через сайт/Telegram/MAX, оплата Robokassa
**Другие города РФ**: перенаправление на маркетплейсы (Ozon, Wildberries, Яндекс.Маркет)

## Key Files

- `agent_prompt.md` — полный промпт для AI-агента (тон, скрипт продаж, возражения)
- `docker-compose.yml` — PostgreSQL + pgvector
- `db/init/01_schema.sql` — схема БД
- `.env.example` — шаблон конфигурации
