---
title: SMGS Quiz and Narration API
emoji: 🏛️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
base_path: /docs
startup_duration_timeout: 1h
---

# SMGS Quiz and Narration API

Uses the existing SMGS FastAPI app and pinned Qwen2.5-1.5B ONNX Q4 model on CPU.
Set `AI_CHAT_SERVICE_KEY` in Space Settings → Secrets before running.
GET `/ready` checks model readiness. POST `/api/v1/studio/drafts` with
`X-Service-Key` generates a quiz (`mode: quiz`) or narration draft.

This service does not read PostgreSQL. The SMGS backend supplies source text,
checks staff permissions and handles curator review and persistence.
Model output still needs review. This is a Docker API, not a standalone museum UI.
