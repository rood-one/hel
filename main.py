import os
import logging
import aiohttp
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# --- الإعدادات ---
BOT_TOKEN = "8520726911:AAGVdtBEtNDrD8cdjldPfmtMjSXDzyqJ4ls"
TARGET_CHANNEL = "@uplovid" 

# إعداد السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- دوال التعامل مع GoFile ---

async def upload_to_gofile_stream(file_path):
    url = "https://upload.gofile.io/uploadfile"
    async with aiohttp.ClientSession() as session:
        try:
            data = aiohttp.FormData()
            with open(file_path, 'rb') as f:
                data.add_field('file', f, filename=os.path.basename(file_path))
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result['status'] == 'ok':
                            return result['data']['downloadPage']
            logger.error(f"GoFile Upload Failed: {resp.status}")
        except Exception as e:
            logger.error(f"Upload Exception: {e}")
    return None

# --- معالج الرسائل ---

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post or update.message
    if not message or not message.video:
        return

    chat = message.chat
    chat_id = str(chat.id)
    chat_username = f"@{chat.username}" if chat.username else ""
    
    target = str(TARGET_CHANNEL)
    if target != chat_id and target != chat_username:
        return

    logger.info(f"Processing video from: {chat_id} / {chat_username}")
    
    os.makedirs("downloads", exist_ok=True)
    file_id = message.video.file_id
    file_name = message.video.file_name or f"video_{message.message_id}.mp4"
    file_path = os.path.join("downloads", f"{message.message_id}_{file_name}")
    
    try:
        # إرسال رسالة تفيد ببدء المعالجة
        status_msg = await message.reply_text("⏳ جاري التحميل من تيليجرام...")
        
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(file_path)
        
        await status_msg.edit_text("📤 جاري الرفع إلى GoFile...")
        link = await upload_to_gofile_stream(file_path)

        if link:
            await status_msg.edit_text(f"✅ تم الرفع بنجاح!\n\nرابط الملف: {link}")
        else:
            await status_msg.edit_text("❌ فشل رفع الملف.")

    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def main():
    # بناء التطبيق
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    # --- حل مشكلة التعارض (Conflict) ---
    # حذف أي Webhook قديم قد يسبب تعارض مع Polling
    logger.info("Cleaning up old connections...")
    await application.bot.delete_webhook(drop_pending_updates=True)
    
    logger.info("Bot is starting...")
    
    # تشغيل البوت
    # ملاحظة: استخدمنا run_polling() لأنها الأسهل في Render عند استخدام "Worker"
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    # إبقاء البوت يعمل
    while True:
        await asyncio.sleep(1000)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
