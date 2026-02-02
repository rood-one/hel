import os
import logging
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# --- الإعدادات ---
# تم إزالة API_ID و API_HASH بناءً على طلبك، البوت يعمل الآن بالتوكن فقط
BOT_TOKEN = "8520726911:AAGVdtBEtNDrD8cdjldPfmtMjSXDzyqJ4ls"

# معرف القناة: يمكن أن يكون @username أو رقم ID (مثل -100123456789)
TARGET_CHANNEL = "@uplovid" 

# إعداد السجلات (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- دوال التعامل مع GoFile ---

async def upload_to_gofile_stream(file_path):
    """
    رفع الملف إلى GoFile باستخدام الـ Streaming لتوفير الرام.
    """
    url = "https://upload.gofile.io/uploadfile"
    
    async with aiohttp.ClientSession() as session:
        try:
            data = aiohttp.FormData()
            # فتح الملف كـ stream لتقليل استهلاك الذاكرة (مهم لـ Render)
            with open(file_path, 'rb') as f:
                data.add_field('file', f, filename=os.path.basename(file_path))
                
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result['status'] == 'ok':
                            return result['data']['downloadPage']
                        else:
                            logging.error(f"GoFile Error: {result.get('status')}")
                    else:
                        logging.error(f"Upload failed with status: {resp.status}")
        except Exception as e:
            logging.error(f"Upload Exception: {e}")
            
    return None

# --- معالج الرسائل ---

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post or update.message
    if not message or not message.video:
        return

    # التحقق من أن الرسالة قادمة من القناة المستهدفة
    chat = message.chat
    chat_id = str(chat.id)
    chat_username = f"@{chat.username}" if chat.username else ""
    
    # دعم التحقق من المعرف سواء كان ID أو Username
    target = str(TARGET_CHANNEL)
    if target != chat_id and target != chat_username:
        # إذا لم يتطابق المعرف، نتجاهل الرسالة
        return

    logging.info(f"New video detected in {chat.title or chat.id}")
    
    # إنشاء مجلد التحميلات
    os.makedirs("downloads", exist_ok=True)
    
    file_id = message.video.file_id
    file_name = message.video.file_name or f"video_{message.message_id}.mp4"
    file_path = os.path.join("downloads", f"{message.message_id}_{file_name}")
    
    try:
        # 1. تحميل الفيديو
        logging.info(f"Downloading {file_name}...")
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(file_path)
        logging.info("Download complete.")

        # 2. الرفع إلى GoFile
        logging.info("Uploading to GoFile...")
        link = await upload_to_gofile_stream(file_path)

        if link:
            logging.info(f"✅ Success! Link: {link}")
            await message.reply_text(f"✅ تم الرفع بنجاح!\n\nرابط الملف: {link}")
        else:
            logging.error("❌ Failed to get link.")
            await message.reply_text("❌ فشل رفع الملف إلى GoFile.")

    except Exception as e:
        logging.error(f"Error processing video: {e}")

    finally:
        # 3. التنظيف
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Cleaned up: {file_path}")

if __name__ == '__main__':
    # بناء التطبيق باستخدام التوكن فقط
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # إضافة معالج للفيديوهات في القنوات والمحادثات
    video_handler = MessageHandler(filters.VIDEO, handle_video)
    application.add_handler(video_handler)
    
    logging.info("Bot is starting using python-telegram-bot...")
    application.run_polling()
