-- Enable pgvector extension for RAG
CREATE EXTENSION IF NOT EXISTS vector;

-- Products catalog
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    volume VARCHAR(50) NOT NULL,
    pack_size INTEGER NOT NULL,
    price_per_pack INTEGER NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inventory
CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    stock_packs INTEGER NOT NULL DEFAULT 0,
    reserved_packs INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Customers
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    email VARCHAR(255),
    city VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    channel VARCHAR(50) NOT NULL, -- telegram, web, max, marketplace
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, paid, processing, delivering, completed, cancelled
    city VARCHAR(100),
    address TEXT,
    total_amount INTEGER NOT NULL,
    discount_amount INTEGER DEFAULT 0,
    final_amount INTEGER NOT NULL,
    payment_status VARCHAR(50) DEFAULT 'pending', -- pending, paid, failed
    payment_link TEXT,
    robokassa_order_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Order items
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    sku VARCHAR(20) NOT NULL,
    qty_packs INTEGER NOT NULL,
    price_per_pack INTEGER NOT NULL,
    subtotal INTEGER NOT NULL
);

-- Deliveries
CREATE TABLE deliveries (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    provider VARCHAR(50), -- yandex, dpd, etc
    tracking_number VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    delivery_cost INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge base for RAG (embeddings)
CREATE TABLE knowledge_base (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB,
    embedding vector(1536), -- OpenAI ada-002 dimension
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Chat sessions (interaction logs)
CREATE TABLE chat_sessions (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    channel VARCHAR(50) NOT NULL, -- telegram, web, max
    external_chat_id VARCHAR(100), -- telegram user_id, etc
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

-- Chat messages
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- user, assistant, tool, system
    content TEXT,
    tool_name VARCHAR(100), -- for tool calls
    tool_args JSONB, -- tool call arguments
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_inventory_product_id ON inventory(product_id);
CREATE INDEX idx_knowledge_base_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_chat_sessions_customer_id ON chat_sessions(customer_id);
CREATE INDEX idx_chat_sessions_channel ON chat_sessions(channel);
CREATE INDEX idx_chat_sessions_external_chat_id ON chat_sessions(external_chat_id);
CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id);
CREATE INDEX idx_chat_messages_created_at ON chat_messages(created_at);

-- Insert initial products
INSERT INTO products (sku, name, volume, pack_size, price_per_pack, description) VALUES
    ('0_5L', 'AQUADOKS 0.5л', '0.5 литра', 12, 1000, 'Упаковка 12 бутылок по 0.5 литра'),
    ('1L', 'AQUADOKS 1л', '1 литр', 9, 1250, 'Упаковка 9 бутылок по 1 литру'),
    ('5L', 'AQUADOKS 5л', '5 литров', 2, 800, 'Упаковка 2 бутылок по 5 литров'),
    ('19L', 'AQUADOKS 19л', '19 литров', 1, 1000, 'Упаковка 1 бутыль 19 литров');

-- Initialize inventory for all products
INSERT INTO inventory (product_id, stock_packs)
SELECT id, 100 FROM products;
