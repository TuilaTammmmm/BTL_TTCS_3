from flask import Flask, render_template, request, redirect, url_for, flash, session
import functools
from werkzeug.security import check_password_hash
from database import (
    get_db_connection, init_db, uuid7, now_iso,
    get_user_role_in_workspace, check_workspace_permission, Role
)
from api import api as api_blueprint
import os
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = 'taskmaster-super-secret-key-btl-ttcs3'

# Register API Blueprint (JWT + RBAC REST API)
app.register_blueprint(api_blueprint)

# Ensure database exists on startup
if not os.path.exists(os.path.join(os.path.dirname(__file__), 'app_data.db')):
    init_db()

# ---------------------------------------------------------------------------
# Custom Jinja2 Filters
# ---------------------------------------------------------------------------
@app.template_filter('date_format')
def date_format_filter(value):
    if not value:
        return "-"
    try:
        dt = datetime.strptime(str(value).split('T')[0].split()[0], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(value)

@app.template_filter('is_overdue')
def is_overdue_filter(due_date_str, status):
    if not due_date_str or status == 'Completed':
        return False
    try:
        due_date = datetime.strptime(str(due_date_str).split('T')[0], "%Y-%m-%d").date()
        return due_date < date.today()
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Auth Helpers
# ---------------------------------------------------------------------------
def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để sử dụng ứng dụng!', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_user():
    """Inject current user info and active workspace into all templates."""
    return dict(
        current_user=session.get('fullname'),
        current_role=session.get('role'),           # role trong active workspace
        current_username=session.get('username'),
        current_user_id=session.get('user_id'),
        active_workspace_id=session.get('workspace_id'),
        active_workspace_name=session.get('workspace_name'),
        Role=Role,                                   # expose Role constants to Jinja2
    )

def _get_user_first_workspace(user_id: str):
    """Lấy workspace đầu tiên mà user có quyền truy cập."""
    conn = get_db_connection()
    row = conn.execute('''
        SELECT w.id, w.name, wm.role
        FROM workspace_members wm
        JOIN workspaces w ON wm.workspace_id = w.id
        WHERE wm.user_id = ? AND w.is_active = 1
        ORDER BY CASE wm.role
            WHEN 'Owner'  THEN 1 WHEN 'Admin'  THEN 2
            WHEN 'Member' THEN 3 WHEN 'Viewer' THEN 4 END
        LIMIT 1
    ''', (user_id,)).fetchone()
    conn.close()
    return row

# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id']  = user['id']
            session['username'] = user['username']
            session['fullname'] = user['fullname']

            # Load first workspace and role into session
            ws = _get_user_first_workspace(user['id'])
            if ws:
                session['workspace_id']   = ws['id']
                session['workspace_name'] = ws['name']
                session['role']           = ws['role']
            else:
                session['workspace_id']   = None
                session['workspace_name'] = None
                session['role']           = None

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

# Switch workspace
@app.route('/switch_workspace/<ws_id>')
@login_required
def switch_workspace(ws_id):
    conn = get_db_connection()
    member = conn.execute(
        "SELECT wm.role, w.name FROM workspace_members wm JOIN workspaces w ON wm.workspace_id = w.id WHERE wm.user_id = ? AND wm.workspace_id = ?",
        (session['user_id'], ws_id)
    ).fetchone()
    conn.close()
    if member:
        session['workspace_id']   = ws_id
        session['workspace_name'] = member['name']
        session['role']           = member['role']
        flash(f'Đã chuyển sang workspace: {member["name"]}', 'info')
    else:
        flash('Bạn không có quyền truy cập workspace này!', 'danger')
    return redirect(url_for('dashboard'))

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route('/')
@login_required
def dashboard():
    conn = get_db_connection()
    today_str = date.today().isoformat()
    ws_id = session.get('workspace_id')

    # Workspace list for the switcher in navbar
    user_workspaces = conn.execute('''
        SELECT w.id, w.name, wm.role
        FROM workspace_members wm JOIN workspaces w ON wm.workspace_id = w.id
        WHERE wm.user_id = ? AND w.is_active = 1
    ''', (session['user_id'],)).fetchall()

    # Task stats (scoped to active workspace)
    def count(sql, params=()):
        return conn.execute(sql, params).fetchone()[0]

    total_tasks      = count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ?", (ws_id,))
    completed_tasks  = count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND status = 'Completed'", (ws_id,))
    in_progress_tasks= count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND status = 'In Progress'", (ws_id,))
    todo_tasks       = count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND status = 'To Do'", (ws_id,))
    overdue_tasks    = count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND status != 'Completed' AND due_date < ?", (ws_id, today_str))
    urgent_tasks     = count("SELECT COUNT(*) FROM tasks WHERE workspace_id = ? AND priority = 'Urgent' AND status != 'Completed'", (ws_id,))
    completion_rate  = round(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # Recent Tasks
    recent_tasks = conn.execute('''
        SELECT t.*, p.name AS project_name, p.color AS project_color,
               u.fullname AS assignee_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u ON t.assignee_id = u.id
        WHERE t.workspace_id = ?
        ORDER BY t.created_at DESC LIMIT 6
    ''', (ws_id,)).fetchall()

    # Projects with progress
    projects = conn.execute('''
        SELECT p.*,
               COUNT(t.id) AS total_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) AS done_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        WHERE p.workspace_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''', (ws_id,)).fetchall()

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
                           projects=projects,
                           user_workspaces=user_workspaces)

# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@app.route('/projects')
@login_required
def projects():
    ws_id = session.get('workspace_id')
    conn = get_db_connection()
    projects_list = conn.execute('''
        SELECT p.*,
               u.fullname AS creator_name,
               COUNT(t.id) AS total_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) AS done_tasks,
               SUM(CASE WHEN t.status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress_tasks,
               SUM(CASE WHEN t.status = 'To Do' THEN 1 ELSE 0 END) AS todo_tasks
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        LEFT JOIN users u ON p.created_by = u.id
        WHERE p.workspace_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''', (ws_id,)).fetchall()
    conn.close()
    return render_template('projects.html', projects=projects_list)

@app.route('/projects/add', methods=['POST'])
@login_required
def project_add():
    ws_id = session.get('workspace_id')
    name        = request.form['name'].strip()
    description = request.form.get('description', '').strip()
    color       = request.form.get('color', '#4f46e5')
    status      = request.form.get('status', 'Active')

    if name and ws_id:
        now = now_iso()
        uid = session['user_id']
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO projects (id, workspace_id, name, description, color, status, created_by, created_at, updated_by, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (uuid7(), ws_id, name, description, color, status, uid, now, uid, now)
        )
        conn.commit()
        conn.close()
        flash('Thêm dự án mới thành công!', 'success')
    return redirect(url_for('projects'))

@app.route('/projects/edit/<proj_id>', methods=['POST'])
@login_required
def project_edit(proj_id):
    name        = request.form['name'].strip()
    description = request.form.get('description', '').strip()
    color       = request.form.get('color', '#4f46e5')
    status      = request.form.get('status', 'Active')
    now = now_iso()
    uid = session['user_id']

    conn = get_db_connection()
    conn.execute(
        "UPDATE projects SET name=?, description=?, color=?, status=?, updated_by=?, updated_at=? WHERE id=?",
        (name, description, color, status, uid, now, proj_id)
    )
    conn.commit()
    conn.close()
    flash('Cập nhật dự án thành công!', 'success')
    return redirect(url_for('projects'))

@app.route('/projects/delete/<proj_id>', methods=['POST'])
@login_required
def project_delete(proj_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM projects WHERE id=?", (proj_id,))
    conn.commit()
    conn.close()
    flash('Đã xóa dự án thành công.', 'info')
    return redirect(url_for('projects'))

# ---------------------------------------------------------------------------
# Tasks — List View
# ---------------------------------------------------------------------------
@app.route('/tasks')
@login_required
def tasks():
    ws_id      = session.get('workspace_id')
    search     = request.args.get('search', '').strip()
    project_id = request.args.get('project_id', '')
    status     = request.args.get('status', '')
    priority   = request.args.get('priority', '')

    conn = get_db_connection()
    projects_list = conn.execute(
        "SELECT * FROM projects WHERE workspace_id = ? ORDER BY name", (ws_id,)
    ).fetchall()
    users_list = conn.execute(
        "SELECT * FROM users ORDER BY fullname"
    ).fetchall()

    query = '''
        SELECT t.*,
               p.name  AS project_name, p.color AS project_color,
               ua.fullname AS assignee_name,
               uc.fullname AS creator_name
        FROM tasks t
        LEFT JOIN projects p  ON t.project_id   = p.id
        LEFT JOIN users ua    ON t.assignee_id   = ua.id
        LEFT JOIN users uc    ON t.created_by    = uc.id
        WHERE t.workspace_id = ?
    '''
    params = [ws_id]

    if search:
        query += " AND (t.title LIKE ? OR t.description LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if project_id:
        query += " AND t.project_id = ?"
        params.append(project_id)
    if status:
        query += " AND t.status = ?"
        params.append(status)
    if priority:
        query += " AND t.priority = ?"
        params.append(priority)

    query += " ORDER BY CASE t.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, t.due_date ASC"
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
    ws_id       = session.get('workspace_id')
    title       = request.form['title'].strip()
    description = request.form.get('description', '').strip()
    project_id  = request.form.get('project_id') or None
    assignee_id = request.form.get('assignee_id') or None
    priority    = request.form.get('priority', 'Medium')
    status      = request.form.get('status', 'To Do')
    due_date    = request.form.get('due_date') or None

    if not project_id:
        flash('Lỗi: Bạn phải chọn một dự án để tạo công việc!', 'danger')
        return redirect(request.referrer or url_for('tasks'))

    if title and ws_id:
        now = now_iso()
        uid = session['user_id']
        conn = get_db_connection()
        conn.execute('''
            INSERT INTO tasks
                (id, project_id, workspace_id, title, description, assignee_id,
                 priority, status, due_date, created_by, created_at, updated_by, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (uuid7(), project_id, ws_id, title, description, assignee_id,
              priority, status, due_date, uid, now, uid, now))
        conn.commit()
        conn.close()
        flash('Tạo công việc mới thành công!', 'success')

    return redirect(request.referrer or url_for('tasks'))

@app.route('/tasks/edit/<task_id>', methods=['POST'])
@login_required
def task_edit(task_id):
    title       = request.form['title'].strip()
    description = request.form.get('description', '').strip()
    project_id  = request.form.get('project_id') or None
    assignee_id = request.form.get('assignee_id') or None
    priority    = request.form.get('priority', 'Medium')
    status      = request.form.get('status', 'To Do')
    due_date    = request.form.get('due_date') or None
    now = now_iso()
    uid = session['user_id']

    conn = get_db_connection()
    conn.execute('''
        UPDATE tasks
        SET title=?, description=?, project_id=?, assignee_id=?,
            priority=?, status=?, due_date=?, updated_by=?, updated_at=?
        WHERE id=?
    ''', (title, description, project_id, assignee_id, priority, status, due_date, uid, now, task_id))
    conn.commit()
    conn.close()
    flash('Cập nhật công việc thành công!', 'success')
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tasks/quick_status/<task_id>', methods=['POST'])
@login_required
def task_quick_status(task_id):
    new_status = request.form.get('status')
    now = now_iso()
    uid = session['user_id']
    conn = get_db_connection()
    conn.execute(
        "UPDATE tasks SET status=?, updated_by=?, updated_at=? WHERE id=?",
        (new_status, uid, now, task_id)
    )
    conn.commit()
    conn.close()
    flash('Đã cập nhật trạng thái công việc!', 'info')
    return redirect(request.referrer or url_for('tasks'))

@app.route('/tasks/delete/<task_id>', methods=['POST'])
@login_required
def task_delete(task_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    flash('Đã xóa công việc thành công.', 'info')
    return redirect(request.referrer or url_for('tasks'))

# ---------------------------------------------------------------------------
# Kanban Board
# ---------------------------------------------------------------------------
@app.route('/kanban')
@login_required
def kanban():
    ws_id      = session.get('workspace_id')
    project_id = request.args.get('project_id', '')

    conn = get_db_connection()
    projects_list = conn.execute(
        "SELECT * FROM projects WHERE workspace_id = ? ORDER BY name", (ws_id,)
    ).fetchall()
    users_list = conn.execute("SELECT * FROM users ORDER BY fullname").fetchall()

    query = '''
        SELECT t.*, p.name AS project_name, p.color AS project_color,
               u.fullname AS assignee_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users u    ON t.assignee_id = u.id
        WHERE t.workspace_id = ?
    '''
    params = [ws_id]
    if project_id:
        query += " AND t.project_id = ?"
        params.append(project_id)
    query += " ORDER BY t.position ASC, t.due_date ASC"

    all_tasks = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('kanban.html',
                           todo_tasks       =[t for t in all_tasks if t['status'] == 'To Do'],
                           in_progress_tasks=[t for t in all_tasks if t['status'] == 'In Progress'],
                           completed_tasks  =[t for t in all_tasks if t['status'] == 'Completed'],
                           projects=projects_list,
                           users=users_list,
                           project_id=project_id)

# ---------------------------------------------------------------------------
# Task Detail + Comments
# ---------------------------------------------------------------------------
@app.route('/tasks/<task_id>')
@login_required
def task_detail(task_id):
    conn = get_db_connection()
    task = conn.execute('''
        SELECT t.*,
               p.name  AS project_name, p.color AS project_color,
               ua.fullname AS assignee_name,
               uc.fullname AS creator_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id  = p.id
        LEFT JOIN users ua   ON t.assignee_id  = ua.id
        LEFT JOIN users uc   ON t.created_by   = uc.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()

    if not task:
        conn.close()
        flash('Không tìm thấy công việc!', 'danger')
        return redirect(url_for('tasks'))

    # Task labels
    labels = conn.execute('''
        SELECT l.* FROM labels l
        JOIN task_labels tl ON l.id = tl.label_id
        WHERE tl.task_id = ?
    ''', (task_id,)).fetchall()

    # Comments — created_by replaces old user_id field
    comments = conn.execute('''
        SELECT c.*, u.fullname AS user_name
        FROM comments c
        JOIN users u ON c.created_by = u.id
        WHERE c.task_id = ?
        ORDER BY c.created_at ASC
    ''', (task_id,)).fetchall()

    conn.close()
    return render_template('task_detail.html', task=task, comments=comments, labels=labels)

@app.route('/tasks/<task_id>/comment', methods=['POST'])
@login_required
def task_add_comment(task_id):
    content = request.form['content'].strip()
    if content:
        now = now_iso()
        uid = session['user_id']
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO comments (id, task_id, content, is_edited, created_by, created_at, updated_by, updated_at) VALUES (?,?,?,0,?,?,?,?)",
            (uuid7(), task_id, content, uid, now, uid, now)
        )
        conn.commit()
        conn.close()
        flash('Đã thêm bình luận!', 'success')
    return redirect(url_for('task_detail', task_id=task_id))

# ---------------------------------------------------------------------------
# Team Members
# ---------------------------------------------------------------------------
@app.route('/members')
@login_required
def members():
    ws_id = session.get('workspace_id')
    conn = get_db_connection()
    members_list = conn.execute('''
        SELECT u.*,
               wm.role,
               wm.joined_at,
               COUNT(t.id)  AS assigned_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) AS completed_tasks
        FROM workspace_members wm
        JOIN users u ON wm.user_id = u.id
        LEFT JOIN tasks t ON u.id = t.assignee_id AND t.workspace_id = ?
        WHERE wm.workspace_id = ?
        GROUP BY u.id
        ORDER BY CASE wm.role
            WHEN 'Owner'  THEN 1 WHEN 'Admin'  THEN 2
            WHEN 'Member' THEN 3 WHEN 'Viewer' THEN 4 END
    ''', (ws_id, ws_id)).fetchall()
    conn.close()
    return render_template('members.html', members=members_list)

# ---------------------------------------------------------------------------
# Workspace Invitations
# ---------------------------------------------------------------------------
@app.route('/invitations')
@login_required
def invitations():
    ws_id = session.get('workspace_id')
    conn  = get_db_connection()
    inv_list = conn.execute('''
        SELECT wi.*, u.fullname AS invited_by_name
        FROM workspace_invitations wi
        JOIN users u ON wi.invited_by = u.id
        WHERE wi.workspace_id = ?
        ORDER BY wi.created_at DESC
    ''', (ws_id,)).fetchall()
    conn.close()
    return render_template('invitations.html', invitations=inv_list)

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("Starting TaskMaster - Task Management System (Flask)...")
    app.run(debug=True, port=5000)
