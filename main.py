import os
import logging
import threading
import asyncio
import requests
import re
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from requests.auth import HTTPBasicAuth

# --- إعدادات السجلات ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
PIXELDRAIN_API_KEY = os.getenv("PIXELDRAIN_API_KEY") 
# متغير جديد للبروكسي (مثال: http://user:pass@ip:port)
HTTP_PROXY = os.getenv("HTTP_PROXY") 

# --- Flask ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running with Proxy Support!"

def run_flask():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- دالة الرفع مع البروكسي ---
def stream_upload_task(source_url, filename):
    if not PIXELDRAIN_API_KEY:
        return False, "⚠️ خطأ: PIXELDRAIN_API_KEY مفقود."

    try:
        # إعداد البروكسي إذا وجد
        proxies = None
        if HTTP_PROXY:
            proxies = {
                "http": HTTP_PROXY,
                "https": HTTP_PROXY
            }
            logger.info("Using Proxy for connection...")

        # 1. الاتصال بالملف المصدر (بدون بروكسي عادةً، أو يمكن إضافته إذا كان المصدر محجوباً أيضاً)
        # ملاحظة: التحميل من المصدر نادراً ما يحتاج بروكسي إلا إذا كان الموقع محجوباً
        with requests.get(source_url, stream=True, timeout=30) as r_source:
            r_source.raise_for_status()
            
            safe_filename = re.sub(r'[^\w\-_\. ]', '', filename).strip()
            if not safe_filename: safe_filename = "file.mp4"

            upload_url = f"https://pixeldrain.com/api/file/{safe_filename}"
            auth = HTTPBasicAuth('', PIXELDRAIN_API_KEY)
            
            # 2. الرفع إلى Pixeldrain (عبر البروكسي لتجاوز الحظر)
            response = requests.put(
                upload_url,
                data=r_source.iter_content(chunk_size=5 * 1024 * 1024), 
                auth=auth,
                proxies=proxies,  # هنا التغيير المهم
                timeout=7200,
                verify=False # أحياناً ضروري مع البروكسيات المجانية (تجاهل شهادة SSL)
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                if data.get('success'):
                    return True, f"https://pixeldrain.com/u/{data.get('id')}"
                else:
                    return False, f"Pixeldrain API Error: {data}"
            else:
                return False, f"HTTP Error: {response.status_code} - {response.text}"

    except Exception as e:
        return False, f"Connection Error: {str(e)}"

# --- معالجة الطلبات ---

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['pending_url'] = update.message.text.strip()
    await update.message.reply_text("✅ تم حفظ الرابط. أرسل اسم الملف الآن:")

async def handle_filename_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'pending_url' not in context.user_data:
        await update.message.reply_text("⚠️ أرسل الرابط أولاً.")
        return

    filename = update.message.text.strip()
    if "." not in filename: filename += ".mp4"
    url = context.user_data.pop('pending_url')

    status_msg = await update.message.reply_text(f"⏳ **جاري الرفع عبر البروكسي...**\n`{filename}`", parse_mode='Markdown')

    loop = asyncio.get_running_loop()
    success, result = await loop.run_in_executor(None, stream_upload_task, url, filename)

    if success:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"✅ **تم!**\n🔗 {result}",
            parse_mode='Markdown'
        )
    else:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"❌ **فشل:**\n{result}"
        )

# --- التشغيل ---
if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    if not TOKEN:
        print("❌ Error: TELEGRAM_TOKEN missing")
    else:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(MessageHandler(filters.Regex(r'^https?://') & (~filters.COMMAND), handle_url))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.Regex(r'^https?://')) & (~filters.COMMAND), handle_filename_and_upload))
        application.run_polling()