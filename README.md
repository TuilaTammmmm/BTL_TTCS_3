# 📘 TaskMaster - Hướng Dẫn Cài Đặt & Phát Triển Ứng Dụng Quản Lý Công Việc (Python Flask + SQLite)

**TaskMaster** là ứng dụng Quản Lý Công Việc & Dự Án (Task & Project Management Web Application) được phát triển cho **Bài Tập Lớn Thực Tập Cơ Sở 3 (BTL TTCS3)** bằng ngôn ngữ **Python**, framework **Flask**, cơ sở dữ liệu **SQLite**, bộ template **Jinja2** và giao diện **Bootstrap 5**.

---

## 🛠 Phần 1: Cài Đặt & Khởi Chạy Ứng Dụng

### 1. Cấu Trúc Thư Mục Dự Án
```text
BTL_TTCS_3/
├── app.py                  # Routing, Controller & Flask Server logic
├── database.py             # Khởi tạo SQLite DB Schema & Dữ liệu mẫu (Seed Data)
├── app_data.db             # File cơ sở dữ liệu SQLite
├── requirements.txt        # Thư viện yêu cầu (Flask, Werkzeug, Jinja2)
├── static/
│   └── css/
│       └── style.css       # Style tùy chỉnh (Kanban columns, priority badges, cards)
├── templates/
│   ├── base.html           # Khung chung (Sidebar, Navigation, Clock display)
│   ├── login.html          # Trang Đăng nhập hệ thống
│   ├── dashboard.html      # Trang Tổng quan KPI & Chart.js
│   ├── tasks.html          # Trang Danh sách Task (Tìm kiếm, Lọc, CRUD, Quick Status)
│   ├── kanban.html         # Bảng tương tác Kanban (To Do, In Progress, Completed)
│   ├── projects.html       # Trang Quản lý Dự án & Tiến độ Progress Bar
│   ├── task_detail.html    # Trang Chi tiết Task & Thảo luận (Comments thread)
│   └── members.html        # Trang Quản lý Thành viên Team
└── README.md               # Tài liệu hướng dẫn cài đặt & phát triển
```

### 2. Các Bước Khởi Chạy

1. **Tạo và kích hoạt môi trường ảo (Virtualenv)**:
   ```bash
   python -m venv venv
   # Trên Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   ```

2. **Cài đặt các thư viện phụ thuộc**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Khởi tạo Cơ sở dữ liệu SQLite và Dữ liệu mẫu**:
   ```bash
   python database.py
   ```

4. **Khởi chạy Server Flask**:
   ```bash
   python app.py
   ```
   Truy cập trình duyệt tại: **`http://127.0.0.1:5000`**

### 🔑 Tài Khoản Đăng Nhập Mẫu
| Vai trò | Username | Password | Quyền hạn |
|---|---|---|---|
| **Admin** | `admin` | `admin123` | Quản trị toàn bộ dự án |
| **Project Manager** | `pm_tuan` | `123456` | Quản lý công việc & phân công |
| **Developer** | `dev_nam` | `123456` | Nhận công việc & Cập nhật tiến độ |
| **Designer** | `designer_lan` | `123456` | Nhận công việc & Cập nhật tiến độ |

---

## 🚀 Phần 2: Hướng Dẫn Chi Tiết Phát Triển Ứng Dụng Quản Lý Công Việc Từ Đầu

Dưới đây là từng bước giúp bạn nắm vững tư duy và kiến thức để tự xây dựng một ứng dụng web Quản lý công việc hoàn chỉnh bằng Python Flask.

### Bước 1: Khởi Tạo Dự Án & Thiết Kế Cơ Sở Dữ Liệu (SQLite Schema)

Một ứng dụng quản lý công việc chuẩn cần có 4 bảng chính:
1. `users`: Lưu thông tin tài khoản (id, username, password_hash, fullname, role).
2. `projects`: Lưu danh sách dự án (id, name, description, color, status).
3. `tasks`: Lưu danh sách công việc (id, title, description, project_id, assignee_id, priority, status, due_date).
4. `comments`: Lưu bình luận / trao đổi trong từng task (id, task_id, user_id, content).

#### Ví dụ tạo bảng `tasks` trong Python (`database.py`):
```python
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        project_id INTEGER,
        assignee_id INTEGER,
        priority TEXT NOT NULL DEFAULT 'Trung bình',
        status TEXT NOT NULL DEFAULT 'To Do',
        due_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (project_id) REFERENCES projects (id),
        FOREIGN KEY (assignee_id) REFERENCES users (id)
    )
''')
```

### Bước 2: Thiết Lập Routing & Đăng Nhập (Authentication) trong `app.py`

Sử dụng `session` trong Flask để ghi nhớ người dùng đã đăng nhập và dùng decorator `@login_required` để bảo vệ các route.

```python
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
import functools

app = Flask(__name__)
app.secret_key = 'bi-mat-session-key'

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập trước!', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
```

### Bước 3: Phát Triển Giao Diện Bảng Kanban (`templates/kanban.html`)

Bảng Kanban phân chia công việc thành 3 cột chính:
- **Cần làm (To Do)**
- **Đang làm (In Progress)**
- **Hoàn thành (Completed)**

Truy vấn dữ liệu và phân loại danh sách task theo cột:
```python
@app.route('/kanban')
@login_required
def kanban():
    conn = get_db_connection()
    all_tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()

    todo_tasks = [t for t in all_tasks if t['status'] == 'To Do']
    in_progress_tasks = [t for t in all_tasks if t['status'] == 'In Progress']
    completed_tasks = [t for t in all_tasks if t['status'] == 'Completed']

    return render_template('kanban.html', todo=todo_tasks, in_progress=in_progress_tasks, completed=completed_tasks)
```

### Bước 4: Xử Lý Chuyển Trạng Thái Nhanh (Quick Status Update)

Cho phép người dùng bấm nút bấm chuyển task giữa các cột Kanban:

```python
@app.route('/tasks/quick_status/<int:id>', methods=['POST'])
@login_required
def task_quick_status(id):
    new_status = request.form.get('status')
    conn = get_db_connection()
    conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('kanban'))
```

### Bước 5: Viết Filter Custom Trong Jinja2 Để Kiểm Tra Task Quá Hạn

Tạo filter kiểm tra task quá hạn ngay trên giao diện:

```python
@app.template_filter('is_overdue')
def is_overdue_filter(due_date_str, status):
    if not due_date_str or status == 'Completed':
        return False
    due_date = datetime.strptime(str(due_date_str).split()[0], "%Y-%m-%d").date()
    return due_date < date.today()
```

Sử dụng trong template HTML:
```html
<span class="{% if task['due_date'] | is_overdue(task['status']) %}text-danger fw-bold{% endif %}">
    {{ task['due_date'] }}
</span>
```

---

## 🎯 Tổng Kết
Với kiến trúc trên, bạn đã có một **Ứng dụng Quản Lý Công Việc & Dự Án (TaskMaster)** chuẩn chỉnh, đầy đủ tính năng thực tế để báo cáo Bài Tập Lớn Thực Tập Cơ Sở 3 (BTL TTCS3).
