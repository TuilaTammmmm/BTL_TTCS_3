# BTL Thực Tập Cơ Sở 3 - Hệ Thống Quản Lý Bán Hàng & Tồn Kho (Flask + SQLite + Jinja2 + Bootstrap)

Hệ thống Quản lý Bán hàng & Tồn kho chuyên nghiệp được phát triển cho Bài Tập Lớn Thực Tập Cơ Sở 3 (BTL TTCS3) bằng ngôn ngữ **Python**, framework **Flask**, cơ sở dữ liệu **SQLite**, bộ sinh giao diện **Jinja2** và thiết kế hiện đại với **Bootstrap 5**.

---

## 🚀 Tính Năng Nổi Bật

1. **Quản Lý Đăng Nhập & Phân Quyền (Authentication & Sessions)**:
   - Đăng nhập bảo mật với mật khẩu mã hóa `Werkzeug (PBKDF2/SHA256)`.
   - Phân quyền tài khoản `Admin` và `Staff` (Nhân viên).
   - Tự động lưu và theo dõi phiên đăng nhập (`Session`).

2. **Bảng Điều Khiển Tổng Quan (Dashboard)**:
   - Thống kê KPI thời gian thực: Doanh thu tích lũy, tổng số đơn hàng, tổng số sản phẩm, cảnh báo hàng sắp hết trong kho.
   - Biểu đồ tương tác **Chart.js** xếp hạng Top 5 sản phẩm bán chạy nhất.
   - Danh sách các đơn hàng vừa phát sinh.

3. **Quản Lý Sản Phẩm & Tồn Kho (Products & Inventory)**:
   - Tìm kiếm sản phẩm theo Mã SP (SKU) hoặc Tên sản phẩm.
   - Lọc sản phẩm theo từng Danh mục.
   - Thêm sản phẩm mới, chỉnh sửa thông tin, giá bán, giá vốn nhập, tồn kho, đơn vị tính.
   - Cảnh báo tự động badge màu sắc đối với sản phẩm sắp hết kho ($\le 10$).

4. **Quản Lý Danh Mục (Categories)**:
   - Phân loại sản phẩm khoa học.
   - Thống kê tự động số lượng sản phẩm thuộc mỗi danh mục.

5. **Quản Lý Khách Hàng (Customers)**:
   - Danh bạ thông tin khách hàng: Họ tên, số điện thoại, email, địa chỉ giao hàng.
   - Thống kê tự động tổng số đơn hàng và tổng số tiền khách hàng đã mua.

6. **Tạo Đơn Hàng Mới / Điểm Bán Hàng (POS - Point of Sale)**:
   - Giao diện bán hàng linh hoạt, cho phép thêm dynamic nhiều dòng sản phẩm trong 1 đơn.
   - Tự động tính tổng tiền thực tế theo thời gian thực bằng JavaScript.
   - Kiểm tra và tự động giới hạn số lượng bán không vượt quá số lượng còn lại trong kho.
   - Lựa chọn hình thức thanh toán (Tiền mặt, Chuyển khoản QR, Quẹt thẻ POS).

7. **Chi Tiết Đơn Hàng & In Hóa Đơn (Order Invoice)**:
   - Giao diện hóa đơn bán hàng chuẩn thiết kế in ấn (Printable Layout CSS `@media print`).
   - Hỗ trợ nút In Hóa Đơn trực tiếp cho khách hàng.
   - Cho phép cập nhật trạng thái đơn hàng: *Hoàn thành*, *Đang xử lý*, *Đã hủy*.

8. **Báo Cáo & Phân Tích (Reports & Analytics)**:
   - Biểu đồ Doughnut tỷ lệ doanh thu theo danh mục sản phẩm.
   - Biểu đồ Bar biểu diễn doanh thu qua các tháng.

---

## 🛠 Hướng Dẫn Cài Đặt & Khởi Chạy

### 1. Chuẩn bị Môi trường
Yêu cầu hệ thống đã cài đặt **Python 3.8+**.

### 2. Cài đặt Thư viện
Mở Terminal / Command Prompt tại thư mục dự án và chạy:

```bash
# Tạo môi trường ảo (Virtualenv)
python -m venv venv

# Kích hoạt môi trường ảo (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Cài đặt thư viện yêu cầu
pip install -r requirements.txt
```

### 3. Khởi tạo Cơ sở dữ liệu SQLite
Chạy file `database.py` để tạo cơ sở dữ liệu `app_data.db` và nạp dữ liệu mẫu ban đầu:

```bash
python database.py
```

### 4. Khởi chạy Ứng dụng Flask
Chạy file `app.py`:

```bash
python app.py
```

Truy cập ứng dụng trên trình duyệt web tại đường dẫn: **`http://127.0.0.1:5000`**

---

## 🔑 Tài Khoản Đăng Nhập Mẫu

| Vai trò | Tên đăng nhập | Mật khẩu | Quyền hạn |
|---|---|---|---|
| **Quản trị viên (Admin)** | `admin` | `admin123` | Toàn quyền quản lý hệ thống |
| **Nhân viên (Staff)** | `nhanvien` | `staff123` | Tạo đơn hàng, xem danh sách sản phẩm & đơn hàng |

---

## 📁 Cấu Trúc Thư Mục Dự Án

```text
BTL_TTCS_3/
├── app.py                  # Server application chính (Routing, Authentication, Controllers)
├── database.py             # Khởi tạo SQLite database schema & dữ liệu mẫu initial seed
├── requirements.txt        # Thư viện phụ thuộc (Flask, Werkzeug, Jinja2, etc.)
├── app_data.db             # Cơ sở dữ liệu SQLite (Tự động khởi tạo khi chạy lần đầu)
├── static/
│   └── css/
│       └── style.css       # CSS tùy chỉnh bổ sung cho Bootstrap 5
├── templates/
│   ├── base.html           # Layout khung cơ bản (Sidebar, Header, Footer, Clock)
│   ├── login.html          # Trang đăng nhập
│   ├── dashboard.html      # Trang Tổng quan & KPI Dashboard
│   ├── products.html       # Trang Quản lý Sản phẩm & Tồn kho
│   ├── categories.html     # Trang Quản lý Danh mục sản phẩm
│   ├── customers.html      # Trang Quản lý Khách hàng
│   ├── orders.html         # Trang Quản lý Lịch sử Đơn hàng
│   ├── order_create.html   # Trang Tạo Đơn Hàng Mới (POS)
│   ├── order_detail.html   # Trang Chi tiết & In Hóa Đơn Bán Hàng
│   └── reports.html        # Trang Báo Cáo Doanh Thu (Charts)
└── README.md               # Tài liệu hướng dẫn dự án
```
