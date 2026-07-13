# Deployment MVP Patch

This patch fixes the immediate EC2 deployment blockers found in the uploaded project:

- Frontend host/container port mismatch (`5173:80` vs Vite on `5173`).
- Frontend API calls pointing to the visitor's own `localhost`.
- Browser receiving the internal Docker LiveKit hostname.
- CORS limited to localhost only.
- LiveKit UDP port `7882` not mapped.
- SIP services starting before EC2-specific SIP configuration is ready.
- Host-networked LiveKit SIP unable to reach Redis inside the Docker network.
- `auto_setup_trunks.py` missing from the backend image.
- Local `.env` files entering Docker build contexts.

The patch intentionally starts the base stack first. Telephony services are behind the `telephony` profile and can be started later with:

```bash
docker compose -f ci_cd/docker-compose.prod.yml --profile telephony up -d
```

Before using telephony, replace the hardcoded values in `livekit-sip.yaml` with the EC2 configuration and open the required SIP/RTP firewall ports.