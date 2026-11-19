# Implementation log

## 2026-11-19 — TTS pacing and BE/HF integration audit

- Added museum-v4 punctuation/paragraph pauses, explicit sherpa GenerationConfig,
  speed factor 0.9 and prosody-aware cache invalidation. Real local Piper CPU:
  15.483 s baseline vs 17.812 s revised; measured quiet runs 0.16 s vs 2.66 s.
  4/4 audio checks and 13/13 unit/API checks passed. Earlier silence-only attempt
  failed 2 checks; retained failed-v3.json. Human listening not approved; Azure
  deployment and production BE playback remain pending.
- BE public museum endpoints returned HTTP 200. User confirms DB on BE host;
  local configs still target local DB. HF quiz/chat/tour consume BE request data,
  not direct DB credentials. Found quiz/chat share ArtifactGuide options, requiring
  separate quiz routing for two Spaces. Added manual CONNECT_BE_VI.md; no BE
  code, production config, DB or existing HF deployments changed.

## 2026-11-18 — Expanded live personalized-tour verification

- At user's request, ran `verify_live_tour.py` against the actual HF `smgs-ai-guide` app: **12 synthetic test cases, 64/64 checks passed**. This exercised real cloud Gradio queue + unchanged CPU tour algorithm, with no model fixture, GPU calls or database writes.
- Confirmed pottery -> artifacts 2/1 (11.5 min), bronze -> artifact 3 (8 min), five-minute budget -> zero stops, exact six-minute budget -> one bowl stop, maxStops=1, explicit unmatched-interest fallback, mixed preferences and deterministic repeat output. Every accepted result used only supplied unique artifact IDs/content versions, remained within duration, and had totals equal to visit+walk minutes.
- Live invalid-input cases rejected mixed museum IDs, duplicate artifacts, empty interests and duration >240 min. Authenticated REST boundary returned 401 for missing/incorrect key before processing input. **A successful REST call with a current valid Secret was not verified**: did not reuse the key text disclosed in chat or save keys in source/reports. Optional `--prompt-key` allows entering a current key locally with hidden input for that remaining check.
- Saved inputs, outputs, timing and exact checks in `deploy/huggingface/tour-live-20261118.json`. Calls for this three-candidate synthetic set took roughly 0.53–1.12 seconds; this is not a load benchmark or proof of tour persistence/access-control/full-product integration. Earlier chat quota failure remains recorded separately and does not consume/block CPU tour execution.

## 2026-11-18 — Separate HF chatbot and personalized-tour adapter

- User chose HF chatbot + tour first and created `Trungnam1644/smgs-ai-guide`. Quiz Space remains independent. Clarified DB is Supabase; no new PostgreSQL, BE/FE deployment, Scan/TTS changes or schema/data writes in this work.
- Added `deploy/huggingface/gradio-guide`: two Gradio tabs, Qwen PyTorch adapter with pinned upstream revision `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, original chatbot prompt/parser/source guard, and unchanged CPU tour engine/schema. `prepare-hf-space.py --service guide --sdk gradio` exports only allowlisted files to a new directory, leaving default quiz export behavior intact.
- Preserved REST contracts `/api/v1/guide/answers` and `/api/v1/tours/recommend`; separate server-side Secrets, auth before parsing, bounded streamed bodies. Chat enters Gradio queue for real ZeroGPU context, with error envelopes preserving worker error codes/messages. Tour runs outside GPU allocation. Canonical launch installs both routes and auth middleware; SSR disabled to keep one listener.
- Local Gradio HTTP/queue verification: 42/42 checks passed with an explicitly labelled **chat fixture** and real tour algorithm. Original tour suite: 9/9 passed. Chat JSON schema equals original service; copied tour source bytes and export allowlist verified. These checks do not establish cloud inference/availability. Sandbox TestClient/Gradio runs stalled and were interrupted; the reported successful HTTP suite ran outside sandbox. No data was reset.
- Added `GUIDE_TOUR_DEPLOY_VI.md` and real-CPU model probe. Public Gradio demo is intentionally public; REST key does not privatize the whole Space. No unlimited-quota/always-on production guarantee.
- Real Qwen CPU BF16 probe: initial 45-second budget produced 2/3 accepted cases; the missing-date case hit the budget with incomplete JSON and was rejected (502). Preserved `guide-real-cpu-20261118.json`. A separate 90-second CPU probe achieved 3/3: ceramic material, drum purpose, missing date -> `supported=false`; times 38.61/37.22/41.44 s. `guide-real-cpu-budget90-20261118.json` explicitly records the extended CPU budget; deployed GPU generation budget remains 45 s, allocation 60 s. These are synthetic-source checks, not general historical accuracy evidence.
- Committed and pushed the separate Space checkout to **`6273197d802ba21bd4deed0f2d913c77bdf86e75`**. HF public runtime confirmed **RUNNING**, requested/current ZeroGPU, `spaces` SDK 0.51.3. New app host: `https://trungnam1644-smgs-ai-guide.hf.space`. No push to quiz Space or other service repos.
- Live cloud tour checks passed: pottery interests -> artifacts 2/1 (11.5 min), bronze -> artifact 3 (8 min), five-minute budget -> zero stops. All records are synthetic. Model readiness confirms loaded CUDA adapter, but real cloud chat **was NOT completed**: HF returned `ZeroGPU quota exceeded` / anonymous runs limit, asking for authenticated quota. Raw evidence retained in `guide-live-6273197-20261118.json` (7/8 checks; failed check is real chatbot completion). Do not report this as successful HF GPU inference.
- At live check, `/ready` returned 503 with `chat_api_configured=false` and `tour_api_configured=false`: user still needs to add both >=32-character service Secrets. REST was verified to reject anonymous input; authenticated cloud REST has not been tested. Public UI/tour works separately. No HF CLI token was available for an authenticated GPU retest; did not extract Git credentials or request token text in chat. User was asked to configure Secrets directly in HF Settings.
- Follow-up at 15:35 Vietnam time: anonymous `/ready` returned 200, `model_ready=true`, device CUDA, both API configuration flags true. Saved only public status fields in `guide-readiness-20261118.json`; this checks configuration, not authenticated REST inference. User pasted service-key values in chat; those values were not used, repeated or written to files/logs. Advised replacing both through HF Secrets with freshly generated values. Rotation has not been verified.

## 2026-11-18 — Clarified cloud scope: AI-System only

- User clarified that AI-System must run online independently of the personal PC; BE/FE deployment is outside this work. Earlier interactive notebook/local suggestions do not satisfy this requirement.
- Updated the cloud options document with a proposed x86_64 Ubuntu VM/container deployment, persistent scan storage, authenticated HTTPS and cloud SMGS PostgreSQL for existing Scan/Vision schemas. BE need not run for these AI APIs, but their DB requirement remains.
- Verified Azure for Students official terms: eligible students receive $100 credit for use within 12 months, no credit card required. This is conditional, finite credit, not an unlimited free production VM. Proposed 4-vCPU/16-GB initial measurement target is not a measured minimum or capacity guarantee.
- Planning/documentation only: no deployment configuration or pipeline changes, cloud resources, live endpoint, DB migration or cloud scan verification in this step.

## 2026-11-18 — Scan cloud deployment feasibility without deployed BE

- User requests a separate Scan deployment, confirms HF Free and prefers cloud/notebook rather than running the personal PC. Reviewed actual Dockerfile, DB-backed API and DB-independent local runner; no reconstruction pipeline or production API/DB change made.
- HF Free cannot be advertised as an unchanged CPU Docker deployment: compute-Space creation restrictions, PostgreSQL egress and ephemeral files remain relevant. Native COLMAP/OpenMVS subprocess workloads are not the existing PyTorch quiz workload. No dummy GPU wrapper proposed to imply support.
- Verified primary provider documentation: Colab supports free interactive notebooks with resource/session limits, not a permanent web API/tunneled service; Modal Starter includes $30/month compute but requires a payment method and can bill beyond included usage. Modal's long-running CPU/container functions are a deployment candidate, not a verified free Scan deployment yet.
- Wrote `deploy/SCAN_CLOUD_OPTIONS_2026_11_18.md` with actual code paths, tradeoffs, sources and unimplemented adapter work. No account creation, payment setup, cloud execution, uploads, resource purchase or service exposure performed. Local Scan port was not reachable and Docker Engine pipe absent during read-only checks; no reset/restart or data deletion applied.

## 2026-11-17 — Live HF five-question success; asyncio cleanup warning nonfatal in observed run

- User pushed `465b25b226d8b26b70bb3eb7f4cf66dc5ed42332` and supplied an `Exception ignored in BaseEventLoop.__del__` / `Invalid file descriptor: -1` traceback after startup. HF public runtime confirmed RUNNING on that exact commit, SDK 0.51.3; readiness returned model_ready=true/device=cuda.
- Real anonymous request on the deployed Space at 22:36 Vietnam time returned 5/5, complete=true, no warnings, in 4.08 seconds. The five questions ask purpose, material, mouth shape, decoration and crafting technique respectively. Each has four unique options, the correct option is in its assigned source passage, and the citation is an exact source substring. Source is the synthetic ceramic demo, not an approved museum artifact. Raw response: `deploy/huggingface/gradio-live-quality-465b25b-20261117.json`; assistant/guard postflight: `gradio-live-quality-review-465b25b-20261117.json`.
- This confirms one real HF GPU five-question run after the consolidated improvement, not a general accuracy/performance or uptime guarantee. No full BE/FE/DB or Museum Staff approval verification in this call. CPU two-source evidence and older failed responses are retained separately.
- The user traceback occurs during asyncio destructor/selector cleanup; its exact originating library/resource lifecycle is not proven from the fragment. A similar Gradio/HF traceback has an upstream report where the app continued working (https://github.com/gradio-app/gradio/issues/12699), but that does not establish this instance's root cause. No monkeypatch, suppression, forced SDK version change or restart applied: the observed quiz request succeeded despite the warning.

## 2026-11-17 — Consolidated five-question quality improvement before one user push

- Added `quiz_quality.py`: exact-span clause parsing, software-test disclaimer exclusion, topic-diverse evidence planning and paraphrase/source deduplication. Diversity guard checks normalized question stems, same topic/answer, topic mismatch, negative/yes-no questions and observed Chinese/English drift. These are rules with false-positive/negative limits, NOT an independent semantic or historical verifier.
- Bounded recovery now skips a rejected source fact and tries remaining facts instead of stopping the set at the first invalid candidate. At most two attempts per fact, a capped total number of calls and shared 85-second GPU budget. Retry carries the rejection reason and uses reproducible low-temperature sampling; terminal quota/time errors stop without padding.
- Actual CPU diagnostics showed the freeform 1.5B model mixing Chinese in a question, English/nonsensical distractors, and copying five wrong options while omitting the answer. Kept `qwen-real-quality-cpu-20261117.json` (FP16, first case only 2/5 at 249.86s; second case interrupted) and `qwen-real-quality-bf16-20261117.json` (diagnostic candidates, interrupted before a completed case). Do not describe those as successful five-question runs.
- For recognized fact types, moved option assembly to source-constrained rules: answer extracted verbatim, three distractors selected from a controlled Vietnamese vocabulary, deterministic shuffle and consistent option casing. Qwen writes the question using the assigned fact/hint. It must return valid question JSON; blank/extra fields do not receive a server-filled question. Unknown fact forms keep full-JSON generation plus validation. This is explicitly a hybrid generator rather than claiming all fields are freely generated by AI. No changes to the shared local ONNX studio, BE contracts or FE implementation in this turn.
- Real pinned Qwen checkpoint tested on CPU **bfloat16** via `check_real_quiz_cpu.py`: ceramic and drum synthetic sources each returned 5/5, five distinct topics (purpose/material/shape/decoration/technique), all ten model questions in Vietnamese and supported by their assigned sources. Assistant reviewed all ten and the latest guard postflight passed. Times 157.81s / 151.95s with a separate 360s CPU test budget; these do NOT prove performance inside the Space's 85s GPU budget. Raw: `qwen-real-hybrid-cpu-20261117.json`; postflight: `qwen-real-hybrid-review-20261117.json`. Museum Staff approval remains false; sources are synthetic, not historical museum records.
- Added 26 adversarial/unit checks covering the actual failed pair, same-fact paraphrases, different legitimate shape facts, wrong-topic/negative/yes-no questions, language drift, malformed or extra-field model outputs, exact spans, metadata/decimal parsing, recovery, quota/deadline and no fake padding. All 26 passed. All 39 Gradio/API/queue contract checks also passed on the final prepared checkout; these remain separately marked fixtures in `gradio-quality-final-check-20261117.json`. Same-checkpoint local CPU content evidence is stronger than fixtures, but the consolidated HF GPU revision still needs push and runtime verification.
- Updated exporter to include `quiz_quality.py`, guides and the existing HF checkout so the user can push all runtime changes together. Model weights/cache remain under D:/SEP409/tmp, excluded from the Space bundle. No commit/push performed on the user's behalf, no paid resource started, and prior failed real HF reports retained.

## 2026-11-17 — Live c2ba700 generated only 2/5; assign distinct evidence per question

- User pushed `c2ba70080649ec0c98de56612c93c4f2de07cdb5`. HF public runtime confirmed RUNNING on that exact commit. Real anonymous five-question inference with the same synthetic five-fact source returned 2/5, complete=false, in 5.38 seconds. Both accepted questions paraphrased the same crafting-technique fact. Raw response retained at `deploy/huggingface/gradio-live-indexed-five-c2ba700-20261117.json`. Do NOT count this as a successful or diverse five-question set.
- Changed orchestration from soft preference for unused evidence to server-assigned distinct passages. The model now generates only question/options/correctIndex; citations and their IDs cannot be supplied/overridden by model output. Duplicate source passages are removed while retaining exact input substrings. Legacy single-item FE calls rotate assignment by prior-question count; arbitrary excluded-question semantics are not inferred.
- Apply the shared validator to the assigned source passage and confirm that passage is literally from the full input. This resolves the correct option within the intended fact rather than incorrectly disallowing a distractor just because it occurs in another source fact. Added a small schema example and mandatory target-passage instructions. No fake padding or substitution of fixed demo questions; incomplete/invalid outputs still fail or return an explicitly partial set.
- Fixtures now verify five distinct evidence quotes, rejection of model-supplied source override, and deduplication of repeated source paragraphs in addition to prior checks. Separate results: `deploy/huggingface/gradio-targeted-check-20261117.json`. No FE/BE implementation change in this follow-up. This revised prompt/assignment still needs a new user push and real Qwen verification.

## 2026-11-17 — Live HF startup confirmed; citation-generation failure and fix

- User pushed `18970d1` and showed Running on ZERO. Live anonymous readiness at 21:37 Vietnam time returned model_ready=true, device=cuda. A real five-question request using the synthetic demo source returned SSE error `ChatFailure` after 5.48 seconds, no quiz output. Preserved raw response in `deploy/huggingface/gradio-live-five-20261117.json`; did NOT report five-question inference success.
- User supplied container traceback: GPU worker reached PyTorch generation and shared validator; validation failed where evidenceQuote must be a literal source substring. SDK propagated only the custom exception class name, obscuring the reason. The temperature/top_p/top_k warning is not the failing validator condition.
- Added Space-only `grounded_quiz.py`: source passages retain exact input substrings; model selects an evidence index and supplies question/options/index. Server copies the chosen original passage into citation/explanation, runs the existing SMGS validator and additionally requires the resolved correct option in that chosen passage. Invalid indices, fabricated citation fields, unsupported answers and duplicates are rejected. One invalid candidate may be retried under the same global deadline. No changes to the local ONNX studio/validator and no fake fallback questions.
- Converted known ChatFailure to gr.Error inside the decorated GPU function so ZeroGPU preserves the actionable message. Updated the exporter and prepared the Space checkout with the new module. Local fixtures cover original API/batch cases plus exact source copying, wrong/out-of-range evidence rejection, invented quote field rejection, substring preservation for long input, bounded retry and worker error preservation; raw report `deploy/huggingface/gradio-indexed-check-20261117.json`.
- Browser log-reading was attempted with the computer-use skill but its JS kernel failed to write assets even after reset; no Windows UI action occurred. Diagnosis instead used the user-provided traceback. No user credentials/tokens were read or requested.
- This fix still requires a user push and live Qwen retest. Indexed citations prove the quote is from source and the answer appears there; they do not prove the question's semantics or historical truth. Human review remains required. Prior failed real response and fixture reports retained.

## 2026-11-17 — ZeroGPU startup correction and five-question quiz sets

- Read the actual web studio, its BE adapter/controller, and QuestionBank. Existing FE already offers 1/3/5, generates one question per request with accumulated exclusions and supports editing/saving all imported drafts. Set the FE default to 5; did not replace the BE contract or modify the user's existing BE configuration changes.
- User's runtime log for the SDK-fixed Space shows model download/loading completed, followed by bind failure on 7860; HF reports no GPU function detected during startup. SDK 0.51.3 source registers `startup_report` on `Blocks.launch`, which our direct Uvicorn startup bypassed. Replaced mount/Uvicorn startup with canonical `demo.launch(ssr_mode=False)` and registered the same REST routes through app_kwargs. This invokes the SDK launch hook and avoids a competing SSR listener. Model/CUDA placement remains at module scope per HF guidance. Actual HF startup after this fix is still unverified until push/rebuild.
- Added `quiz_set.py`: default 5 (1/3/5 selectable), one decorated GPU call for a full Space quiz set, overall 85-second inference budget within a 90-second allocation. Every question passes the existing source validator, has four options and excludes prior questions. On invalid output, quota or time limit, preserve accepted questions and report `complete=false`, actual count and warning; no fabricated padding or success for incomplete sets.
- Added authenticated `/api/v1/studio/quiz-sets`. Kept `/api/v1/studio/drafts` returning one raw quiz object so existing BE/FE loops remain compatible. The FE is NOT wired to the new batch endpoint: it still makes sequential requests and may hit ZeroGPU quota. Do not claim that the complete FE flow now uses one allocation per set. Narration/chat/scan deployment and semantic duplicate detection remain outside this change.
- FE now rejects normalized text duplicates, reports the actual last failure on partial sets, and unlocks controls after cancellation. Removed misleading fixed 50s timing and wording that implied source exhaustion or verified historical dates. Existing question-bank implementation was only read; stale E2E selectors were updated to its current labels.
- Verification: actual Gradio 6.32 / spaces 0.51.3 dependency environment, canonical launch with an actual SDK `one_launch` probe and forced SSR-on environment overridden by ssr_mode=False. UI/API/queue checks cover complete five-question sets, 1/3/5 behavior, four options, exclusions/legacy five sequential requests, partial duplicate/quota results, auth/input rejection and total deadline. Results: `deploy/huggingface/gradio-five-check-20261117.json`; all are explicitly model fixtures, NOT real GPU inference.
- Four targeted Edge-headless FE E2E tests passed, including five drafts → question bank → save all as drafts; partial 2/5 and cancel are covered. Production FE build passed (existing large-chunk advisory). First E2E attempts found the five-second expectation was shorter than the existing 1.5-second inter-question pauses, and old heading/button selectors no longer matched current QuestionBank labels; corrected test waits/selectors. Final raw log: `D:/SEP409/tmp/fe-five-quiz-e2e-verified.log`.
- Updated the original template, allowlist exporter, Vietnamese guides, FE log and existing Space checkout. No commit/push performed for these fixes; user must push the prepared app/quiz_set/README changes. HF startup, Qwen generation quality and BE-to-HF with real role/DB remain pending; prior raw check reports retained.

## 2026-11-17 — Fix actual HF ZeroGPU build SDK conflict

- User successfully pushed Space commit `e8b06394d19fad8d0a1ad1e1b3f331be05d1658c`. Public HF runtime confirmed the commit and ZeroGPU build. User then supplied the real failed build log: HF appends `spaces==0.51.3` to its pip command while our first requirements pinned `spaces==0.52.1`; pip correctly rejected conflicting direct requirements. The earlier local 0.52.1 check did not reproduce HF's injected SDK constraint.
- Removed our `spaces` version pin in both the tracked template and the user's existing Space checkout. HF now owns the supported SDK version; other model/dependency pins remain. No API/model/prompt change. Preserved the earlier contract report instead of replacing it.
- Installed with the actual HF pip arguments (`spaces==0.51.3`, `gradio[oauth,mcp]==6.32.0`, `torch<=2.13.0`, uvicorn/websockets), then checked dependencies and contract using that SDK. Separate raw result: `deploy/huggingface/gradio-hf-sdk-check-20261117.json`, including package versions. These remain fixture contract checks, not real GPU inference.
- Prepared fix locally; it still needs a new user commit/push and an actual successful HF rebuild. The failed build did not reach model startup. Docker local crash is unrelated to this pip conflict.

## 2026-11-17 — Gradio / ZeroGPU quiz Space preparation

- Read-only cloned the user-created `Trungnam1644/smgs-ai-quiz` Space; its SDK is Gradio 6.32.0 / Python 3.12. Added a separate `deploy/huggingface/gradio-quiz` template with the pinned official Qwen2.5-1.5B PyTorch checkpoint for ZeroGPU, reusing existing SMGS studio prompts and source-grounding validation. The local ONNX model engine is unchanged.
- Added a public Gradio quiz UI and service-key-protected `/api/v1/studio/drafts` quiz bridge through the real Gradio queue; preserves raw quiz response and up to 5 excluded questions. No narration/chat/scan endpoints in this Space. Documented that BE ArtifactGuide configuration is shared, so pointing it at this quiz-only Space does not migrate other features.
- Fixed dependency compatibility: Gradio 6.32 requires HF Hub >=1.16; Transformers 4.x caps Hub below 1. Selected Transformers 5.0.0 / Hub 1.16.0, plus urllib3 2.8.0 required by the Hub inference-provider import. Model placement at module scope follows ZeroGPU guidance; no fake tensor example and no dummy quiz fallback in app code.
- Local Windows Python CPU environment: installed actual dependencies and exercised UI/readiness, service key rejection, payload/mode validation, REST → Gradio queue → shared validator, raw response and duplicate rejection using a clearly labelled model fixture. This is a contract test, NOT real PyTorch inference or an HF GPU test. Reproduction: `deploy/huggingface/check_gradio_contract.py`; raw results: `deploy/huggingface/gradio-local-check-20261117.json`. Existing 15/16 local chat test result remains unchanged; no independent semantic answer verification was added.
- Local Docker test could not finish: Docker Desktop's virtual disk logged read/write I/O errors and an aborted EXT4 journal, then containerd SIGBUS at 19:05. Host C had ~4.2 GiB free; Docker VHDX was on C. Root cause unconfirmed. No reset, purge, VHDX deletion, diagnostic upload or Docker service restart performed. Continued contract testing outside Docker, with environment files on D.
- Prepared an allowlisted Space checkout and Vietnamese deployment guide at `deploy/huggingface/GRADIO_GUIDE_VI.md`. No commit/push to HF and no paid compute activated. Actual HF build, PyTorch generation, GPU quota, cold start and BE-to-HF end-to-end checks remain pending. ZeroGPU bridge uses anonymous quota; it is a limited demo, not an always-available backend guarantee.

## 2026-11-17 — Hugging Face quiz Space deployment preparation

- Added allowlisted `tools/prepare-hf-space.py` and Docker Space template under `deploy/huggingface/quiz`. Reuses existing chat/studio API; pinned model downloaded at build time, UID 1000, port 7860, one worker, 2 ONNX CPU threads via new optional `AI_CHAT_NUM_THREADS` (existing default remains 8).
- Built exported bundle `D:/SEP409/tmp/hf-smgs-quiz-20261117` locally. Real 2-CPU/16-GiB container: readiness 200, missing key 401, one grounded quiz 200 in 19.14 seconds. Raw result: `deploy/huggingface/local-check-20261117.json`. Local test container stopped; no Space/account/paid compute created and no upload.
- Chat/studio tests: 15/16 passed. Existing consistency test fails identically on original HEAD and current code because it expects the independent answer check removed by the current studio implementation. No test deleted or changed to conceal it.
- Documented current HF paid-plan requirement for creating Docker compute Spaces, ephemeral storage, and outbound-port restrictions. Current scan service cannot be advertised as deploy-and-run unchanged on HF: direct PostgreSQL on 5432, durable scan files and job recovery remain unresolved for that platform. Keep scan on local/VPS worker for the current architecture. See `deploy/huggingface/DEPLOY_GUIDE_VI.md`.

## 2026-11-12 — Museum Staff web scan integration

Added validated multipart datasets (5–200 photos + optional LR3D metadata/reference OBJ), same local CPU worker through DB-backed API jobs, scoped BE gateway, authenticated preview/save/discard, and React artifact 3D tab with folder selection, polling, preview and model persistence/deletion through existing media service. Standalone local setup no longer depends on sibling FE node_modules. Added start-scan.ps1 and BE start-with-scan.ps1; DB/key are process environment only. No new model storage architecture or fake fallback color. See [guide, checks and remaining work](3D%20Scan/STAFF_WEB_GUIDE.md). Live 180-photo Museum Staff web-to-DB verification passed: job 04473380-4377-45f0-bfef-556b95e2d6bd COMPLETED on demo artifact 10; stored GLB 8,232,748 bytes SHA256 equals generated output. Fixed non-seekable AI download stream by bounded temporary-file buffering before existing GLB validation; regression checked. Unit/API and media checks pass. Live delete not performed.

## 2026-11-12 — Local folder-to-GLB command

- Added `3D Scan/tools/scan_folder.py`: accepts a quoted folder path (or prompts for it), reads JPG/PNG recursively, chooses `images/` when present to exclude source texture atlases, and launches an isolated CPU Docker worker. Source mounted read-only; no artifact ID, database calls, uploads, or publication. New output folder per run; logs, status JSON, embedded-texture GLB, provenance and HTTP viewer retained.
- Added `local_scan_worker.py` and `local_scan_viewer.html`; local CPU PatchMatch runs at resolution level 0, followed by existing mesh/refine/texture/embedding steps. CLI injects a JSON status callback and optional fixed sparse model into the shared pipeline. API contract and default SGM/fallback behavior stay unchanged.
- Generalized the existing LR3D camera audit from a hardcoded metal-cup filename to one OBJ per dataset. Auto benchmark mode explicitly records use of reference silhouettes to infer missing camera intrinsics. Output triangles/texture come from reconstruction; original OBJ is not converted into the output. Normal photo mode estimates cameras with COLMAP.
- Verified `D:\3D\ceramic_vases_1\ceramic_vases_1`: 180 images / 43.1 MiB. Ran actual container input validation and camera calibration only, yielding `CHECKED`, bbox RMSE 0.268 px and camera/reference silhouette IoU 98.72–99.05%. These metrics do not evaluate a newly reconstructed model. Full ceramic reconstruction has NOT been run; user requested a command to run it themselves.
- Validation: Python compilation and 17 local/API regression tests passed. Tests ran in a disposable container with test-only httpx installed; no change to service image dependencies. Guide: `3D Scan/LOCAL_FOLDER_GUIDE.md`.
- Not implemented: local jobs publishing to BE, resume after interruption, arbitrary formats of camera metadata, quality guarantee for unknown image sets. Geometry completeness and per-face texture quality require visual review.

## 2026-11-04 — Điều chỉnh bộ ảnh 3D theo yêu cầu thực tế

- Web/API nhận từ 5 ảnh cho một hiện vật; bỏ khuyến nghị bắt buộc 15–40 ảnh trên UI. Giữ 80 là giới hạn trên để bảo vệ tài nguyên.
- Test API dùng đúng 5 ảnh để kiểm tra nhận job; test web xác nhận gửi đủ 5 ảnh và chặn dưới 5 ảnh.
- Kiểm thử: 9 test 3D pass; Node FE 26 pass/1 skip; React production build thành công.
- Đây là thay đổi điều kiện tiếp nhận ảnh, không phải xác nhận COLMAP đã dựng thành công từ 5 ảnh thật. UI và README ghi rõ có thể thất bại/thiếu chi tiết.

## 2026-11-04 — Sửa độ tin cậy, vận hành và hợp đồng AI/FE

- Vision: sửa ambiguity khi top_k=1, bỏ vector hỏng, ảnh giới hạn pixel, constant-time key, quota dưới advisory lock và route inference không khóa event loop.
- TTS: cache có ngân sách, atomic file, fingerprint model/tốc độ chính xác, Unicode tiếng Việt NFC, xử lý busy, WAV hỏng và model archive/download an toàn hơn.
- 3D: readiness COLMAP/DB/worker, UUID, ảnh decode, metadata limit, cleanup khi persist lỗi, claim job atomic và không reset PROCESSING của worker khác.
- FE: đọc candidates/reference_images/error đúng contract; chọn 10–80 JPG/PNG, hiển thị lỗi polling và không nhầm approve với publish. Build lại Visitor Flutter web.
- AI tests: 26 pass, 2 DB skip local; FE Node 25 pass/1 skip, Flutter 73 pass/1 skip, Edge 14 pass. Không inference model, DB/R2 hoặc COLMAP thật.
- CI có test TTS/Vision/3D; bỏ tracking pyc. Xem [chi tiết và phần còn thiếu](AI_CODE_UPGRADE_2026_11_04.md).

## 2026-10-26 — Dùng PostgreSQL chung với Backend

- AI Vision thay SQLite bằng PostgreSQL client `psycopg`; embeddings nằm trong schema `ai_vision` của cùng DB/instance đã cấu hình cho BE. Compose không còn volume/database riêng cho dữ liệu Vision; chỉ giữ volume cache model.
- 3D Scan thay SQLite job store bằng PostgreSQL, lưu job metadata trong schema `ai_3d_scan` của cùng DB. Ảnh scan và GLB vẫn nằm trên disk local trong PoC.
- Thêm cấu hình `AI_SYSTEM_DB_*`, `.env.example` (không chứa secret thật), yêu cầu Compose password và hướng dẫn khớp cấu hình BE. TTS không cần DB.
- Chưa nối metadata upload ảnh tham chiếu của portal vào BE API; AI Vision hiện giữ embeddings, còn BE cần sở hữu `artifact_reference_images`/media và gọi service.
- Runtime chưa xác minh kết nối DB vì PostgreSQL ở `127.0.0.1:5432` không lắng nghe trong môi trường hiện tại. Cần cấu hình `AI-System/.env` theo BE và chạy migration/khởi động PostgreSQL BE trước khi start AI Vision/3D Scan.
- `python -m compileall` cho AI Vision/3D Scan và `docker compose config --quiet` đạt. `python -m unittest discover -s tests -v` bỏ qua integration test vì máy chưa cài psycopg và chưa có DB test. Chưa build lại container: Docker Desktop Engine pipe hiện không khả dụng; host PostgreSQL cũng không lắng nghe ở `127.0.0.1:5432`, nên chưa kiểm tra kết nối/runtime.

## 2026-10-22 — Chuyển AI Vision sang CLIP ONNX

- Thay OpenCLIP/PyTorch image encoder bằng ONNX Runtime CPU trong `AI Vision/`; dùng pretrained CLIP ViT-B/32 ONNX image encoder từ `infinilabs/pizza-clip-base-v1`.
- Bổ sung tải model vào cache `/models` khi khởi động, preprocessing CLIP RGB 224×224, vector 512 chiều chuẩn hóa L2; giữ nguyên API index references và recognition.
- Bổ sung `model_id` cho từng embedding. Vector OpenCLIP đã có trong SQLite được giữ lại nhưng không đem so với ONNX vì cùng 512 chiều không đồng nghĩa cùng không gian vector. Ảnh tham chiếu cần index lại.
- Bỏ cài PyTorch/torchvision khỏi Docker image AI Vision; thêm `onnxruntime` và `huggingface_hub`.
- Chưa train/fine-tune model: pretrained CLIP là baseline tổng quát; chưa có benchmark trên bộ ảnh hiện vật SMGS.
- Chưa chạy inference do dependencies ONNX/FastAPI chưa cài trong môi trường. Docker image build bị sandbox chặn quyền truy cập Buildx lock; `docker compose config` vẫn đạt. Chưa xác minh tải artifact, output graph, preprocessing parity, dung lượng/RAM, tốc độ hoặc độ chính xác. Cần pin revision và kiểm tra license/hash trước production.
- `python -m unittest discover -s tests -v` (migration SQLite/cách ly embedding theo model commit), `python -m compileall` và `docker compose config` đạt.

## 2026-10-21 — 3D Scan PoC và Flutter model URL

- Thêm `3D Scan/` như microservice riêng trong `AI-System`, nhận nhiều ảnh JPG/PNG, giới hạn dung lượng, lưu job SQLite và đưa tái tạo COLMAP vào background.
- Dùng pipeline COLMAP tự động, tìm mesh Poisson/Delaunay, thử tạo texture atlas rồi xuất GLB; job dừng ở `REVIEW_REQUIRED` để không tự xuất bản model chưa duyệt.
- Bảo vệ API bằng `X-Service-Key`; endpoint chỉ dành cho gọi server-to-server. Chưa nối service key vào web/mobile.
- Flutter `Artifact` nhận thêm `modelUrl` tùy chọn; màn hình 3D dùng URL của artifact và vẫn fallback sang GLB mẫu khi chưa có URL.
- Rà `smgs_schema.dbml`: bảng `artifacts` chưa có `model_url`, và Backend hiện chưa có scan-job/model-review API. Vì vậy chưa nối upload iPhone Safari, BE gateway, database, storage hay curator role.
- COLMAP CLI chưa được cài/xác minh trong môi trường hiện tại; PoC mới kiểm tra tĩnh. Cần cài COLMAP và thử bộ ảnh thật để xác nhận pipeline, texture, chất lượng GLB, thời gian và tài nguyên.
- `python -m compileall` và `git diff --check` thành công. FastAPI chưa cài trong môi trường nên chưa chạy endpoint; COLMAP executable và .NET SDK cũng chưa có, do đó chưa kiểm thử runtime/BE build. Web build hiện có thành công; Flutter analyze không trả kết quả trong phiên kiểm tra và đã dừng.

## 2026-10-16 — TTS microservice MVP

- Tạo service mới tại `tts-service/` theo cấu trúc microservice của repo `AI-System`.
- Thêm API `POST /api/v1/speech`: nhận văn bản, ngôn ngữ và tốc độ; trả WAV tiếng Việt.
- Dùng `sherpa-onnx` với voice Piper `vi_VN-vais1000-medium`; model chạy trong service container, không nằm trong Flutter và không gọi nhà cung cấp AI bên ngoài trong mỗi lượt nghe.
- Tải model/eSpeak ở lần chạy đầu và giữ trong Docker volume. Cache WAV theo nội dung, voice và tốc độ đọc.
- Thêm Docker Compose, health endpoint, giới hạn đầu vào và tài liệu nối Flutter.
- Ranh giới dữ liệu: Flutter/Content Catalog lấy nội dung đã duyệt; TTS service chỉ chuyển văn bản được gửi vào thành tiếng, không truy cập database hoặc tự biên soạn nội dung.
- AI nhận diện hiện vật chưa được triển khai; Flutter chưa được nối API trong thay đổi này.

## Còn lại trước khi chạy end-to-end

- Cần môi trường Docker có quyền truy cập internet ở lần khởi chạy đầu để tải model.
- Cần Content/Catalog API thực tế để Flutter lấy nội dung theo `artifactId` và chỉ trả nội dung đã xuất bản.
- Cần cập nhật Flutter để gửi nội dung đến service và phát bytes WAV.
- Cần xác nhận voice/license và nghe thử trên thuyết minh bảo tàng trước khi chọn làm voice production.
- Runtime chưa được khởi chạy trong phiên này; vì vậy model tải thực tế, chất lượng audio và thời gian đáp ứng chưa được xác nhận.

## 2026-10-17 — Đối chiếu schema BE

- Đọc `BackEnd/project-docs/smgs_schema.dbml`.
- Xác định QR nằm ở `artifacts.qr_code`; bài thuyết minh nằm ở `narrations`; văn bản phiên bản nằm ở `narration_versions.script`.
- Bổ sung mapping theo `language_id` → `languages.code`, `length_level`, `detail_level`; chỉ chọn `narration_versions.status = published` và `is_current = true`.
- Ghi rõ TTS Service chỉ nhận script từ Content/Catalog API, không đọc DB trực tiếp; DBML tự ghi là bản đề xuất chưa chốt.
- Làm rõ `narration_versions.audio_url`: nếu có audio được duyệt thì Flutter có thể phát trực tiếp; cache WAV nội bộ hiện tại chưa tự ghi ngược URL vào DB/object storage.

## 2026-10-20 — Rà soát source BE/FE để xác định tích hợp TTS

- Rà solution .NET, EF entities/migrations, API controllers, Flutter visitor, React portal, DBML và tài liệu mapping.
- Xác nhận BE hiện là một ASP.NET Core API chia project layer; migration hiện chưa có các bảng narration trong DBML.
- Xác nhận Flutter đang mock QR recognition, nội dung narration lấy từ mock `artifact.aiGuide`, player dùng timer và chưa có playback/TTS client.
- Xác nhận React curation cũng dùng state/mock data; mapping FE đến `narration_versions` chưa có endpoint/backend persistence thực tế.
- Ghi hợp đồng nối phù hợp và thứ tự công việc trong `BE_FE_REVIEW.md`.
- Nêu các điểm môi trường cần giải quyết: base URL Flutter lệch launch profile BE và các endpoint ghi artifact đang allow anonymous. Giá trị secrets không được sao chép vào log.

## 2026-10-20 — Sắp xếp TTS và tạo AI Vision MVP

- Chuyển nội dung service TTS vào folder `TTS AI/` theo cấu trúc người dùng đưa.
- Tạo microservice `AI Vision/` dùng OpenCLIP embeddings để so khớp ảnh query với ảnh tham chiếu được index theo `artifactId`.
- Thêm API có xác thực service key để index/xóa ảnh tham chiếu và nhận diện ảnh; kết quả có similarity, top candidates và ngưỡng yêu cầu xác nhận.
- Embedding lưu trong SQLite volume; ảnh query không được lưu. Service không truy cập database BE.
- Cập nhật README cấp repo và README từng service để mô tả luồng hai service, cách chạy, nạp ảnh và giới hạn.
- `compileall` và `docker compose config` cho cả hai service đều thành công.
- Docker build AI Vision đã thử nhưng Docker Desktop Linux engine hiện không chạy (`dockerDesktopLinuxEngine` pipe không tồn tại), nên chưa xác minh được dependency install/model download/inference.
- Cần xác nhận tải model, dependencies, RAM, ngưỡng similarity và độ chính xác trên bộ ảnh thật khi Docker engine sẵn sàng.

## 2026-10-27 — AI Vision đa hiện vật

- Chọn ảnh hiện vật tại Bảo tàng Lịch sử TP.HCM từ Wikimedia Commons: trống đồng Đông Sơn, ấm đồng triều Lê thế kỷ 18 (CC0), chuông đồng văn hóa Đông Sơn (CC BY-SA 3.0). Giữ creator, license và nguồn từng ảnh trong `AI-System/test-data/hcm-history/manifest.csv`.
- Thêm hai ảnh tham chiếu và một ảnh holdout cho mỗi loại; ảnh holdout không đưa vào embeddings. Bộ ảnh gồm 9 ảnh tổng cộng.
- Seed 3 artifact test vào bảng Backend `artifacts` trong PostgreSQL chung: IDs 1, 2, 3; codes có tiền tố `AI-TEST-`. Database có 2 embeddings mỗi artifact (6 tổng cộng) trong schema `ai_vision`.
- CLIP ONNX holdout: trống đồng → ID 1, similarity 0.9133, margin 0.1040; ấm đồng → ID 2, 0.9358, margin 0.2032; chuông → ID 3, 0.9227, margin 0.1370. Cả ba được xếp đúng trong lần thử này khi cạnh tranh với hai lớp còn lại.
- Đây là inference bằng pretrained CLIP, không train/fine-tune. Chưa phải benchmark production: cần nhiều hiện vật, ảnh điện thoại trong ánh sáng/tủ kính thật, hard negatives và đo false positives trước khi chỉnh ngưỡng.
- Ảnh gốc đang là file trong `AI-System/test-data`; DB chỉ lưu tên file và embedding, chưa lưu bytes ảnh. Nếu cần hiển thị/quản lý ảnh trong sản phẩm, lưu file ở object storage và metadata/URL trong DB.
- `AI-System/.env` chứa cấu hình local và được gitignore. AI Vision health trả 6 reference embeddings.

## 2026-11-11 — Bộ ảnh mẫu đồ gốm và thử COLMAP CPU

- Tải bộ ảnh test từ [LR3D-CULT2](https://data.mendeley.com/datasets/jr23fnrvx2/1), DOI `10.17632/jr23fnrvx2.1`, license CC BY 4.0. Chỉ giữ 40 ảnh PNG render của vật thể `ly_dong_1` (20 góc từ mỗi vòng camera); không giữ mesh nguồn trong thư mục test. Ảnh là render Blender, không phải ảnh chụp hiện vật thật.
- Đặt ảnh trong `AI-System/3D Scan/test-data/LR3D-CULT2/metal-cup-ly-dong-1/images/`; thêm thông tin nguồn, license và giới hạn academic-use trong README cùng thư mục.
- COLMAP 3.8 CPU sparse chạy trực tiếp: đăng ký đủ 40/40 ảnh, 3,704 điểm sparse, sai số chiếu lại trung bình 0.307 px. Lưu kết quả `sparse-colmap-cpu.ply` và ảnh xem bốn hướng `sparse-preview.png`.
- Dense CPU được thử với `--dense 1 --use_gpu 0`; COLMAP bỏ qua PatchMatch stereo vì build không có CUDA, không có dense mesh/GLB.
- Thử POST thật qua Scan API: trả `QUEUED`, sau đó `FAILED`, lỗi COLMAP exit `-6` do worker không truyền `--use_gpu 0` nên COLMAP cố tạo OpenGL context trong container headless. Service hiện chưa hoàn tất luồng tạo GLB bằng CPU; `/ready` chỉ xác nhận binary, worker và DB.
- Việc cần xử lí để demo: cấu hình worker dùng CPU cho feature extraction/matching, sau đó chọn một bước dựng dense mesh chạy CPU thay PatchMatch CUDA, hoặc đổi qua COLMAP build/GPU phù hợp. Chưa đưa model mẫu có sẵn vào hồ sơ hiện vật để tránh nhầm là kết quả do AI-System dựng.

## 2026-11-11 — Sửa luồng CPU và xuất GLB xem trước

- `automatic_reconstructor` giờ chạy headless với `--use_gpu 0 --num_threads 4`, tránh lỗi tạo OpenGL context khi chỉ dùng CPU.
- Khi COLMAP không có dense mesh, worker chuyển sparse COLMAP model sang PLY rồi xuất `model.glb` dạng point cloud. API trả `modelType=sparse_point_cloud` và cảnh báo đây không phải surface mesh kín; dense mesh trả `modelType=mesh`.
- Nâng cấp schema `ai_3d_scan.scan_jobs` idempotent để lưu `model_type`.
- Ban đầu tạo GLB point cloud từ PLY local để kiểm tra đóng gói (60,228 bytes, 3,704 điểm); unit check helper và khởi tạo/migration schema đều đạt.
- Sau đó Docker Desktop cho phép truy cập: rebuild/recreate Scan service thành công, `/ready` healthy và gửi đủ 40 ảnh qua Scan API. Job `ee9a43fb-0e7a-42fa-8517-e2a615e254a4` chuyển `QUEUED → PROCESSING → REVIEW_REQUIRED`; GET model trả GLB 55,920 bytes, đọc lại được với 3,435 điểm. File API tạo đã lưu tại `3D Scan/test-data/LR3D-CULT2/metal-cup-ly-dong-1/model.glb`.
- Kết quả xác nhận end-to-end CPU sparse reconstruction và GLB delivery qua API. Giới hạn còn lại: GLB là point cloud rời rạc, chưa có bề mặt/texture; dense reconstruction cần backend MVS phù hợp CPU hoặc COLMAP build có CUDA.

## 2026-11-11 — Chuyển Scan sang pipeline CPU COLMAP + OpenMVS SGM

- COLMAP chạy CPU với `--use_gpu 0`, `--dense 0`, `--num_threads 4`; thêm `--blank_pixels 1` để giữ vùng ảnh khi undistort. Bản OpenMVS Ubuntu x64 v2.4.0 được ghim trong Dockerfile, SHA-256 `7104ae1ddd6ca38fbca9e0e4a70b20af59e21e0b497eb7181c864fbf38ca8d00`; không cần CUDA. Debian Bookworm không tương thích GLIBC/GLIBCXX của binary nên Scan image chuyển sang Ubuntu 24.04/Python 3.12.
- Worker chạy `InterfaceCOLMAP` → `DensifyPointCloud --fusion-mode -2` (CPU SGM) → `ReconstructMesh` → `RefineMesh` → `TextureMesh --export-type glb`, rồi kiểm tra GLB phải có vertices và faces. Đã bỏ fallback sparse cloud; API không nhận job nếu thiếu OpenMVS.
- Build/recreate container thành công; `/ready` xác nhận COLMAP, 5 binary OpenMVS, worker và PostgreSQL đều sẵn sàng. PostgreSQL chung ban đầu stopped, sau khi bật container phát hiện password đang lưu trong volume khác giá trị credential BE/AI-System đã cấu hình; đã đồng bộ role `postgres` về credential đã cấu hình, không thay đổi dữ liệu/schema.
- Gửi 40 ảnh LR3D-CULT2 qua Scan API. Job `9649b34b-ced2-43cd-846a-dae4bac98155` thất bại vì OpenMVS chạy sai working directory, đã sửa. Job `a1ed74f3-10f9-49c3-ac98-dd0c73e20289` đi qua dense reconstruction và refine nhưng dừng ở tên project trung gian của `TextureMesh`; log được giữ trong DB/container.
- Job cuối `6d9f771a-acb1-4a57-a483-6741ae41a56e` chạy thành công qua API: `REVIEW_REQUIRED`, `modelType=mesh`. GLB được GET lại từ API, 245,740 bytes; đọc lại có texture, 6,327 vertices và 9,812 faces. Mesh không watertight nên vẫn cần curator xem và duyệt. Tệp lưu tại `3D Scan/test-data/LR3D-CULT2/metal-cup-ly-dong-1/api-openmvs-cpu-mesh.glb`.
- GLB tham chiếu texture ngoài `model_0.png`; endpoint hiện chỉ trả GLB. Đã thêm PNG companion vào bộ demo và cập nhật `api-mesh-viewer.html`: mặc định dùng vật liệu đồng trung tính để geometry không bị đen, có nút xem texture thô. Atlas texture thật của lượt test có nhiều mảng đen/cam và seams; đây là lỗi chất lượng reconstruction/texture, không chỉ lỗi ánh sáng. GLB API chưa tự chứa texture.
- Khi hiển thị texture thô, model trông gần đen do atlas OpenMVS có nhiều vùng đen/cam; viewer ban đầu cũng mất texture vì thiếu PNG companion. Đã sửa viewer để tải đúng GLB + PNG, mặc định hiển thị silhouette bằng vật liệu màu đồng phẳng (tránh phụ thuộc normals/ánh sáng của mesh), và thêm nút chuyển sang texture gốc. Đã kiểm tra trực quan qua browser: mode màu đồng nhìn thấy hình khối, mode texture vẫn phản ánh các lỗi texture thực tế.
- Theo yêu cầu màu gần hiện vật, đã chạy thử riêng `TextureMesh` trên cùng mesh, không chạy lại COLMAP/dense: `--virtual-face-images 3 --cost-smoothness-ratio 0.5 --empty-color 6440515` (RGB nâu trung vị `98,86,67` lấy từ ảnh test). Số patch trong log tăng từ 117 lên 307; atlas fallback cam chuyển sang nâu. Tuy nhiên xem GLB trực quan vẫn không cho màu/chi tiết trung thực, nên chưa thay cấu hình API bằng thử nghiệm này.
- Tạo preview gap-fill riêng bằng cách lấp pixel đen hoàn toàn của atlas với màu nâu trung vị để đánh giá. Model lên nâu nhưng khá phẳng, không khôi phục họa tiết gốc. Đây là preview có tô bù, không phải texture photogrammetry trung thực. `api-mesh-viewer.html?variant=texture-try` và `?variant=gapfill` giữ biến thể thử; GLB API gốc và texture thô không bị ghi đè.
- Đây là bộ ảnh render Blender, không phải ảnh chụp hiện vật thật; chưa chứng minh chất lượng với ảnh iPhone/bảo tàng. API chưa nối Backend modelUrl/curator role. OpenMVS công bố AGPL-3.0; giữ license text tại `3D Scan/THIRD_PARTY_LICENSES/OpenMVS-LICENSE`, nhóm cần xem điều kiện phân phối image.
- `py_compile`, `git diff --check`, Compose parse và container readiness đã kiểm tra. Unittest suite được thử nhưng request đầu tiên treo quá 60 giây và dừng; nguyên nhân chưa xác minh nên không ghi bộ test là pass.

## 2026-11-11 — 3D pipeline audit correction

- Re-audited actual COLMAP/OpenMVS logs, mesh topology, GLB UV/material and atlas coverage. The previously reported API job `6d9f771a-acb1-4a57-a483-6741ae41a56e` had 40/40 registered images but OpenMVS SGM produced 0 dense points; its exported GLB was meshed from sparse points. This corrects the prior “dense scan completed” claim.
- Added a detailed evidence and experiment report in [`3D Scan/PIPELINE_AUDIT_2026-11-11.md`](3D%20Scan/PIPELINE_AUDIT_2026-11-11.md). In short: original PLY topology was watertight with valid normals; bad appearance was largely caused by zero dense points and an atlas with ~47.6% orange fallback pixels. UV-centroid sampling showed only ~8.2% source-texture coverage on the original GLB.
- Updated the worker to reject zero-point dense output, retry with CPU PatchMatch in a clean folder, tune TextureMesh from a measured same-mesh comparison, and embed the PNG atlas in GLB. Removed median-color/gap-fill experiment files and added a COLMAP-pose-aligned source/model comparison page.
- Rebuilt Scan with the 80% COLMAP registration gate. Verification job `b21737db-6a72-42a3-89f7-d3fe9fa24dea` (40 rendered test views) had six sparse models; the best registered 25/40. SGM produced 0 dense points; CPU PatchMatch then produced 106,006 points in 2m41s, but this did not establish a faithful reconstruction. TextureMesh produced a 2048 atlas and the GLB embedded its PNG, but UV source coverage remained unverified and the mesh had 127 boundary edges. Corrected this job from `REVIEW_REQUIRED` to `FAILED`, cleared `model_path`/`model_type`, and retained its raw logs for diagnosis. The worker now rejects this input before dense reconstruction because it falls below the 80% image-coverage threshold. `compileall` could not write `__pycache__` as the container user; importing the module and registered-image count check succeeded.

## 2026-11-11 — Follow-up on the visibly incorrect artifact

- Later user approval: an incomplete model is acceptable for preview. Generated `reconstructed-partial.glb` from the 180-image reconstructed mesh plus source-image TextureMesh output (24.74s, embedded 2048 atlas, 11,223,768 bytes). The viewer defaults to this partial textured reconstruction and retains separate geometry/reference modes. The central-floor hole remains; no original OBJ was substituted into this reconstructed output.

- Found and corrected a comparison-viewer calibration error: 512×512 raw source dimensions were used with the OpenMVS undistorted camera; the actual undistorted images are 1024×1024. The page now compares the matching undistorted image/projection and offers an original-image toggle.
- The COLMAP shared camera has `k=-7.595533`; the radial map folds inside the image extent and the undistorted input visibly contains a stretched ring around the object. Added a SIMPLE_RADIAL fold guard before sending that calibration to OpenMVS. This explains why 40 registered views alone did not ensure a valid reconstruction.
- Isolated seam processing on the same mesh: near-black atlas pixels were 34.65% with both options enabled, 0% with both disabled, 35.19% with global only, and 26.34% with local only. Disabled both seam options in the worker. Texture remains sourced from images; the gray background/incorrect geometry remain visible, so the diagnostic GLB is explicitly marked failed. No average-color or gap filling is applied.
- Recovered the full LR3D-CULT2 metal-cup archive with verified SHA-256. It contains 180 images, OBJ/MTL/PNG and metadata with camera positions but no rotations/intrinsics. Added an offline camera audit/conversion tool; inferred look-at cameras plus reference-calibrated intrinsics achieved 98.70–99.03% silhouette IoU on eight held-out images. This uses the source OBJ to calibrate a synthetic benchmark and is not a general unknown-object scan workflow. Details: `3D Scan/DATASET_CAMERA_AUDIT_2026-11-11.md`. A fixed-prior 180-image triangulation produced 16,411 points at 0.887 px reprojection error; poses were unchanged to floating-point precision. Native worker commands now preserve stdout/stderr and command arguments in per-step log files.
- Full 180-image CPU dense result: 665,122 points in 7m28s; refined geometry 70,537 vertices / 141,041 faces, 95.14–96.83% silhouette IoU, but 41 boundary edges and a missing central interior floor. No TextureMesh was run on this geometry because it failed the pre-texture check. Source-reference ray tests confirmed the central floor is occluded from all 180 cameras; the dense PLY has zero points in that region. Free-space graph-cut was tested and rejected as worse. Exported a neutral diagnostic GLB and a clearly separate original-OBJ/PNG imported reference asset with provenance labels; neither is claimed as an approved scan. Worker now disables automatic hole filling and tower mode and preserves refine detail; byte-level texture embedding preserves UV/material/unlit extensions and was checked against original geometry/PNG bytes.
