# Scan 3D cloud khi chưa deploy Backend — 18/11/2026

## Yêu cầu cập nhật: AI-System chạy hoàn toàn trên cloud

**Điều chỉnh theo user sau đó:** DB hiện dùng Supabase; không dựng PostgreSQL mới trên Azure và không deploy BE/FE trong công việc này. User đã tạo Space HF `Trungnam1644/smgs-ai-guide` cho chatbot + personalized tour; triển khai bộ này trước, giữ Space quiz riêng. TTS và Scan là phạm vi cloud tiếp theo. Các đề xuất VM/DB bên dưới là lịch sử đánh giá, không phải cấu hình đã tạo. Hướng dẫn mới: `huggingface/GUIDE_TOUR_DEPLOY_VI.md`.

User đã làm rõ: chỉ tập trung AI-System, không triển khai BE/FE trong công việc này. AI phải có endpoint online, xử lý được khi máy cá nhân tắt. Các phương án notebook tương tác/local ở bên dưới là đánh giá trước khi làm rõ yêu cầu, không đáp ứng mục tiêu triển khai này.

Hướng triển khai đề xuất, chưa thực hiện:

- Giữ Space quiz đang hoạt động; chưa coi Space quiz là bản thay thế cho toàn bộ API chat/narration.
- Đưa các service AI còn cần triển khai lên Linux VM x86_64 Ubuntu 24.04 bằng container, ưu tiên Scan CPU và persistent volume trước. Không cần dựng lại reconstruction hoặc chờ BE/FE.
- API Scan và Vision hiện vẫn cần PostgreSQL. Chưa deploy BE không có nghĩa là bỏ DB: dùng DB SMGS trên cloud với các schema hiện có, cho BE kết nối cùng DB sau này. Không tự tạo dữ liệu hiện vật hoặc claim đã có dữ liệu BE trên cloud.
- Endpoint HTTPS có xác thực; PostgreSQL chỉ trên mạng riêng. Giữ ảnh, job metadata và GLB qua restart; kiểm thử upload → xử lý → xem/tải/xóa bằng API trước khi tuyên bố triển khai xong.
- Một VM chứa nhiều container vẫn giữ ranh giới service. Mốc thử tài nguyên ban đầu là 4 vCPU/16 GB RAM, một scan đồng thời; đây là cấu hình để đo thử, chưa phải mức tối thiểu đã được benchmark hoặc cam kết đủ cho mọi bộ ảnh/tất cả AI chạy cùng lúc.

Ứng viên chi phí: Azure for Students, nếu tài khoản đủ điều kiện, có $100 credit dùng trong 12 tháng và không cần thẻ theo https://azure.microsoft.com/en-us/free/students (kiểm tra 18/11/2026). Đây là credit có hạn, không phải VM cấu hình lớn miễn phí vĩnh viễn. Cần kiểm tra eligibility, quota, vùng và giá VM/disk trước khi tạo tài nguyên. Chưa chọn subscription, chưa tạo resource hoặc upload dữ liệu.

## Trạng thái đã kiểm tra

- User đang dùng HF Free, ưu tiên miễn phí và chạy cloud/notebook để không phụ thuộc máy cá nhân. Backend chưa deploy.
- API production `3D Scan/app/main.py` gọi PostgreSQL khi startup và quản lý scan jobs qua schema của BE. Không thể coi việc đưa nguyên API này lên một host là demo độc lập không DB.
- Luồng `3D Scan/tools/local_scan_worker.py` dùng lại `app/reconstruction.py` với status callback, không tạo DB job. Có thể dùng làm lõi cho adapter demo cloud không cần BE, không thay thế API production.
- Dockerfile hiện có dùng Ubuntu 24.04 + COLMAP apt + OpenMVS 2.4.0 x64 ghim checksum; CPU-only. Không phải PyTorch workload ZeroGPU như quiz. Native OpenMVS Ubuntu binaries cũng không được mặc định là chạy được trên mọi image Colab/Debian hoặc ARM.
- Tại lần kiểm tra này localhost:8002 không truy cập được và Docker Engine pipe chưa có. Điều này không chứng minh Docker hỏng dữ liệu; cũng có thể Desktop chưa được mở. Không khởi động lại, reset hay xóa dữ liệu Docker trong bước đánh giá này.

## Hai lựa chọn phù hợp

| Nơi chạy | Miễn phí thế nào | Phù hợp với mục tiêu nào | Giới hạn |
|---|---|---|---|
| Google Colab | Notebook có tài nguyên miễn phí, cấp phát không bảo đảm | Mở notebook, upload bộ ảnh, chạy CPU reconstruction và tải GLB | Session có thể kết thúc; không dùng làm API/worker web phục vụ hệ thống thường trực hoặc tunnel để bỏ qua notebook UI |
| Modal Starter | Không phí gói, có $30 compute credits mỗi tháng | Deploy worker CPU/container, HTTP API nhận job và tải GLB | Cần payment method; vượt credit hoặc dùng sản phẩm không được credit bao gồm có thể bị tính phí. Chưa kiểm chứng pipeline thực trên Modal |

Nguồn được kiểm tra trực tiếp:

- Colab: https://research.google.com/colaboratory/faq.html — tài nguyên không bảo đảm, VM có vòng đời hữu hạn; free runtime giới hạn việc bypass notebook UI để dùng chủ yếu qua web UI. Không hướng dẫn dùng Colab như backend thường trực.
- Modal pricing: https://modal.com/pricing — Starter $0 + compute, $30/month included compute. Đây là credit miễn phí có giới hạn, không phải compute miễn phí vô hạn. Model APIs theo token không nằm trong credit compute; Scan chạy native tools dùng Function compute, không cần Model APIs.
- Modal billing: https://modal.com/docs/guide/billing — cần payment method; usage được tính và thanh toán sau khi trừ credit. Chưa tạo tài khoản, thêm thẻ, đặt budget hoặc deploy resource thay user.
- Modal timeouts: https://modal.com/docs/guide/timeouts — Function mặc định 300 giây, có thể cấu hình tới 24 giờ. Scan job phải cấu hình thời gian riêng; không dùng timeout HTTP ngắn để chạy đồng bộ cả reconstruction.

## HF Free không phải đường đưa nguyên Scan CPU lên cloud

Theo https://huggingface.co/docs/hub/en/spaces-overview, tạo Gradio/Docker compute Space mới cần gói trả phí, có ngoại lệ tối đa hai Gradio ZeroGPU cho tài khoản Free đủ điều kiện. COLMAP/OpenMVS CPU không tự biến thành workload PyTorch ZeroGPU. Không thêm một phép tính GPU giả chỉ để gắn nhãn ZeroGPU.

HF egress chỉ 80/443/8080; kết nối PostgreSQL 5432 hiện tại không được mặc định hỗ trợ. Disk Space mặc định là tạm. Nguồn: Spaces overview mục Networking; https://huggingface.co/docs/hub/en/spaces-storage.

## Phạm vi adapter cloud có thể triển khai tiếp

Không cần chờ BE deploy để demo: nhận bộ ảnh và optional metadata/reference → worker CPU hiện có → GLB + provenance → xem/tải kết quả. Tuy nhiên lớp nhận upload, trạng thái job, giới hạn tài nguyên, lưu file và download trên nhà cung cấp được chọn vẫn cần chuẩn bị/kiểm thử. Chưa triển khai lớp đó trong bước đánh giá nhà cung cấp này.

- Nếu chỉ cần thử cloud miễn phí không thêm phương thức thanh toán: chuẩn bị notebook Colab, thao tác trong notebook; kiểm tra OS/native binaries và RAM trước khi chạy. Chưa có notebook hoặc reconstruction Colab đã được kiểm chứng trong repo.
- Nếu cần URL API để FE/BE gọi về sau: Modal là ứng viên phù hợp về chức năng container/CPU/long-running jobs, nhưng user phải chấp nhận điều kiện billing. Khi được chọn, chuẩn bị adapter demo riêng dùng local runner, giữ production API/DB của SMGS nguyên trạng. Không tuyên bố đã nối DB/BE/FE.
- Mode benchmark vẫn phải ghi rõ dùng OBJ nguồn để hiệu chỉnh camera. Không dùng OBJ gốc làm output scan; không đảm bảo ảnh chụp bất kỳ đạt chất lượng tương tự dữ liệu benchmark.

Chưa có job cloud, ảnh hoặc GLB nào được upload trong bước đánh giá này. Chưa có benchmark RAM/thời gian hoặc ước tính số lượt miễn phí; không lấy thời gian chạy local làm cam kết trên cloud.
