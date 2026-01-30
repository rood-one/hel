import asyncio
from pyrogram import Client

API_ID = 899701233
API_HASH = "@rood_onepiece"
BOT_TOKEN = "8520726911:AAGVdtBEtNDrD8cdjldPfmtMjSXDzyqJ4ls"

async def test():
    try:
        app = Client("test_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
        async with app:
            me = await app.get_me()
            print(f"Bot connected successfully: {me.username}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
