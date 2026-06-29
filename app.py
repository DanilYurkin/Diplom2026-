from flask import Flask, jsonify, render_template, request, session, send_from_directory, url_for, redirect
from contextlib import closing
import sqlite3
import uuid
import os
import json
import sqlite3
from contextlib import closing
import qrcode
from ozon_api import get_products_from_ozon
from database import save_products_from_ozon, init_db, save_qr_code, get_qr_code, get_btb_prices, update_btb_price, get_all_products, delete_btb_price

app = Flask(__name__,
    static_folder='static',
    static_url_path='/static')
app.secret_key = os.urandom(24)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# Инициализация БД с автоматической загрузкой товаров
def initialize_app():
    from database import init_db, save_products_from_ozon
    from ozon_api import get_products_from_ozon

    init_db()

    try:
        with closing(sqlite3.connect('Ozon_products.db', timeout=10)) as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            with conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM stocks")
                cur.execute("DELETE FROM images")
                cur.execute("DELETE FROM products")
    except sqlite3.OperationalError as e:
        print(f"❌ Ошибка при удалении: {e}")
        return

    products = get_products_from_ozon()
    if products:
        save_products_from_ozon(products)
        print(f"✅ Загружено {len(products)} товаров с Ozon")
    else:
        print("⚠ Не удалось загрузить товары с Ozon")

    with sqlite3.connect('Ozon_products.db') as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, offer_id FROM products")
        rows = cur.fetchall()
        print(f"📦 Всего в базе {len(rows)} товаров:")
        for r in rows[:5]:
            print(" -", r)

initialize_app()

@app.route('/update-products')
def update_products():
    products = get_products_from_ozon()
    if products:
        save_products_from_ozon(products)
        return jsonify({"status": "success", "message": f"Обновлено {len(products)} товаров"})
    return jsonify({"status": "error", "message": "Ошибка загрузки"})

init_db()

if not os.path.exists('static/qrcodes'):
    os.makedirs('static/qrcodes')

# Функции для работы с корзиной
def calculate_total(cart):
    total = 0
    for category in cart.values():
        for item in category.values():
            total += item['product_info']['price'] * item['quantity']
    return round(total, 2)

def calculate_total_quantity(cart):
    return sum(sum(item['quantity'] for item in category.values())
               for category in cart.values())

@app.context_processor
def utility_processor():
    return {
        'calculate_total': calculate_total,
        'calculate_total_quantity': calculate_total_quantity
    }

@app.before_request
def before_request():
    if 'cart' not in session:
        session['cart'] = {'btc': {}, 'btb': {}}

@app.route('/')
def home():
    return redirect(url_for('about_page'))

@app.route('/btc')
def btc_page():
    products = get_all_products()
    return render_template('product_list.html', title="Продажа BTC", category="btc", products=products)

@app.route('/btb')
def btb_page():
    products = get_all_products()
    for p in products:
        print(f'''
        DEBUG: 
        - Product ID: {p['product_id']}
        - BTB Price: {p.get('btb_price', 'N/A')}
        - Ozon Price: {p.get('ozon_price', 'N/A')}
        ''')
    print("[DEBUG] Данные товара:", products[0])
    return render_template('product_list.html', title="Продажа BTB", category="btb", products=products)

@app.route('/about')
def about_page():
    return render_template('about.html', title="О нас")

@app.route('/cart')
def view_cart():
    return render_template('cart.html', title="Корзина", cart=session.get('cart', {}))

@app.route('/api/products', methods=['GET'])
def get_products():
    products = get_all_products()
    return jsonify(products)

@app.route('/api/cart/add', methods=['POST'])
def add_to_cart():
    data = request.json
    product_id = data['product_id']
    quantity = int(data['quantity'])
    category = data['category']

    products = get_all_products()
    product = next((p for p in products if p['product_id'] == product_id), None)
    if not product:
        return jsonify({'status': 'error', 'message': 'Товар не найден'}), 404

    if category == 'btb' and product.get('btb_price') is not None:
        effective_price = product['btb_price']
    else:
        effective_price = product['ozon_price']

    product_for_cart = product.copy()
    product_for_cart['price'] = effective_price

    cart_key = str(product_id)
    if cart_key in session['cart'][category]:
        session['cart'][category][cart_key]['quantity'] += quantity
    else:
        session['cart'][category][cart_key] = {
            'quantity': quantity,
            'product_info': product_for_cart
        }

    session.modified = True
    return jsonify({
        'status': 'success',
        'cart_count': calculate_total_quantity(session['cart'])
    })

@app.route('/api/cart', methods=['GET'])
def get_cart():
    return jsonify(session.get('cart', {'btc': {}, 'btb': {}}))

@app.route('/api/cart/remove', methods=['POST'])
def remove_from_cart():
    data = request.json
    product_id = str(data['product_id'])
    category = data['category']

    if category in session['cart'] and product_id in session['cart'][category]:
        del session['cart'][category][product_id]
        session.modified = True

    return jsonify({'status': 'success', 'cart_count': calculate_total_quantity(session['cart'])})

@app.route('/api/cart/update', methods=['POST'])
def update_cart_item():
    data = request.json
    product_id = str(data['product_id'])
    quantity = int(data['quantity'])
    category = data['category']

    if quantity <= 0:
        return jsonify({'status': 'error', 'message': 'Количество должно быть больше 0'})

    if category in session['cart'] and product_id in session['cart'][category]:
        session['cart'][category][product_id]['quantity'] = quantity
        session.modified = True

    return jsonify({'status': 'success', 'cart_count': calculate_total_quantity(session['cart'])})

@app.route('/api/cart/clear', methods=['POST'])
def clear_cart():
    session['cart'] = {'btc': {}, 'btb': {}}
    session.modified = True
    return jsonify({'status': 'success'})

@app.route('/api/orders/create', methods=['POST'])
def create_order():
    try:
        order_data = request.json
        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO orders (order_data) VALUES (?)',
                         (json.dumps(order_data),))
            order_id = cursor.lastrowid
            conn.commit()

        return jsonify({
            'status': 'success',
            'order_id': order_id,
            'amount': order_data['total']
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/generate-qr/<int:order_id>')
def generate_qr(order_id):
    try:
        existing_path = get_qr_code(order_id)
        if existing_path and os.path.exists(existing_path):
            directory, filename = os.path.split(existing_path)
            return send_from_directory(directory, filename)

        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cur = conn.cursor()
            cur.execute('SELECT order_data FROM orders WHERE id = ?', (order_id,))
            row = cur.fetchone()

        if not row:
            return send_from_directory('static', 'no_qr.png')

        order_data = json.loads(row[0])
        amount = order_data.get('total')
        if amount is None:
            app.logger.error(f"Order {order_id} missing 'total' in order_data: {order_data}")
            return send_from_directory('static', 'no_qr.png')

        recipient_details = {
            "Name": "OMB",
            "PersonalAcc": "40817810427007193144",
            "BankName": "ТИНЬКОФФ БАНК",
            "BIC": "043304609",
            "CorrespAcc": "30101810500000000609",
            "PayeeINN": "7707083893",
            "Category": "Прочие",
            "Phone": "79005211388"
        }
        sum_kop = int(round(amount * 100))
        payment_data = [
            "ST00012",
            f"Name={recipient_details['Name']}",
            f"PersonalAcc={recipient_details['PersonalAcc']}",
            f"BankName={recipient_details['BankName']}",
            f"BIC={recipient_details['BIC']}",
            f"CorrespAcc={recipient_details['CorrespAcc']}",
            f"PayeeINN={recipient_details['PayeeINN']}",
            f"Category={recipient_details['Category']}",
            f"Sum={sum_kop}",
            f"Purpose=Оплата заказа {order_id}",
            f"Phone={recipient_details['Phone']}"
        ]
        payment_data_str = "|".join(payment_data)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(payment_data_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        os.makedirs('static/qrcodes', exist_ok=True)
        filename = f"qrcode_{order_id}.png"
        filepath = os.path.join('static/qrcodes', filename)
        img.save(filepath)

        save_qr_code(order_id, payment_data_str, filepath)

        return send_from_directory('static/qrcodes', filename)
    except Exception as e:
        app.logger.error(f"Error generating QR for order {order_id}: {e}")
        return send_from_directory('static', 'no_qr.png')

@app.route('/order/<int:order_id>')
def view_order(order_id):
    try:
        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT order_data, payment_status, created_at FROM orders WHERE id = ?',
                (order_id,)
            )
            row = cur.fetchone()

        if not row:
            return "Заказ не найден", 404

        order_data     = json.loads(row[0])
        payment_status = row[1]
        created_at     = row[2]
        qr_url         = url_for('generate_qr', order_id=order_id)

        return render_template(
            'order.html',
            order_id=order_id,
            order_data=order_data,
            payment_status=payment_status,
            created_at=created_at,
            qr_url=qr_url
        )
    except Exception as e:
        app.logger.error(f"Error viewing order {order_id}: {e}")
        return "Внутренняя ошибка сервера", 500

@app.route('/api/orders/status/<order_id>', methods=['GET'])
def check_order_status(order_id):
    try:
        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT payment_status FROM orders WHERE id = ?', (order_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({'status': 'error', 'message': 'Заказ не найден'}), 404

        return jsonify({
            'status': 'success',
            'payment_status': 'paid'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/product/<int:product_id>')
def product_page(product_id):
    products = get_all_products()
    product = next((p for p in products if p["product_id"] == product_id), None)
    if not product:
        return "Товар не найден", 404
    category = 'btc' if 'btc' in request.referrer else 'btb'
    return render_template('product.html', product=product, category=category)

@app.route('/account')
def account_page():
    if 'user_id' not in session:
        return render_template('account.html', logged_in=False)

    user_id = session['user_id']
    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT full_name, phone, address, username FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

    return render_template('account.html', logged_in=True, user=user)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = {
            'full_name': request.form['full_name'],
            'phone': request.form['phone'],
            'address': request.form['address'],
            'username': request.form['username'],
            'password': request.form['password']
        }

        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (full_name, phone, address, username, password)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                data['full_name'], data['phone'], data['address'],
                data['username'], data['password']
            ))
            conn.commit()

        return redirect(url_for('account_page'))

    return render_template('register.html')

@app.route('/register-admin', methods=['GET', 'POST'])
def register_admin():
    if not session.get('is_admin'):
        return redirect(url_for('account_page'))

    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        address = request.form['address']
        username = request.form['username']
        password = request.form['password']

        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (full_name, phone, address, username, password, is_admin)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (full_name, phone, address, username, password))
            conn.commit()

        return redirect(url_for('account_page'))

    return render_template('register_admin.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, is_admin FROM users WHERE username = ? AND password = ?
            ''', (username, password))
            user = cursor.fetchone()

        if user:
            session['user_id'] = user[0]
            session['username'] = username
            session['is_admin'] = bool(user[1])
            return redirect(url_for('account_page'))
        else:
            return render_template('login.html', error="Неверный логин или пароль", username=username)

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('account_page'))

@app.route('/api/btb_price/update', methods=['POST'])
def update_btb_price_route():
    if not session.get('is_admin'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    data = request.json
    product_id = data.get('product_id')
    price = data.get('price')

    try:
        update_btb_price(product_id, price)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ===== ИСПРАВЛЕННЫЙ МАРШРУТ ДЛЯ УДАЛЕНИЯ =====
@app.route('/api/btb_price/delete/<int:product_id>', methods=['DELETE'])
def delete_btb_price_route(product_id):
    """Удалить BTB-цену для товара (только для администратора)."""
    if not session.get('is_admin'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403

    try:
        delete_btb_price(product_id)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Старый маршрут с POST удалён – теперь используется версия с параметром и методом DELETE

@app.route('/edit-profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        full_name = request.form['full_name']
        phone = request.form['phone']
        address = request.form['address']

        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users
                SET full_name = ?, phone = ?, address = ?
                WHERE id = ?
            ''', (full_name, phone, address, user_id))
            conn.commit()

        return redirect(url_for('account_page'))

    with closing(sqlite3.connect('Ozon_products.db')) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT full_name, phone, address FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

    return render_template('edit_profile.html', user=user)

@app.route('/admin/products')
def admin_products():
    if not session.get('is_admin'):
        return redirect(url_for('account_page'))

    products = get_all_products()
    return render_template('product_list_ad.html', products=products)

@app.after_request
def fix_content_type_and_cache(response):
    if request.path.startswith('/static'):
        return response
    if response.content_type.startswith('text/html'):
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@app.route('/test-styles')
def test_styles():
    return send_from_directory(app.static_folder, 'styles.css', mimetype='text/css')

@app.route('/api/btb_price/bulk_update_all', methods=['POST'])
def bulk_update_all_btb_prices():
    if not session.get('is_admin'):
        return jsonify({'status': 'error', 'message': 'Access denied'}), 403
    data = request.json
    updates = data.get('updates', [])
    if not updates:
        return jsonify({'status': 'error', 'message': 'Нет данных для обновления'}), 400
    try:
        with closing(sqlite3.connect('Ozon_products.db')) as conn:
            cursor = conn.cursor()
            for item in updates:
                product_id = item['product_id']
                price = item['price']
                if price is not None and price > 0:
                    cursor.execute('''
                        INSERT OR REPLACE INTO BTB_price (product_id, admin_price)
                        VALUES (?, ?)
                    ''', (product_id, price))
            conn.commit()
        return jsonify({'status': 'success', 'message': f'Обновлено {len(updates)} товаров'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    return jsonify({'logged_in': 'user_id' in session})

@app.route('/personal-data')
def personal_data():
    """Страница с текстом Федерального закона № 152-ФЗ «О персональных данных»"""
    return render_template('personal_data.html')


if __name__ == '__main__':
    app.run(debug=True)
