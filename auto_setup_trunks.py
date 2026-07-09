#!/usr/bin/env python3
"""
auto_setup_trunks.py
─────────────────────────────────────────────────────────
docker compose up করলেই automatic চলবে (sip-setup service হিসেবে)।

এই script:
  1. LiveKit ready না হওয়া পর্যন্ত wait করে (retry with backoff)
  2. পুরানো Jio trunks/rules মুছে ফেলে
  3. নতুন Inbound + Outbound Trunk + Dispatch Rule তৈরি করে
  4. sip_trunk_ids.json এ save করে (backend mount করে পড়ে)
  5. .env ফাইলে JIO_OUTBOUND_TRUNK_ID auto-update করে

কোনো manual step নেই — যেকোনো machine-এ docker compose up দিলেই সব হয়ে যাবে।
─────────────────────────────────────────────────────────
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env from mounted path (docker) or local ────────────
ENV_PATH = Path("/app/.env")
if not ENV_PATH.exists():
    ENV_PATH = Path(".env")
load_dotenv(ENV_PATH)

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
API_KEY     = os.getenv("LIVEKIT_API_KEY", "")
API_SECRET  = os.getenv("LIVEKIT_API_SECRET", "")

JIO_SIP_HOST = os.getenv("JIO_SIP_HOST", "")
JIO_USERNAME = os.getenv("JIO_SIP_USERNAME", "")
JIO_PASSWORD = os.getenv("JIO_SIP_PASSWORD", "")
JIO_DID      = os.getenv("JIO_DID_NUMBER", "")
MY_SIP_HOST  = os.getenv("MY_SIP_HOST", "")
MY_SIP_PORT  = int(os.getenv("MY_SIP_PORT", "5062"))
AGENT_NAME   = os.getenv("LIVEKIT_AGENT_NAME", "collection-agent")

# Retry config
MAX_RETRIES     = 30
RETRY_DELAY_SEC = 3

# Output paths
SIP_JSON_PATH = Path("/app/sip_trunk_ids.json")
if not SIP_JSON_PATH.parent.exists():
    SIP_JSON_PATH = Path("sip_trunk_ids.json")


def update_env_file(key: str, value: str):
    """Update or add a key=value in the .env file."""
    env_file = ENV_PATH
    if not env_file.exists():
        env_file.write_text(f"{key}={value}\n")
        print(f"  📝 .env তৈরি হয়েছে: {key}={value}")
        return

    content = env_file.read_text()
    pattern = rf"^{re.escape(key)}=.*$"

    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += f"{key}={value}\n"

    env_file.write_text(content)
    print(f"  📝 .env updated: {key}={value}")


async def wait_for_livekit():
    """Retry connecting to LiveKit until it's ready."""
    from livekit import api as lk_api

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            lk = lk_api.LiveKitAPI(
                url=LIVEKIT_URL, api_key=API_KEY, api_secret=API_SECRET
            )
            # A lightweight call to verify connectivity
            await lk.sip.list_sip_inbound_trunk(
                lk_api.ListSIPInboundTrunkRequest()
            )
            print(f"✅ LiveKit ready (attempt {attempt})")
            return lk
        except Exception as e:
            print(
                f"⏳ LiveKit not ready (attempt {attempt}/{MAX_RETRIES}): {e}"
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY_SEC)
            else:
                print("❌ LiveKit connect failed after max retries. Exiting.")
                sys.exit(1)


async def cleanup_old_trunks(lk):
    """Delete any existing jio-* trunks and dispatch rules."""
    from livekit import api as lk_api

    # Inbound
    try:
        existing = await lk.sip.list_sip_inbound_trunk(
            lk_api.ListSIPInboundTrunkRequest()
        )
        for t in existing.items or []:
            if "jio" in (t.name or "").lower():
                print(f"  🗑  Deleting old inbound trunk: {t.sip_trunk_id}")
                await lk.sip.delete_sip_trunk(
                    lk_api.DeleteSIPTrunkRequest(sip_trunk_id=t.sip_trunk_id)
                )
    except Exception as e:
        print(f"  (inbound list error: {e})")

    # Outbound
    try:
        existing = await lk.sip.list_sip_outbound_trunk(
            lk_api.ListSIPOutboundTrunkRequest()
        )
        for t in existing.items or []:
            if "jio" in (t.name or "").lower():
                print(f"  🗑  Deleting old outbound trunk: {t.sip_trunk_id}")
                await lk.sip.delete_sip_trunk(
                    lk_api.DeleteSIPTrunkRequest(sip_trunk_id=t.sip_trunk_id)
                )
    except Exception as e:
        print(f"  (outbound list error: {e})")

    # Dispatch rules
    try:
        existing = await lk.sip.list_sip_dispatch_rule(
            lk_api.ListSIPDispatchRuleRequest()
        )
        for r in existing.items or []:
            if "jio" in (r.name or "").lower():
                print(f"  🗑  Deleting old dispatch rule: {r.sip_dispatch_rule_id}")
                await lk.sip.delete_sip_dispatch_rule(
                    lk_api.DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=r.sip_dispatch_rule_id
                    )
                )
    except Exception as e:
        print(f"  (dispatch rule list error: {e})")


async def create_trunks(lk):
    """Create fresh inbound + outbound trunks and dispatch rule."""
    from livekit import api as lk_api
    from livekit.protocol import room as room_proto

    # ── Inbound ──────────────────────────────────────────────
    allowed_addresses = [
        "0.0.0.0/0",  # broad — tighten in production
    ]
    for ip in [JIO_SIP_HOST, MY_SIP_HOST]:
        ip = (ip or "").strip()
        if ip and ip not in allowed_addresses:
            allowed_addresses.append(ip)

    in_trunk = await lk.sip.create_sip_inbound_trunk(
        lk_api.CreateSIPInboundTrunkRequest(
            trunk=lk_api.SIPInboundTrunkInfo(
                name="jio-inbound",
                numbers=[],
                allowed_addresses=allowed_addresses,
                auth_username=JIO_USERNAME,
                auth_password=JIO_PASSWORD,
            )
        )
    )
    print(f"  ✅ Inbound Trunk: {in_trunk.sip_trunk_id}")

    # ── Outbound ─────────────────────────────────────────────
    out_trunk = await lk.sip.create_sip_outbound_trunk(
        lk_api.CreateSIPOutboundTrunkRequest(
            trunk=lk_api.SIPOutboundTrunkInfo(
                name="jio-outbound",
                address=f"{MY_SIP_HOST}:{MY_SIP_PORT}",
                numbers=["*"],
                auth_username=JIO_USERNAME,
                auth_password=JIO_PASSWORD,
            )
        )
    )
    print(f"  ✅ Outbound Trunk: {out_trunk.sip_trunk_id}")

    # ── Dispatch Rule ────────────────────────────────────────
    room_config = room_proto.RoomConfiguration()
    dispatch_entry = room_config.agents.add()
    dispatch_entry.agent_name = AGENT_NAME

    rule = await lk.sip.create_sip_dispatch_rule(
        lk_api.CreateSIPDispatchRuleRequest(
            dispatch_rule=lk_api.SIPDispatchRuleInfo(
                name="jio-voicebot",
                trunk_ids=[in_trunk.sip_trunk_id],
                rule=lk_api.SIPDispatchRule(
                    dispatch_rule_individual=lk_api.SIPDispatchRuleIndividual(
                        room_prefix="jio-call-",
                    )
                ),
                room_config=room_config,
            )
        )
    )
    print(f"  ✅ Dispatch Rule: {rule.sip_dispatch_rule_id}")

    return in_trunk, out_trunk, rule


async def main():
    print("=" * 60)
    print("🚀 Auto SIP Trunk Setup Starting...")
    print("=" * 60)

    # 1. Wait for LiveKit
    lk = await wait_for_livekit()

    # 2. Cleanup old trunks
    print("\n🧹 Cleaning up old trunks...")
    await cleanup_old_trunks(lk)

    # 3. Create new trunks
    print("\n📞 Creating new trunks...")
    in_trunk, out_trunk, rule = await create_trunks(lk)

    # 4. Save to sip_trunk_ids.json
    trunk_info = {
        "inbound_trunk_id": in_trunk.sip_trunk_id,
        "outbound_trunk_id": out_trunk.sip_trunk_id,
        "dispatch_rule_id": rule.sip_dispatch_rule_id,
        "jio_did": JIO_DID,
        "jio_sip_host": JIO_SIP_HOST,
    }
    SIP_JSON_PATH.write_text(json.dumps(trunk_info, indent=2))
    print(f"\n💾 Saved to {SIP_JSON_PATH}")

    # 5. Update .env with outbound trunk ID
    print("\n📝 Updating .env...")
    update_env_file("JIO_OUTBOUND_TRUNK_ID", out_trunk.sip_trunk_id)

    print(f"\n{'=' * 60}")
    print("✅ Auto setup complete!")
    print(f"   Inbound:  {in_trunk.sip_trunk_id}")
    print(f"   Outbound: {out_trunk.sip_trunk_id}")
    print(f"   Rule:     {rule.sip_dispatch_rule_id}")
    print(f"{'=' * 60}")

    await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
