# Deploy Chatbot + Personalized Tour lên Hugging Face — 18/11/2026

## Phạm vi

Space mới: https://huggingface.co/spaces/Trungnam1644/smgs-ai-guide.
Hai chức năng có tab/API riêng trong cùng Space Gradio ZeroGPU. Không thay đổi
Space quiz `smgs-ai-quiz`. Không deploy Scan, TTS, Vision, BE hoặc FE trong bước này.

## Trạng thái kiểm chứng ngày 18/11/2026

| Hạng mục | Kết quả thực tế |
|---|---|
| Push và runtime | Commit `6273197d802ba21bd4deed0f2d913c77bdf86e75`, HF báo RUNNING trên ZeroGPU, SDK 0.51.3 |
| UI + HTTP/queue local | 42/42 kiểm tra đạt; **chat engine fixture**, thuật toán tour thật |
| Test tour gốc | 9/9 đạt; source/schema export không thay đổi |
| Qwen CPU thật | Budget 45 s: 2/3, một JSON bị cắt và bị chặn; budget thử riêng 90 s: 3/3. Giữ cả hai báo cáo, không dùng budget CPU 90 s làm bằng chứng hiệu năng GPU |
| Tour trên HF | Đổi gốm/đồng làm thay đổi điểm dừng; budget 5 phút trả 0 điểm đúng; dữ liệu giả lập |
| Chat GPU trên HF | Model đã nạp CUDA; lượt inference bị HF chặn do hết quota anonymous. **Chưa xác nhận một lượt chat GPU thành công** |
| REST cloud có key | Chưa test: hai Secret chưa cấu hình tại lần kiểm tra; `/ready` báo 503 configuration_required |

Bằng chứng: `guide-contract-20261118.json`, `guide-real-cpu-20261118.json`,
`guide-real-cpu-budget90-20261118.json`, `guide-live-6273197-20261118.json`.
Lượt live có 7/8 check đạt; check inference chatbot thất bại vì quota, không bị xóa
khỏi báo cáo. Cần thử chatbot từ phiên HF đã đăng nhập còn quota, và thêm hai
Secrets trước khi kiểm chứng REST có xác thực. Không đọc/trích Git credentials.

**Cập nhật 15:35:** hai Secrets đã được cấu hình; `/ready` trả 200, model CUDA,
`chat_api_configured=true` và `tour_api_configured=true`. Xem
`guide-readiness-20261118.json`. Chưa kiểm chứng REST có xác thực hoặc inference GPU
thành công. User đã gửi giá trị key trong chat, nên cần thay mới trong HF Secrets;
không lưu các giá trị đó vào tài liệu/code/log. Chưa xác nhận việc thay mới.

**Kiểm thử tour mở rộng:** chạy lại trên HF thật với 12 ca, **64/64 kiểm tra đạt**;
chi tiết request/response trong `tour-live-20261118.json`. Bao gồm đổi sở thích,
budget sát biên/không đủ, maxStops, fallback, kết quả lặp ổn định, không bịa/trùng
ID và từ chối request sai bảo tàng/ID/thời gian. Kiểm tra REST chặn thiếu/sai key
đã đạt; REST thành công với đúng key mới vẫn chưa thử. Đây là kiểm chứng thuật
toán cloud trên dữ liệu giả lập, không phải lưu tour hoặc kiểm quyền nghiệp vụ.

Có thể chạy lại và nhập key **ẩn trên máy**, không ghi key vào file/lệnh/chat:

```powershell
cd D:\SEP409
.\AI-System\.venv\Scripts\python.exe -X utf8 .\AI-System\deploy\huggingface\verify_live_tour.py --prompt-key --output .\tmp\hf-tour-rest-verification.json
```

Không có `--prompt-key` thì script chạy các ca qua Gradio public và đánh dấu
`authenticatedRestTested=false`, không báo giả rằng đã kiểm REST thành công.

- Chatbot: adapter PyTorch Qwen2.5-1.5B, prompt/parser/source guard từ service ONNX hiện có.
- Tour cá nhân: giữ nguyên thuật toán TF-IDF, giới hạn thời gian và schema của `AI Tour`.
- Hai API stateless, nhận dữ liệu trong request; không cần cấu hình Supabase hoặc DB để chạy.
  Không tự nạp hồ sơ hiện vật, kiểm quyền người dùng, lưu lịch sử hoặc lưu tour.

## Chuẩn bị bộ code

PowerShell, tại `D:\SEP409`:

```powershell
.\AI-System\.venv\Scripts\python.exe .\AI-System\tools\prepare-hf-space.py .\tmp\hf-smgs-guide-20261118 --sdk gradio --service guide
```

Exporter chỉ ghi vào **folder mới** và chỉ copy allowlist: adapter, prompt/guard,
thuật toán/schema tour, ví dụ giả lập và dependency/README. Không copy `.env`,
ảnh, DB, token hoặc model cache. Lần sau dùng tên folder mới nếu folder đã tồn tại.

Repo Space để commit/push riêng:

```powershell
git clone https://huggingface.co/spaces/Trungnam1644/smgs-ai-guide D:\SEP409\tmp\hf-gradio-smgs-ai-guide-20261118
```

Khi đã clone thì không chạy clone lần nữa. Bộ export được copy vào repo Space,
giữ thư mục `.git`; dùng `git status` kiểm tra đúng file trước khi commit.

## Cấu hình HF

1. SDK **Gradio**, template **Blank**, hardware **ZeroGPU**.
2. Giữ `sdk_version: 6.32.0`, Python 3.12 trong README được export.
3. Settings → Variables and secrets → **Secrets**:
   - `AI_CHAT_SERVICE_KEY`: chuỗi ngẫu nhiên tối thiểu 32 ký tự.
   - `AI_TOUR_SERVICE_KEY`: chuỗi ngẫu nhiên khác, tối thiểu 32 ký tự.
4. Không đặt password DB, token HF, key vào public Variables, source code hoặc input UI.
   Không gửi key vào chat. Public demo UI vẫn mở; hai Secret chỉ bảo vệ REST riêng.
5. HF quản lý phiên bản `spaces` tương thích; không ghim phiên bản SDK khác trong requirements.

Từ folder repo Space, sau khi copy bundle:

```powershell
git add app.py contracts.py pytorch_engine.py examples.json requirements.txt README.md app tour .dockerignore
git commit -m "Deploy SMGS artifact chatbot and personalized tours"
git push
```

Git dùng thông tin xác thực sẵn có; nếu hỏi password thì dùng HF write token qua
credential prompt, không gắn token vào URL/lệnh hoặc commit.

## Kiểm tra sau build

- URL ứng dụng dự kiến: https://trungnam1644-smgs-ai-guide.hf.space.
- `/live`: process đang chạy.
- `/ready`: model đã nạp, hai REST key đủ dài. Thiếu Secret trả 503 nhưng demo UI
  vẫn có thể dùng. Không nhầm readiness với quota GPU hoặc đảm bảo đáp án đúng.
- Tab Chatbot: dùng tư liệu giả lập trong UI, hỏi chất liệu; thử câu hỏi về năm
  chế tác không có trong tư liệu. Kiểm tra cả trường `supported` và nội dung trả lời.
- Tab Tour cá nhân: đổi `interests` từ `gốm` sang `đồng`, kiểm tra các điểm được chọn;
  giảm quỹ thời gian để kiểm tra không vượt budget. Không có điểm phù hợp hoặc thiếu
  thời gian được báo rõ, không chèn hiện vật giả.

## API giữ hợp đồng hiện tại

| API | Header | Input | Output |
|---|---|---|---|
| `POST /api/v1/guide/answers` | `X-Service-Key` = chat Secret | `context`, `question`, `history` | `answer`, `supported` |
| `POST /api/v1/tours/recommend` | `X-Service-Key` = tour Secret | `museumId`, `availableMinutes`, `interests`, `maxStops`, `candidates` | `engineVersion`, `estimatedMinutes`, `usedFallback`, `notice`, `stops` |

Request mẫu đầy đủ nằm trong `gradio-guide/examples.json` và được export ra root
Space. Chat không tự lấy nguồn từ DB: bên gọi phải gửi `artifactId`, `artifactName`,
`title`, `description`, optional `narrationText`. Lịch sử tối đa bốn cặp user/assistant.
Tour nhận 1–500 ứng viên cùng bảo tàng, 1–8 sở thích, 5–240 phút và tối đa 30 điểm.

REST chat đi qua queue Gradio rồi mới vào hàm `@spaces.GPU`; không gọi GPU trực
tiếp ngoài context Gradio. Worker trả envelope nội bộ để giữ lỗi 422/502/503/504;
REST gỡ envelope và kiểm tra nguồn lại trước khi trả schema gốc.
Tour REST chạy CPU trực tiếp, không gọi model hoặc xin GPU.

Khi nối caller sau này, hai BaseUrl cùng dùng host Space mới; hai service key riêng.
Chỉ endpoint chatbot và tour được triển khai ở đây. Không trỏ endpoint narration/
quiz/scan/TTS vào Space này. Space quiz hiện tại tiếp tục dùng host của chính nó.

## Giới hạn đã biết

- HF Free có điều kiện tài khoản và tối đa hai ZeroGPU Spaces; không mặc định
  cho phép tạo thêm CPU Docker/Gradio Space. Nguồn: https://huggingface.co/docs/hub/en/spaces-overview.
- Chat qua loopback bridge sử dụng quota anonymous; key dịch vụ không nâng quota.
  Có hàng đợi/cold start/sleep, không cam kết uptime 24/7. Không dùng keepalive né sleep.
  Nguồn: https://huggingface.co/docs/hub/en/spaces-zerogpu.
- Chỉ cho nhập tư liệu được phép dùng trên demo công khai. Không lưu dữ liệu người
  dùng vào repo/log; shared Space vẫn là hạ tầng bên thứ ba xử lý request.
- Source guard kiểm tra câu trả lời nằm trong nguồn, không chứng minh đúng ngữ nghĩa.
  Bộ câu hỏi/nguồn thử giả lập không thay thế đánh giá với hiện vật thật.
- Tour dùng ước tính di chuyển theo phòng/tầng; không phải tìm đường trong nhà.
- Hai tính năng có chung lifecycle Space; model khởi động hoặc Space ngủ ảnh hưởng
  cả hai, dù tour không cần quota GPU.

## Bằng chứng kiểm thử

`check_guide_contract.py`: chạy HTTP + queue Gradio thật với **chat engine fixture**,
thuật toán tour thật, kiểm auth/body limit/schema/tour và lỗi GPU bridge. Không phải
kiểm chứng inference thật hoặc quota HF.

`check_real_guide_cpu.py`: chạy checkpoint Qwen thật đã tải, trên CPU, nguồn giả lập.
Không phải bằng chứng GPU trên HF. Kết quả và trạng thái deploy thực tế được ghi trong
`IMPLEMENTATION_LOG.md`; không coi việc export/push là một lượt cloud inference thành công.
