# Azure: Scan CPU, TTS and Vision

## Verified 21/11/2026 — live Scan activity and cancellation

- The interrupted artifact-2 job `9b41b7a1-114a-4c35-8fb6-fe5a99dd43ab`
  was conditionally marked FAILED after verifying no native worker existed.
  Its input photos, partial files and logs were retained; no bulk status reset.
- The next job `b0519c24-ac66-4755-9398-f8eccdb24555` was kept running at the
  user's request and reached REVIEW_REQUIRED 100%. Its GLB is 6,768,124 bytes;
  all 180 input images survived the subsequent guarded Scan-only replacement.
  It remains a draft for review; no model was saved into the BE catalog.
- Live activity reports 180 distinct photos and 540 completed depth operations.
  Repeated refinement passes must not be described as new distinct photos.
- `scan-status` serves only authenticated GET status/list routes. It has no
  worker lifespan, uses `/data` read-only, 384 MiB / 0.25 CPU, and lets status
  parsing deploy independently of a busy native worker. Caddy routes only
  matching GET paths to it; uploads/model/cancel requests go to `scan`.
- The guarded worker update ran only after the job reached review and all
  queued/processing jobs and native processes were absent. Real Linux process
  cancellation, rollback-only DB cancellation/idempotency/late-write protection,
  public 401/409 protection and readiness checks passed. No test job remained.
- Frontend main release `783d440` displays stage counters, refinement operations
  and an indeterminate bar when no native denominator exists. Vercel's public
  bundle was checked for the live counter and exclusion of the mock UI fixture.
- The AWS BE cancellation route changed from 404 to 401 during the rollout,
  confirming the authenticated route is now present. Staff assignment and
  cross-artifact cancellation were checked locally with the BE test harness;
  no real user's production job was cancelled. Existing AiScan configuration
  is sufficient.

For a fresh deployment, build/start both `scan` and `scan-status` before enabling
the Caddy status route. Preserve `scan-data`; do not recreate a busy Scan worker.
The verified release bundle, guard and check reports are staged at
`/home/azureuser/scan-cancel-20261121` on the VM and
`D:\SEP409\tmp\scan-cancel-20261121` locally.

## Verified 21/11/2026 — Vision running; BE rollout pending

- Vision is running on the existing VM at
  https://vision.172-198-161-72.sslip.io/ready (HTTP 200, model_ready=true).
- Existing PostgreSQL `smgs_demo` connects as `smgs_vision`, schema `ai_vision`,
  TLS 1.3 with certificate/hostname verification. This role cannot create a
  database or create schemas in the database. Scan credentials are separate.
- CLIP ViT-B/32 ONNX is pinned to
  `f71041903f3a04f7a883b90f0126eeb4ab44fa7c`; the offline image includes the
  graph and external weights, verified against `app/vision_model_manifest.json`.
  Model embeddings are 512-dimensional. A synthetic image encode took 0.113s
  in the isolated Azure smoke test; this is not end-to-end latency or accuracy.
- Real model + DB index/read/recognition checks passed in a rolled-back
  transaction. No test reference was persisted. Authenticated invalid images
  return 415; requests without the service key return 401 before parsing uploads.
- The reference index is empty. Hosting/readiness does not imply that real
  museum artifacts can already be recognized. Staff must add reference images.
- Production BE integration is pending. Private `.env.be-vision` contains only
  `AiVision__BaseUrl` and `AiVision__ServiceKey` for the BE operator; do not paste
  the key into chat or configure it as a VITE/Flutter variable.
- Deploy the BE `ArtifactVisionController` and named `artifact-vision` client.
  Web/mobile use user JWTs via `/api/vision/health`, `/api/vision/recognitions`
  and `/api/artifacts/{id}/vision/references`. Reference mutations require
  staff/admin assignment; recognition searches only active published artifacts.
  Deploy those client changes after the BE gateway is available.

Vision uses a separate private `.env.vision` (template `.env.vision.example`).
On the VM, run only the requested service:

```sh
cd /home/azureuser/smgs-ai/deploy/azure
sudo docker compose --env-file .env.azure --env-file .env.vision --profile vision up -d --no-deps --no-build vision
```

The installed image is `smgs-vision:azure`. Its build used an offline bundle of
Linux wheels and the verified pinned model because PyPI timed out during Azure
builds. Deployment staging is `/home/azureuser/vision-deploy-20261121`; the local
bundle is in `D:\SEP409\tmp\vision-deploy-20261121`. No secrets are in the bundle.
`VISION_MODEL_LOCAL_DIR` points to `/models/pinned/<revision>` for that image.
For a standard source rebuild without bundled weights, leave this setting empty
to use the normal pinned Hugging Face cache download. Keep `vision-models` volume.

The older dated sections below describe earlier deployment states.

## Verified 20/11/2026 — Scan connected

- Both TTS and Scan are running and healthy. Scan public readiness:
  https://scan.172-198-161-72.sslip.io/ready returned 200, database_ready=true.
- Existing BE PostgreSQL smgs_demo connected as separate smgs_scan role with
  TLS 1.3 and PGSSLMODE=verify-full. PGSSLROOTCERT is explicitly passed to the
  container using its system CA bundle. No TLS verification bypass was used.
- Eight Azure-to-DB checks passed; insert/read/update test used a transaction
  rollback and left no test job. Ten public HTTPS readiness/auth/DB-read checks
  passed, including BE's artifact-list route through Caddy.
- .env.be-scan contains the actual two-line BE configuration with the existing
  Scan service key, on VM and local workspace, ignored by Git. BE must load this
  file into its own process/container environment and recreate/restart to apply.
- Full image-upload/photogrammetry reconstruction and production BE integration
  have not been tested in this deployment. No model or museum record was created.
- EC2/PostgreSQL must remain available for Scan jobs. TTS does not use that DB.
  The 19/11 notes below are historical and describe the earlier pending state.

## Verified 19/11/2026

- VM SSH, Docker Engine/Compose installed; only TTS and Caddy containers running.
- TTS HTTPS https://tts.172-198-161-72.sslip.io/ready returned 200 with verified
  public TLS certificate. Real Piper WAV, cache and auth passed 8 VM-loopback
  checks plus 6 public HTTPS checks. This is not a BE production integration test.
- Private BE config with the real TTS key is in `.env.be-tts` on the VM and local
  workspace (ignored by Git). Copy its three lines into the BE process/container
  environment; do not paste the key into chat. Requires BE recreate/restart.
- Existing DB credentials/network access are pending from the BE owner. Scan
  is not running; its hostname/certificate exist but /ready currently returns 502.
  Do not configure it as a working service or claim a completed reconstruction.
- Scan image built successfully. COLMAP and all five OpenMVS binaries executed
  help commands and resolved shared libraries in a network-disabled container.
  Missing-DB deployment guard passed; this is not a reconstruction test.
- TTS restart persistence passed: ready=true, first request HIT, WAV identical.
- Proxy error logging was tested with a fake header; request metadata is removed.
- No automatic deallocation schedule or managed-identity RBAC was installed.
- DB owner handoff: `DB_HANDOFF_VI.md` and `scan_database.sql`. Outbound IPv4
  measured from VM is 172.198.161.72; user portal screenshot confirms Static.
  Allowlist only 172.198.161.72/32. DB remains inaccessible/unconfigured; no script
  has been run on EC2 and no network rule was changed on AWS.

VM smgs-ai-server, 4 vCPU/16 GB, Ubuntu 24.04 x86_64. This Compose does not
deploy BE/FE/PostgreSQL/HF services. Scan stays behind a profile until the existing
BE database connection is supplied. No SQLite replacement or second database.

Use `.env.azure.example` as the private `.env.azure` template. Generate distinct
random service keys; configure the same keys in BE `ArtifactSpeech__ServiceKey`
and `AiScan__ServiceKey`. Never commit or print resolved Compose config.

From this directory on the VM:

```sh
sudo sh deploy.sh tts
# Only after configuring the existing PostgreSQL and allowing Azure to connect:
sudo sh deploy.sh scan
```

Builds use only Dockerfile/app/requirements/tools/license allowlists, without
models, datasets, `.env`, private keys or Git history. Named volumes retain TTS
model/cache and Scan input/jobs/GLB across container recreation. Do not use down -v.

HTTPS proxy uses separate root hosts for TTS and Scan, compatible with BE URL
validation. Azure NSG must permit TCP 80/443 for ACME/public API; only proxy is
public. Python API ports 8000/8002 bind loopback. No access logging of request
bodies or service keys. Scan CPU cap 3.5, TTS 1; Scan worker concurrency remains 1.

On 21/11 the running Scan container CPU quota was raised from 3 to 3.5 using
`docker update --cpus 3.5`, preserving the running job and its native process.
Two-second samples showed 6.02 CPU seconds before and 7.00 afterward. This
confirms extra CPU allocation, not a measured reduction in total reconstruction
time. The existing VM remains 4 vCPU; no VM size change was made.

BE settings after HTTPS/readiness verification:

```dotenv
ArtifactSpeech__Enabled=true
ArtifactSpeech__BaseUrl=https://tts.172-198-161-72.sslip.io/
ArtifactSpeech__ServiceKey=<same TTS_SERVICE_API_KEY on VM>
AiScan__BaseUrl=https://scan.172-198-161-72.sslip.io/
AiScan__ServiceKey=<same SCAN_SERVICE_API_KEY on VM>
```

DB/readiness/auth are verified; test a permitted real image set through BE before
claiming the full reconstruction workflow works end to end.
Use verify-full with the trusted CA bundle specified by PGSSLROOTCERT. Future
private-tunnel configurations require separate review of container connectivity.
Confirm DB firewall/listen settings with the BE owner; never open DB globally.

Stopping a container does not stop VM compute billing. Use Azure Stop and confirm
Stopped (deallocated) when finished. Managed identity alone does not grant VM
deallocation permission; an automatic deallocation schedule is not installed yet.
Interrupted PROCESSING scans need review; no claim of automatic crash recovery.
