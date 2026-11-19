# Azure: Scan CPU + TTS only

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
bodies or service keys. Scan CPU cap 3, TTS 1; Scan worker concurrency remains 1.

BE settings after HTTPS/readiness verification:

```dotenv
ArtifactSpeech__Enabled=true
ArtifactSpeech__BaseUrl=https://tts.172-198-161-72.sslip.io/
ArtifactSpeech__ServiceKey=<same TTS_SERVICE_API_KEY on VM>
AiScan__BaseUrl=https://scan.172-198-161-72.sslip.io/
AiScan__ServiceKey=<same SCAN_SERVICE_API_KEY on VM>
```

Do not enable BE Scan before successful DB/readiness and reconstruction tests.
The hostnames above are deployment configuration, not proof services are live.
`PGSSLMODE=require` encrypts DB traffic without authenticating the DB certificate;
use verify-full with a trusted CA or an authenticated private tunnel as appropriate.
Confirm DB firewall/listen settings with the BE owner; never open DB globally.

Stopping a container does not stop VM compute billing. Use Azure Stop and confirm
Stopped (deallocated) when finished. Managed identity alone does not grant VM
deallocation permission; an automatic deallocation schedule is not installed yet.
Interrupted PROCESSING scans need review; no claim of automatic crash recovery.
