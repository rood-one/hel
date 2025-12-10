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

# --- إعدادات السجلات (Logs) ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- متغيرات البيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
# تأكد من إضافة هذا المتغير في إعدادات Render
PIXELDRAIN_API_KEY = os.getenv("PIXELDRAIN_API_KEY") 

# --- سيرفر Flask (لإبقاء البوت يعمل 24/7) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running efficiently!"

def run_flask():
    # منع رسائل Flask المزعجة
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- دالة الرفع الذكي (Streaming) ---
# هذه الدالة تنقل البيانات بايت-بايت من المصدر إلى Pixeldrain دون تخزينها
def stream_upload_task(source_url, filename):
    if not PIXELDRAIN_API_KEY:
        return False, "⚠️ خطأ: لم يتم ضبط PIXELDRAIN_API_KEY في إعدادات السيرفر."

    try:
        # 1. الاتصال بالملف المصدر
        # stream=True تمنع تحميل الملف للذاكرة
        with requests.get(source_url, stream=True, timeout=20) as r_source:
            r_source.raise_for_status()
            
            # تنظيف اسم الملف
            safe_filename = re.sub(r'[^\w\-_\. ]', '', filename).strip()
            if not safe_filename: safe_filename = "file.mp4"

            # رابط الرفع الخاص بـ Pixeldrain
            upload_url = f"https://pixeldrain.com/api/file/{safe_filename}"
            
            # إعداد المصادقة
            auth = HTTPBasicAuth('', PIXELDRAIN_API_KEY)
            
            # 2. الرفع المباشر (Piping)
            # نقرأ 5 ميجا ونرسلها، ثم نحذفها من الرام، وهكذا
            response = requests.put(
                upload_url,
                data=r_source.iter_content(chunk_size=5 * 1024 * 1024), 
                auth=auth,
                timeout=7200 # مهلة ساعتين للملفات الضخمة
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                if data.get('success'):
                    return True, f"https://pixeldrain.com/u/{data.get('id')}"
                else:
                    return False, f"Pixeldrain Error: {data}"
            elif response.status_code == 429:
                return False, "⛔ تجاوزت حد الرفع اليومي لحسابك."
            elif response.status_code == 507:
                return False, "⛔ المساحة ممتلئة في حساب Pixeldrain."
            else:
                return False, f"HTTP Error: {response.status_code} - {response.text}"

    except Exception as e:
        return False, f"Exception: {str(e)}"

# --- معالجة الطلبات ---

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المرحلة 1: استلام الرابط"""
    url = update.message.text.strip()
    
    # حفظ الرابط في ذاكرة المستخدم المؤقتة
    context.user_data['pending_url'] = url
    
    await update.message.reply_text(
        "✅ **تم حفظ الرابط.**\n"
        "أرسل الآن **اسم الملف** (مثال: `Episode 1.mp4`):",
        parse_mode='Markdown'
    )

async def handle_filename_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """المرحلة 2: استلام الاسم وبدء الرفع"""
    if 'pending_url' not in context.user_data:
        await update.message.reply_text("⚠️ أرسل الرابط أولاً.")
        return

    filename = update.message.text.strip()
    # إضافة امتداد افتراضي mp4 إذا لم يكتبه المستخدم
    if "." not in filename:
        filename += ".mp4"
        
    url = context.user_data.pop('pending_url')

    # رسالة الانتظار
    status_msg = await update.message.reply_text(
        f"⏳ **جاري العمل...**\n"
        f"يتم نقل: `{filename}`\n"
        f"العملية تتم سحابياً (Server-to-Server) للحفاظ على السرعة.",
        parse_mode='Markdown'
    )

    # تشغيل عملية الرفع في الخلفية (Asyncio Executor)
    loop = asyncio.get_running_loop()
    
    # هذه الخطوة مهمة جداً: تشغيل كود requests الثقيل في thread منفصل
    success, result = await loop.run_in_executor(None, stream_upload_task, url, filename)

    if success:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"✅ **تم الرفع بنجاح!**\n\n"
                 f"📂 اسم الملف: `{filename}`\n"
                 f"🔗 **الرابط:**\n{result}",
            parse_mode='Markdown'
        )
    else:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"❌ **فشلت العملية**\n\nالسبب: {result}"
        )

# --- نقطة البداية ---
if __name__ == '__main__':
    # 1. تشغيل Flask في الخلفية
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # 2. التحقق من التوكنات
    if not TOKEN:
        print("❌ Error: TELEGRAM_TOKEN is missing")
    elif not PIXELDRAIN_API_KEY:
        print("⚠️ Warning: PIXELDRAIN_API_KEY is missing (Uploads might fail)")
    else:
        print("✅ Bot is starting...")
        application = ApplicationBuilder().token(TOKEN).build()

        # معالج الروابط: أي رسالة تبدأ بـ http
        application.add_handler(MessageHandler(
            filters.Regex(r'^https?://') & (~filters.COMMAND), 
            handle_url
        ))
        
        # معالج الأسماء: أي نص ليس رابطاً
        application.add_handler(MessageHandler(
            filters.TEXT & (~filters.Regex(r'^https?://')) & (~filters.COMMAND), 
            handle_filename_and_upload
        ))
        
        application.run_polling()