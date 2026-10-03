from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
import functools
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db_connection, init_db
import os
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'taskmaster-super-secret-key-btl-ttcs3'

# Ensure database exists on startup
if not os.path.exists(os.path.join(os.path.dirname(__file__), 'app_data.db')):
    init_db()

# Custom Jinja Filters
@app.template_filter('date_format')
def date_format_filter(value):
    if not value:
        return "-"
    try:
        if isinstance(value, str):
            dt = datetime.strptime(value.split()[0], "%Y-%m-%d")
        else:
            dt = value
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(value)

@app.template_filter('is_overdue')
def is_overdue_filter(due_date_str, status):
    if not due_date_str or status == 'Completed':
        return False
    try:
        due_date = datetime.strptime(str(due_date_str).split()[0], "%Y-%m-%d").date()
        return due_date < date.today()
    except Exception:
        return False

# Login decorator
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để sử dụng ứng dụng!', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Context processor for current user
@app.context_processor
def inject_user():
    return dict(
        current_user=session.get('fullname'),
        current_role=session.get('role'),
        current_username=session.get('username'),
        current_user_id=session.get('user_id')
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
    today_str = date.today().strftime('%Y-%m-%d')
    
    # Task Statistics
    total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    completed_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Completed'").fetchone()[0]
    in_progress_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'In Progress'").fetchone()[0]
    todo_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'To Do'").fetchone()[0]
    
    overdue_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE status != 'Completed' AND due_date < ?", (today_str,)).fetchone()[0]
    urgent_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE priority = 'Khẩn cấp' AND status != 'Completed'").fetchone()[0]

    completion_rate = round((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0

    # Recent Tasks
    recent_tasks = conn.execute('''
        SELECT t.*, p.name as project_name, p.color as project_color, u.fullname as assignee_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u ON t.assignee_id = u.id
        ORDER BY t.created_at DESC LIMIT 6
    ''').fetchall()

    # Active Projects Progress
    projects = conn.execute('''
        SELECT p.*,
               COUNT(t.id) as total_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) as done_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        GROUP BY p.id
        ORDER BY p.id DESC
    ''').fetchall()

    conn.close()

    return render_template('dashboard.html',
                           total_tasks=total_tasks,
                           completed_tasks=completed_tasks,
                           in_progress_tasks=in_progress_tasks,
                           todo_tasks=todo_tasks,
                           overdue_tasks=overdue_tasks,
                           urgent_tasks=urgent_tasks,
                           completion_rate=completion_rate,
                           recent_tasks=recent_tasks,
                           projects=projects)

# Projects Routes
@app.route('/projects')
@login_required
def projects():
    conn = get_db_connection()
    projects_list = conn.execute('''
        SELECT p.*,
               COUNT(t.id) as total_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) as done_tasks,
               SUM(CASE WHEN t.status = 'In Progress' THEN 1 ELSE 0 END) as in_progress_tasks,
               SUM(CASE WHEN t.status = 'To Do' THEN 1 ELSE 0 END) as todo_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        GROUP BY p.id
        ORDER BY p.id DESC
    ''').fetchall()
    conn.close()
    return render_template('projects.html', projects=projects_list)

@app.route('/projects/add', methods=['POST'])
@login_required
def project_add():
    name = request.form['name'].strip()
    description = request.form.get('description', '').strip()
    color = request.form.get('color', '#4f46e5')
    status = request.form.get('status', 'Đang thực hiện')

    if name:
        conn = get_db_connection()
        conn.execute("INSERT INTO projects (name, description, color, status) VALUES (?, ?, ?, ?)",
                     (name, description, color, status))
        conn.commit()
        conn.close()
        flash('Thêm dự án mới thành công!', 'success')

    return redirect(url_for('projects'))

@app.route('/projects/edit/<int:id>', methods=['POST'])
@login_required
def project_edit(id):
    name = request.form['name'].strip()
    description = request.form.get('description', '').strip()
    color = request.form.get('color', '#4f46e5')
    status = request.form.get('status', 'Đang thực hiện')

    conn = get_db_connection()
    conn.execute("UPDATE projects SET name = ?, description = ?, color = ?, status = ? WHERE id = ?",
                 (name, description, color, status, id))
    conn.commit()
    conn.close()

    flash('Cập nhật dự án thành công!', 'success')
    return redirect(url_for('projects'))

@app.route('/projects/delete/<int:id>', methods=['POST'])
@login_required
def project_delete(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM projects WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Đã xóa dự án thành công.', 'info')
    return redirect(url_for('projects'))

# Tasks Routes (List View)
@app.route('/tasks')
@login_required
def tasks():
    search = request.args.get('search', '').strip()
    project_id = request.args.get('project_id', '')
    status = request.args.get('status', '')
    priority = request.args.get('priority', '')

    conn = get_db_connection()
    projects_list = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    users_list = conn.execute("SELECT * FROM users ORDER BY fullname").fetchall()

    query = '''
        SELECT t.*, p.name as project_name, p.color as project_color,
               u_assign.fullname as assignee_name, u_creator.fullname as creator_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u_assign ON t.assignee_id = u_assign.id
        LEFT JOIN users u_creator ON t.creator_id = u_creator.id
        WHERE 1=1
    '''
    params = []

    if search:
        query += " AND (t.title LIKE ? OR t.description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if project_id:
        query += " AND t.project_id = ?"
        params.append(project_id)

    if status:
        query += " AND t.status = ?"
        params.append(status)

    if priority:
        query += " AND t.priority = ?"
        params.append(priority)

    query += " ORDER BY CASE t.priority WHEN 'Khẩn cấp' THEN 1 WHEN 'Cao' THEN 2 WHEN 'Trung bình' THEN 3 ELSE 4 END, t.due_date ASC"
    
    tasks_list = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('tasks.html',
                           tasks=tasks_list,
                           projects=projects_list,
                           users=users_list,
                           search=search,
                           project_id=project_id,
                           status=status,
                           priority=priority)

@app.route('/tasks/add', methods=['POST'])
@login_required
def task_add():
    title = request.form['title'].strip()
    description = request.form.get('description', '').strip()
    project_id = request.form.get('project_id') or None
    assignee_id = request.form.get('assignee_id') or None
    priority = request.form.get('priority', 'Trung bình')
    status = request.form.get('status', 'To Do')
    due_date = request.form.get('due_date') or None

    if title:
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO tasks (title, description, project_id, assignee_id, creator_id, priority, status, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, project_id, assignee_id, session['user_id'], priority, status, due_date))
        conn.commit()
        conn.close()
        flash('Tạo công việc mới thành công!', 'success')

    return redirect(request.referrer or url_for('tasks'))

@app.route('/tasks/edit/<int:id>', methods=['POST'])
@login_required
def task_edit(id):
    title = request.form['title'].strip()
    description = request.form.get('description', '').strip()
    project_id = request.form.get('project_id') or None
    assignee_id = request.form.get('assignee_id') or None
    priority = request.form.get('priority', 'Trung bình')
    status = request.form.get('status', 'To Do')
    due_date = request.form.get('due_date') or None

    conn = get_db_connection()
    conn.execute('''
        UPDATE tasks
        SET title = ?, description = ?, project_id = ?, assignee_id = ?, priority = ?, status = ?, due_date = ?
        WHERE id = ?
    ''', (title, description, project_id, assignee_id, priority, status, due_date, id))
    conn.commit()
    conn.close()

    flash('Cập nhật công việc thành công!', 'success')
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tasks/quick_status/<int:id>', methods=['POST'])
@login_required
def task_quick_status(id):
    new_status = request.form.get('status')
    conn = get_db_connection()
    conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    conn.close()
    flash('Đã cập nhật trạng thái công việc!', 'info')
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tasks/delete/<int:id>', methods=['POST'])
@login_required
def task_delete(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM tasks WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Đã xóa công việc thành công.', 'info')
    return redirect(request.referrer or url_for('tasks'))

# Kanban Board
@app.route('/kanban')
@login_required
def kanban():
    project_id = request.args.get('project_id', '')

    conn = get_db_connection()
    projects_list = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
    users_list = conn.execute("SELECT * FROM users ORDER BY fullname").fetchall()

    query = '''
        SELECT t.*, p.name as project_name, p.color as project_color, u.fullname as assignee_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u ON t.assignee_id = u.id
        WHERE 1=1
    '''
    params = []
    if project_id:
        query += " AND t.project_id = ?"
        params.append(project_id)

    query += " ORDER BY t.due_date ASC"
    all_tasks = conn.execute(query, params).fetchall()
    conn.close()

    todo_tasks = [t for t in all_tasks if t['status'] == 'To Do']
    in_progress_tasks = [t for t in all_tasks if t['status'] == 'In Progress']
    completed_tasks = [t for t in all_tasks if t['status'] == 'Completed']

    return render_template('kanban.html',
                           todo_tasks=todo_tasks,
                           in_progress_tasks=in_progress_tasks,
                           completed_tasks=completed_tasks,
                           projects=projects_list,
                           users=users_list,
                           project_id=project_id)

# Task Detail & Comments
@app.route('/tasks/<int:id>')
@login_required
def task_detail(id):
    conn = get_db_connection()
    task = conn.execute('''
        SELECT t.*, p.name as project_name, p.color as project_color,
               u_assign.fullname as assignee_name, u_creator.fullname as creator_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u_assign ON t.assignee_id = u_assign.id
        LEFT JOIN users u_creator ON t.creator_id = u_creator.id
        WHERE t.id = ?
    ''', (id,)).fetchone()

    if not task:
        conn.close()
        flash('Không tìm thấy công việc!', 'danger')
        return redirect(url_for('tasks'))

    comments = conn.execute('''
        SELECT c.*, u.fullname as user_name, u.role as user_role
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.task_id = ?
        ORDER BY c.created_at ASC
    ''', (id,)).fetchall()
    conn.close()

    return render_template('task_detail.html', task=task, comments=comments)

@app.route('/tasks/<int:id>/comment', methods=['POST'])
@login_required
def task_add_comment(id):
    content = request.form['content'].strip()
    if content:
        conn = get_db_connection()
        conn.execute("INSERT INTO comments (task_id, user_id, content) VALUES (?, ?, ?)",
                     (id, session['user_id'], content))
        conn.commit()
        conn.close()
        flash('Đã thêm bình luận!', 'success')
    return redirect(url_for('task_detail', id=id))

# Team / Members
@app.route('/members')
@login_required
def members():
    conn = get_db_connection()
    members_list = conn.execute('''
        SELECT u.*,
               COUNT(t.id) as assigned_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) as completed_tasks
        FROM users u
        LEFT JOIN tasks t ON u.id = t.assignee_id
        GROUP BY u.id
        ORDER BY u.fullname
    ''').fetchall()
    conn.close()
    return render_template('members.html', members=members_list)

if __name__ == '__main__':
    print("Starting TaskMaster - Task Management System (Flask)...")
    app.run(debug=True, port=5000)
