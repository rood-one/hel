import os
import aiohttp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# --- الإعدادات ---
# ملاحظة: API_ID و API_HASH الموجودة قد تكون غير صحيحة، يرجى التأكد منها من https://my.telegram.org/apps
API_ID = 899701233  
API_HASH = "8095402128e46973302061328087955b" # هذا مثال لهاش صحيح، الهاش الأصلي كان يبدو كاسم مستخدم
BOT_TOKEN = "8520726911:AAGVdtBEtNDrD8cdjldPfmtMjSXDzyqJ4ls"

# معرف القناة (يجب أن يكون البوت مشرفاً فيها)
TARGET_CHANNEL = "@uplovid" 

# إنشاء تطبيق Pyrogram
app = Client(
    "my_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- دوال التعامل مع GoFile ---

async def upload_to_gofile_stream(file_path):
    """
    رفع الملف إلى GoFile باستخدام الـ Streaming لتوفير الرام.
    تم تحديث الرابط إلى الرابط العالمي الجديد حسب التوثيق.
    """
    url = "https://upload.gofile.io/uploadfile"
    
    # استخدام ClientSession واحدة أو إدارتها بشكل جيد
    async with aiohttp.ClientSession() as session:
        try:
            # نستخدم FormData لرفع الملف
            data = aiohttp.FormData()
            # فتح الملف كـ stream لتقليل استهلاك الذاكرة
            with open(file_path, 'rb') as f:
                data.add_field('file', f, filename=os.path.basename(file_path))
                
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result['status'] == 'ok':
                            return result['data']['downloadPage']
                        else:
                            print(f"GoFile Error: {result.get('status')}")
                    else:
                        print(f"Upload failed with status: {resp.status}")
        except Exception as e:
            print(f"Upload Exception: {e}")
            
    return None

# --- معالج الفيديو ---

@app.on_message(filters.chat(TARGET_CHANNEL) & filters.video)
async def handle_video(client: Client, message: Message):
    print(f"New video detected: {message.video.file_name or 'Unknown'}")
    
    # إنشاء مجلد التحميلات إذا لم يكن موجوداً
    os.makedirs("downloads", exist_ok=True)
    
    file_name = message.video.file_name or f"video_{message.id}.mp4"
    file_path = os.path.join("downloads", f"{message.id}_{file_name}")
    
    try:
        # 1. تحميل الفيديو من تيليجرام
        # ملاحظة: Render لديه مساحة قرص محدودة في النسخة المجانية، لذا نحذف الملف فوراً بعد الرفع
        print(f"Downloading {file_name} from Telegram...")
        downloaded_path = await message.download(file_path)
        print("Download complete.")

        # 2. رفع الفيديو إلى GoFile
        print("Uploading to GoFile...")
        link = await upload_to_gofile_stream(downloaded_path)

        if link:
            print(f"✅ Success! Link: {link}")
            # إرسال الرابط كرد على الفيديو في القناة
            await message.reply_text(f"✅ تم الرفع بنجاح!\n\nرابط الملف: {link}", quote=True)
        else:
            print("❌ Failed to get link.")
            await message.reply_text("❌ فشل رفع الملف إلى GoFile.", quote=True)

    except Exception as e:
        print(f"Error processing video: {e}")

    finally:
        # 3. التنظيف: حذف الملف من السيرفر لتوفير المساحة
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up local file: {file_path}")

# تشغيل البوت
if __name__ == "__main__":
    print("Bot is starting...")
    app.run()
