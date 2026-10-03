import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_FILE = os.path.join(os.path.dirname(__file__), 'app_data.db')

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            fullname TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'staff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT
        )
    ''')

    # Create products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            cost_price REAL NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            unit TEXT DEFAULT 'Cái',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')

    # Create customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE,
            email TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_code TEXT UNIQUE NOT NULL,
            customer_id INTEGER,
            user_id INTEGER,
            total_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Hoàn thành',
            payment_method TEXT DEFAULT 'Tiền mặt',
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Create order_items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            quantity INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')

    # Check if admin user exists, if not seed initial data
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count == 0:
        # Seed users
        admin_pass = generate_password_hash('admin123')
        staff_pass = generate_password_hash('staff123')
        cursor.execute("INSERT INTO users (username, password_hash, fullname, role) VALUES (?, ?, ?, ?)",
                       ('admin', admin_pass, 'Quản trị viên System', 'admin'))
        cursor.execute("INSERT INTO users (username, password_hash, fullname, role) VALUES (?, ?, ?, ?)",
                       ('nhanvien', staff_pass, 'Nguyễn Văn An', 'staff'))

        # Seed categories
        categories = [
            ('Điện thoại & Máy tính', 'Các thiết bị công nghệ, di động, laptop'),
            ('Phụ kiện công nghệ', 'Tai nghe, bàn phím, sạc dự phòng, chuột'),
            ('Thiết bị văn phòng', 'Máy in, màn hình, dụng cụ văn phòng'),
            ('Gia dụng thông minh', 'Đèn bàn, ổ cắm thông minh, máy hút bụi')
        ]
        cursor.executemany("INSERT INTO categories (name, description) VALUES (?, ?)", categories)

        # Seed products
        products = [
            (1, 'SP001', 'Laptop Dell XPS 15', 35990000, 31000000, 15, 'Máy', 'Laptop mỏng nhẹ hiệu năng cao'),
            (1, 'SP002', 'iPhone 15 Pro Max 256GB', 32490000, 28500000, 25, 'Chiếc', 'Điện thoại cao cấp Apple'),
            (1, 'SP003', 'Samsung Galaxy S24 Ultra', 29990000, 26000000, 18, 'Chiếc', 'Flagship AI của Samsung'),
            (2, 'SP004', 'Tai nghe Bluetooth Sony WH-1000XM5', 7990000, 6200000, 40, 'Cái', 'Tai nghe chống ồn đỉnh cao'),
            (2, 'SP005', 'Bàn phím cơ Keychron K2 Pro', 2390000, 1800000, 30, 'Cái', 'Bàn phím cơ không dây layout 75%'),
            (2, 'SP006', 'Chuột Logitech MX Master 3S', 2490000, 1950000, 22, 'Cái', 'Chuột làm việc cao cấp siêu nhạy'),
            (3, 'SP007', 'Màn hình LG UltraGear 27 inch 144Hz', 5690000, 4500000, 12, 'Cái', 'Màn hình đồ họa và chơi game'),
            (4, 'SP008', 'Robot hút bụi Xiaomi Vacuum X10', 8490000, 6800000, 8, 'Chiếc', 'Robot lau nhà thông minh tự động')
        ]
        cursor.executemany("INSERT INTO products (category_id, code, name, price, cost_price, stock_quantity, unit, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", products)

        # Seed customers
        customers = [
            ('Trần Thị Bích', '0912345678', 'bich.tran@example.com', '123 Nguyễn Trãi, Quận 5, TP.HCM'),
            ('Lê Hoàng Nam', '0987654321', 'nam.le@example.com', '456 Hoàng Hoa Thám, Ba Đình, Hà Nội'),
            ('Phạm Minh Đức', '0905112233', 'duc.pham@example.com', '789 Trần Phú, Hải Châu, Đà Nẵng'),
            ('Vũ Thị Mai', '0938445566', 'mai.vu@example.com', '101 Nguyễn Văn Linh, Cần Thơ')
        ]
        cursor.executemany("INSERT INTO customers (name, phone, email, address) VALUES (?, ?, ?, ?)", customers)

        # Seed sample orders
        orders = [
            ('HD20261001-001', 1, 1, 38480000, 'Hoàn thành', 'Chuyển khoản', 'Đã thanh toán đủ', '2026-10-01 10:15:00'),
            ('HD20261002-002', 2, 2, 32490000, 'Hoàn thành', 'Tiền mặt', 'Giao hàng tận nơi', '2026-10-02 14:30:00'),
            ('HD20261003-003', 3, 1, 10380000, 'Đang xử lý', 'Chuyển khoản', 'Khách hẹn lấy chiều nay', '2026-10-03 08:20:00')
        ]
        cursor.executemany("INSERT INTO orders (order_code, customer_id, user_id, total_amount, status, payment_method, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", orders)

        # Seed order items
        order_items = [
            (1, 1, 35990000, 1, 35990000), # Dell XPS
            (1, 6, 2490000, 1, 2490000),   # Logitech mouse
            (2, 2, 32490000, 1, 32490000), # iPhone 15
            (3, 4, 7990000, 1, 7990000),   # Sony WH-1000XM5
            (3, 5, 2390000, 1, 2390000)    # Keychron K2
        ]
        cursor.executemany("INSERT INTO order_items (order_id, product_id, price, quantity, subtotal) VALUES (?, ?, ?, ?, ?)", order_items)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully!")
