import asyncio
import httpx
import os
import json

CARTESIA_API_KEY = "sk_car_Xjms6baGLcFWFAeY2zjXBs"

async def test():
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
        "Content-Type": "application/json",
    }
    
    for lang in ["bn", "hi", "en", "en-IN"]:
        body = {
            "model_id": "sonic-2",
            "transcript": "নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি?",
            "voice": {"mode": "id", "id": "2ba861ea-7cdc-43d1-8608-4045b5a41de5"},
            "language": lang,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": 24000,
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://api.cartesia.ai/tts/bytes", json=body, headers=headers)
            print(f"Lang: {lang}, Status: {resp.status_code}")
            if resp.status_code != 200:
                print(resp.text)

asyncio.run(test())
