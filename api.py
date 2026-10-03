"""
api.py  —  REST API Blueprint
==============================
Cài đặt đúng flow từ 2 sequence diagram:

Diagram 1: POST /api/auth/login → JWT Access Token
Diagram 2: Request + Bearer JWT → Auth Check → Permission Check → CRUD

Tất cả endpoint trả về JSON.
"""

from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash
from auth import (
    create_access_token, jwt_required, require_permission
)
from database import (
    get_db_connection, uuid7, now_iso, get_user_role_in_workspace
)

api = Blueprint('api', __name__, url_prefix='/api')


# ===========================================================================
# DIAGRAM 1 — POST /api/auth/login
# Client → username + password
#        ← 200 OK { access_token }  |  401 Unauthorized
# ===========================================================================
@api.route('/auth/login', methods=['POST'])
def api_login():
    """
    Diagram 1, bước 1-4:
      1. POST /auth/login (username, password)
      2. Truy vấn user & kiểm tra mật khẩu
      3. Thông tin user hợp lệ
      4. 200 OK (JWT Access Token)
    """
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({
            'error': 'Bad Request',
            'message': 'username và password là bắt buộc.'
        }), 400

    # Bước 2: Truy vấn user & kiểm tra mật khẩu (Diagram 1)
    conn = get_db_connection()
    user = conn.execute(
        "SELECT id, username, fullname, password_hash, is_active FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()

    if not user or not user['is_active'] or not check_password_hash(user['password_hash'], password):
        # Bước 3 (thất bại): 401 Unauthorized
        return jsonify({
            'error':   'Unauthorized',
            'message': 'Tên đăng nhập hoặc mật khẩu không chính xác.'
        }), 401

    # Bước 4: 200 OK (JWT Access Token)
    token = create_access_token(user['id'], user['username'], user['fullname'])
    return jsonify({
        'access_token': token,
        'token_type':   'Bearer',
        'expires_in':   8 * 3600,          # 8 giờ (giây)
        'user': {
            'id':       user['id'],
            'username': user['username'],
            'fullname': user['fullname'],
        }
    }), 200


# ---------------------------------------------------------------------------
# Endpoint kiểm tra token còn hợp lệ không (helper cho client)
# ---------------------------------------------------------------------------
@api.route('/auth/me', methods=['GET'])
@jwt_required
def api_me():
    """Trả về thông tin user từ JWT + danh sách workspace."""
    conn = get_db_connection()
    workspaces = conn.execute('''
        SELECT w.id, w.name, w.slug, wm.role
        FROM workspace_members wm
        JOIN workspaces w ON wm.workspace_id = w.id
        WHERE wm.user_id = ? AND w.is_active = 1
    ''', (g.current_user['id'],)).fetchall()
    conn.close()

    return jsonify({
        'user': g.current_user,
        'workspaces': [dict(ws) for ws in workspaces]
    }), 200


# ===========================================================================
# DIAGRAM 2 — Tasks API (JWT + RBAC)
# ===========================================================================

# ---------------------------------------------------------------------------
# GET /api/workspaces/<workspace_id>/tasks
# Diagram 2: Viewer trở lên có thể xem
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/tasks', methods=['GET'])
@jwt_required
@require_permission('task.view')
def api_list_tasks(workspace_id):
    """
    Diagram 2, bước 8-10:
      8. Thực hiện CRUD Task (READ)
      9. Thành công
     10. 200 OK (Trả dữ liệu)
    """
    status   = request.args.get('status', '')
    priority = request.args.get('priority', '')
    project_id = request.args.get('project_id', '')

    conn = get_db_connection()
    query = '''
        SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date,
               t.position, t.created_at, t.updated_at,
               p.name  AS project_name,
               ua.fullname AS assignee_name,
               uc.fullname AS created_by_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id  = p.id
        LEFT JOIN users ua   ON t.assignee_id  = ua.id
        LEFT JOIN users uc   ON t.created_by   = uc.id
        WHERE t.workspace_id = ?
    '''
    params = [workspace_id]

    if status:
        query += ' AND t.status = ?'
        params.append(status)
    if priority:
        query += ' AND t.priority = ?'
        params.append(priority)
    if project_id:
        query += ' AND t.project_id = ?'
        params.append(project_id)

    query += ' ORDER BY t.position ASC, t.created_at DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify({
        'workspace_id': workspace_id,
        'role':         g.current_role,
        'total':        len(rows),
        'tasks':        [dict(r) for r in rows]
    }), 200


# ---------------------------------------------------------------------------
# POST /api/workspaces/<workspace_id>/tasks
# Diagram 1 bước 5-12 + Diagram 2 full flow
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/tasks', methods=['POST'])
@jwt_required
@require_permission('task.create')
def api_create_task(workspace_id):
    """
    Diagram 1 + 2 kết hợp:
      - JWT đã verified bởi @jwt_required
      - Role đã checked bởi @require_permission('task.create')
      - Diagram 1 bước 8: create_task(db_session, task_data, user)
      - Diagram 1 bước 9: INSERT INTO tasks (title, status, user_id)
      - Diagram 1 bước 12: 201 Created (Thông tin Task)
    """
    data = request.get_json(silent=True) or {}

    title       = data.get('title', '').strip()
    description = data.get('description', '')
    project_id  = data.get('project_id')
    assignee_id = data.get('assignee_id')
    priority    = data.get('priority', 'Medium')
    status      = data.get('status', 'To Do')
    due_date    = data.get('due_date')

    if not title:
        return jsonify({'error': 'Bad Request', 'message': 'title là bắt buộc.'}), 400

    if priority not in ('Urgent', 'High', 'Medium', 'Low'):
        return jsonify({'error': 'Bad Request', 'message': 'priority phải là: Urgent/High/Medium/Low'}), 400

    if status not in ('To Do', 'In Progress', 'In Review', 'Completed', 'Cancelled'):
        return jsonify({'error': 'Bad Request', 'message': 'status không hợp lệ.'}), 400

    now = now_iso()
    uid = g.current_user['id']
    task_id = uuid7()

    conn = get_db_connection()

    # Validate project_id thuộc workspace
    if project_id:
        proj = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND workspace_id = ?",
            (project_id, workspace_id)
        ).fetchone()
        if not proj:
            conn.close()
            return jsonify({'error': 'Bad Request', 'message': 'project_id không thuộc workspace này.'}), 400

    # Diagram 1 bước 9: INSERT INTO tasks
    conn.execute('''
        INSERT INTO tasks
            (id, project_id, workspace_id, title, description, assignee_id,
             priority, status, due_date, created_by, created_at, updated_by, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (task_id, project_id, workspace_id, title, description, assignee_id,
          priority, status, due_date, uid, now, uid, now))
    conn.commit()

    # Diagram 1 bước 11: Bản ghi task mới tạo (Task Schema)
    task = conn.execute('''
        SELECT t.*, p.name AS project_name, ua.fullname AS assignee_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users ua   ON t.assignee_id = ua.id
        WHERE t.id = ?
    ''', (task_id,)).fetchone()
    conn.close()

    # Diagram 1 bước 12: 201 Created (Thông tin Task)
    return jsonify({
        'message': 'Task đã được tạo thành công.',
        'task':    dict(task)
    }), 201


# ---------------------------------------------------------------------------
# GET /api/workspaces/<workspace_id>/tasks/<task_id>
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/tasks/<task_id>', methods=['GET'])
@jwt_required
@require_permission('task.view')
def api_get_task(workspace_id, task_id):
    conn = get_db_connection()
    task = conn.execute('''
        SELECT t.*, p.name AS project_name,
               ua.fullname AS assignee_name, uc.fullname AS created_by_name
        FROM tasks t
        LEFT JOIN projects p ON t.project_id = p.id
        LEFT JOIN users ua   ON t.assignee_id = ua.id
        LEFT JOIN users uc   ON t.created_by = uc.id
        WHERE t.id = ? AND t.workspace_id = ?
    ''', (task_id, workspace_id)).fetchone()

    labels = conn.execute('''
        SELECT l.id, l.name, l.color FROM labels l
        JOIN task_labels tl ON l.id = tl.label_id
        WHERE tl.task_id = ?
    ''', (task_id,)).fetchall()

    comments = conn.execute('''
        SELECT c.id, c.content, c.is_edited, c.created_at, u.fullname AS author
        FROM comments c JOIN users u ON c.created_by = u.id
        WHERE c.task_id = ? ORDER BY c.created_at ASC
    ''', (task_id,)).fetchall()
    conn.close()

    if not task:
        return jsonify({'error': 'Not Found', 'message': 'Task không tồn tại.'}), 404

    return jsonify({
        'task':     dict(task),
        'labels':   [dict(l) for l in labels],
        'comments': [dict(c) for c in comments],
        'role':     g.current_role,
    }), 200


# ---------------------------------------------------------------------------
# PUT /api/workspaces/<workspace_id>/tasks/<task_id>
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/tasks/<task_id>', methods=['PUT'])
@jwt_required
@require_permission('task.update')
def api_update_task(workspace_id, task_id):
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ? AND workspace_id = ?",
        (task_id, workspace_id)
    ).fetchone()

    if not existing:
        conn.close()
        return jsonify({'error': 'Not Found', 'message': 'Task không tồn tại.'}), 404

    data        = request.get_json(silent=True) or {}
    now         = now_iso()
    uid         = g.current_user['id']
    title       = data.get('title', '').strip()
    description = data.get('description')
    assignee_id = data.get('assignee_id')
    priority    = data.get('priority')
    status      = data.get('status')
    due_date    = data.get('due_date')

    updates, params = [], []
    if title:        updates.append('title = ?');       params.append(title)
    if description is not None: updates.append('description = ?'); params.append(description)
    if assignee_id is not None: updates.append('assignee_id = ?'); params.append(assignee_id)
    if priority:     updates.append('priority = ?');    params.append(priority)
    if status:       updates.append('status = ?');      params.append(status)
    if due_date is not None: updates.append('due_date = ?'); params.append(due_date)

    updates += ['updated_by = ?', 'updated_at = ?']
    params  += [uid, now, task_id]

    conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    return jsonify({'message': 'Task đã được cập nhật thành công.'}), 200


# ---------------------------------------------------------------------------
# DELETE /api/workspaces/<workspace_id>/tasks/<task_id>
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/tasks/<task_id>', methods=['DELETE'])
@jwt_required
@require_permission('task.delete')
def api_delete_task(workspace_id, task_id):
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM tasks WHERE id = ? AND workspace_id = ?",
        (task_id, workspace_id)
    ).fetchone()

    if not existing:
        conn.close()
        return jsonify({'error': 'Not Found', 'message': 'Task không tồn tại.'}), 404

    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Task đã được xóa thành công.'}), 200


# ---------------------------------------------------------------------------
# POST /api/workspaces/<workspace_id>/tasks/<task_id>/comments
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/tasks/<task_id>/comments', methods=['POST'])
@jwt_required
@require_permission('comment.create')
def api_add_comment(workspace_id, task_id):
    data    = request.get_json(silent=True) or {}
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'error': 'Bad Request', 'message': 'content là bắt buộc.'}), 400

    now = now_iso()
    uid = g.current_user['id']
    cid = uuid7()

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO comments (id, task_id, content, is_edited, created_by, created_at, updated_by, updated_at) VALUES (?,?,?,0,?,?,?,?)",
        (cid, task_id, content, uid, now, uid, now)
    )
    conn.commit()
    conn.close()

    return jsonify({
        'message':    'Comment đã được thêm.',
        'comment_id': cid
    }), 201


# ---------------------------------------------------------------------------
# GET /api/workspaces/<workspace_id>/projects
# ---------------------------------------------------------------------------
@api.route('/workspaces/<workspace_id>/projects', methods=['GET'])
@jwt_required
@require_permission('project.view')
def api_list_projects(workspace_id):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT p.*,
               COUNT(t.id) AS total_tasks,
               SUM(CASE WHEN t.status = 'Completed' THEN 1 ELSE 0 END) AS done_tasks,
               u.fullname AS created_by_name
        FROM projects p
        LEFT JOIN tasks t ON p.id = t.project_id
        LEFT JOIN users u ON p.created_by = u.id
        WHERE p.workspace_id = ?
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''', (workspace_id,)).fetchall()
    conn.close()

    return jsonify({
        'workspace_id': workspace_id,
        'role':         g.current_role,
        'total':        len(rows),
        'projects':     [dict(r) for r in rows]
    }), 200


# ---------------------------------------------------------------------------
# Error Handlers (JSON format cho API)
# ---------------------------------------------------------------------------
@api.app_errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not Found', 'message': str(e)}), 404
    return e

@api.app_errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Method Not Allowed', 'message': str(e)}), 405
    return e
