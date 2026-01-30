import os
import aiohttp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# --- الإعدادات ---
# احصل على API_ID و API_HASH من: https://my.telegram.org/apps
API_ID = 899701233  # استبدله برقمك
API_HASH = "@rood_onepiece"
BOT_TOKEN = "8520726911:AAGVdtBEtNDrD8cdjldPfmtMjSXDzyqJ4ls"

# معرف القناة (يجب أن يكون البوت مشرفاً فيها)
# مثال: -100123456789 أو @channelname
TARGET_CHANNEL = "@uplovid" 

# إنشاء تطبيق Pyrogram
app = Client(
    "my_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- دوال التعامل مع GoFile ---

async def get_gofile_server():
    """الحصول على أفضل سيرفر متاح للرفع لتجنب الضغط"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://api.gofile.io/servers") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data['status'] == 'ok' and data['data']['servers']:
                        return data['data']['servers'][0]['name']
        except Exception as e:
            print(f"Error getting server: {e}")
    return "store1" # سيرفر احتياطي

async def upload_to_gofile_stream(file_path):
    """
    رفع الملف باستخدام الـ Streaming لتوفير الرام.
    يقرأ الملف قطعة بقطعة ويرسلها مباشرة.
    """
    server = await get_gofile_server()
    url = f"https://{server}.gofile.io/uploadFile"
    
    async with aiohttp.ClientSession() as session:
        try:
            # نستخدم FormData لفتح الملف كـ Stream
            with open(file_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename=os.path.basename(file_path))
                
                # الرفع الفعلي
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result['status'] == 'ok':
                            return result['data']['downloadPage']
                    else:
                        print(f"Upload failed: {resp.status}")
        except Exception as e:
            print(f"Upload Exception: {e}")
            
    return None

# --- معالج الفيديو ---

@app.on_message(filters.chat(TARGET_CHANNEL) & filters.video)
async def handle_video(client: Client, message: Message):
    print(f"New video detected: {message.video.file_name or 'Unknown'}")
    
    file_path = f"downloads/{message.id}_{message.video.file_name or 'video.mp4'}"
    
    # التأكد من وجود مجلد التحميلات
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    try:
        # 1. تحميل الفيديو من تيليجرام (يدعم الملفات الكبيرة)
        print("Downloading from Telegram...")
        # يتم التحميل وحفظه على القرص لتقليل استهلاك الرام
        downloaded_path = await message.download(file_path)
        print("Download complete.")

        # 2. رفع الفيديو إلى GoFile
        print("Uploading to GoFile...")
        link = await upload_to_gofile_stream(downloaded_path)

        if link:
            print(f"✅ Success! Link: {link}")
            # اختياري: إرسال الرابط إلى القناة أو إلى مجموعة السجل
            # await client.send_message("me", f"رابط الملف: {link}")
        else:
            print("❌ Failed to get link.")

    except Exception as e:
        print(f"Error processing video: {e}")

    finally:
        # 3. التنظيف: حذف الملف من السيرفر لتوفير المساحة
        if os.path.exists(file_path):
            os.remove(file_path)
            print("Cleaned up local file.")

# تشغيل البوت
print("Bot is running professionally...")
app.run()
