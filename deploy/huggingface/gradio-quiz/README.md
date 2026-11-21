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

## Source-constrained generation

The planner splits exact source spans into usable facts, removes software-test
disclaimers and duplicate passages, and prioritizes different topics. Each question
gets its own source passage rather than letting the model repeatedly select one.

For recognized facts (purpose, material, shape, decoration and technique), rules
extract the answer from that passage and select three Vietnamese distractors from
a small controlled vocabulary. Choices are shuffled reproducibly. **Qwen writes
the question** using the assigned fact and a question hint; it does not need to
count four options or invent an evidence quote. This is a hybrid quiz generator,
not unconstrained generation of all quiz fields. Unknown fact types retain the
stricter full-JSON model path; coverage of new museum terminology needs review.

Source grounding, topic compatibility, question/answer similarities, language drift
and negative/yes-no question checks reject known bad candidates. These are rules,
not an independent semantic model: they can miss paraphrases or reject legitimate
questions. A different source passage alone does not prove a different meaning.

Each fact has at most two attempts. A retry receives the rejection reason and uses
low-temperature sampling with a reproducible seed. Invalid facts can be skipped
in favor of other source facts; total model calls and time are capped. Quota/time
failures stop the batch. **No server question or fixed demo question is inserted
when the model returns an empty or invalid question.** Citation text always comes
from the original assigned passage.

The result includes `requestedCount`, `generatedCount`, `complete`, `questions`
and `warnings`, with `distinctEvidenceCount` and `reviewRequired=true`.
Partial sets remain explicitly incomplete; no fake questions pad
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
For legacy single-item calls, the prior-question count rotates the assigned fact;
the API does not infer the evidence used by arbitrary historic questions.
`POST /api/v1/studio/drafts` also accepts `mode=narration`, plus `audience`
and `tone`, using the same service key. It returns `title`, `narrationText`,
and `evidenceQuotes` as required by BE. Quotes must occur in the source;
invented numeric facts are rejected. This generates a draft only; audio is
produced by the separate Azure TTS service through BE.
Narration rewrites notes into connected visitor-facing prose with an opening,
guided observation and a closing (normally 120–180 Vietnamese words for a short
source). Audience/tone affect the instructions. Added transitions must not invent
facts or turn tentative descriptions into certainty. Copied/very short output is
rejected and gets one correction attempt within the existing inference budget.
The model writes prose without a stock narration example. The adapter retains the
supplied artifact name as title and attaches up to three literal source excerpts,
ranked by overlap with the prose. This avoids JSON/citation-count generation errors;
the BE response schema is unchanged. Overlap is not semantic verification.
These checks do not prove historical accuracy; curator review is still required.
Narration uses Qwen3-4B-Instruct-2507 with a separate prose prompt/decoder;
quiz retains Qwen2.5-1.5B. Both GPU and ONNX revisions are pinned in their adapters.
The Qwen3 ONNX export includes two external weight shards, downloaded lazily with
the graph. Its first CPU request can take longer while downloading/loading.
Quiz/chat defaults are unchanged. Total inference time remains bounded, including
one correction. No minimum token floor forces a model to invent filler.
Direct Gradio APIs: `/tao_quiz`, with inputs name, source, difficulty,
excluded JSON array and count; `/soan_thuyet_minh`, with inputs name, source,
audience and tone.

Startup uses `demo.launch(ssr_mode=False)` so ZeroGPU's launch hook reports the
decorated function, with one listener on the configured Gradio port. REST routes
are registered via `app_kwargs`; no second Uvicorn/Node server is started.

ZeroGPU is quota-limited shared compute. Backend bridge requests use anonymous
quota; readiness does not promise GPU availability, response time or production
uptime. This Space does not scan 3D or train models.

The REST bridge forwards HF's `x-ip-token` only to its own loopback Gradio
queue, retaining the caller's quota context. This does not grant unlimited GPU
access. A single question or narration requests 45 seconds; larger quiz batches
request 90 seconds. Inference and retry budgets finish before the allocation.

If HF explicitly reports GPU quota exhaustion or a GPU duration limit, REST
requests run the mode's pinned model as ONNX INT4 on the Space's existing
CPU. This does not allocate a paid GPU or change hardware. The pinned CPU model
loads lazily; the first request includes its download/startup time. CPU inference
is slower, with one active request and bounded generation time. A success has
`X-AI-Runtime: onnx-cpu`. Real model and citation validation are still required;
there is no static-content fallback. Other infrastructure/model errors are not
hidden or automatically retried. Readiness reports whether CPU has loaded.
Authenticated server calls may set `X-AI-Runtime-Preference: cpu` to select CPU
explicitly for a reproducible check or when avoiding GPU quota is preferred.
The normal BE request uses automatic GPU/CPU selection and requires no change.
