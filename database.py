import sqlite3
import json
from contextlib import closing

def init_db():
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        cursor = conn.cursor()

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            product_id INTEGER UNIQUE,
            offer_id TEXT,
            name TEXT,
            price REAL,
            old_price REAL,
            btb_price REAL,
            currency_code TEXT,
            is_archived BOOLEAN,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        cursor.execute("PRAGMA table_info(products)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'btb_price' not in columns:
            cursor.execute("ALTER TABLE products ADD COLUMN btb_price REAL")

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS BTB_price (
            id INTEGER PRIMARY KEY,
            product_id INTEGER UNIQUE,
            admin_price REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            source TEXT,
            present INTEGER,
            reserved INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            order_data TEXT,
            payment_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS qr_codes (
            id INTEGER PRIMARY KEY,
            order_id INTEGER UNIQUE,
            qr_data TEXT NOT NULL,
            image_path TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            phone INTEGER,
            address TEXT,
            username TEXT UNIQUE,
            password TEXT,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO users (full_name, phone, address, username, password, is_admin)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', ('Администратор', '+79991234567', 'г. Москва, ул. Примерная, д. 1', 'admin', 'admin123', 1))
            print("✅ Создан администратор по умолчанию: логин admin, пароль admin123")

        conn.commit()
        print("✅ База данных инициализирована")

def save_qr_code(order_id, qr_data, image_path):
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO qr_codes (order_id, qr_data, image_path) VALUES (?, ?, ?)',
                       (order_id, qr_data, image_path))
        conn.commit()

def get_qr_code(order_id):
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT image_path FROM qr_codes WHERE order_id = ?', (order_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def get_all_products():
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT
            p.id,
            p.product_id,
            p.offer_id,
            p.name,
            p.price,
            p.old_price,
            COALESCE(b.admin_price, p.btb_price) AS btb_price,
            p.currency_code,
            p.is_archived,
            GROUP_CONCAT(i.image_url, ', ' ORDER BY i.id) AS images,
            GROUP_CONCAT(s.source || ': ' || s.present || '/' || s.reserved, ', ') AS stocks
        FROM products p
        LEFT JOIN BTB_price b ON p.product_id = b.product_id
        LEFT JOIN images i ON p.product_id = i.product_id
        LEFT JOIN stocks s ON p.product_id = s.product_id
        GROUP BY p.product_id
        ORDER BY p.offer_id COLLATE NOCASE
        ''')
        rows = cursor.fetchall()
        result = []
        for row in rows:
            stocks_raw = row[10].split(', ') if row[10] else []
            unique_stocks = []
            seen_sources = set()
            for stock in stocks_raw:
                if not stock: continue
                source = stock.split(':')[0]
                if source not in seen_sources:
                    seen_sources.add(source)
                    unique_stocks.append(stock)

            images_raw = row[9].split(', ') if row[9] else []
            seen_images = set()
            images = []
            for img in images_raw:
                if img and img not in seen_images:
                    seen_images.add(img)
                    images.append(img)

            result.append({
                "id": row[0],
                "product_id": row[1],
                "offer_id": row[2],
                "name": row[3],
                "ozon_price": row[4],
                "old_price": row[5],
                "btb_price": row[6],
                "price": row[6] if row[6] is not None else row[4],
                "currency_code": row[7],
                "is_archived": row[8],
                "images": images,
                "stocks": unique_stocks
            })
        return result

def save_products_from_ozon(products):
    if not products:
        print("⚠ Нет данных для сохранения")
        return False
    try:
        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            for product in products:
                cursor.execute('''
                INSERT OR REPLACE INTO products
                    (product_id, offer_id, name, price, old_price, btb_price, currency_code, is_archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (product['id'], product['offer_id'], product['name'],
                      product['price'], product['old_price'], None,
                      product['currency_code'], product['is_archived']))
                cursor.execute('DELETE FROM stocks WHERE product_id = ?', (product['id'],))
                cursor.execute('DELETE FROM images WHERE product_id = ?', (product['id'],))

                for stock in product.get('stocks', []):
                    cursor.execute('INSERT INTO stocks (product_id, source, present, reserved) VALUES (?, ?, ?, ?)',
                                   (product['id'], stock['source'], stock['present'], stock['reserved']))

                for image_url in product.get('images', []):
                    if image_url:
                        cursor.execute('INSERT INTO images (product_id, image_url) VALUES (?, ?)',
                                       (product['id'], image_url))

            conn.commit()
            print(f"✅ Успешно сохранено {len(products)} товаров")
            return True
    except Exception as e:
        print(f"❌ Ошибка при сохранении: {e}")
        return False

def get_btb_prices():
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT product_id, admin_price FROM BTB_price')
        return {row[0]: row[1] for row in cursor.fetchall()}

def update_btb_price(product_id, price):
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM products WHERE product_id = ?", (product_id,))
        if not cursor.fetchone():
            raise ValueError(f"Товар с ID {product_id} не существует")
        cursor.execute('INSERT OR REPLACE INTO BTB_price (product_id, admin_price) VALUES (?, ?)',
                       (product_id, price))
        conn.commit()

def delete_btb_price(product_id):
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM BTB_price WHERE product_id = ?', (product_id,))
        conn.commit()

def save_order(order_data):
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO orders (order_data) VALUES (?)', (json.dumps(order_data),))
        conn.commit()
