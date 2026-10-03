import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

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
            email TEXT,
            role TEXT NOT NULL DEFAULT 'member',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create projects table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#4f46e5',
            status TEXT NOT NULL DEFAULT 'Đang thực hiện',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create tasks table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            project_id INTEGER,
            assignee_id INTEGER,
            creator_id INTEGER,
            priority TEXT NOT NULL DEFAULT 'Trung bình',
            status TEXT NOT NULL DEFAULT 'To Do',
            due_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL,
            FOREIGN KEY (assignee_id) REFERENCES users (id) ON DELETE SET NULL,
            FOREIGN KEY (creator_id) REFERENCES users (id) ON DELETE SET NULL
        )
    ''')

    # Create comments table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Check if admin user exists, if not seed initial data
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count == 0:
        # Seed users
        admin_pass = generate_password_hash('admin123')
        user_pass = generate_password_hash('123456')

        cursor.execute("INSERT INTO users (username, password_hash, fullname, email, role) VALUES (?, ?, ?, ?, ?)",
                       ('admin', admin_pass, 'Quản trị viên System', 'admin@taskmaster.vn', 'admin'))
        cursor.execute("INSERT INTO users (username, password_hash, fullname, email, role) VALUES (?, ?, ?, ?, ?)",
                       ('pm_tuan', user_pass, 'Trần Anh Tuấn', 'tuan.ta@taskmaster.vn', 'manager'))
        cursor.execute("INSERT INTO users (username, password_hash, fullname, email, role) VALUES (?, ?, ?, ?, ?)",
                       ('dev_nam', user_pass, 'Lê Hoàng Nam', 'nam.lh@taskmaster.vn', 'member'))
        cursor.execute("INSERT INTO users (username, password_hash, fullname, email, role) VALUES (?, ?, ?, ?, ?)",
                       ('designer_lan', user_pass, 'Phạm Phương Lan', 'lan.pp@taskmaster.vn', 'member'))

        # Seed projects
        projects = [
            ('Xây dựng Website E-Commerce', 'Thiết kế & lập trình website bán hàng trực tuyến toàn diện', '#4f46e5', 'Đang thực hiện'),
            ('Phát triển Mobile App iOS/Android', 'Ứng dụng di động quản lý dịch vụ cho khách hàng VIP', '#0ea5e9', 'Đang thực hiện'),
            ('Nâng cấp Hạ tầng Cloud & CI/CD', 'Tối ưu hiệu năng server, tự động hóa quy trình triển khai', '#10b981', 'Đang thực hiện'),
            ('Chiến dịch Marketing Q4', 'Lập kế hoạch truyền thông và chạy quảng cáo các dòng sản phẩm mới', '#f59e0b', 'Hoàn thành')
        ]
        cursor.executemany("INSERT INTO projects (name, description, color, status) VALUES (?, ?, ?, ?)", projects)

        # Dates calculations
        today = datetime.now().date()
        date_past = (today - timedelta(days=2)).strftime('%Y-%m-%d')
        date_today = today.strftime('%Y-%m-%d')
        date_future1 = (today + timedelta(days=3)).strftime('%Y-%m-%d')
        date_future2 = (today + timedelta(days=7)).strftime('%Y-%m-%d')
        date_future3 = (today + timedelta(days=14)).strftime('%Y-%m-%d')

        # Seed tasks
        tasks = [
            ('Thiết kế UI/UX Giao diện Trang chủ', 'Thiết kế wireframe và mockup Figma cho Homepage & Product Detail', 1, 4, 2, 'Cao', 'Completed', date_past),
            ('Lập trình API Authentication & User', 'Viết API Login, Register, JWT Auth và phân quyền User/Admin', 1, 3, 2, 'Khẩn cấp', 'Completed', date_past),
            ('Tích hợp Cổng thanh toán VNPAY / Momo', 'Kết nối API thanh toán trực tuyến, xử lý webhook callback', 1, 3, 2, 'Khẩn cấp', 'In Progress', date_future1),
            ('Tối ưu SEO & Tốc độ tải trang', 'Tối ưu hình ảnh, nén CSS/JS, cài đặt Google Analytics & Tag Manager', 1, 4, 2, 'Trung bình', 'To Do', date_future2),
            ('Thiết kế Mockup App di động iOS', 'Vẽ UI màn hình Login, Dashboard và Cấu hình tài khoản', 2, 4, 2, 'Cao', 'In Progress', date_future1),
            ('Cấu hình Kubernetes Cluster trên AWS', 'Thiết lập EKS cluster, cấu hình ingress controller và SSL certificate', 3, 3, 1, 'Cao', 'To Do', date_future2),
            ('Viết tài liệu Hướng dẫn Sử dụng (User Guide)', 'Biên soạn file PDF & Markdown hướng dẫn các thao tác cơ bản', 1, 2, 1, 'Thấp', 'To Do', date_future3)
        ]
        cursor.executemany('''
            INSERT INTO tasks (title, description, project_id, assignee_id, creator_id, priority, status, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', tasks)

        # Seed comments
        comments = [
            (3, 3, 'Đã hoàn thành phần tạo URL thanh toán VNPAY sandbox, đang chờ duyệt IPN.'),
            (3, 2, 'Tuyệt vời, Nam kiểm tra kỹ trường hợp khách hàng hủy giao dịch nhé!'),
            (5, 4, 'Đã update file Figma phiên bản v2.0 cho màn hình Dashboard rồi nhé cả nhà.')
        ]
        cursor.executemany("INSERT INTO comments (task_id, user_id, content) VALUES (?, ?, ?)", comments)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Task Management Database initialized successfully!")
