import asyncio
import httpx
import os

CARTESIA_API_KEY = "sk_car_Xjms6baGLcFWFAeY2zjXBs"

async def test():
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": "2024-06-10",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.cartesia.ai/models", headers=headers)
        print("Status:", resp.status_code)
        print("Models:", resp.text)

asyncio.run(test())
