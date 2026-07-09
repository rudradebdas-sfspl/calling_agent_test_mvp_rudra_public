# Redis Integration Guide — কোথায় কী Add করতে হবে

এই project-এ Redis লাগানোর জন্য মোট **৬ জায়গায়** কাজ করতে হবে। প্রতিটার exact
file path + কী add করবে নিচে দেওয়া। শেষে **RDB vs AOF** এর উত্তর।

Module টা (`module/redis_core/`) আগেই বানানো — এটা reusable, অন্য project-এ
শুধু folder copy করলেই চলবে। এই guide হলো এই voice-agent project-এ wiring করার।

---

## 1️⃣ `requirements.txt` — redis package add

ফাইলের শেষে যোগ করো:

```
redis>=5.0
```

---

## 2️⃣ `backend/config.py` — Settings-এ Redis field add

`class Settings` এর ভেতরে (যেকোনো block-এর পরে) এই লাইনগুলো যোগ করো:

```python
    # ----- Redis / Cache -----
    CACHE_BACKEND: str = "redis"          # "redis" | "memory" (memory = dev/test)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_NAMESPACE: str = "voiceagent"   # সব key-এর prefix

    # cache TTL (সেকেন্ড)
    KB_QUERY_CACHE_TTL: int = 300         # RAG/KB query cache — 5 min
    SESSION_TTL: int = 3600               # conversation state — 1 ghonta
```

> ⚠️ Docker-এ চললে `REDIS_HOST=redis` আর `REDIS_PORT=6379` (internal DNS)।
> Host machine থেকে চালালে `REDIS_HOST=localhost` আর `REDIS_PORT=6380`
> (তোমার compose-এ host port 6380 → container 6379)।

---

## 3️⃣ `backend/services/cache.py` — ✅ আগেই বানানো

এটা singleton factory — `module/redis_core` কে `settings` এর সাথে connect করে।
কিছু করতে হবে না, শুধু import করে ব্যবহার করবে:

```python
from backend.services.cache import get_cache
cache = get_cache()
```

---

## 4️⃣ `backend/services/rag.py` — KB query cache (সবচেয়ে বড় win)

এখন প্রতি user utterance-এ DB-তে full-text search চলে। একই প্রশ্ন বারবার এলে
প্রতিবার DB hit হয়। Cache দিলে repeated query গুলো RAM থেকে instant আসবে →
latency কমবে, DB load কমবে।

`retrieve()` function-টা এভাবে wrap করো (file-এর উপরে import যোগ করে):

```python
import hashlib
from backend.config import settings
from backend.services.cache import get_cache

async def retrieve(agent_id, query, top_k=4, original_text=""):
    query = query.strip()
    if not query:
        return []

    # ── cache lookup ──────────────────────────────────────────────
    cache = get_cache()
    raw = f"{agent_id}|{query}|{original_text}|{top_k}"
    cache_key = f"kb:{hashlib.md5(raw.encode()).hexdigest()}"
    try:
        cached = await cache.get_json(cache_key)
        if cached is not None:
            log.info("KB cache HIT for: %s", query[:60])
            return cached
    except Exception:
        log.exception("cache read failed — falling back to DB")

    # ── (এখানে তোমার existing DB search code টা পুরোটা থাকবে) ──────
    # ... results = [...] ...

    # ── cache-এ রাখো (return করার আগে) ───────────────────────────
    try:
        await cache.set_json(cache_key, results[:top_k], ttl=settings.KB_QUERY_CACHE_TTL)
    except Exception:
        log.exception("cache write failed — ignoring")

    return results[:top_k]
```

> KB update হলে stale cache সমস্যা করতে পারে। `backend/api/kb.py`-তে যেখানে
> নতুন chunk add/delete হয়, সেখানে ওই agent-এর cache key গুলো invalidate করো
> (অথবা TTL ছোট রাখলে এমনিতেই expire হয়ে যাবে — 5 min যথেষ্ট)।

---

## 5️⃣ `backend/worker/agent_worker.py` — Conversation state persist (optional কিন্তু recommended)

এখন `AgentPipeline.__init__` এ `self.history = []` — এই history শুধু RAM-এ
থাকে, worker crash/restart হলে পুরো কথোপকথন হারিয়ে যায়। Redis-এ রাখলে call
টিকে থাকে এবং একাধিক worker-এর মধ্যে share করা যায়।

`AgentPipeline`-এ একটা `session_id` (room name ব্যবহার করতে পারো) আর দুটো helper
যোগ করো:

```python
from backend.services.cache import get_cache
from backend.config import settings

class AgentPipeline:
    def __init__(self, agent, session_id: str = ""):
        self.agent = agent
        self.session_id = session_id
        self.history: list[dict] = []
        # ... বাকি existing code ...

    async def load_history(self):
        if not self.session_id:
            return
        cached = await get_cache().get_json(f"session:{self.session_id}")
        if cached:
            self.history = cached

    async def save_history(self):
        if not self.session_id:
            return
        await get_cache().set_json(
            f"session:{self.session_id}", self.history, ttl=settings.SESSION_TTL
        )
```

তারপর — প্রতিবার `self.history.append(...)` এর পরে `await self.save_history()`
call করো (greeting + প্রতি turn-এ)। আর entrypoint-এ pipeline বানানোর সময়
room name দাও:

```python
# entrypoint() এর ভেতর
pipeline = AgentPipeline(agent, session_id=ctx.room.name)
await pipeline.load_history()
```

> এই step optional — শুধু prototype হলে skip করতে পারো। কিন্তু production /
> multi-worker / call-transfer চাইলে এটা দরকারি।

---

## 6️⃣ `docker-compose.yml` + persistence

তোমার compose-এ Redis service আগেই আছে (LiveKit SIP এর জন্য)। এখন এটাকে cache
হিসেবেও ব্যবহার করবে — তাই persistence + volume যোগ করো যাতে restart-এ data
না হারায়।

বর্তমান block:

```yaml
  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:6380:6379"
```

এটাকে বানাও:

```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "127.0.0.1:6380:6379"
    volumes:
      - redisdata:/data
      - ./redis.conf:/usr/local/etc/redis/redis.conf:ro
```

আর নিচে `volumes:` block-এ যোগ করো:

```yaml
volumes:
  pgdata:
  redisdata:     # ← এটা যোগ করো
```

`backend` service-এর env-এ (অথবা `.env`-এ) সেট করো:

```
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=1          # SIP/LiveKit DB 0 ব্যবহার করে; cache আলাদা DB-তে রাখো
REDIS_NAMESPACE=voiceagent
```

> DB 1 আলাদা রাখলে তোমার cache key গুলো LiveKit-এর key-এর সাথে মিশবে না।

---

## 🔑 RDB না AOF — কোনটা?

**সংক্ষেপে: AOF ব্যবহার করো (`appendfsync everysec`)।**

কারণ:

| | RDB (snapshot) | AOF (append-only log) |
|---|---|---|
| কীভাবে | নির্দিষ্ট সময় পরপর পুরো dataset-এর snapshot | প্রতিটা write command log করে |
| Restart-এ data loss | শেষ snapshot-এর পরের সব হারায় (মিনিট হতে পারে) | সর্বোচ্চ ~1 সেকেন্ড হারায় |
| File size | ছোট, compact | বড় (rewrite করে কমানো যায়) |
| Restart speed | দ্রুত | একটু ধীর |
| Best for | pure throwaway cache | session / state যেটা হারানো যাবে না |

তোমার voice agent-এ Redis দুই কাজ করছে:
1. **KB query cache** — হারালে সমস্যা নেই (আবার DB থেকে আসবে)।
2. **Conversation / session state** — চলমান call-এর মাঝে হারালে call ভেঙে যাবে।

দ্বিতীয়টার জন্য durability দরকার, তাই **AOF**। `everysec` মোড দিলে performance
প্রায় RDB-র সমান থাকে কিন্তু data loss সর্বোচ্চ ১ সেকেন্ড।

### `redis.conf` (project root-এ নতুন ফাইল)

```conf
# ----- Persistence -----
appendonly yes
appendfsync everysec
appendfilename "appendonly.aof"
dir /data

# AOF auto-rewrite (file বড় হলে compact করে)
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# RDB ও চালু রাখা ভালো — দ্রুত restart + backup snapshot হিসেবে।
# Redis দুটো একসাথে চালাতে পারে; restart-এ AOF কে priority দেয়।
save 900 1
save 300 10

# ----- Memory cap (cache অংশের জন্য safety) -----
# cache RAM ভরে গেলে সবচেয়ে কম-ব্যবহৃত key গুলো আগে মুছবে
maxmemory 256mb
maxmemory-policy allkeys-lru
```

> **শুধু prototype / single machine, কিছু হারালেও সমস্যা নেই** → persistence
> পুরো বন্ধ রেখেও চলবে (`appendonly no`, `save ""`)। কিন্তু একবার session state
> Redis-এ রাখা শুরু করলে **AOF on** রাখো।

> ⚠️ `maxmemory-policy allkeys-lru` দিলে session key-ও evict হতে পারে memory
> ভরে গেলে। session আর cache একসাথে এক instance-এ রাখলে হয় (ক) আলাদা DB
> ব্যবহার করো, নয়তো (খ) session-গুলোকে যথেষ্ট TTL দাও আর maxmemory বড় রাখো।

---

## ✅ Wiring সারমর্ম

```
module/redis_core/  ←──  backend/services/cache.py  ←──  rag.py  (KB cache)
                                                    └──  agent_worker.py  (session state)
                                                    └──  যেকোনো নতুন জায়গা (rate-limit, TTS cache...)
```

`get_cache()` একটাই shared instance ফেরত দেয় — যেখানে দরকার সেখানে import করে
`await cache.get_json(...)` / `await cache.set_json(...)` করলেই হবে।