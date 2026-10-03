from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import functools
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection, init_db
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super-secret-key-btl-ttcs3-tam'

# Ensure database exists on startup
if not os.path.exists(os.path.join(os.path.dirname(__file__), 'app_data.db')):
    init_db()

# Custom Jinja2 Filters
@app.template_filter('currency_vnd')
def currency_vnd_filter(amount):
    if amount is None:
        return "0 đ"
    return f"{amount:,.0f}".replace(",", ".") + " đ"

@app.template_filter('datetime_format')
def datetime_format_filter(value):
    if not value:
        return ""
    try:
        dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)

# Login decorator
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để truy cập trang này!', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Context processor for current user
@app.context_processor
def inject_user():
    return dict(
        current_user=session.get('fullname'),
        current_role=session.get('role'),
        current_username=session.get('username')
    )

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['fullname'] = user['fullname']
            session['role'] = user['role']
            flash(f'Xin chào {user["fullname"]}! Đăng nhập thành công.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Tên đăng nhập hoặc mật khẩu không chính xác!', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất thành công.', 'info')
    return redirect(url_for('login'))

# Dashboard
@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    
    # Stats metrics
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_revenue = conn.execute("SELECT SUM(total_amount) FROM orders WHERE status = 'Hoàn thành'").fetchone()[0] or 0
    low_stock_count = conn.execute("SELECT COUNT(*) FROM products WHERE stock_quantity <= 10").fetchone()[0]
    
    # Recent orders
    recent_orders = conn.execute('''
        SELECT o.*, c.name as customer_name, u.fullname as staff_name
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.id
        LEFT JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC LIMIT 5
    ''').fetchall()

    # Top selling products
    top_products = conn.execute('''
        SELECT p.name, SUM(oi.quantity) as total_qty, SUM(oi.subtotal) as total_val
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status = 'Hoàn thành'
        GROUP BY p.id
        ORDER BY total_qty DESC LIMIT 5
    ''').fetchall()

    conn.close()

    return render_template('dashboard.html',
                           total_products=total_products,
                           total_orders=total_orders,
                           total_revenue=total_revenue,
                           low_stock_count=low_stock_count,
                           recent_orders=recent_orders,
                           top_products=top_products)

# Products Routes
@app.route('/products')
@login_required
def products():
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category_id', '')

    conn = get_db_connection()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    query = '''
        SELECT p.*, c.name as category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE 1=1
    '''
    params = []

    if search:
        query += " AND (p.name LIKE ? OR p.code LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if category_id:
        query += " AND p.category_id = ?"
        params.append(category_id)

    query += " ORDER BY p.id DESC"
    products_list = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('products.html', products=products_list, categories=categories, search=search, category_id=category_id)

@app.route('/products/add', methods=['POST'])
@login_required
def product_add():
    code = request.form['code'].strip()
    name = request.form['name'].strip()
    category_id = request.form.get('category_id')
    price = float(request.form.get('price', 0))
    cost_price = float(request.form.get('cost_price', 0))
    stock_quantity = int(request.form.get('stock_quantity', 0))
    unit = request.form.get('unit', 'Cái').strip()
    description = request.form.get('description', '').strip()

    conn = get_db_connection()
    try:
        conn.execute('''
            INSERT INTO products (code, name, category_id, price, cost_price, stock_quantity, unit, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (code, name, category_id, price, cost_price, stock_quantity, unit, description))
        conn.commit()
        flash('Thêm sản phẩm mới thành công!', 'success')
    except sqlite3.IntegrityError:
        flash('Mã sản phẩm đã tồn tại! Vui lòng chọn mã khác.', 'danger')
    finally:
        conn.close()

    return redirect(url_for('products'))

@app.route('/products/edit/<int:id>', methods=['POST'])
@login_required
def product_edit(id):
    name = request.form['name'].strip()
    category_id = request.form.get('category_id')
    price = float(request.form.get('price', 0))
    cost_price = float(request.form.get('cost_price', 0))
    stock_quantity = int(request.form.get('stock_quantity', 0))
    unit = request.form.get('unit', 'Cái').strip()
    description = request.form.get('description', '').strip()

    conn = get_db_connection()
    conn.execute('''
        UPDATE products
        SET name = ?, category_id = ?, price = ?, cost_price = ?, stock_quantity = ?, unit = ?, description = ?
        WHERE id = ?
    ''', (name, category_id, price, cost_price, stock_quantity, unit, description, id))
    conn.commit()
    conn.close()

    flash('Cập nhật thông tin sản phẩm thành công!', 'success')
    return redirect(url_for('products'))

@app.route('/products/delete/<int:id>', methods=['POST'])
@login_required
def product_delete(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM products WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Đã xóa sản phẩm thành công.', 'info')
    return redirect(url_for('products'))

# Categories Routes
@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name'].strip()
        description = request.form.get('description', '').strip()

        if name:
            conn.execute("INSERT INTO categories (name, description) VALUES (?, ?)", (name, description))
            conn.commit()
            flash('Thêm danh mục mới thành công!', 'success')
            conn.close()
            return redirect(url_for('categories'))

    categories_list = conn.execute('''
        SELECT c.*, COUNT(p.id) as product_count
        FROM categories c
        LEFT JOIN products p ON c.id = p.category_id
        GROUP BY c.id
        ORDER BY c.name
    ''').fetchall()
    conn.close()

    return render_template('categories.html', categories=categories_list)

@app.route('/categories/delete/<int:id>', methods=['POST'])
@login_required
def category_delete(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM categories WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Đã xóa danh mục thành công.', 'info')
    return redirect(url_for('categories'))

# Customers Routes
@app.route('/customers', methods=['GET', 'POST'])
@login_required
def customers():
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form['name'].strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()

        if name:
            try:
                conn.execute("INSERT INTO customers (name, phone, email, address) VALUES (?, ?, ?, ?)",
                             (name, phone, email, address))
                conn.commit()
                flash('Thêm khách hàng mới thành công!', 'success')
            except sqlite3.IntegrityError:
                flash('Số điện thoại khách hàng đã tồn tại!', 'danger')
            conn.close()
            return redirect(url_for('customers'))

    customers_list = conn.execute('''
        SELECT c.*, COUNT(o.id) as total_orders, COALESCE(SUM(o.total_amount), 0) as total_spent
        FROM customers c
        LEFT JOIN orders o ON c.id = o.customer_id AND o.status = 'Hoàn thành'
        GROUP BY c.id
        ORDER BY c.id DESC
    ''').fetchall()
    conn.close()

    return render_template('customers.html', customers=customers_list)

# Orders Routes
@app.route('/orders')
@login_required
def orders():
    conn = get_db_connection()
    orders_list = conn.execute('''
        SELECT o.*, c.name as customer_name, c.phone as customer_phone, u.fullname as staff_name
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.id
        LEFT JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    ''').fetchall()
    conn.close()
    return render_template('orders.html', orders=orders_list)

@app.route('/orders/create', methods=['GET', 'POST'])
@login_required
def order_create():
    conn = get_db_connection()
    if request.method == 'POST':
        customer_id = request.form.get('customer_id')
        payment_method = request.form.get('payment_method', 'Tiền mặt')
        note = request.form.get('note', '')

        # Products arrays from form
        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('price[]')

        if not product_ids:
            flash('Vui lòng chọn ít nhất 1 sản phẩm cho đơn hàng!', 'danger')
            return redirect(url_for('order_create'))

        order_code = f"HD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        total_amount = 0

        # Calculate total
        for i in range(len(product_ids)):
            qty = int(quantities[i])
            price = float(prices[i])
            total_amount += qty * price

        # Insert order
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO orders (order_code, customer_id, user_id, total_amount, status, payment_method, note)
            VALUES (?, ?, ?, ?, 'Hoàn thành', ?, ?)
        ''', (order_code, customer_id if customer_id else None, session['user_id'], total_amount, payment_method, note))

        order_id = cursor.lastrowid

        # Insert order items and update stock
        for i in range(len(product_ids)):
            p_id = int(product_ids[i])
            qty = int(quantities[i])
            price = float(prices[i])
            subtotal = qty * price

            cursor.execute('''
                INSERT INTO order_items (order_id, product_id, price, quantity, subtotal)
                VALUES (?, ?, ?, ?, ?)
            ''', (order_id, p_id, price, qty, subtotal))

            # Deduct stock
            cursor.execute('''
                UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?
            ''', (qty, p_id))

        conn.commit()
        conn.close()
        flash(f'Tạo đơn hàng {order_code} thành công!', 'success')
        return redirect(url_for('order_detail', id=order_id))

    products_list = conn.execute("SELECT * FROM products WHERE stock_quantity > 0 ORDER BY name").fetchall()
    customers_list = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    conn.close()

    return render_template('order_create.html', products=products_list, customers=customers_list)

@app.route('/orders/<int:id>')
@login_required
def order_detail(id):
    conn = get_db_connection()
    order = conn.execute('''
        SELECT o.*, c.name as customer_name, c.phone as customer_phone, c.address as customer_address, u.fullname as staff_name
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.id
        LEFT JOIN users u ON o.user_id = u.id
        WHERE o.id = ?
    ''', (id,)).fetchone()

    if not order:
        conn.close()
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('orders'))

    items = conn.execute('''
        SELECT oi.*, p.name as product_name, p.code as product_code, p.unit
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (id,)).fetchall()
    conn.close()

    return render_template('order_detail.html', order=order, items=items)

@app.route('/orders/update_status/<int:id>', methods=['POST'])
@login_required
def order_update_status(id):
    new_status = request.form.get('status')
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    conn.close()
    flash(f'Đã cập nhật trạng thái đơn hàng thành: {new_status}', 'info')
    return redirect(url_for('order_detail', id=id))

# Reports & Analytics
@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()

    # Total stats
    revenue_data = conn.execute('''
        SELECT strftime('%m/%Y', created_at) as month, SUM(total_amount) as total
        FROM orders
        WHERE status = 'Hoàn thành'
        GROUP BY month
        ORDER BY created_at ASC
    ''').fetchall()

    category_data = conn.execute('''
        SELECT c.name, SUM(oi.subtotal) as total_sales
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN categories c ON p.category_id = c.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.status = 'Hoàn thành'
        GROUP BY c.id
    ''').fetchall()

    conn.close()
    return render_template('reports.html', revenue_data=revenue_data, category_data=category_data)

if __name__ == '__main__':
    print("Starting Sales & Inventory Management System (Flask)...")
    app.run(debug=True, port=5000)
