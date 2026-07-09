#!/usr/bin/env python3
"""
SIP Registration Proxy for JIO Inbound Calls
=============================================
1. Registers with JIO PBX as extension 9000 (MY_PORT=5062)
2. JIO routes DID calls to 172.16.1.57:5062 (our Contact)
3. We forward INVITE to livekit-sip (127.0.0.1:5060)
4. RTP media flows directly JIO <-> livekit-sip (no relay)
"""

import asyncio
import hashlib
import logging
import os
import random
import re
import string

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sip-proxy")

JIO_HOST    = os.getenv("JIO_SIP_HOST",     "172.16.0.10")
JIO_PORT    = int(os.getenv("JIO_SIP_PORT", "5060"))
MY_HOST     = os.getenv("MY_SIP_HOST",      "172.16.1.57")
MY_PORT     = int(os.getenv("MY_SIP_PORT",  "5062"))
LK_HOST     = os.getenv("LIVEKIT_SIP_HOST", "127.0.0.1")
LK_PORT     = int(os.getenv("LIVEKIT_SIP_PORT", "5060"))
SIP_USER    = os.getenv("JIO_SIP_USERNAME", "")
SIP_PASS    = os.getenv("JIO_SIP_PASSWORD", "")
LK_USER     = os.getenv("LIVEKIT_SIP_USERNAME") or SIP_USER  # LiveKit inbound trunk auth username
LK_PASS     = os.getenv("LIVEKIT_SIP_PASSWORD") or SIP_PASS  # LiveKit inbound trunk auth password
REG_INTERVAL = int(os.getenv("SIP_REG_INTERVAL", "55"))


# ── helpers ────────────────────────────────────────────────────────────────

def _rand(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def _md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()

def _digest(realm, nonce, method, uri, username=SIP_USER, password=SIP_PASS):
    ha1 = _md5(f"{username}:{realm}:{password}")
    ha2 = _md5(f"{method}:{uri}")
    return _md5(f"{ha1}:{nonce}:{ha2}")

def _header(msg: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}:\s*(.+)$", msg, re.I | re.M)
    return m.group(1).strip() if m else ""

def _all_via(msg: str):
    return re.findall(r"(?im)^(Via:.+)$", msg)

def _build_message(head: str, body: str) -> str:
    lines = head.split("\r\n")
    out = []
    replaced = False
    for line in lines:
        if re.match(r"(?i)^Content-Length:", line):
            out.append(f"Content-Length: {len(body.encode())}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"Content-Length: {len(body.encode())}")
    return "\r\n".join(out) + "\r\n\r\n" + body

def _prefer_pcma_sdp(msg: str) -> str:
    """Force SIP SDP offers/answers to prefer PCMA (G.711 A-law) for JIO trunks.

    JIO inbound here behaves reliably with narrowband PCMA only. Some INVITEs still
    advertise G722 first, and LiveKit may negotiate that codec even though the trunk
    path effectively behaves like G.711 only, which leads to one-way/no-audio for
    the caller. We sanitize SDP on both the forwarded INVITE and the 200 OK so the
    media path stays on PCMA.
    """
    if "application/sdp" not in msg.lower():
        return msg
    if "\r\n\r\n" not in msg:
        return msg

    head, body = msg.split("\r\n\r\n", 1)
    sdp_lines = body.split("\r\n")
    if not any(line.startswith("m=audio ") for line in sdp_lines):
        return msg

    codec_pts: dict[str, str] = {}
    dtmf_pt = ""
    for line in sdp_lines:
        m = re.match(r"^a=rtpmap:(\d+)\s+([A-Za-z0-9\-]+)/(\d+)", line)
        if not m:
            continue
        pt, codec, rate = m.groups()
        codec_upper = codec.upper()
        if codec_upper == "PCMA" and rate == "8000":
            codec_pts["PCMA"] = pt
        elif codec_upper == "PCMU" and rate == "8000":
            codec_pts["PCMU"] = pt
        elif codec_upper == "G722" and rate == "8000":
            codec_pts["G722"] = pt
        elif codec_upper == "TELEPHONE-EVENT":
            dtmf_pt = pt

    pcma_pt = codec_pts.get("PCMA")
    if not pcma_pt:
        return msg

    keep_pts = {pcma_pt}
    if dtmf_pt:
        keep_pts.add(dtmf_pt)

    rewritten: list[str] = []
    for line in sdp_lines:
        if line.startswith("m=audio "):
            parts = line.split()
            if len(parts) >= 4:
                payloads = [pcma_pt]
                if dtmf_pt:
                    payloads.append(dtmf_pt)
                line = " ".join(parts[:3] + payloads)
        elif line.startswith("a=rtpmap:") or line.startswith("a=fmtp:") or line.startswith("a=rtcp-fb:"):
            pt_match = re.match(r"^a=(?:rtpmap|fmtp|rtcp-fb):(\d+)\b", line)
            if pt_match and pt_match.group(1) not in keep_pts:
                continue
        rewritten.append(line)

    new_body = "\r\n".join(rewritten)
    return _build_message(head, new_body)


# ── UDP Protocol ────────────────────────────────────────────────────────────

class SIPProxyProtocol(asyncio.DatagramProtocol):

    def __init__(self):
        self.transport = None
        self._call_id_reg = f"{_rand(12)}@{MY_HOST}"
        self._tag         = _rand(8)
        self._cseq        = 0
        self._registered  = False
        self._last_auth_cseq = -1
        # call_id -> source addr (JIO side)
        self._calls: dict[str, tuple] = {}
        # call_id -> original INVITE for auth retry
        self._pending_invites: dict[str, str] = {}

    # ── send helpers ────────────────────────────────────────────────────────

    def _send(self, msg: str, addr: tuple):
        self.transport.sendto(msg.encode(), addr)
        log.debug("SEND → %s:%d  %s", *addr, msg.split("\r\n")[0])

    # ── SIP REGISTER ────────────────────────────────────────────────────────

    def _register(self, auth: str = ""):
        self._cseq += 1
        if auth:
            self._last_auth_cseq = self._cseq
        branch = f"z9hG4bK{_rand()}"
        msg = (
            f"REGISTER sip:{JIO_HOST} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP {MY_HOST}:{MY_PORT};branch={branch};rport\r\n"
            f"From: <sip:{SIP_USER}@{JIO_HOST}>;tag={self._tag}\r\n"
            f"To: <sip:{SIP_USER}@{JIO_HOST}>\r\n"
            f"Call-ID: {self._call_id_reg}\r\n"
            f"CSeq: {self._cseq} REGISTER\r\n"
            f"Contact: <sip:{SIP_USER}@{MY_HOST}:{MY_PORT}>;expires=3600\r\n"
            f"Max-Forwards: 70\r\n"
            f"User-Agent: LK-SIP-Proxy/1.0\r\n"
        )
        if auth:
            msg += auth + "\r\n"
        msg += "Content-Length: 0\r\n\r\n"
        self._send(msg, (JIO_HOST, JIO_PORT))

    def _handle_challenge(self, raw: str, method: str, addr: tuple):
        hdr = re.search(r"(?im)^(WWW-Authenticate|Proxy-Authenticate):\s*Digest\s+(.+)$", raw)
        if not hdr:
            log.warning("Challenge without auth header")
            return
        challenge_header = hdr.group(1)
        auth_header = "Proxy-Authorization" if challenge_header.lower() == "proxy-authenticate" else "Authorization"
        params = dict(re.findall(r'(\w+)="?([^",\r\n]+)"?', hdr.group(2)))
        realm = params.get("realm", JIO_HOST)
        nonce = params.get("nonce", "")
        call_id = _header(raw, "Call-ID")

        if method == "REGISTER":
            cseq_hdr = _header(raw, "CSeq")
            resp_cseq = int(cseq_hdr.split()[0]) if cseq_hdr else 0
            if self._last_auth_cseq == resp_cseq:
                log.error("Auth failed for REGISTER (bad credentials?), stopping retry loop.")
                return
            uri = f"sip:{JIO_HOST}"
            resp = _digest(realm, nonce, method, uri, SIP_USER, SIP_PASS)
            auth = (
                f'Authorization: Digest username="{SIP_USER}", '
                f'realm="{realm}", nonce="{nonce}", uri="{uri}", '
                f'response="{resp}", algorithm=MD5'
            )
            self._register(auth)
        elif method == "INVITE" and call_id:
            # Handle INVITE challenge - resend with auth
            pending_invite = self._pending_invites.get(call_id, "")
            pending_parts = pending_invite.split("\r\n", 1)[0].split()
            request_uri = pending_parts[1] if len(pending_parts) > 1 else ""
            
            is_from_jio = (addr[0] == JIO_HOST)
            
            if is_from_jio:
                # 401 from JIO for our outbound INVITE
                uri = params.get("uri") or request_uri or f"sip:{JIO_HOST}"
                resp = _digest(realm, nonce, method, uri, SIP_USER, SIP_PASS)
                auth = (
                    f'{auth_header}: Digest username="{SIP_USER}", '
                    f'realm="{realm}", nonce="{nonce}", uri="{uri}", '
                    f'response="{resp}", algorithm=MD5'
                )
                self._resend_invite_with_auth(call_id, auth, dest=(JIO_HOST, JIO_PORT))
            else:
                # 401 from LiveKit for inbound INVITE
                uri = params.get("uri") or request_uri or f"sip:{LK_USER}@{LK_HOST}:{LK_PORT}"
                resp = _digest(realm, nonce, method, uri, LK_USER, LK_PASS)
                auth = (
                    f'{auth_header}: Digest username="{LK_USER}", '
                    f'realm="{realm}", nonce="{nonce}", uri="{uri}", '
                    f'response="{resp}", algorithm=MD5'
                )
                self._resend_invite_with_auth(call_id, auth, dest=(LK_HOST, LK_PORT))

    def _resend_invite_with_auth(self, call_id: str, auth_hdr: str, dest: tuple):
        """Resend stored INVITE with authentication header."""
        if call_id not in self._pending_invites:
            log.warning("No pending INVITE for call_id %s", call_id)
            return

        original = self._pending_invites[call_id]
        lines = [
            line for line in original.split("\r\n")
            if not re.match(r"(?i)^(Proxy-Authorization|Authorization):", line)
        ]
        # Insert auth header after the first line
        new_msg = "\r\n".join([lines[0], auth_hdr] + lines[1:])
        log.info("Resending INVITE with auth for call_id %s", call_id)
        self._send(new_msg, dest)

    async def _register_loop(self):
        while True:
            self._register()
            log.info("REGISTER sent → %s:%d as %s", JIO_HOST, JIO_PORT, SIP_USER)
            await asyncio.sleep(REG_INTERVAL)

    # ── inbound INVITE handling ─────────────────────────────────────────────

    def _respond(self, raw: str, code: int, reason: str, addr: tuple):
        lines  = raw.split("\r\n")
        vias   = [line for line in lines if re.match(r"(?i)via:", line)]
        frm    = _header(raw, "From")
        to     = _header(raw, "To")
        cid    = _header(raw, "Call-ID")
        cseq   = _header(raw, "CSeq")
        resp   = f"SIP/2.0 {code} {reason}\r\n"
        for v in vias:
            resp += v + "\r\n"
        resp += (
            f"From: {frm}\r\n"
            f"To: {to}\r\n"
            f"Call-ID: {cid}\r\n"
            f"CSeq: {cseq}\r\n"
            f"Content-Length: 0\r\n\r\n"
        )
        self._send(resp, addr)

    def _forward_invite(self, raw: str, src: tuple):
        """Add our Via on top and forward to livekit-sip."""
        raw = _prefer_pcma_sdp(raw)
        branch  = f"z9hG4bK{_rand()}"
        our_via = f"Via: SIP/2.0/UDP {MY_HOST}:{MY_PORT};branch={branch};rport"
        lines   = raw.split("\r\n")
        # insert our Via after the request line
        new_msg = "\r\n".join([lines[0], our_via] + lines[1:])
        call_id = _header(raw, "Call-ID")
        if call_id:
            self._pending_invites[call_id] = new_msg  # Store forwarded INVITE for auth retry
        self._send(new_msg, (LK_HOST, LK_PORT))
        log.info("INVITE forwarded → livekit-sip %s:%d", LK_HOST, LK_PORT)

    def _forward_response_to_jio(self, raw: str, call_id: str):
        """Strip our Via and forward response back to JIO."""
        raw = _prefer_pcma_sdp(raw)
        lines, skipped = raw.split("\r\n"), False
        out = []
        for line in lines:
            if not skipped and re.match(r"(?i)via:", line) and MY_HOST in line:
                skipped = True
                continue
            out.append(line)
        addr = self._calls.get(call_id)
        if addr:
            self._send("\r\n".join(out), addr)

    def _forward_to_livekit(self, raw: str):
        """Forward ACK/BYE/etc from JIO to livekit-sip."""
        branch  = f"z9hG4bK{_rand()}"
        our_via = f"Via: SIP/2.0/UDP {MY_HOST}:{MY_PORT};branch={branch};rport"
        lines   = raw.split("\r\n")
        new_msg = "\r\n".join([lines[0], our_via] + lines[1:])
        self._send(new_msg, (LK_HOST, LK_PORT))

    # ── asyncio DatagramProtocol ────────────────────────────────────────────

    def connection_made(self, transport):
        self.transport = transport
        log.info("UDP socket ready on %s:%d", MY_HOST, MY_PORT)
        asyncio.get_event_loop().create_task(self._register_loop())

    def datagram_received(self, data: bytes, addr: tuple):
        asyncio.get_event_loop().create_task(self._dispatch(data, addr))

    async def _dispatch(self, data: bytes, addr: tuple):
        raw  = data.decode(errors="replace")
        line = raw.split("\r\n")[0]
        log.debug("RECV ← %s:%d  %s", *addr, line)

        if line.startswith("SIP/2.0"):
            # ── response ──────────────────────────────────────────────────
            code = int(line.split()[1])
            cseq_hdr = _header(raw, "CSeq")
            method   = cseq_hdr.split()[-1] if cseq_hdr else ""
            call_id  = _header(raw, "Call-ID")

            if code in (401, 407):
                log.info("Auth challenge for %s, retrying with digest", method)
                self._handle_challenge(raw, method, addr)

            elif code == 200 and method == "REGISTER":
                if not self._registered:
                    log.info("✅ SIP Registration successful! JIO will route calls to %s:%d", MY_HOST, MY_PORT)
                self._registered = True

            elif method in ("INVITE", "BYE", "CANCEL"):
                # forward response from livekit-sip back to JIO
                if code >= 300:
                    # Call rejected/ended — stop tracking so future JIO messages aren't forwarded
                    self._calls.pop(call_id, None)
                self._forward_response_to_jio(raw, call_id)

        else:
            # ── request ───────────────────────────────────────────────────
            method  = line.split()[0]
            call_id = _header(raw, "Call-ID")

            if method == "INVITE":
                is_from_jio = addr[0] == JIO_HOST
                
                if is_from_jio:
                    log.info("📞 Inbound INVITE from JIO | call_id=%s | from=%s", call_id, addr)
                    self._calls[call_id] = addr
                    self._respond(raw, 100, "Trying", addr)
                    self._forward_invite_to_lk(raw, addr)
                else:
                    log.info("📞 Outbound INVITE from LiveKit | call_id=%s | from=%s", call_id, addr)
                    self._calls[call_id] = addr
                    self._forward_invite_to_jio(raw, addr)

            elif method in ("ACK", "BYE", "CANCEL"):
                is_from_jio = addr[0] == JIO_HOST
                log.info("%s from %s | call_id=%s", method, "JIO" if is_from_jio else "LiveKit", call_id)
                
                if method == "CANCEL":
                    if call_id in self._calls:
                        if is_from_jio:
                            self._forward_to_livekit(raw)
                        else:
                            self._forward_to_jio(raw)
                        self._calls.pop(call_id, None)
                    # Always ACK the CANCEL so sender stops retransmitting
                    self._respond(raw, 200, "OK", addr)
                elif method == "BYE":
                    if is_from_jio:
                        self._forward_to_livekit(raw)
                    else:
                        self._forward_to_jio(raw)
                    self._respond(raw, 200, "OK", addr)
                    self._calls.pop(call_id, None)
                else:  # ACK
                    if is_from_jio:
                        self._forward_to_livekit(raw)
                    else:
                        self._forward_to_jio(raw)

            elif method == "OPTIONS":
                self._respond(raw, 200, "OK", addr)

            else:
                log.debug("Unhandled method: %s", method)

    def _forward_invite_to_lk(self, raw: str, src: tuple):
        """Add our Via on top and forward to livekit-sip."""
        raw = _prefer_pcma_sdp(raw)
        branch  = f"z9hG4bK{_rand()}"
        our_via = f"Via: SIP/2.0/UDP {MY_HOST}:{MY_PORT};branch={branch};rport"
        lines   = raw.split("\r\n")
        # insert our Via after the request line
        new_msg = "\r\n".join([lines[0], our_via] + lines[1:])
        call_id = _header(raw, "Call-ID")
        if call_id:
            self._pending_invites[call_id] = new_msg  # Store forwarded INVITE for auth retry
        self._send(new_msg, (LK_HOST, LK_PORT))
        log.info("INVITE forwarded → livekit-sip %s:%d", LK_HOST, LK_PORT)

    def _forward_invite_to_jio(self, raw: str, src: tuple):
        """Add our Via on top and forward to JIO."""
        raw = _prefer_pcma_sdp(raw)
        branch  = f"z9hG4bK{_rand()}"
        our_via = f"Via: SIP/2.0/UDP {MY_HOST}:{MY_PORT};branch={branch};rport"
        lines   = raw.split("\r\n")
        new_msg = "\r\n".join([lines[0], our_via] + lines[1:])
        call_id = _header(raw, "Call-ID")
        if call_id:
            self._pending_invites[call_id] = new_msg
        self._send(new_msg, (JIO_HOST, JIO_PORT))
        log.info("INVITE forwarded → JIO %s:%d", JIO_HOST, JIO_PORT)

    def _forward_to_jio(self, raw: str):
        """Forward ACK/BYE/etc from LiveKit to JIO."""
        branch  = f"z9hG4bK{_rand()}"
        our_via = f"Via: SIP/2.0/UDP {MY_HOST}:{MY_PORT};branch={branch};rport"
        lines   = raw.split("\r\n")
        new_msg = "\r\n".join([lines[0], our_via] + lines[1:])
        self._send(new_msg, (JIO_HOST, JIO_PORT))

async def main():
    log.info("SIP Proxy starting — %s:%d → JIO %s:%d → livekit-sip %s:%d",
             MY_HOST, MY_PORT, JIO_HOST, JIO_PORT, LK_HOST, LK_PORT)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        SIPProxyProtocol,
        local_addr=("0.0.0.0", MY_PORT),
    )
    try:
        await asyncio.sleep(float("inf"))
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())
