# Deploy SMGS gen quiz lên Hugging Face Spaces — 17/11/2026

**Space `Trungnam1644/smgs-ai-quiz` đã chọn Gradio/ZeroGPU:** làm theo [hướng dẫn Gradio riêng](GRADIO_GUIDE_VI.md). Phần Docker dưới đây là lựa chọn khác, không áp dụng nguyên bộ cho Space Gradio.

## Chọn phần nào trước

**Gen quiz/thuyết minh trước**: service `AI Chat` nhận nội dung từ BE, chạy Qwen2.5-1.5B ONNX Q4 và trả bản nháp. Không cần kết nối PostgreSQL trực tiếp. BE vẫn giữ phân quyền, lấy nguồn hiện vật và lưu nội dung sau kiểm duyệt.

Thông tin “Docker Spaces miễn phí hoàn toàn/free mãi mãi” không còn đúng cho mọi tài khoản: tài liệu HF hiện yêu cầu gói trả phí để tạo Docker Space mới, dù CPU Basic không có phí theo giờ. CPU Basic được niêm yết 2 vCPU, 16 GB RAM. Kiểm tra quyền tạo Space và giá trên tài khoản của bạn trước khi đăng ký; hướng dẫn này không mua gói hay tạo Space thay bạn.

Nguồn: [Spaces overview](https://huggingface.co/docs/hub/en/spaces-overview), [quyền tạo compute Space](https://huggingface.co/docs/huggingface_hub/en/guides/manage-spaces#create-a-space-on-the-hub).

## 1. Bộ file đã chuẩn bị

Máy hiện tại có bundle tại `D:\SEP409\tmp\hf-smgs-quiz-20261117`.
Muốn tạo lại sau khi sửa code, dùng folder MỚI:

```powershell
cd D:\SEP409\AI-System
python tools/prepare-hf-space.py D:\SEP409\tmp\hf-smgs-quiz-moi
```

Bundle chỉ có Dockerfile, README cấu hình Spaces, requirements, app Python và script tải model đã khóa revision. Không copy `.env`, ảnh, DB hay cache local. Không upload toàn bộ repo AI-System lên Space.

Dockerfile cài dependencies, tải model công khai khi build, chạy user UID 1000 và uvicorn cổng 7860. Model được đóng trong image; không phải tải lại ở mỗi request. Đã đặt `AI_CHAT_NUM_THREADS=2` cho CPU Basic. Build lần đầu cần Internet và có thể mất vài phút.

## 2. Tạo Space

Vào [Create Space](https://huggingface.co/new-space):

1. Owner: tài khoản của bạn; tên: `smgs-ai-quiz`.
2. SDK: **Docker**, template **Blank**.
3. Hardware: CPU Basic nếu tài khoản được phép. Nếu HF yêu cầu trả phí, kiểm tra chi phí trước khi tiếp tục.
4. Chọn **Public** cho cách tích hợp BE hiện tại: source code công khai, API nghiệp vụ vẫn cần `X-Service-Key`. Space Private cần thêm xác thực HF mà client BE hiện tại chưa gửi.
5. Trong Settings → Secrets, thêm `AI_CHAT_SERVICE_KEY`: một chuỗi ngẫu nhiên dài tối thiểu 32 ký tự. Không ghi vào Dockerfile, README, Git hoặc FE.

Có thể tự tạo khóa trên máy:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 3. Đẩy bộ file lên repo Space

Ví dụ `TEN_HF` là username của bạn:

```powershell
cd D:\SEP409\tmp
git clone https://huggingface.co/spaces/TEN_HF/smgs-ai-quiz
Get-ChildItem -LiteralPath D:\SEP409\tmp\hf-smgs-quiz-20261117 -Force |
    Copy-Item -Destination D:\SEP409\tmp\smgs-ai-quiz -Recurse -Force
cd D:\SEP409\tmp\smgs-ai-quiz
git add .
git commit -m "Deploy SMGS quiz ONNX API"
git push
```

Git cần quyền ghi vào đúng repo Space. Xác thực bằng công cụ HF/Git của tài khoản; không nhúng token trong URL hoặc gửi token vào chat. Code push xong sẽ kích hoạt build. Xem Build logs và Container logs trên trang Space.

Đây là API; trang `/docs` là tài liệu FastAPI, không phải giao diện staff SMGS.

## 4. Kiểm tra trực tiếp trước khi nối BE

Lấy app URL thực tế dạng `https://TEN-HF-smgs-ai-quiz.hf.space` từ Space.

```powershell
$spaceUrl = 'https://TEN-HF-smgs-ai-quiz.hf.space'
Invoke-RestMethod "$spaceUrl/ready"
```

Chỉ nối BE khi trả `status: ok`, `model_ready: true`. Không có cam kết wake trong 30 giây; build, cold start và tải model phụ thuộc dịch vụ. Nếu 503, xem log và kiểm tra Secret/model.

Test một quiz (đặt biến môi trường `AI_CHAT_SERVICE_KEY` trên terminal bằng cùng khóa ở HF):

```powershell
$quizBody = @{
    artifactId = 1
    artifactName = 'Bình gốm DEMO'
    sourceText = 'Bình gốm được dùng để đựng nước. Đây là tư liệu giả lập để kiểm thử phần mềm.'
    mode = 'quiz'
    difficulty = 'easy'
} | ConvertTo-Json
Invoke-RestMethod "$spaceUrl/api/v1/studio/drafts" -Method Post `
    -Headers @{ 'X-Service-Key' = $env:AI_CHAT_SERVICE_KEY } `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($quizBody)) -TimeoutSec 240
```

Đầu ra là bản nháp cần kiểm tra đáp án và nguồn; không tự xuất bản. Đây là ví dụ payload, không tạo hiện vật ID 1 trên server.

## 5. Nối BE/FE hiện có

Đặt trên môi trường chạy Backend:

```text
ArtifactGuide__Enabled=true
ArtifactGuide__BaseUrl=https://TEN-HF-smgs-ai-quiz.hf.space/
ArtifactGuide__ServiceKey=<cùng khóa AI_CHAT_SERVICE_KEY trong Space>
```

Khởi động lại BE. FE tiếp tục gọi BE `/api/artifacts/{id}/ai/drafts`; BE gọi Space `/api/v1/studio/drafts`. Dùng ID hiện vật thật và nguồn được BE chọn. Không đưa service key vào biến VITE/Flutter.

Nếu chạy bằng `BackEnd/tools/start-with-ai.ps1`, script đó ghi đè BaseUrl về localhost. Khi dùng Space, chạy BE trực tiếp với ba biến trên và cấu hình DB hiện có, hoặc điều chỉnh launcher có chủ đích. Timeout client draft BE/FE hiện tại là 240 giây; cần đo trên HF, không suy ra tốc độ từ máy local. Tránh gọi nhiều request cùng lúc: engine hiện xử lý một lần suy luận mỗi instance.

## Scan 3D: chưa thể deploy nguyên trạng theo cách trên

Scan cần COLMAP/OpenMVS binaries nên Dockerfile Python tối giản không đủ. Repo đã có Dockerfile CPU cài chúng. Tuy nhiên:

- Service hiện dùng psycopg kết nối PostgreSQL trực tiếp, mặc định 5432. Tài liệu HF chỉ cho egress cổng 80/443/8080, nên không thể mặc định dùng DB này từ Space. `localhost`/`host.docker.internal` trên HF cũng không phải máy Windows của bạn.
- Job metadata, ảnh và GLB phải sống qua restart. Disk Space là ephemeral; cần volume/storage ngoài và cách khôi phục job. Không coi GLB trên disk tạm là dữ liệu đã lưu bền vững.
- Worker hiện là background task một instance, chưa có lease/resume cho job đang xử lý bị dừng. 2 vCPU sẽ phải benchmark lại cho bộ 180 ảnh; chưa có bằng chứng thời gian/độ ổn định trên HF.

Nguồn: [Networking](https://huggingface.co/docs/hub/en/spaces-overview#networking), [disk/storage](https://huggingface.co/docs/hub/en/spaces-storage), [Docker Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-docker).

Phương án giữ kiến trúc hiện tại: đưa **quiz lên HF**, giữ **scan CPU trên máy local/VPS** có thể kết nối DB BE và giữ volume `/data`. BE gọi hai địa chỉ service khác nhau. Nếu bắt buộc scan trên HF, cần xử lý đường kết nối DB được hỗ trợ và lưu trữ/job recovery trước; chưa triển khai các thay đổi đó trong gói này.

## Kiểm chứng và giới hạn

- Đã xuất bundle local bằng allowlist; chưa upload, chưa tạo Space và chưa dùng phần cứng tính phí.
- 15/16 tests chat/studio qua. Một test `test_question_answer_consistency_requires_independent_grounded_answer` thất bại cả trên HEAD gốc lẫn bản thêm cấu hình threads: logic hiện bỏ lượt kiểm chứng đáp án độc lập, còn test vẫn yêu cầu lượt đó. Không sửa/xóa test để giấu lỗi; đây là giới hạn cần xử lý trước khi công bố chất lượng quiz.
- Dockerfile bundle đã build thành công, tải đủ graph/tokenizer đúng revision. Container local giới hạn 2 CPU/16 GiB: `/ready` HTTP 200 với ONNX CPU; API không có khóa HTTP 401; một quiz mẫu HTTP 200 sau **19,14 giây** (thời gian request, không gồm build/startup). Container thử đã dừng. Xem [kết quả gốc](local-check-20261117.json). Một ca ngắn không chứng minh tốc độ/chất lượng tổng quát; chưa chạy trên runtime Hugging Face.
