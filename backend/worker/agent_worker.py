"""
Agent worker — the real-time pipeline (spec section 6).

Flow per session:
  1. Worker joins the LiveKit room (room name carries the agent id).
  2. Loads the selected agent's full config from PostgreSQL.
  3. Initializes the SELECTED VAD preset, STT, LLM/SLM, and TTS providers.
  4. For each user utterance:
       VAD gates speech  ->  STT  ->  RAG (if KB on)  ->  LLM  ->  TTS  ->  publish.

Only the audio-frame plumbing is LiveKit-version specific (marked TODO). Provider
selection always goes through OUR factories, never a hardcoded model.

SDK: pip install "livekit-agents[silero]" livekit
"""
import asyncio
import logging
import uuid

from backend.database import SessionLocal
from backend.models.agent import Agent
from backend.services.llm.factory import build_llm_provider
from backend.services.rag import build_context_prompt, retrieve, retrieve_entry, build_router_prompt
from backend.services.stt.factory import STTProviderFactory
from backend.services.tts.factory import TTSProviderFactory
from backend.services.noise_cancellation.factory import build_noise_canceller
from backend.services.vad.presets import resolve_vad_params

from backend.config import settings
from backend.services.redis.cache import get_cache

log = logging.getLogger("agent_worker")


# Sticky-entry follow-up detection.
# A locked LLM_ANSWERED troubleshooting entry should only "stick" for genuine
# short follow-up replies ("yes I did", "still not working", "হ্যাঁ করেছি").
# If the caller instead asks a brand-new, self-contained question mid-call —
# most importantly a POLICY question — we must release the lock so it reaches
# the KB (structured entry or document RAG) instead of being funneled into the
# active troubleshooting entry's transfer path.
_FOLLOWUP_MAX_WORDS = 7
# System / policy terms whose presence signals a new, self-contained request.
# IT system names stay in English even inside Bengali/Hindi speech, so matching
# these ASCII tokens is reliable regardless of the spoken language.
_NEW_TOPIC_TERMS = (
    "esaf", "nexid", "ikigai", "tms", "m365", "br.net", "brnet",
    "m-bank", "mbank", "clp", "sampurna", "smpp", "vpn",
    "policy", "policies", "rule", "allowed", "permitted",
    "password", "reset", "usb", "pen drive", "pendrive",
    "email", "outlook", "account", "leave", "salary",
)


def _looks_like_new_question(text: str) -> bool:
    """True if `text` looks like a NEW self-contained request rather than a
    short follow-up to the currently active troubleshooting entry.

    Heuristic (language-agnostic):
      - any explicit IT system / policy term present  -> new question, or
      - the utterance is longer than a short acknowledgment.
    Short, term-free utterances ("yes I did", "না হচ্ছে না") stay follow-ups.
    """
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(term in t for term in _NEW_TOPIC_TERMS):
        return True
    return len(t.split()) > _FOLLOWUP_MAX_WORDS


def _agent_id_from_room(room_name: str) -> uuid.UUID | None:
    # Web rooms: agent-<uuid>-<suffix> → extract UUID
    # SIP rooms: jio-call-_+91xxxxxxxxxx_<random> → no UUID, return None
    if not room_name.startswith("agent-"):
        return None
    parts = room_name.split("-")
    raw = "-".join(parts[1:6])
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def load_agent(agent_id: uuid.UUID) -> Agent:
    db = SessionLocal()
    try:
        agent = db.get(Agent, agent_id)
        if not agent:
            raise RuntimeError(f"Agent {agent_id} not found")
        db.expunge(agent)
        return agent
    finally:
        db.close()


def load_default_agent() -> Agent:
    """For SIP calls — room name has no agent UUID.
    Uses the agent marked is_sip_default=True; falls back to the first agent."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.is_sip_default == True).first()  # noqa: E712
        if agent:
            db.expunge(agent)
            log.info("SIP call: using SIP-default agent %s (%s)", agent.id, agent.name)
            return agent
        agent = db.query(Agent).first()
        if not agent:
            raise RuntimeError("No agents found in database — create an agent first")
        db.expunge(agent)
        log.info("SIP call: no SIP default set, using first agent %s (%s)", agent.id, agent.name)
        return agent
    finally:
        db.close()


class AgentPipeline:
    """Holds the per-agent provider instances and runs one turn end-to-end."""

    def __init__(self, agent: Agent, session_id: str = ""):
        self.agent = agent
        self.session_id = session_id
        self.vad_params = resolve_vad_params(agent)
        self.stt = STTProviderFactory.create(agent)
        self.llm = build_llm_provider(agent)
        self.tts = TTSProviderFactory.create(agent)
        self.nc = build_noise_canceller(agent)
        self.history: list[dict] = []
        # Sticky troubleshooting entry: once a call locks onto a KB entry, short
        # follow-up replies ("yes I did", "still not working") won't re-search and
        # accidentally fall back to the transfer-prone document RAG. Held for the
        # duration of the call, replaced only when a NEW issue matches confidently.
        self.active_entry: dict | None = None
        self.active_turns: int = 0
        log.info(
            "Pipeline ready: llm=%s/%s stt=%s tts=%s vad=%s(th=%.2f) nc=%s",
            agent.llm_provider, agent.llm_model, agent.stt_provider,
            agent.tts_provider, agent.vad_mode, self.vad_params.threshold,
            (agent.noise_cancellation_provider if getattr(agent, 'noise_cancellation_enabled', False) else 'off'),
        )

    async def load_history(self):
        """Restore conversation history for this session from Redis (if any)."""
        if not self.session_id:
            return
        try:
            cached = await get_cache().get_json(f"session:{self.session_id}")
            if cached:
                self.history = cached
                log.info("Restored %d history msgs for %s", len(cached), self.session_id)
        except Exception:
            log.exception("load_history failed — starting fresh")

    async def save_history(self):
        """Persist conversation history to Redis with a TTL."""
        if not self.session_id:
            return
        try:
            await get_cache().set_json(
                f"session:{self.session_id}", self.history, ttl=settings.SESSION_TTL
            )
        except Exception:
            log.exception("save_history failed — ignoring")

    async def handle_greeting(self):
        """Generates an initial greeting based on the system prompt."""
        system_prompt = self.agent.system_prompt or ""
        voice_system = (
            f"{system_prompt}\n\nReply in 1-3 short spoken sentences. "
            "Do not use markdown, lists, or emojis."
        )
        self.history.append({"role": "user", "content": "Hello. Please start."})
        answer = await self.llm.generate(voice_system, self.history)

        self.history.append({"role": "assistant", "content": answer})
        log.info("Agent greeting: %s", answer)
        await self.save_history()

        async for chunk in self.tts.synthesize(answer):
            yield chunk

    async def handle_utterance(self, audio: bytes, sample_rate: int):
        """One full turn: STT -> RAG -> LLM -> TTS. Returns async audio chunks."""
        stt_result = await self.stt.transcribe(audio, sample_rate)
        text = stt_result.text
        if not text:
            return
        log.info("User said: %s (Language: %s)", text, stt_result.language)

        # Keep the TTS language in sync with the detected spoken language.
        # This is provider-neutral: we only update config.language. Any
        # provider-specific voice resolution (e.g. Cartesia's env-by-language
        # voice ID fallback) happens INSIDE the provider at synthesis time.
        if stt_result.language and not self.tts.config.voice_id:
            # Only auto-switch language when no explicit voice ID is pinned, so a
            # user-chosen voice is never overridden. When unset, the provider
            # resolves the right voice for the new language internally.
            if self.tts.config.language != stt_result.language:
                self.tts.config.language = stt_result.language
                log.info("Synced TTS language to detected '%s'", stt_result.language)

        system_prompt = self.agent.system_prompt or ""
        if self.agent.kb_enabled:
            routed = False
            # 1) Structured troubleshooting router (with sticky entry).
            try:
                decision = await retrieve_entry(self.agent.id, text, original_text=text)
                if decision:
                    # Confident NEW match -> lock onto this entry for the call.
                    entry = decision["entry"]
                    pol = decision.get("policy") or {}
                    log.info(
                        "ROUTER mode=%s entry=%s sim=%.3f policy=%s",
                        decision["mode"], entry.get("entry_id"),
                        decision["similarity"], pol.get("rule_id"),
                    )
                    self.active_entry = decision
                    self.active_turns = 0
                    system_prompt = build_router_prompt(system_prompt, decision)
                    routed = True
                elif self.active_entry and self.active_entry["mode"] == "LLM_ANSWERED":
                    # No confident NEW match, but we're mid-troubleshooting.
                    # The sticky entry is ONLY for short follow-up replies
                    # ("yes I did", "still not working"). If this is instead a
                    # brand-new, self-contained question (e.g. a policy query
                    # asked in the same call), we must NOT absorb it into the
                    # active troubleshooting entry — doing so funnels it into
                    # that entry's transfer path and it never reaches the KB.
                    # Release the lock so it falls through to document RAG and
                    # gets a real KB-grounded answer, exactly as it would on a
                    # fresh call.
                    max_sticky = (self.active_entry["entry"].get("max_steps") or 5) + 2
                    if _looks_like_new_question(text):
                        log.info(
                            "ROUTER releasing sticky entry=%s — new question mid-call: %r",
                            self.active_entry["entry"].get("entry_id"), text[:60],
                        )
                        self.active_entry = None
                        # routed stays False -> falls through to chunk RAG below.
                    elif self.active_turns < max_sticky:
                        self.active_turns += 1
                        log.info(
                            "ROUTER sticky entry=%s turn=%d/%d (weak match — treating as follow-up)",
                            self.active_entry["entry"].get("entry_id"),
                            self.active_turns, max_sticky,
                        )
                        system_prompt = build_router_prompt(system_prompt, self.active_entry)
                        routed = True
                    else:
                        log.info("ROUTER sticky expired — releasing entry, falling back")
                        self.active_entry = None
            except Exception:
                log.exception("router failed — falling back to chunk RAG")

            # 2) Fallback: generic document-chunk RAG when nothing matched.
            if not routed:
                self.active_entry = None
                try:
                    keyword_system = (
                        "You are a keyword extractor for Sampurna's IT support knowledge base.\n"
                        "Extract 3-5 English search keywords from the user's query.\n\n"
                        "Rules:\n"
                        "- Keep IT system names EXACTLY as typed: ESAF, NexID, IKIGAI, TMS, M365, Br.net, M-Bank, CLP, Sampurna, SMPP, VPN\n"
                        "- Bengali pronunciation mappings: 'ইসাব'/'ইসাফ' = ESAF, 'নেক্সআইডি' = NexID, 'টিএমএস' = TMS, 'এমব্যাংক' = M-Bank\n"
                        "- For ID creation questions use: <system-name> ID creation process\n"
                        "- Output ONLY the keywords separated by spaces, no punctuation or explanation."
                    )
                    keywords_text = await self.llm.generate(keyword_system, [{"role": "user", "content": text}])
                    log.info("RAG search keywords: %s", keywords_text)
                    chunks = await retrieve(self.agent.id, keywords_text, original_text=text)
                except Exception as e:
                    log.warning("Failed to generate keywords for RAG: %s", e)
                    chunks = await retrieve(self.agent.id, text)

                if chunks:
                    log.info("=== KNOWLEDGE BASE CONTEXT ===")
                    for i, chunk in enumerate(chunks, 1):
                        log.info("--- Chunk [%d] ---\n%s", i, chunk)
                    log.info("==============================")

                system_prompt = build_context_prompt(system_prompt, chunks)

        self.history.append({"role": "user", "content": text})
        # Keep answers short + voice-friendly.
        voice_system = (
            f"{system_prompt}\n\nReply in 1-3 short spoken sentences. "
            "Do not use markdown, lists, or emojis."
        )
        if self.agent.call_transfer_number:
            voice_system += (
                "\n\nIf the user asks to talk to support, a human agent, or escalate the call, "
                "you MUST reply EXACTLY with '[TRANSFER] I am transferring your call to the support team now.' "
                "and nothing else."
            )

        voice_system += (
            "\n\nIf the user says they are busy, asks to hang up, or ends the conversation, "
            "you MUST reply EXACTLY with '[HANGUP] Okay, I am ending the call now. Goodbye.' "
            "and nothing else."
        )

        answer = await self.llm.generate(voice_system, self.history)

        transfer_requested = False
        hangup_requested = False
        if "[TRANSFER]" in answer:
            transfer_requested = True
            answer = answer.replace("[TRANSFER]", "").strip()
        if "[HANGUP]" in answer:
            hangup_requested = True
            answer = answer.replace("[HANGUP]", "").strip()

        self.history.append({"role": "assistant", "content": answer})
        log.info("Agent reply: %s", answer)
        await self.save_history()

        # Stream synthesized audio back to the caller.
        async for chunk in self.tts.synthesize(answer):
            yield chunk

        if transfer_requested:
            yield b"__TRANSFER__"
        if hangup_requested:
            yield b"__HANGUP__"


# --------------------------------------------------------------------------
# LiveKit agents entrypoint
# --------------------------------------------------------------------------
async def entrypoint(ctx):
    """
    `ctx` is a livekit.agents JobContext. This function:
      - connects to the room
      - builds the per-agent pipeline
      - runs Silero VAD over the incoming user track and drives the turn loop
    """
    from livekit import rtc
    from livekit.plugins import silero  # noqa: F401  (Silero VAD only)

    await ctx.connect()
    log.info("Room joined: %s", ctx.room.name)
    agent_id = _agent_id_from_room(ctx.room.name)
    if agent_id is not None:
        agent = load_agent(agent_id)
    else:
        log.info("SIP room detected — loading default agent from DB")
        agent = load_default_agent()
    pipeline = AgentPipeline(agent, session_id=ctx.room.name)
    await pipeline.load_history()

    # Silero VAD configured from the SELECTED preset (speech/turn detection only —
    # no noise cancellation of any kind).
    vad = silero.VAD.load(
        min_speech_duration=pipeline.vad_params.min_speech_ms / 1000,
        min_silence_duration=pipeline.vad_params.min_silence_ms / 1000,
        activation_threshold=pipeline.vad_params.threshold,
    )

    audio_source = rtc.AudioSource(24000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent-voice", audio_source)
    await ctx.room.local_participant.publish_track(track)

    current_task = None

    async def play_greeting():
        try:
            leftover = b""
            async for chunk in pipeline.handle_greeting():
                chunk = leftover + chunk
                leftover = b""
                if len(chunk) % 2 != 0:
                    leftover = chunk[-1:]
                    chunk = chunk[:-1]
                if chunk:
                    await audio_source.capture_frame(
                        rtc.AudioFrame(chunk, 24000, 1, len(chunk) // 2)
                    )
        except asyncio.CancelledError:
            log.info("Greeting cancelled.")
        except Exception:
            log.exception("Error playing greeting")

    current_task = asyncio.create_task(play_greeting())

    async def process_track(user_track: "rtc.AudioTrack", participant: "rtc.RemoteParticipant"):
        """
        Read frames from the user's mic track, gate them through VAD, and on each
        completed utterance run the pipeline and push audio to `audio_source`.

        NOTE: exact VAD stream/event API differs by livekit-agents version. The
        intent below is stable; adapt `vad.stream()` event names to your version.
        """
        nonlocal current_task
        log.info("Started processing user track: %s from participant %s", getattr(user_track, "sid", "unknown"), participant.identity)
        if not pipeline.agent.vad_enabled:
            log.warning("VAD disabled for agent %s — using raw frames", agent_id)

        vad_stream = vad.stream()
        audio_stream = rtc.AudioStream(user_track)

        async def pump_vad():
            nonlocal current_task
            try:
                async for ev in vad_stream:
                    event_type = str(getattr(ev, "type", "")).upper()
                    if "START" in event_type:
                        if current_task and not current_task.done():
                            log.info("User started speaking! Cancelling current speech...")
                            current_task.cancel()
                    elif "END" in event_type:
                        frames = getattr(ev, "frames", [])
                        if not frames:
                            continue
                        audio_bytes = b"".join(f.data.tobytes() for f in frames)
                        sr = frames[0].sample_rate
                        log.info("VAD end-of-speech: %d bytes @ %d Hz", len(audio_bytes), sr)

                        async def run_utterance(audio, sample_rate):
                            try:
                                leftover = b""
                                should_transfer = False
                                should_hangup = False
                                async for chunk in pipeline.handle_utterance(audio, sample_rate):
                                    if chunk == b"__TRANSFER__":
                                        should_transfer = True
                                        continue
                                    if chunk == b"__HANGUP__":
                                        should_hangup = True
                                        continue
                                    chunk = leftover + chunk
                                    leftover = b""
                                    if len(chunk) % 2 != 0:
                                        leftover = chunk[-1:]
                                        chunk = chunk[:-1]
                                    if chunk:
                                        await audio_source.capture_frame(
                                            rtc.AudioFrame(chunk, 24000, 1, len(chunk) // 2)
                                        )

                                if should_hangup:
                                    log.info("User requested to end call. Hanging up.")
                                    from livekit.api import LiveKitAPI
                                    from livekit.protocol.room import RoomParticipantIdentity
                                    api = LiveKitAPI()
                                    try:
                                        # Kick the user to drop the SIP call completely
                                        req = RoomParticipantIdentity(
                                            room=ctx.room.name,
                                            identity=participant.identity
                                        )
                                        await api.room.remove_participant(req)
                                    except Exception as e:
                                        log.error("Failed to remove SIP participant: %s", e)
                                    finally:
                                        await api.aclose()

                                    await ctx.room.disconnect()
                                elif should_transfer and pipeline.agent.call_transfer_number:
                                    transfer_to = pipeline.agent.call_transfer_number.strip()
                                    if not (transfer_to.startswith("sip:") or transfer_to.startswith("sips:") or transfer_to.startswith("tel:")):
                                        # Assume it's a phone number or extension, prepend tel:
                                        transfer_to = f"tel:{transfer_to}"

                                    log.info("Initiating SIP transfer to %s", transfer_to)
                                    from livekit.api import LiveKitAPI
                                    from livekit.protocol.sip import TransferSIPParticipantRequest
                                    api = LiveKitAPI()
                                    try:
                                        req = TransferSIPParticipantRequest(
                                            participant_identity=participant.identity,
                                            room_name=ctx.room.name,
                                            transfer_to=transfer_to
                                        )
                                        await api.sip.transfer_sip_participant(req)
                                        log.info("Call transfer initiated successfully.")
                                        # Leave the room after transfer
                                        await ctx.room.disconnect()
                                    except Exception as transfer_err:
                                        log.error("Failed to transfer SIP call: %s", transfer_err)
                                    finally:
                                        await api.aclose()

                            except asyncio.CancelledError:
                                log.info("Utterance cancelled.")
                            except Exception:
                                log.exception("Error in pipeline (STT/LLM/TTS)")

                        if current_task and not current_task.done():
                            current_task.cancel()
                        current_task = asyncio.create_task(run_utterance(audio_bytes, sr))
            except Exception:
                log.exception("Fatal error in VAD pump loop")

        vad_task = asyncio.create_task(pump_vad())
        nc = pipeline.nc  # None when noise cancellation is disabled for this agent
        try:
            async for frame_event in audio_stream:
                frame = frame_event.frame
                if nc is not None and nc.is_active:
                    for enhanced in nc.process_frame(frame):
                        vad_stream.push_frame(enhanced)
                else:
                    vad_stream.push_frame(frame)
        finally:
            if nc is not None and nc.is_active:
                try:
                    for enhanced in nc.flush():
                        vad_stream.push_frame(enhanced)
                except Exception:
                    pass
            vad_task.cancel()

    # Attach to the first audio track the user publishes.
    for participant in ctx.room.remote_participants.values():
        for pub in participant.track_publications.values():
            if pub.track:
                log.info("Found existing track: %s", pub.track.kind)
                if pub.track.kind == rtc.TrackKind.KIND_AUDIO:
                    asyncio.create_task(process_track(pub.track, participant))

    @ctx.room.on("track_subscribed")
    def _on_track(track, publication, participant):
        from livekit import rtc as _rtc
        log.info("Track subscribed: %s from %s", track.kind, participant.identity)
        if track.kind == _rtc.TrackKind.KIND_AUDIO:
            asyncio.create_task(process_track(track, participant))

    # Keep the worker alive for the session.
    await asyncio.Event().wait()


if __name__ == "__main__":
    # Run with the livekit-agents CLI runner.
    #   python -m backend.worker.agent_worker
    from livekit.agents import WorkerOptions, cli

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))