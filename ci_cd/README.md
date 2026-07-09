# Voice Agent CI/CD Folder

This folder keeps the project-specific CI/CD assets in one place so developers can understand deployment without digging through random notes.

## Important rule

GitHub Actions workflow files must stay in `.github/workflows/`. GitHub will not execute workflows kept only inside `ci_cd/`.

So the structure is:

```text
.github/workflows/pipeline.yml   # actual GitHub Actions runner
ci_cd/                           # docs, prod compose, scripts, templates
```

## What the pipeline checks before deployment

1. Python lint: `ruff check backend module telephony sip-proxy`
2. Offline unit tests: VAD presets, schema validation, provider factory mapping, mocked agent pipeline
3. Integration tests: FastAPI `/health`, Agent CRUD, KB upload/list/delete, real Redis roundtrip, PostgreSQL/pgvector schema
4. Frontend build: `npm ci` when lockfile exists, otherwise `npm install`, then `npm run build`
5. Docker build: backend, frontend, sip-proxy images build on every PR/push
6. GHCR push: images are pushed only on `main`
7. VM deploy: staging first, production after GitHub Environment approval

## Why provider tests are mocked

CI should not call Sarvam, Cartesia, Gemini, Deepgram, or Quail on every push. That creates cost, latency, flaky failures, and secret exposure risk. The pipeline validates that our code builds the correct provider config and that the full VAD -> STT -> LLM -> TTS flow works with fake providers.

Real provider quality tests should run manually or on a scheduled workflow with strict limits.

## Manual deploy from VM

```bash
cd ~/voice-agent
git fetch --all
git reset --hard origin/main
export TAG=<github_sha>
export GHCR_IMAGE_PREFIX=ghcr.io/<owner>/<repo>
bash ci_cd/scripts/deploy.sh
```