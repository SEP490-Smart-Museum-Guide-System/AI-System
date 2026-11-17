---
title: SMGS AI Quiz
emoji: 🏛️
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 6.32.0
python_version: '3.12'
app_file: app.py
pinned: false
startup_duration_timeout: 1h
---

# SMGS Quiz — Gradio ZeroGPU

Select ZeroGPU hardware in Space Settings. This variant uses the official
Qwen/Qwen2.5-1.5B-Instruct PyTorch checkpoint (pinned revision), not the local
ONNX CPU decoder. It reuses SMGS output validation with a Space-specific
evidence-index prompt.

Hugging Face pins the supported `spaces` SDK in its build command. The requirement
is deliberately unversioned here to avoid conflicting with that platform pin.

The public UI defaults to a set of **five Vietnamese questions** (1/3/5 selectable),
each with four options, a correct index, explanation and source quote. One GPU
allocation composes the set sequentially under an 85-second budget. Every question
passes the existing SMGS source validator and excludes already generated questions.
The model selects an `evidenceIndex`; the service copies that exact source passage
into `evidenceQuote` and explanation. The correct option must occur in the selected
passage, and invented/invalid indices or unsupported answers are rejected. The model
does not write citation text. One bounded retry is allowed for an invalid candidate,
within the same overall budget. This does not independently prove question semantics.
The result includes `requestedCount`, `generatedCount`, `complete`, `questions`
and `warnings`. Partial sets remain explicitly incomplete; no fake questions pad
the result. Review the answers and source before publication. Do not paste private museum documents into
a public demo. No database credentials, private photographs or .env files belong here.

Optional BE bridge: add `AI_CHAT_SERVICE_KEY` in Settings → Secrets.
`GET /ready` checks model loading. `POST /api/v1/studio/drafts` accepts the SMGS
quiz payload with `X-Service-Key`, submits it through Gradio's queue and returns
the raw single-question object for compatibility with the current BE/FE loop.
`excludeQuestions` supports up to 5 prior questions.
`POST /api/v1/studio/quiz-sets` accepts the same fields plus `count` (1/3/5,
default 5) and returns the whole set. This new endpoint is not yet called by the
existing BE/FE; those still aggregate single-question responses.
Narration is not implemented here. Direct Gradio API: `/tao_quiz`, with inputs
name, source, difficulty, excluded JSON array and count.

Startup uses `demo.launch(ssr_mode=False)` so ZeroGPU's launch hook reports the
decorated function, with one listener on the configured Gradio port. REST routes
are registered via `app_kwargs`; no second Uvicorn/Node server is started.

ZeroGPU is quota-limited shared compute. Backend bridge requests use anonymous
quota; readiness does not promise GPU availability, response time or production
uptime. This Space does not scan 3D or train models.
