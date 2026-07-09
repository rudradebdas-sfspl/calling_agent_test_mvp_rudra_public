# Full CI/CD Addon for Voice Agent

Copy the contents of this addon into the root of `structure_fixed`.

```bash
unzip voice_agent_ci_cd_full.zip -d /path/to/structure_fixed
cd /path/to/structure_fixed
git add .github ci_cd tests requirements-dev.txt
git commit -m "Add full CI/CD test gates"
git push origin main
```

## Added test coverage

- VAD preset unit tests
- Agent schema/provider validation tests
- STT/TTS/LLM factory mapping tests without real API calls
- Full mocked AgentPipeline one-turn smoke test
- FastAPI health test
- Agent CRUD API test
- KB text upload/list/delete API test
- Real Redis sidecar roundtrip test
- PostgreSQL/pgvector schema creation through the integration fixture
- Frontend build gate
- Docker image build gate for backend, frontend, and sip-proxy

## Before first push

Make sure secrets and runtime files are not tracked:

```bash
git ls-files | grep -E '(^|/)\.env$|frontend/\.env|worker.*log|sip_trunk_ids.json'
```

If any are tracked:

```bash
git rm --cached .env frontend/.env worker.log worker_trimmed.log sip_trunk_ids.json 2>/dev/null || true
```

## Frontend lockfile

Recommended:

```bash
cd frontend
npm install --package-lock-only
cd ..
git add frontend/package-lock.json
```

The workflow can fall back to `npm install`, but committing `package-lock.json` is the cleaner production approach.