# module/redis_core

Reusable **cache module** — Redis (production) + in-memory (dev/test fallback)।
`stt_core` / `tts_core` এর মতোই একই pattern (base / registry / errors / providers)।

কোনো extra framework লাগবে না — শুধু redis backend ব্যবহার করতে হলে `redis`
package লাগবে। memory backend-এর জন্য কিচ্ছু লাগে না।

---

## Structure

```
module/
  redis_core/                        ← plain directory
    base.py                          ← CacheConfig, BaseCache (async contract + JSON helpers)
    registry.py                      ← create_provider, list_providers, register_provider, from_env
    errors.py                        ← CacheError, BackendNotFound, MissingDependency, ...
    providers/
      redis/
        provider.py                  ← RedisCache  (async, redis-py)
        client.py                    ← connection pool builder
        errors.py                    ← RedisCacheError
      memory/
        provider.py                  ← MemoryCache (TTL-aware, no dependency)
```

---

## অন্য Project-এ Share / Copy করার নিয়ম

**Step 1 — folder copy করো (নাম `module` রাখতে হবে):**
```
their_project/
  module/
    redis_core/        ← এই folder টা হুবহু copy করে দাও
  their_code.py
```

> ⚠️ folder rename করা যাবে না — ভেতরে সব import `module.redis_core.xxx`
> হিসেবে hardcoded। নাম বদলালে import ভেঙে যাবে।

**Step 2 — dependency (শুধু redis backend লাগলে):**
```bash
pip install redis
```

**Step 3 — সরাসরি import করো:**
```python
from module.redis_core.base import CacheConfig
from module.redis_core.registry import create_provider, from_env
```

---

## Quick Start

```python
import asyncio
from module.redis_core.base import CacheConfig
from module.redis_core.registry import create_provider

async def main():
    cache = create_provider("redis", config=CacheConfig(
        host="localhost",
        port=6379,
        db=0,
        namespace="myapp",     # সব key-এর আগে "myapp:" বসবে
        default_ttl=300,       # set() এ ttl না দিলে 300s
    ))

    await cache.set("greeting", "hello")        # string
    print(await cache.get("greeting"))          # -> "hello"

    await cache.set_json("user:1", {"name": "Rahim"}, ttl=60)
    print(await cache.get_json("user:1"))       # -> {"name": "Rahim"}

    await cache.incr("page_views")              # atomic counter -> 1
    print(await cache.exists("greeting"))       # -> True
    await cache.delete("greeting")

    await cache.close()

asyncio.run(main())
```

### env থেকে build করা

```python
from module.redis_core.registry import from_env

# REDIS_URL / REDIS_HOST / REDIS_PORT / REDIS_DB / REDIS_PASSWORD পড়ে
cache = from_env("redis", namespace="kb", default_ttl=300)
```

### Redis ছাড়া (dev / test)

```python
cache = create_provider("memory")   # কোনো server লাগে না, কোনো install লাগে না
```

> memory backend শুধু এই process-এ থাকে — restart-এ মুছে যায়, অন্য worker দেখে না।
> Production / multi-worker হলে অবশ্যই `redis` ব্যবহার করো।

---

## BaseCache API

| Method | কাজ |
|--------|-----|
| `await get(key)` | string ফেরত দেয়, না থাকলে `None` |
| `await set(key, value, ttl=None)` | string রাখে; `ttl` সেকেন্ডে (না দিলে config.default_ttl) |
| `await get_json(key)` | JSON decode করে object ফেরত দেয় |
| `await set_json(key, obj, ttl=None)` | object JSON-encode করে রাখে |
| `await delete(key)` | key মুছে দেয় |
| `await exists(key)` | আছে কিনা (`bool`) |
| `await incr(key, amount=1)` | atomic counter, নতুন value ফেরত দেয় |
| `await expire(key, ttl)` | existing key-এ TTL বসায় |
| `await ping()` | reachable কিনা (`bool`) |
| `await close()` | connection pool ছেড়ে দেয় |

---

## CacheConfig Fields

| Field | Type | Default | বিবরণ |
|-------|------|---------|-------|
| `host` | `str` | `"localhost"` | Redis host |
| `port` | `int` | `6379` | Redis port |
| `db` | `int` | `0` | Redis DB number |
| `password` | `str \| None` | `None` | Redis password |
| `url` | `str \| None` | `None` | `redis://:pass@host:6379/0` — দিলে এটাই জেতে |
| `namespace` | `str` | `""` | প্রতি key-এর prefix (multi-app safe) |
| `default_ttl` | `int \| None` | `None` | set() এ ttl না দিলে এটা ব্যবহার হয় |
| `socket_timeout` | `float` | `5.0` | connect / command timeout (সেকেন্ড) |

---

## নতুন Backend যোগ করা

1. `module/redis_core/providers/<name>/provider.py` বানাও
2. `@register_provider("<name>")` দিয়ে `BaseCache` extend করো
3. `registry.py` এর `_load_providers()`-এ import যোগ করো

> Backend গুলো lazy load — প্রথমবার `create_provider()` / `list_providers()`
> call করলে register হয়।