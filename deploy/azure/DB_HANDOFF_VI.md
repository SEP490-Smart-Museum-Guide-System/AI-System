# Thông tin gửi team BE để nối Scan — 19/11/2026

## Đã đo từ VM Azure

- VM: smgs-ai-server.
- IPv4 outbound đo qua HTTPS từ chính VM: **172.198.161.72**.
- CIDR allowlist: **172.198.161.72/32**.
- Ảnh Azure Public IP Configuration do user cung cấp xác nhận Assignment: Static,
  Public IP: 172.198.161.72. ARM API bị 403 nên xác nhận Static dựa trên ảnh portal.

## DB và quyền

- Dùng DB đang có trên EC2: **smgs_demo**.
- User riêng đề xuất: **smgs_scan**, không dùng user BE smgs.
- Schema: **ai_3d_scan**; bảng: **ai_3d_scan.scan_jobs**.
- Index: **ix_scan_jobs_status_created**, trên (status, created_at).
- Script đi kèm: **scan_database.sql**, khớp DDL hiện hành trong 3D Scan/app/jobs.py.
- Script đã qua 10 kiểm tra trên PostgreSQL 18.6 cục bộ tách biệt: chạy lại an
  toàn, startup Scan, tạo/claim/cập nhật/duyệt job, từ chối đọc bảng BE và tạo
  schema khác. Chưa thử xác thực mật khẩu/TLS hoặc kết nối EC2 production.
- UUID do ứng dụng tạo, không cần extension/sequence. artifact_id là metadata;
  service không cần SELECT hoặc FK vào bảng hiện vật của BE. Ảnh và GLB nằm ở
  volume Scan trên Azure, DB chỉ lưu job/metadata/đường dẫn nội bộ.

Chạy bằng administrator PostgreSQL trên EC2 đang bật, kết nối DB smgs_demo:

```sh
psql -X -v ON_ERROR_STOP=1 -U postgres -d smgs_demo -f scan_database.sql
```

Nếu PostgreSQL ở Docker, copy/mount script vào container DB rồi dùng psql trong
container đó theo tên container thật. Không tạo DB hoặc container production mới.

Script tạo role không có password, sau đó đặt mật khẩu riêng trong psql admin:

```text
SET password_encryption = 'scram-sha-256';
\password smgs_scan
```

Script không sửa bảng BE, không cấp CREATE trên toàn DB, không tự đổi owner của
schema/bảng Scan đã tồn tại dưới role khác. Nếu gặp trường hợp đó, admin cần xem
xét chuyển riêng các đối tượng Scan trước khi chạy lại. Không xóa dữ liệu Scan.

**Tương thích startup hiện tại:** role smgs_scan sở hữu schema/bảng Scan vì API
hiện chạy CREATE TABLE / ALTER TABLE / CREATE INDEX khi startup. Chỉ GRANT CRUD
trên bảng do admin sở hữu sẽ chưa đủ. Role không có SUPERUSER, CREATEDB,
CREATEROLE, REPLICATION, BYPASSRLS hoặc membership vào role BE. Nếu muốn runtime
chỉ có DML, cần tách migration khỏi startup trong một thay đổi ứng dụng riêng.
Bản Scan mới kiểm tra schema đã tồn tại trước khi tạo để không đòi quyền CREATE
trên toàn database cho schema được admin cấp sẵn; cần dùng bản này khi khởi động.
Các quyền cấp rộng cho PUBLIC đã có ở cluster cũng cần admin rà soát; script
không tự thu hồi quyền PUBLIC ngoài schema Scan để tránh ảnh hưởng BE.

## Chọn đường kết nối

1. **PostgreSQL qua TLS:** chỉ cho TCP 5432 từ 172.198.161.72/32 vào EC2, bật TLS
   và giới hạn DB/user/CIDR trong pg_hba.conf. Dòng gợi ý cho kết nối mới:

   ```text
   hostssl smgs_demo smgs_scan 172.198.161.72/32 scram-sha-256
   ```

   Rà soát thứ tự pg_hba.conf để rule rộng có sẵn không ghi đè giới hạn. PostgreSQL
   phải lắng nghe trên interface nội bộ EC2 phù hợp, không chỉ loopback. IP public
   EC2 thường là NAT; không tự gán 52.62.165.39 vào listen_addresses nếu IP đó
   không tồn tại trên NIC. Team BE cung cấp hostname khớp chứng chỉ và CA để phía
   Azure dùng verify-full; không tắt xác minh chứng chỉ để né lỗi.

2. **Đường hầm SSH/VPN:** giữ PostgreSQL chỉ ở 127.0.0.1:5432. Chỉ mở cổng đường
   hầm cho Azure và cấp tài khoản/key tunnel riêng. Cần địa chỉ tunnel có thể
   truy cập từ container Scan; localhost của container không phải loopback EC2.
   Chưa cài hoặc chọn tunnel nào trong phiên này.

Không mở 5432 cho toàn Internet. EC2 phải bật để kết nối hoạt động. Do stop/start
EC2 có thể đổi public IP nếu chưa có Elastic IP, team BE cần xác nhận endpoint
hiện tại thay vì mặc định IP 52.62.165.39 còn giữ nguyên.

Sau khi cấu hình, cung cấp endpoint/port, user smgs_scan, CA hoặc thông tin tunnel.
Mật khẩu điền riêng vào D:\SEP409\AI-System\deploy\azure\.env.azure:
AI_SYSTEM_DB_HOST / AI_SYSTEM_DB_PORT / AI_SYSTEM_DB_NAME=smgs_demo /
AI_SYSTEM_DB_USER=smgs_scan / AI_SYSTEM_DB_PASSWORD. Tham số TLS/tunnel sẽ được
cấu hình theo phương án thực tế trước khi bật profile Scan.

Nguồn quyền PostgreSQL: https://www.postgresql.org/docs/current/sql-createschema.html,
https://www.postgresql.org/docs/current/sql-altertable.html.
IP Azure: https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses.
