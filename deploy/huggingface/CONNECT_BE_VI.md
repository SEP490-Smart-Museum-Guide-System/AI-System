# Nối hai Space HF với BE — 19/11/2026

BE: https://smgs-52-62-165-39.sslip.io. Hai API đọc công khai
`/api/museums/cities` và `/api/museums?pageSize=1` đã trả HTTP 200.
Chưa kiểm chứng AI production với JWT/service key. Theo người dùng, PostgreSQL
nằm trên máy chủ BE. HF nhận nguồn từ request BE, không cần mật khẩu DB.

## 1. Secret trên HF

Mở Settings → Variables and secrets → Secrets của từng Space:

| Space | Secret | Tên gọi dưới đây |
|---|---|---|
| `Trungnam1644/smgs-ai-quiz` | `AI_CHAT_SERVICE_KEY` | QUIZ_KEY |
| `Trungnam1644/smgs-ai-guide` | `AI_CHAT_SERVICE_KEY` | CHAT_KEY |
| `Trungnam1644/smgs-ai-guide` | `AI_TOUR_SERVICE_KEY` | TOUR_KEY |

Mỗi giá trị dài ít nhất 32 ký tự; các khóa có thể khác nhau. Nếu không còn giữ
Secret cũ, đặt giá trị mới rồi cập nhật BE tương ứng. Không gửi key qua chat,
commit vào Git hoặc đưa ra FE. Không dùng HF access token thay service key.

## 2. Tách cấu hình quiz khỏi chatbot trong BE

Code workspace hiện tại dùng chung `GuideModelOptions`/`ArtifactGuide` cho
`LocalStaffAiModel` (quiz) và `LocalArtifactGuideModel` (chatbot). Chỉ thêm
`StaffAi__BaseUrl` khi chưa sửa code sẽ không có tác dụng.
Hướng dẫn này chưa sửa hoặc redeploy BE.

Trong `SMGS.Infrastructure/DependencyInjection.cs`, giữ đăng ký ArtifactGuide
hiện có, thêm bên dưới:

```csharp
services.AddOptions<GuideModelOptions>("StaffAi")
    .Bind(configuration.GetSection("StaffAi"));
```

Trong `SMGS.Infrastructure/Services/LocalStaffAiModel.cs`, đổi tham số constructor
`IOptions<GuideModelOptions> options` thành:

```csharp
IOptionsMonitor<GuideModelOptions> options
```

Đổi dòng `var config = options.Value;` thành:

```csharp
var config = options.Get("StaffAi");
```

Giữ nguyên LocalArtifactGuideModel và PersonalizedTourModel. Nếu bộ test BE tạo
LocalStaffAiModel trực tiếp, cập nhật mock IOptionsMonitor.Get("StaffAi").
Build/test BE trước khi redeploy. Đây là [named options của ASP.NET Core](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/configuration/options?view=aspnetcore-8.0#named-options-support-using-iconfigurenamedoptions).

## 3. Cấu hình process/container BE production

Thay placeholder bằng khóa đúng Space; không giữ dấu `< >` trong giá trị thật:

```dotenv
ArtifactGuide__Enabled=true
ArtifactGuide__BaseUrl=https://trungnam1644-smgs-ai-guide.hf.space/
ArtifactGuide__ServiceKey=<CHAT_KEY>

StaffAi__Enabled=true
StaffAi__BaseUrl=https://trungnam1644-smgs-ai-quiz.hf.space/
StaffAi__ServiceKey=<QUIZ_KEY>

PersonalizedTours__BaseUrl=https://trungnam1644-smgs-ai-guide.hf.space/
PersonalizedTours__ServiceKey=<TOUR_KEY>
```

Dùng app URL `.hf.space`, không dùng trang repo `huggingface.co/spaces/...`.
Giữ `/` cuối và không nối `/api/v1` vào BaseUrl. Giữ cấu hình DB đang chạy.

Docker Compose: khai báo file chứa tám biến trên bằng `env_file: ./be-ai.env`
ở service BE, hoặc map đủ biến trong `environment:`. `.env` dùng nội suy không
tự truyền tất cả biến vào container. Giữ file khóa ngoài Git. Rebuild image với
code bước 2 rồi recreate riêng service BE theo tên service thật. Restart container
cũ không nạp image/env mới. Không chạy `down -v` hoặc thay service DB.

Systemd: đặt biến trong EnvironmentFile của unit BE, publish build mới rồi restart
đúng unit. Script local `BackEnd/tools/start-with-ai.ps1` đặt URL lại localhost,
nên không dùng script đó để chạy BE production với HF.

## 4. Kiểm tra

Chờ Space Running; GET `/ready` của hai host HF kiểm tra khởi động. Điều này chưa
chứng minh còn quota hoặc inference thành công.

| Chức năng | API HF, header X-Service-Key |
|---|---|
| Quiz nháp | quiz host: POST `/api/v1/studio/drafts`, mode=quiz |
| Chat hiện vật | guide host: POST `/api/v1/guide/answers` |
| Tour cá nhân | guide host: POST `/api/v1/tours/recommend` |

FE vẫn gọi BE bằng JWT. BE lấy tư liệu/ứng viên từ DB và gửi HF, không tự biết dữ
liệu chỉ vì đã deploy. Thử quiz bằng tài khoản Staff/Admin với hiện vật có nguồn;
chat bằng Visitor với hiện vật đã xuất bản; tour bằng bảo tàng có ứng viên hợp lệ.
Kiểm tra kết quả và trạng thái lưu, không chỉ HTTP 200. Quiz HF chưa cung cấp gen
narration. 401 từ HF thường do key; 404 kiểm tra host/API; 503/504 cần đối chiếu
readiness/quota/timeout. Không đưa service key ra FE.
