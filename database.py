"""
database.py - TaskMaster Database Module
=========================================
Schema Design:
  - users              : Tài khoản người dùng hệ thống
  - workspaces         : Không gian làm việc (tenant)
  - workspace_members  : Thành viên workspace + RBAC role (Owner/Admin/Member/Viewer)
  - workspace_invitations : Lời mời tham gia workspace qua email
  - projects           : Dự án thuộc workspace
  - tasks              : Công việc thuộc dự án
  - labels             : Nhãn/Tag thuộc workspace
  - task_labels        : Bảng nối nhiều-nhiều Task <-> Label
  - comments           : Bình luận thuộc task

ID Strategy: UUID v7 (time-ordered UUID) cho mọi bảng chính.
Audit Fields: created_at, created_by, updated_at, updated_by trên mọi bảng thay đổi.
RBAC Roles: Owner > Admin > Member > Viewer
"""

import sqlite3
import os
import time
import struct
import random
import secrets
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_data.db')

# ---------------------------------------------------------------------------
# UUID v7 Generator
# UUID v7: [48-bit unix_ts_ms][4-bit ver=7][12-bit rand_a][2-bit var][62-bit rand_b]
# Produces lexicographically sortable, time-ordered UUIDs per RFC 9562.
# ---------------------------------------------------------------------------
_last_ms: int = 0
_seq: int = 0

def uuid7() -> str:
    """Generate a UUID v7 string (time-ordered, globally unique)."""
    global _last_ms, _seq

    now_ms = int(time.time() * 1000)
    if now_ms == _last_ms:
        _seq = (_seq + 1) & 0x0FFF       # 12-bit sequence counter
        if _seq == 0:
            now_ms += 1                   # overflow → bump ms
    else:
        _seq = random.randint(0, 0x0FFF)  # reset with random start each ms
    _last_ms = now_ms

    rand_b = random.getrandbits(62)

    # Pack: 48-bit ts | 4-bit ver(7) | 12-bit seq | 2-bit var(0b10) | 62-bit rand_b
    hi = (now_ms << 16) | (0x7 << 12) | _seq
    lo = (0b10 << 62) | rand_b

    # Format as xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    raw = struct.pack('>QQ', hi, lo)
    h = raw.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


# ---------------------------------------------------------------------------
# RBAC Role Definitions
# ---------------------------------------------------------------------------
class Role:
    OWNER  = 'Owner'    # Toàn quyền: xóa workspace, thay đổi Owner
    ADMIN  = 'Admin'    # Quản lý project/task/member, không xóa workspace
    MEMBER = 'Member'   # Tạo/sửa task; không xóa project
    VIEWER = 'Viewer'   # Chỉ xem (read-only)

    ALL = [OWNER, ADMIN, MEMBER, VIEWER]

ROLE_PERMISSIONS: dict[str, set[str]] = {
    Role.OWNER: {
        'workspace.delete', 'workspace.update', 'workspace.transfer_ownership',
        'workspace.invite', 'workspace.remove_member', 'workspace.change_role',
        'project.create', 'project.update', 'project.delete',
        'task.create', 'task.update', 'task.delete', 'task.assign',
        'label.create', 'label.update', 'label.delete',
        'comment.create', 'comment.delete_any',
        'workspace.view', 'project.view', 'task.view',
    },
    Role.ADMIN: {
        'workspace.update', 'workspace.invite', 'workspace.remove_member', 'workspace.change_role',
        'project.create', 'project.update', 'project.delete',
        'task.create', 'task.update', 'task.delete', 'task.assign',
        'label.create', 'label.update', 'label.delete',
        'comment.create', 'comment.delete_any',
        'workspace.view', 'project.view', 'task.view',
    },
    Role.MEMBER: {
        'task.create', 'task.update', 'task.assign',
        'comment.create',
        'label.create',
        'workspace.view', 'project.view', 'task.view',
    },
    Role.VIEWER: {
        'workspace.view', 'project.view', 'task.view',
    },
}

def has_permission(role: str, permission: str) -> bool:
    """Kiểm tra role có quyền thực hiện permission không."""
    return permission in ROLE_PERMISSIONS.get(role, set())


# ---------------------------------------------------------------------------
# Database Connection
# ---------------------------------------------------------------------------
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # Enable FK enforcement
    conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
    return conn


# ---------------------------------------------------------------------------
# DDL — Schema Creation
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
-- ============================================================
-- TABLE: users
-- Lưu thông tin tài khoản người dùng toàn hệ thống.
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id           TEXT PRIMARY KEY,                    -- UUID v7
    username     TEXT UNIQUE NOT NULL,
    email        TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    fullname     TEXT NOT NULL,
    avatar_url   TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1,          -- 1=active, 0=disabled
    created_at   TEXT NOT NULL,                       -- ISO-8601 UTC
    updated_at   TEXT NOT NULL
);

-- ============================================================
-- TABLE: workspaces
-- Không gian làm việc riêng biệt (multi-tenant).
-- ============================================================
CREATE TABLE IF NOT EXISTS workspaces (
    id           TEXT PRIMARY KEY,                    -- UUID v7
    name         TEXT NOT NULL,
    description  TEXT,
    slug         TEXT UNIQUE NOT NULL,               -- URL-friendly identifier
    logo_url     TEXT,
    is_active    INTEGER NOT NULL DEFAULT 1,
    created_by   TEXT NOT NULL REFERENCES users(id),
    created_at   TEXT NOT NULL,
    updated_by   TEXT REFERENCES users(id),
    updated_at   TEXT NOT NULL
);

-- ============================================================
-- TABLE: workspace_members
-- Thành viên của workspace và vai trò RBAC.
-- Roles: Owner | Admin | Member | Viewer
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace_members (
    id              TEXT PRIMARY KEY,                 -- UUID v7
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('Owner','Admin','Member','Viewer')),
    invited_by      TEXT REFERENCES users(id),
    joined_at       TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_by      TEXT REFERENCES users(id),
    updated_at      TEXT NOT NULL,
    UNIQUE(workspace_id, user_id)
);

-- ============================================================
-- TABLE: workspace_invitations
-- Lời mời tham gia workspace qua email.
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace_invitations (
    id              TEXT PRIMARY KEY,                 -- UUID v7
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    role            TEXT NOT NULL CHECK(role IN ('Admin','Member','Viewer')),
    token           TEXT UNIQUE NOT NULL,             -- Secure random token gửi qua email
    status          TEXT NOT NULL DEFAULT 'Pending'
                        CHECK(status IN ('Pending','Accepted','Declined','Expired')),
    invited_by      TEXT NOT NULL REFERENCES users(id),
    expires_at      TEXT NOT NULL,                   -- ISO-8601 UTC (default +7 ngày)
    accepted_by     TEXT REFERENCES users(id),       -- user đã accept (nếu có)
    accepted_at     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- ============================================================
-- TABLE: projects
-- Dự án thuộc một workspace.
-- ============================================================
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,                 -- UUID v7
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT,
    color           TEXT NOT NULL DEFAULT '#4f46e5', -- Hex color
    status          TEXT NOT NULL DEFAULT 'Active'
                        CHECK(status IN ('Active','Archived','Completed')),
    created_by      TEXT NOT NULL REFERENCES users(id),
    created_at      TEXT NOT NULL,
    updated_by      TEXT REFERENCES users(id),
    updated_at      TEXT NOT NULL
);

-- ============================================================
-- TABLE: tasks
-- Công việc thuộc một dự án.
-- ============================================================
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,                 -- UUID v7
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT,
    assignee_id     TEXT REFERENCES users(id) ON DELETE SET NULL,
    priority        TEXT NOT NULL DEFAULT 'Medium'
                        CHECK(priority IN ('Urgent','High','Medium','Low')),
    status          TEXT NOT NULL DEFAULT 'To Do'
                        CHECK(status IN ('To Do','In Progress','In Review','Completed','Cancelled')),
    due_date        TEXT,                            -- ISO date (YYYY-MM-DD)
    position        INTEGER NOT NULL DEFAULT 0,      -- Ordering within column
    created_by      TEXT NOT NULL REFERENCES users(id),
    created_at      TEXT NOT NULL,
    updated_by      TEXT REFERENCES users(id),
    updated_at      TEXT NOT NULL
);

-- ============================================================
-- TABLE: labels
-- Nhãn/Tag tùy chỉnh thuộc workspace (dùng chung cho mọi project).
-- ============================================================
CREATE TABLE IF NOT EXISTS labels (
    id              TEXT PRIMARY KEY,                 -- UUID v7
    workspace_id    TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    color           TEXT NOT NULL DEFAULT '#64748b', -- Hex color
    created_by      TEXT NOT NULL REFERENCES users(id),
    created_at      TEXT NOT NULL,
    updated_by      TEXT REFERENCES users(id),
    updated_at      TEXT NOT NULL,
    UNIQUE(workspace_id, name)
);

-- ============================================================
-- TABLE: task_labels  (Many-to-Many: tasks <-> labels)
-- ============================================================
CREATE TABLE IF NOT EXISTS task_labels (
    task_id         TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    label_id        TEXT NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
    assigned_by     TEXT NOT NULL REFERENCES users(id),
    assigned_at     TEXT NOT NULL,
    PRIMARY KEY (task_id, label_id)
);

-- ============================================================
-- TABLE: comments
-- Bình luận / trao đổi trên từng task.
-- ============================================================
CREATE TABLE IF NOT EXISTS comments (
    id              TEXT PRIMARY KEY,                 -- UUID v7
    task_id         TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    is_edited       INTEGER NOT NULL DEFAULT 0,      -- 1 nếu đã chỉnh sửa
    created_by      TEXT NOT NULL REFERENCES users(id),
    created_at      TEXT NOT NULL,
    updated_by      TEXT REFERENCES users(id),
    updated_at      TEXT NOT NULL
);

-- ============================================================
-- INDEXES — Tăng tốc các truy vấn phổ biến
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_workspace_members_ws  ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_usr ON workspace_members(user_id);
CREATE INDEX IF NOT EXISTS idx_invitations_ws        ON workspace_invitations(workspace_id);
CREATE INDEX IF NOT EXISTS idx_invitations_email     ON workspace_invitations(email);
CREATE INDEX IF NOT EXISTS idx_invitations_token     ON workspace_invitations(token);
CREATE INDEX IF NOT EXISTS idx_projects_ws           ON projects(workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project         ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_ws              ON tasks(workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee        ON tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status          ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_labels_ws             ON labels(workspace_id);
CREATE INDEX IF NOT EXISTS idx_task_labels_task      ON task_labels(task_id);
CREATE INDEX IF NOT EXISTS idx_task_labels_label     ON task_labels(label_id);
CREATE INDEX IF NOT EXISTS idx_comments_task         ON comments(task_id);
"""


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------
def _seed_data(cursor: sqlite3.Cursor) -> None:
    """Nạp dữ liệu mẫu ban đầu vào database."""

    now = now_iso()
    today = datetime.now(timezone.utc).date()

    # ------------------------------------------------------------------ Users
    users = [
        {
            'id':       uuid7(),
            'username': 'admin',
            'email':    'admin@taskmaster.vn',
            'password': generate_password_hash('admin123'),
            'fullname': 'System Administrator',
        },
        {
            'id':       uuid7(),
            'username': 'pm_tuan',
            'email':    'tuan.ta@taskmaster.vn',
            'password': generate_password_hash('123456'),
            'fullname': 'Trần Anh Tuấn',
        },
        {
            'id':       uuid7(),
            'username': 'dev_nam',
            'email':    'nam.lh@taskmaster.vn',
            'password': generate_password_hash('123456'),
            'fullname': 'Lê Hoàng Nam',
        },
        {
            'id':       uuid7(),
            'username': 'designer_lan',
            'email':    'lan.pp@taskmaster.vn',
            'password': generate_password_hash('123456'),
            'fullname': 'Phạm Phương Lan',
        },
        {
            'id':       uuid7(),
            'username': 'viewer_khoa',
            'email':    'khoa.nv@taskmaster.vn',
            'password': generate_password_hash('123456'),
            'fullname': 'Nguyễn Văn Khoa',
        },
    ]

    cursor.executemany(
        """INSERT INTO users (id, username, email, password_hash, fullname, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
        [(u['id'], u['username'], u['email'], u['password'], u['fullname'], now, now) for u in users]
    )
    # Shorthand references (by index position)
    u_admin, u_pm, u_dev, u_designer, u_viewer = users

    # --------------------------------------------------------------- Workspaces
    ws1_id = uuid7()
    ws2_id = uuid7()

    cursor.executemany(
        """INSERT INTO workspaces (id, name, description, slug, is_active, created_by, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)""",
        [
            (ws1_id, 'TTCS3 Software Team', 'Không gian làm việc chính của nhóm phát triển phần mềm BTL TTCS3',
             'ttcs3-software', u_admin['id'], now, u_admin['id'], now),
            (ws2_id, 'Design & Marketing Hub', 'Workspace dành riêng cho nhóm thiết kế và truyền thông',
             'design-marketing', u_pm['id'], now, u_pm['id'], now),
        ]
    )

    # ---------------------------------------------------- Workspace Members (RBAC)
    members = [
        # Workspace 1 — TTCS3 Software Team
        (uuid7(), ws1_id, u_admin['id'],    Role.OWNER,  None,           now, now, u_admin['id'], now),
        (uuid7(), ws1_id, u_pm['id'],       Role.ADMIN,  u_admin['id'],  now, now, u_admin['id'], now),
        (uuid7(), ws1_id, u_dev['id'],      Role.MEMBER, u_pm['id'],     now, now, u_pm['id'],   now),
        (uuid7(), ws1_id, u_designer['id'], Role.MEMBER, u_pm['id'],     now, now, u_pm['id'],   now),
        (uuid7(), ws1_id, u_viewer['id'],   Role.VIEWER, u_admin['id'],  now, now, u_admin['id'], now),
        # Workspace 2 — Design & Marketing Hub
        (uuid7(), ws2_id, u_pm['id'],       Role.OWNER,  None,           now, now, u_pm['id'],   now),
        (uuid7(), ws2_id, u_designer['id'], Role.ADMIN,  u_pm['id'],     now, now, u_pm['id'],   now),
    ]

    cursor.executemany(
        """INSERT INTO workspace_members
               (id, workspace_id, user_id, role, invited_by, joined_at, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        members
    )

    # -------------------------------------------------- Workspace Invitations
    exp_7d = (datetime.now(timezone.utc) + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    exp_expired = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S.000Z')

    invitations = [
        (uuid7(), ws1_id, 'newdev@example.com',    Role.MEMBER, secrets.token_urlsafe(32),
         'Pending',  u_pm['id'],    exp_7d,       None, None, now, now),
        (uuid7(), ws1_id, 'tester@example.com',    Role.VIEWER, secrets.token_urlsafe(32),
         'Accepted', u_admin['id'], exp_7d,       u_viewer['id'], now, now, now),
        (uuid7(), ws2_id, 'contractor@agency.com', Role.MEMBER, secrets.token_urlsafe(32),
         'Expired',  u_pm['id'],    exp_expired,  None, None, now, now),
    ]

    cursor.executemany(
        """INSERT INTO workspace_invitations
               (id, workspace_id, email, role, token, status, invited_by,
                expires_at, accepted_by, accepted_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        invitations
    )

    # ---------------------------------------------------------------- Projects
    p1_id = uuid7()
    p2_id = uuid7()
    p3_id = uuid7()
    p4_id = uuid7()

    projects = [
        (p1_id, ws1_id, 'Website E-Commerce Platform',
         'Xây dựng hệ thống bán hàng trực tuyến đa nền tảng',
         '#4f46e5', 'Active', u_pm['id'], now, u_pm['id'], now),
        (p2_id, ws1_id, 'Mobile App iOS & Android',
         'Phát triển ứng dụng di động cho khách hàng VIP',
         '#0ea5e9', 'Active', u_pm['id'], now, u_pm['id'], now),
        (p3_id, ws1_id, 'Cloud Infrastructure & CI/CD',
         'Nâng cấp hạ tầng cloud, tự động hóa triển khai DevOps',
         '#10b981', 'Active', u_admin['id'], now, u_admin['id'], now),
        (p4_id, ws2_id, 'Marketing Campaign Q4/2026',
         'Chiến dịch truyền thông quý 4 cho dòng sản phẩm mới',
         '#f59e0b', 'Completed', u_pm['id'], now, u_pm['id'], now),
    ]

    cursor.executemany(
        """INSERT INTO projects (id, workspace_id, name, description, color, status,
                                 created_by, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        projects
    )

    # ----------------------------------------------------------------- Labels
    l1_id, l2_id, l3_id, l4_id, l5_id = uuid7(), uuid7(), uuid7(), uuid7(), uuid7()

    labels = [
        (l1_id, ws1_id, 'Bug',        '#ef4444', u_admin['id'], now, u_admin['id'], now),
        (l2_id, ws1_id, 'Feature',    '#3b82f6', u_admin['id'], now, u_admin['id'], now),
        (l3_id, ws1_id, 'Refactor',   '#8b5cf6', u_admin['id'], now, u_admin['id'], now),
        (l4_id, ws1_id, 'Testing',    '#10b981', u_admin['id'], now, u_admin['id'], now),
        (l5_id, ws2_id, 'Design',     '#f59e0b', u_designer['id'], now, u_designer['id'], now),
    ]

    cursor.executemany(
        """INSERT INTO labels (id, workspace_id, name, color, created_by, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        labels
    )

    # ------------------------------------------------------------------ Tasks
    d_past2  = (today - timedelta(days=2)).isoformat()
    d_past1  = (today - timedelta(days=1)).isoformat()
    d_future3  = (today + timedelta(days=3)).isoformat()
    d_future7  = (today + timedelta(days=7)).isoformat()
    d_future14 = (today + timedelta(days=14)).isoformat()
    d_future21 = (today + timedelta(days=21)).isoformat()

    t1_id, t2_id, t3_id, t4_id = uuid7(), uuid7(), uuid7(), uuid7()
    t5_id, t6_id, t7_id        = uuid7(), uuid7(), uuid7()

    tasks_data = [
        # (id, project_id, ws_id, title, desc, assignee, priority, status, due_date, pos, created_by)
        (t1_id, p1_id, ws1_id,
         'Thiết kế UI/UX Trang chủ & Product Detail',
         'Wireframe → Mockup Figma cho Homepage, Product Listing, Product Detail. Responsive breakpoints: mobile/tablet/desktop.',
         u_designer['id'], 'High', 'Completed', d_past2, 1, u_pm['id'], now, u_pm['id'], now),

        (t2_id, p1_id, ws1_id,
         'API Authentication & Phân quyền người dùng',
         'Xây dựng JWT Auth (access + refresh token), đăng ký/đăng nhập, reset password, phân quyền Role-Based.',
         u_dev['id'], 'Urgent', 'Completed', d_past1, 2, u_pm['id'], now, u_pm['id'], now),

        (t3_id, p1_id, ws1_id,
         'Tích hợp cổng thanh toán VNPAY & MoMo',
         'Kết nối SDK VNPAY sandbox, xử lý IPN webhook, hoàn tiền (refund), lưu lịch sử giao dịch.',
         u_dev['id'], 'Urgent', 'In Progress', d_future3, 3, u_pm['id'], now, u_pm['id'], now),

        (t4_id, p1_id, ws1_id,
         'Tối ưu SEO On-page & Core Web Vitals',
         'Schema markup, sitemap.xml, robots.txt, lazy loading hình ảnh, tối ưu LCP/CLS/FID.',
         u_designer['id'], 'Medium', 'To Do', d_future7, 4, u_pm['id'], now, u_pm['id'], now),

        (t5_id, p2_id, ws1_id,
         'Thiết kế Mockup màn hình App iOS (v2.0)',
         'UI screens: Onboarding, Login, Dashboard, Notification Center, Profile Settings — cập nhật Design System mới.',
         u_designer['id'], 'High', 'In Progress', d_future3, 1, u_pm['id'], now, u_pm['id'], now),

        (t6_id, p3_id, ws1_id,
         'Cấu hình Kubernetes (EKS) trên AWS',
         'Triển khai EKS cluster, setup ingress-nginx, cert-manager (Let\'s Encrypt), HPA auto-scaling.',
         u_dev['id'], 'High', 'To Do', d_future7, 1, u_admin['id'], now, u_admin['id'], now),

        (t7_id, p1_id, ws1_id,
         'Viết Unit Test & Integration Test Backend',
         'Đạt coverage ≥ 80% cho các service layer: Auth, Product, Cart, Order. Dùng pytest + httpx.',
         u_dev['id'], 'Medium', 'To Do', d_future14, 5, u_admin['id'], now, u_admin['id'], now),
    ]

    cursor.executemany(
        """INSERT INTO tasks
               (id, project_id, workspace_id, title, description, assignee_id,
                priority, status, due_date, position, created_by, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        tasks_data
    )

    # --------------------------------------------------------------- Task Labels
    task_labels_data = [
        (t1_id, l2_id, u_pm['id'], now),  # UI task → Feature
        (t1_id, l5_id, u_pm['id'], now),  # UI task → Design (cross-ws label via same user)
        (t2_id, l2_id, u_pm['id'], now),  # Auth API → Feature
        (t2_id, l3_id, u_pm['id'], now),  # Auth API → Refactor
        (t3_id, l2_id, u_pm['id'], now),  # Payment → Feature
        (t3_id, l1_id, u_pm['id'], now),  # Payment → Bug (tracking known issue)
        (t6_id, l3_id, u_admin['id'], now), # K8s → Refactor
        (t7_id, l4_id, u_admin['id'], now), # Testing task → Testing
    ]

    cursor.executemany(
        "INSERT OR IGNORE INTO task_labels (task_id, label_id, assigned_by, assigned_at) VALUES (?, ?, ?, ?)",
        task_labels_data
    )

    # --------------------------------------------------------------- Comments
    comments_data = [
        (uuid7(), t3_id,
         'Đã hoàn thành phần tạo URL thanh toán VNPAY sandbox và nhận IPN. Đang chờ review code trước khi merge.',
         0, u_dev['id'], now, u_dev['id'], now),

        (uuid7(), t3_id,
         '@dev_nam tốt! Cậu kiểm tra thêm edge case khi khách hủy giao dịch giữa chừng nhé. Xem tài liệu IPN section 4.3.',
         0, u_pm['id'], now, u_pm['id'], now),

        (uuid7(), t3_id,
         'Đã xử lý xong edge case hủy giao dịch. Opening PR #42 để review.',
         0, u_dev['id'], now, u_dev['id'], now),

        (uuid7(), t5_id,
         'Đã update Figma file lên v2.0. Link: figma.com/ttcs3-app-v2. Mọi người feedback trước thứ 6 nhé!',
         0, u_designer['id'], now, u_designer['id'], now),

        (uuid7(), t5_id,
         'Design đẹp lắm! Chỉ cần điều chỉnh màu nút CTA ở màn hình Onboarding cho đúng brand guideline.',
         0, u_pm['id'], now, u_pm['id'], now),

        (uuid7(), t1_id,
         'Đã bàn giao toàn bộ Figma assets cho dev. Đã export icon set SVG và design tokens vào Storybook.',
         0, u_designer['id'], now, u_designer['id'], now),
    ]

    cursor.executemany(
        """INSERT INTO comments (id, task_id, content, is_edited, created_by, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        comments_data
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def init_db(force: bool = False) -> None:
    """
    Khởi tạo database schema và nạp dữ liệu mẫu.
    
    Args:
        force: Nếu True, xóa toàn bộ dữ liệu cũ và tạo lại từ đầu.
    """
    if force and os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"[init_db] Deleted old database: {DB_FILE}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # Execute DDL (schema creation + indexes)
    cursor.executescript(SCHEMA_SQL)
    conn.commit()
    print("[init_db] Schema created successfully.")

    # Seed only if users table is empty
    row_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if row_count == 0:
        _seed_data(cursor)
        conn.commit()
        print("[init_db] Seed data inserted successfully.")
    else:
        print(f"[init_db] Skipping seed — already have {row_count} users in database.")

    conn.close()


# ---------------------------------------------------------------------------
# Utility helpers for app.py
# ---------------------------------------------------------------------------
def get_user_role_in_workspace(user_id: str, workspace_id: str) -> str | None:
    """Trả về Role của user trong workspace, hoặc None nếu không là thành viên."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT role FROM workspace_members WHERE user_id = ? AND workspace_id = ?",
        (user_id, workspace_id)
    ).fetchone()
    conn.close()
    return row['role'] if row else None


def check_workspace_permission(user_id: str, workspace_id: str, permission: str) -> bool:
    """Kiểm tra user có quyền thực hiện permission trong workspace không."""
    role = get_user_role_in_workspace(user_id, workspace_id)
    if not role:
        return False
    return has_permission(role, permission)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import sys
    # Ensure UTF-8 output on Windows terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 60)
    print("  TaskMaster - Database Initialization (UUID v7 + RBAC)")
    print("=" * 60)

    # Test UUID v7 output
    print("\n[TEST] Sample UUID v7 values:")
    for _ in range(3):
        print(f"  {uuid7()}")

    # Initialize the database (force=True to reset when run manually)
    print()
    init_db(force=True)

    # Verification summary
    conn = get_db_connection()
    tables = ['users', 'workspaces', 'workspace_members', 'workspace_invitations',
              'projects', 'tasks', 'labels', 'task_labels', 'comments']
    print("\n[VERIFY] Row counts per table:")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<28} {count:>3} rows")

    print("\n[VERIFY] RBAC role assignments in workspace_members:")
    rows = conn.execute("""
        SELECT u.fullname, w.name as ws_name, wm.role
        FROM workspace_members wm
        JOIN users u ON wm.user_id = u.id
        JOIN workspaces w ON wm.workspace_id = w.id
        ORDER BY w.name, wm.role
    """).fetchall()
    for r in rows:
        print(f"  [{r['role']:<7}] {r['fullname']:<30} → {r['ws_name']}")

    conn.close()
    print("\n✅ Database initialized successfully!")
