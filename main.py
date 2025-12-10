import os
import logging
import requests
import threading
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from requests_toolbelt.multipart.encoder import MultipartEncoder
import re
from urllib.parse import unquote

# --- إعدادات التسجيل ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- إعدادات البوت والبيئة ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 5000))

# --- إعدادات Flask (Keep-Alive) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running and healthy!"

def run_flask():
    # إيقاف رسائل الفلاسك المزعجة في اللوج
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=PORT)

# --- دوال مساعدة ---
def get_filename(response, url):
    """
    محاولة ذكية لاستخراج اسم الملف من الهيدر أو الرابط
    """
    filename = None
    # 1. المحاولة من Content-Disposition
    if "Content-Disposition" in response.headers:
        cd = response.headers["Content-Disposition"]
        fnames = re.findall('filename="?([^"]+)"?', cd)
        if fnames:
            filename = fnames[0]
            
    # 2. المحاولة من الرابط إذا فشل الهيدر
    if not filename:
        try:
            filename = url.split("/")[-1].split("?")[0]
            filename = unquote(filename) # فك تشفير الرموز مثل %20
        except:
            pass
            
    # 3. اسم افتراضي
    if not filename or not "." in filename:
        filename = "downloaded_file.bin"
        
    return filename

# --- دالة الرفع على Pixeldrain (استهلاك رام شبه معدوم) ---
def upload_to_pixeldrain(target_url):
    try:
        # فتح اتصال مع الملف المصدر (Stream)
        with requests.get(target_url, stream=True, timeout=20) as r_source:
            r_source.raise_for_status()
            filename = get_filename(r_source, target_url)
            
            # Pixeldrain يقبل الرفع المباشر عبر PUT (Streamed Upload)
            # نستخدم المولد (Generator) لرفع البيانات قطعة بقطعة
            response = requests.put(
                f"https://pixeldrain.com/api/file/{filename}",
                data=r_source.iter_content(chunk_size=8192), # قطع صغيرة جداً 8KB
                auth=('', ''),
                timeout=3600 # ساعة مهلة للملفات الكبيرة
            )
            
            if response.status_code == 201:
                data = response.json()
                return True, filename, f"https://pixeldrain.com/u/{data.get('id')}"
            else:
                return False, filename, f"Pixeldrain Error: {response.status_code}"
    except Exception as e:
        return False, "Unknown", str(e)

# --- دالة الرفع على GoFile (باستخدام requests-toolbelt لتوفير الرام) ---
def upload_to_gofile(target_url, filename_hint):
    try:
        # 1. الحصول على السيرفر
        server_req = requests.get("https://api.gofile.io/getServer", timeout=10)
        server_data = server_req.json()
        if server_data['status'] != 'ok':
            return False, "GoFile Server Error"
        
        server = server_data['data']['server']
        upload_url = f"https://{server}.gofile.io/uploadFile"

        # 2. بدء الرفع المتدفق
        with requests.get(target_url, stream=True, timeout=20) as r_source:
            r_source.raise_for_status()
            
            # استخدام MultipartEncoder لإنشاء تدفق مباشر دون تحميل الملف في الرام
            m = MultipartEncoder(
                fields={
                    'file': (filename_hint, r_source.raw, r_source.headers.get('Content-Type', 'application/octet-stream'))
                }
            )
            
            # الرفع
            response = requests.post(
                upload_url,
                data=m,
                headers={'Content-Type': m.content_type},
                timeout=3600
            )
            
            resp_json = response.json()
            if resp_json['status'] == 'ok':
                return True, resp_json['data']['downloadPage']
            else:
                return False, "GoFile Upload Failed"

    except Exception as e:
        return False, str(e)

# --- معالج العمليات الثقيلة (لتشغيلها في الخلفية) ---
def process_upload(url):
    # نحاول أولاً Pixeldrain
    success, filename, result = upload_to_pixeldrain(url)
    
    if success:
        return True, "Pixeldrain", filename, result
    
    # إذا فشل، نحاول GoFile
    # نستخدم الاسم الذي استخرجناه في المحاولة الأولى إذا وجد
    fname_for_go = filename if filename != "Unknown" else "file.bin"
    success_go, result_go = upload_to_gofile(url, fname_for_go)
    
    if success_go:
        return True, "GoFile", fname_for_go, result_go
    
    return False, "Failed", fname_for_go, f"Pixeldrain: {result} | GoFile: {result_go}"

# --- التفاعلات مع التليجرام ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **مرحباً بك في بوت الرفع السحابي**\n\n"
        "🚀 **طريقة العمل:** أرسل لي رابطاً مباشراً، وسأقوم برفعه لك على Pixeldrain (أو GoFile كبديل).\n"
        "💡 **المميزات:** لا أستهلك من باقتك، وأعمل بكفاءة عالية.",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ الرابط غير صالح.")
        return

    status_msg = await update.message.reply_text("⏳ **بدء الاتصال بالسيرفر...**", parse_mode='Markdown')

    # تشغيل عملية الرفع في Thread منفصل لعدم تجميد البوت (Asyncio Executor)
    loop = asyncio.get_running_loop()
    
    try:
        # استخدام run_in_executor لتشغيل الكود المتزامن (blocking) بشكل غير متزامن
        success, host, fname, link = await loop.run_in_executor(None, process_upload, url)
        
        if success:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text=f"✅ **تم الرفع بنجاح!**\n\n"
                     f"☁️ السيرفر: {host}\n"
                     f"📂 الملف: `{fname}`\n"
                     f"🔗 الرابط: {link}",
                parse_mode='Markdown'
            )
        else:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text=f"❌ **فشلت العملية**\n\nالسبب:\n{link}"
            )
    except Exception as e:
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status_msg.message_id,
            text=f"❌ حدث خطأ غير متوقع: {str(e)}"
        )

# --- التشغيل الرئيسي ---
if __name__ == '__main__':
    # 1. تشغيل سيرفر Flask في خيط منفصل
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True # يغلق تلقائياً عند إغلاق البوت
    flask_thread.start()

    # 2. التحقق من التوكن وتشغيل البوت
    if not TOKEN:
        print("❌ Error: TELEGRAM_TOKEN variable is missing!")
    else:
        print("✅ Bot is starting...")
        application = ApplicationBuilder().token(TOKEN).build()
        
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        application.run_polling()