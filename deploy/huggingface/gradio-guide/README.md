---
title: SMGS AI Guide
emoji: 🏛️
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 6.32.0
python_version: '3.12'
app_file: app.py
pinned: false
startup_duration_timeout: 1h
---

# SMGS — Artifact chatbot and personalized tours

Select **ZeroGPU** in Space hardware. This is a separate deployment from the
existing quiz Space; it neither imports nor replaces the quiz generator.

- Chat: Qwen2.5-1.5B-Instruct, pinned PyTorch checkpoint
  `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`, real ZeroGPU inference.
  Reuses the SMGS ONNX service's prompt, JSON parser and exact-source guard.
  The ONNX decoder itself is not loaded here. No training or Gemini API needed.
- Tour: the original `AI Tour` TF-IDF/interest/time algorithm and Pydantic schemas,
  copied by the allowlist exporter without changes. Runs CPU, outside GPU allocation.
- Public Gradio tabs are for permitted demo input. Examples are synthetic;
  they are not records retrieved from a real museum database.

## Secrets and REST

Add two **Secrets**, each a random string of at least 32 characters:

| Secret | Protected route |
|---|---|
| `AI_CHAT_SERVICE_KEY` | `POST /api/v1/guide/answers` |
| `AI_TOUR_SERVICE_KEY` | `POST /api/v1/tours/recommend` |

Pass the corresponding value as `X-Service-Key`. Never put these values in
public Variables, frontend code, Git, query strings or Gradio inputs.
REST authentication runs before JSON parsing; request size limits are 144,000
bytes for chat and 2,000,000 for tours, including streamed bodies.
Public Gradio UI/API remains anonymous and quota-limited, like other public demos;
the REST key does **not** make the entire Space private.

`GET /live` checks process. `GET /ready` checks that the model loaded and both
REST keys are configured; it does not promise available GPU quota.
`examples.json` contains complete request examples. Chat REST returns the original
`{"answer":"...","supported":true}` schema. Direct Gradio `/hoi_hien_vat`
returns an `ok/result` or `ok/error` envelope so GPU-worker error details survive.
Tour output preserves the camelCase `PlanResult` contract, with no model envelope.

## Data and quality limits

These stateless services receive context/candidate records in the request.
They do not query Supabase/PostgreSQL, fetch credentials, check visitor rights,
publish content, persist chat history or save tours. The caller must supply
approved sources and authorized candidates. Approval/access checks remain the
caller's responsibility, as in the original AI service contracts.

Chat accepts 2,048 input tokens, up to four user/assistant pairs, generates at
most 384 tokens with a 45-second generation budget and a 60-second GPU allocation.
Generation time limits are not a hard prefill/cancellation guarantee.
Unsupported/model-invented prose is rejected by the source-containment guard.
Source containment does not prove semantic relevance; human/domain evaluation is
still needed. No invented fallback answer is supplied after generation errors.

Tours use estimated walking times by room/floor, not actual indoor shortest-path
navigation. The algorithm can return fallback or zero stops; those states remain
explicit. Tour REST runs on CPU and does not need available GPU quota, although
both features still share the Space's process, startup and sleep lifecycle.

Gradio queue: one chat request at a time, maximum queue size eight. REST chat
enters through that queue so ZeroGPU gets the correct execution context.
Loopback bridge requests use anonymous HF quota; API keys do not grant extra HF
quota. No keepalive/sleep bypass, fake GPU computation or uptime guarantee.

## Build and operation

HF manages the compatible `spaces` SDK pin; do not add a conflicting version.
Canonical `demo.launch(ssr_mode=False)` runs one listener and triggers ZeroGPU's
startup hook. Custom REST routes **and their authentication middleware** are
installed through `app_kwargs`.

This bundle contains no Dockerfile, DB, `.env`, model weights, tokens or photos.
HF downloads the pinned model at startup. Persistent museum data is not stored
on the Space disk. First startup, sleep, queues and daily quotas can delay or
reject requests. This is a free cloud demo deployment, not an always-on SLA.

Provider references (checked 18 November 2026):
- https://huggingface.co/docs/hub/en/spaces-zerogpu
- https://huggingface.co/docs/hub/en/spaces-overview

Deployment and verification instructions are maintained in the main repository:
`deploy/huggingface/GUIDE_TOUR_DEPLOY_VI.md`. Local tests are not evidence of an
actual HF GPU run; consult the implementation log for the latest verified status.
