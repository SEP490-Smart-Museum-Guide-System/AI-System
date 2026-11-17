# SMGS Quiz — Space Gradio của Trungnam1644

Space đã tạo: https://huggingface.co/spaces/Trungnam1644/smgs-ai-quiz

Space này dùng **Gradio / ZeroGPU**, không dùng Dockerfile ONNX. Đoạn `greet()` Hugging Face gợi ý chỉ là ví dụ tensor; bộ file dưới đây tạo quiz từ tư liệu theo prompt và validator đang dùng trong SMGS.

## Cập nhật xác minh HF — commit 465b25b

Đã kiểm tra runtime thật lúc 22:36 ngày 17/11/2026 (Việt Nam): RUNNING, readiness CUDA, bộ nguồn giả lập bình gốm trả **5/5 câu khác chủ đề, complete=true** sau 4,08 giây. Đã đối chiếu từng câu/đáp án/trích dẫn: công dụng, chất liệu, miệng bình, trang trí, kỹ thuật. [Raw HF response](gradio-live-quality-465b25b-20261117.json), [postflight](gradio-live-quality-review-465b25b-20261117.json). Đây là một lượt demo thành công, chưa phải benchmark nhiều nguồn hoặc kiểm chứng toàn bộ FE/BE/DB.

Log user có `Exception ignored in BaseEventLoop.__del__` / `Invalid file descriptor: -1` ở bước dọn dẹp asyncio. Space và lượt tạo vừa kiểm tra vẫn thành công, nên chưa có bằng chứng cảnh báo đó làm chết service. Chưa xác định chính xác root cause; không vá/suppress toàn bộ asyncio để che log. Có [báo cáo upstream tương tự](https://github.com/gradio-app/gradio/issues/12699). Không cần bật Gradio share tunnel để dùng app đã host trên HF.

## Bản tổng hợp để push một lần — logic chất lượng

Bản hiện tại là **hybrid có ràng buộc nguồn**: AI soạn câu hỏi, không tự bịa đáp án đúng hoặc câu trích. Với các dạng dữ kiện nhận diện được (công dụng, chất liệu, hình dáng, trang trí, kỹ thuật), luật lấy đáp án nguyên văn từ nguồn và chọn ba phương án nhiễu tiếng Việt trong bộ từ vựng có kiểm soát; vị trí đáp án được xáo trộn. Model vẫn phải trả một câu hỏi hợp lệ: không tự điền question từ mẫu khi model trả rỗng/sai. Dạng dữ kiện chưa được luật hỗ trợ vẫn dùng đường JSON đầy đủ và validator chặt hơn, nên độ bao phủ cần đánh giá tiếp.

- Tách đoạn/ý nguồn tại câu, dấu chấm phẩy và các mệnh đề thuộc tính; giữ trích dẫn là substring gốc. Bỏ disclaimer kiểm thử, loại đoạn trùng và ưu tiên các chủ đề khác nhau.
- Chặn lỗi đã quan sát: hỏi lại cùng ý/đáp án, lệch chủ đề, câu phủ định/Có-Không, chèn chữ Trung Quốc/tiếng Anh; đây là **heuristics**, chưa phải bộ xác minh ngữ nghĩa độc lập, vẫn có thể bỏ sót hoặc chặn nhầm.
- Tối đa hai lần thử cho một dữ kiện, retry có lý do lỗi và sampling nhẹ có seed. Không dừng cả bộ chỉ vì một dữ kiện lỗi nếu còn dữ kiện khác; giới hạn tổng lượt inference và budget 85 giây. Quota/timeout dừng bộ, giữ kết quả một phần và báo đúng số lượng.

**Đã thử model thật local:** Qwen2.5-1.5B cùng checkpoint ghim, CPU **bfloat16**, hai bộ nguồn giả lập bình gốm và trống: mỗi bộ **5/5 câu, năm chủ đề riêng**, tổng 10 câu/10 lượt đầu. Đã đối chiếu câu hỏi, đáp án, trích dẫn và chạy guard bản cuối. CPU mất 157,81 và 151,95 giây, với budget kiểm thử riêng 360 giây; **không suy ra rằng CPU hoàn tất trong budget GPU 85 giây**. Chưa kiểm tra bản tổng hợp mới trên HF sau push, chưa có đánh giá corpus bảo tàng thật hoặc curator duyệt.

Giữ bằng chứng riêng: [raw Qwen CPU](qwen-real-hybrid-cpu-20261117.json), [đối chiếu sau sinh](qwen-real-hybrid-review-20261117.json). Các báo cáo lỗi HF/CPU trước đó vẫn giữ nguyên, không thay bằng kết quả mới.

Kiểm tra bản bàn giao: 26 unit/adversarial tests và [39 contract/API/queue checks](gradio-quality-final-check-20261117.json) qua. Chạy unit bằng `python -B -m unittest discover -s deploy/huggingface/tests -v` từ repo AI-System. Script `check_real_quiz_cpu.py` cho phép lặp lại inference CPU với bundle và checkpoint tải sẵn; kết quả model thật là báo cáo riêng, không trộn với fixtures.

Trong checkout Space đã chuẩn bị, chạy một lần:

```powershell
cd D:\SEP409\tmp\hf-gradio-smgs-ai-quiz-20261117
git add app.py grounded_quiz.py quiz_quality.py quiz_set.py pytorch_engine.py README.md
git commit -m "Improve grounded five-question generation and diversity checks"
git push
```

Không upload model/cache/.env. Sau khi HF Running, phải thử lại bộ 5 trên runtime GPU; `complete=true` chỉ nói đủ số câu qua các kiểm tra hiện tại, không thay cho duyệt lịch sử/ngữ nghĩa của bảo tàng.

## Đẩy code

Repo Space đã được clone và chuẩn bị ở máy này:

```powershell
cd D:\SEP409\tmp\hf-gradio-smgs-ai-quiz-20261117
git status --short
git add app.py pytorch_engine.py quiz_set.py grounded_quiz.py quiz_quality.py requirements.txt README.md app
git commit -m "Deploy SMGS Gradio quiz demo"
git push
```

Chỉ chạy sau khi các file đã được chuẩn bị xong. Nếu Git hỏi password, nhập access token có quyền ghi repo Space vào lời nhắc của Git. Không gửi token vào chat hoặc đặt token trong URL/code. Không cần cài HF CLI và không cần Docker local.

Sau khi push: mở Space → xem Build logs / Container logs → đợi Running. UI nhận tên hiện vật, tư liệu, mức độ, danh sách câu hỏi đã có (JSON array, tùy chọn) và số lượng 1/3/5 (mặc định **5**). Kết quả là bộ câu hỏi nháp cần người duyệt. Kiểm tra `generatedCount` và `complete`; không coi 2/5 câu là bộ 5 câu đã hoàn tất. Chưa push nghĩa là app trên HF chưa được cập nhật.

## Bản sửa startup và bộ 5 câu — 17/11/2026

### Lượt thử commit c2ba700: 2/5, chưa đạt yêu cầu

Space đã RUNNING đúng commit `c2ba700`. Lượt Qwen thật sau sửa trích dẫn có response nhưng `generatedCount=2`, `complete=false`; hai câu khác chữ nhưng cùng hỏi kỹ thuật bàn xoay. Thời gian request 5,38 giây. [Phản hồi nguyên bản](gradio-live-indexed-five-c2ba700-20261117.json). Đây không phải bộ 5 câu thành công.

Bản tiếp theo giao một đoạn nguồn khác nhau cho từng câu thay vì chỉ nhắc model ưu tiên đoạn chưa dùng. Model trả ba trường question/options/correctIndex; không tự chọn hoặc đổi evidenceIndex. Đáp án phải nằm trong đoạn được giao, trích dẫn lấy nguyên văn đoạn đó. Tư liệu trùng nguyên văn được khử trùng; nếu không đủ đoạn hoặc model không đạt validator thì báo thiếu câu, không lấp bằng câu giả. Validator được áp dụng vào đoạn mục tiêu, vì một phương án nhiễu có thể là dữ kiện đúng ở đoạn khác nhưng không trả lời câu hỏi này. Đây vẫn không phải kiểm chứng ngữ nghĩa độc lập.

Luồng FE cũ gửi số câu đã có qua excludeQuestions nên request thứ 1–5 được lần lượt giao các đoạn nguồn kế tiếp; không phân tích ý nghĩa của câu loại trừ để đoán đoạn nguồn lịch sử. Kiểm tra local: `gradio-targeted-check-20261117.json` (fixtures). Cần user push và thử Qwen thật lại; không lấy số tests local làm chứng cứ model thật đã sinh đủ 5.

### Sau khi Space đã Running: sửa trích dẫn model viết lại

Đã kiểm tra Space thật lúc 21:37 giờ Việt Nam: `/ready` trả `model_ready=true`, `device=cuda`. Tuy nhiên một lượt gen bộ 5 bằng nguồn giả lập trả lỗi `ChatFailure`, không có câu đầu ra. [Kết quả gốc](gradio-live-five-20261117.json). Container logs do người dùng cung cấp xác nhận model đã chạy nhưng validator chặn `evidenceQuote` không phải đoạn trích nguyên văn. Không coi trạng thái Running là kiểm chứng tạo quiz thành công. Cảnh báo generation flags temperature/top_p/top_k không phải dòng gây lỗi này.

Bản sửa mới thêm `grounded_quiz.py`: đánh số đoạn nguồn; model trả `evidenceIndex` thay vì tự viết trích dẫn. Dịch vụ lấy nguyên văn đoạn tương ứng, vẫn kiểm tra schema, đáp án duy nhất trong nguồn, đáp án nằm trong đoạn đã chọn, số liệu và câu trùng. Không nới điều kiện nguồn để cho câu bịa đi qua. Mỗi câu có tối đa hai lần thử trong budget tổng; câu chưa hợp lệ không được thêm vào bộ. Chuyển `ChatFailure` sang `gr.Error` bên trong hàm GPU để SDK không làm mất thông báo cụ thể.

Đẩy bản sửa trích dẫn từ checkout hiện có:

```powershell
cd D:\SEP409\tmp\hf-gradio-smgs-ai-quiz-20261117
git add app.py quiz_set.py grounded_quiz.py README.md
git commit -m "Ground quiz citations by source index and preserve GPU errors"
git push
```

[Kiểm tra hồi quy indexed evidence](gradio-indexed-check-20261117.json) dùng model fixture, chưa phải kết quả Qwen thật sau sửa. Vẫn cần kiểm thử trên HF sau commit này và người duyệt kiểm tra ý nghĩa câu hỏi/đáp án.

Log startup người dùng cung cấp đã tải đủ model, nhưng kết thúc bằng lỗi bind cổng 7860; HF đồng thời báo `No @spaces.GPU function detected during startup`. Bản cũ dùng `mount_gradio_app` + Uvicorn, bỏ qua hook `Blocks.launch` của SDK ZeroGPU; SSR trên HF cũng có thể mở Node listener. Bản sửa dùng `demo.launch(ssr_mode=False)`, giữ API qua `app_kwargs`, chỉ mở một server. Khai báo model/CUDA ở cấp module vẫn giữ theo hướng dẫn ZeroGPU.

Đẩy các file sửa trong checkout đã chuẩn bị:

```powershell
cd D:\SEP409\tmp\hf-gradio-smgs-ai-quiz-20261117
git add app.py quiz_set.py requirements.txt README.md
git commit -m "Fix ZeroGPU startup and generate five-question quiz sets"
git push
```

Gradio tạo cả bộ trong một lượt `@spaces.GPU(duration=90)`, với budget inference tổng 85 giây. Mỗi câu vẫn qua validator nguồn và loại trừ câu đã có. Nếu timeout, quota hoặc câu không hợp lệ, giữ các câu hợp lệ nhưng đánh dấu `complete=false` kèm lý do; không tự bịa thêm câu. Nên cung cấp nhiều dữ kiện khác nhau nếu muốn bộ 5 câu có nội dung đa dạng. Kiểm tra ngữ nghĩa vẫn cần người duyệt.

Kiểm chứng bản sửa: [kết quả UI/API/queue và probe hook launch](gradio-five-check-20261117.json). Đã chạy bằng Gradio/SDK thật nhưng model fixture; chưa chứng minh CUDA hoặc Qwen thật hoạt động trên HF. Giữ riêng các báo cáo cũ để phân biệt từng lần thử. UI FE có 4 ca E2E qua, gồm tạo 5 → chuyển Ngân hàng → lưu tất cả thành nháp; build FE qua.

Đã đối chiếu UI thật `FrontEnd/smgs_web/src/components/ai_studio/AIContentStudio.jsx`: chọn 1/3/5, gọi `/api/artifacts/{id}/ai/drafts` tuần tự, truyền `excludeQuestions`, rồi chuyển nháp vào Ngân hàng câu hỏi. Đổi mặc định FE sang 5 và báo thiếu câu theo lỗi thực tế. **FE/BE hiện tại vẫn gọi từng câu**; `/api/v1/studio/drafts` trên Space giữ nguyên object một câu. Endpoint batch mới `/api/v1/studio/quiz-sets` chưa được nối vào BE/FE, nên không coi luồng FE là một lượt GPU cho cả bộ. Quota vẫn có thể ngắt bộ đang tạo.

## Chọn đúng bộ triển khai

### Sửa lỗi build commit e8b0639

Build HF ghim `spaces==0.51.3`, nhưng bundle đầu tiên ghim `spaces==0.52.1`, gây `ResolutionImpossible`. Đây là lỗi cấu hình bundle, không phải do cảnh báo CRLF hay Docker local. Đã sửa requirement thành `spaces` không ghim version; HF chọn phiên bản ZeroGPU mà nền tảng hỗ trợ. Giữ cùng thay đổi trong template gốc và checkout Space. Sau khi kiểm tra, đẩy bản sửa từ checkout:

```powershell
cd D:\SEP409\tmp\hf-gradio-smgs-ai-quiz-20261117
git add requirements.txt
git commit -m "Fix ZeroGPU SDK dependency conflict"
git push
```

HF tự build lại khi nhận commit mới. Local contract test dùng đúng `spaces==0.51.3` và lệnh dependency có extras `gradio[oauth,mcp]` như build HF; kết quả được ghi riêng ở `gradio-hf-sdk-check-20261117.json`. Chưa coi việc sửa dependency là đã chạy thành công model trên HF.

- `deploy/huggingface/gradio-quiz/`: Gradio 6.32.0, PyTorch Qwen2.5-1.5B-Instruct, ZeroGPU; khóa revision model. Giữ prompt và kiểm tra nguồn trong `AI Chat/app/studio.py`.
- `deploy/huggingface/quiz/`: Docker ONNX CPU, dành cho tài khoản được phép tạo Docker Space. Không copy bộ này vào Space Gradio.
- Các service local SMGS vẫn dùng ONNX; adapter PyTorch chỉ dùng cho Space này.

Muốn xuất bộ Gradio mới từ repo, chọn một thư mục chưa tồn tại:

```powershell
cd D:\SEP409\AI-System
python tools/prepare-hf-space.py D:\SEP409\tmp\hf-gradio-bundle-moi --sdk gradio
```

Script chỉ xuất file theo allowlist, không upload `.env`, token, ảnh, DB hoặc cache model. Không push cả AI-System lên Space.

## Nối Backend hiện có (tùy chọn)

1. Space → Settings → Variables and secrets → tạo **Secret** `AI_CHAT_SERVICE_KEY`, chuỗi ngẫu nhiên dài tối thiểu 32 ký tự. UI public không cần khóa này; REST bridge cần khóa.
2. Lấy App URL thật của Space, dạng `https://trungnam1644-smgs-ai-quiz.hf.space`.
3. Trên máy/server chạy BE đặt:

```text
ArtifactGuide__Enabled=true
ArtifactGuide__BaseUrl=https://trungnam1644-smgs-ai-quiz.hf.space/
ArtifactGuide__ServiceKey=<cùng secret ở HF>
```

4. Khởi động lại BE, giữ cấu hình DB đang dùng. FE gọi BE như cũ; không đưa secret vào FE.

`GET /ready` kiểm tra model đã nạp. `POST /api/v1/studio/drafts` nhận payload SMGS và header `X-Service-Key`; bridge đi qua hàng đợi Gradio rồi trả quiz JSON trực tiếp. `excludeQuestions` tối đa 5 câu, mỗi câu tối đa 1.000 ký tự. Chỉ hỗ trợ **mode quiz**; narration/chat/scan chưa triển khai trong Space này. Cấu hình ArtifactGuide được dùng chung với các luồng khác trong BE, nên không coi việc đổi BaseUrl là đã chuyển toàn bộ AI: những endpoint khác vẫn cần service local hoặc routing riêng.

API batch độc lập: `POST /api/v1/studio/quiz-sets`, cùng header/payload, thêm `count: 5`. Trả `{requestedCount, generatedCount, complete, isDraft, questions, warnings}`. API này chỉ tạo nháp, không ghi DB hoặc tự xuất bản.

`BackEnd/tools/start-with-ai.ps1` hiện ghi đè BaseUrl về localhost; khi dùng HF cần chạy BE trực tiếp với biến môi trường trên và cấu hình DB hiện có.

## Giới hạn cần hiểu

Kiểm chứng ban đầu: 10 ca HTTP/queue bằng model fixture được ghi rõ trong [kết quả gốc](gradio-local-check-20261117.json). UI/hàng đợi là Gradio thật; quiz trong báo cáo ban đầu này là fixture, không phải Qwen thật. Kết quả model thật và giới hạn của bản tổng hợp mới nằm ở mục đầu tài liệu. Chạy lại contract bằng môi trường có requirements của bundle:

```powershell
cd D:\SEP409\AI-System
python deploy/huggingface/check_gradio_contract.py --bundle D:\SEP409\tmp\hf-smgs-gradio-quiz-final-20261117
```

- ZeroGPU có quota và hàng đợi. Bridge gọi Gradio qua loopback dùng hạn mức anonymous; không phù hợp cam kết API luôn sẵn sàng hoặc gọi hàng loạt.
- Public Space công khai code và UI: chỉ đưa tư liệu được phép chia sẻ. Quiz vẫn cần kiểm duyệt; validator không chứng minh mọi câu hỏi đều đúng về ngữ nghĩa.
- Giữ tối đa 2.048 input tokens cho cả prompt và nguồn; tư liệu dài bị từ chối thay vì tự cắt mất nguồn. Không trả quiz mẫu giả khi inference lỗi.
- Test local CPU không chứng minh quota, thời gian chờ hoặc CUDA thật trên HF. Cần kiểm thử trực tiếp Space sau build.
- Một test consistency của service gốc hiện thất bại cả trên HEAD chưa sửa; nó yêu cầu lượt kiểm chứng đáp án độc lập đã bị bỏ khỏi code. Không coi toàn bộ suite hiện tại là xanh.

Nguồn: [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu), [Gradio API](https://www.gradio.app/guides/view-api-page).

## Docker local bị crash trong lần thử 17/11/2026

Log tại `C:/Users/trung/AppData/Local/Docker/log/vm/init.log`, khoảng 19:05 giờ Việt Nam: nhiều `I/O error, dev sdd`, EXT4 abort journal, rồi `containerd` SIGBUS. Docker disk nằm tại `C:/Users/trung/AppData/Local/Docker/wsl/disk/docker_data.vhdx` (26,4 GiB); ổ C còn khoảng 4,2 GiB khi kiểm tra. Chưa xác định nguyên nhân gốc (không đủ căn cứ khẳng định hết disk, hỏng disk hay thiếu RAM).

Không reset/purge/xóa VHDX để xử lý khi chưa sao lưu. Việc deploy Gradio bằng Git không cần Docker local. Xem [Docker troubleshooting](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/) và [backup khi Desktop không khởi động](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/).
