"""
auth.py  —  Authentication & Authorization Layer
=================================================
Implements the exact flow from the two sequence diagrams:

Diagram 1  (Authentication):
  Client → POST /api/auth/login (username + password)
         ← 200 OK { access_token: "Bearer JWT" }
  Client → POST /api/tasks   (Bearer JWT + body)
         → Auth Dependency: decode & verify JWT
         ← 201 Created / 401 Unauthorized

Diagram 2  (Authorization — RBAC):
  Client  → Request + Bearer JWT
  Security → verify signature + expiry
           ← 401 Unauthorized   [if invalid]
  Security → pass user_id to Task Service
  Task Service → check workspace_members table
              ← 403 Forbidden   [if not a member]
              → execute CRUD
              ← 200 OK

Tech: PyJWT (HS256), SQLite via database.get_db_connection()
"""

import jwt
import os
import functools
from datetime import datetime, timedelta, timezone
from flask import request, jsonify, g
from database import get_db_connection, has_permission, get_user_role_in_workspace

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
JWT_SECRET  = os.environ.get('JWT_SECRET', 'taskmaster-jwt-secret-btl-ttcs3-2026')
JWT_ALGO    = 'HS256'
JWT_EXPIRY_HOURS = 8          # Access token lifetime


# ---------------------------------------------------------------------------
# Token Utilities
# ---------------------------------------------------------------------------
def create_access_token(user_id: str, username: str, fullname: str) -> str:
    """
    Tạo JWT Access Token chứa thông tin user.
    Diagram 1, bước 4: "200 OK (JWT Access Token)"
    """
    now = datetime.now(timezone.utc)
    payload = {
        'sub':      user_id,           # subject = user UUID
        'username': username,
        'fullname': fullname,
        'iat':      now,               # issued at
        'exp':      now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_access_token(token: str) -> dict:
    """
    Giải mã và xác thực JWT.
    Diagram 2, bước 2: "Check chữ ký Token & Hạn dùng"
    Raises:
        jwt.ExpiredSignatureError  → token hết hạn
        jwt.InvalidTokenError      → token không hợp lệ
    """
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])


def _extract_token_from_header() -> str | None:
    """Lấy token từ Authorization header: 'Bearer <token>'"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


# ---------------------------------------------------------------------------
# Step 1 — Authentication Decorator (Diagram 2, bước 1-4)
# ---------------------------------------------------------------------------
def jwt_required(f):
    """
    Decorator xác thực JWT.

    Flow (Diagram 2):
      1. Client gửi Request + Token JWT
      2. Check chữ ký Token & Hạn dùng
         [Token sai hoặc hết hạn] → 401 Unauthorized
      3. Token chuẩn → g.current_user = { id, username, fullname }
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_header()

        if not token:
            # Diagram 2: "401 Unauthorized (Chặn luôn)"
            return jsonify({
                'error':   'Unauthorized',
                'message': 'Missing Authorization header. Expected: Bearer <token>',
                'code':    401
            }), 401

        try:
            payload = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({
                'error':   'Unauthorized',
                'message': 'Token đã hết hạn. Vui lòng đăng nhập lại.',
                'code':    401
            }), 401
        except jwt.InvalidTokenError as e:
            return jsonify({
                'error':   'Unauthorized',
                'message': f'Token không hợp lệ: {str(e)}',
                'code':    401
            }), 401

        # Diagram 2 bước 4: "Token chuẩn! Chuyển user_id xuống"
        g.current_user = {
            'id':       payload['sub'],
            'username': payload['username'],
            'fullname': payload['fullname'],
        }
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Step 2 — Authorization Decorator (Diagram 2, bước 5-9)
# ---------------------------------------------------------------------------
def require_permission(permission: str):
    """
    Decorator kiểm tra quyền RBAC trong workspace.

    Flow (Diagram 2):
      5. Check: user_id này có trong bảng workspace_members không?
      6. Trả về kết quả (Có / Không)
         [Không thuộc Project] → 403 Forbidden
         [Đúng Member]         → Thực hiện CRUD Task → 200 OK

    Workspace ID đến từ: URL param `workspace_id`, JSON body, hoặc query string.
    Phải dùng sau @jwt_required.

    Usage:
        @bp.route('/tasks', methods=['POST'])
        @jwt_required
        @require_permission('task.create')
        def create_task(): ...
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            # Lấy workspace_id từ nhiều nguồn
            workspace_id = (
                kwargs.get('workspace_id')
                or request.view_args.get('workspace_id')
                or (request.get_json(silent=True) or {}).get('workspace_id')
                or request.args.get('workspace_id')
            )

            if not workspace_id:
                return jsonify({
                    'error':   'Bad Request',
                    'message': 'workspace_id là bắt buộc để kiểm tra quyền.',
                    'code':    400
                }), 400

            user_id = g.current_user['id']

            # Diagram 2 bước 5-6: truy vấn workspace_members
            role = get_user_role_in_workspace(user_id, workspace_id)

            if not role:
                # Diagram 2: "403 Forbidden (Không có quyền sở vào Task này)"
                return jsonify({
                    'error':   'Forbidden',
                    'message': 'Bạn không phải thành viên của workspace này.',
                    'code':    403
                }), 403

            if not has_permission(role, permission):
                return jsonify({
                    'error':   'Forbidden',
                    'message': f'Role [{role}] không có quyền [{permission}].',
                    'code':    403
                }), 403

            # Diagram 2 bước 7-9: "Đúng Member" → Thực hiện CRUD
            g.current_role        = role
            g.current_workspace_id = workspace_id
            return f(*args, **kwargs)
        return decorated
    return decorator
