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

# --- إعدادات البوت ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", 5000))

# هيدر لتمويه السيرفر وكأنه متصفح عادي (ضروري جداً)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- إعدادات Flask ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running..."

def run_flask():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=PORT)

# --- دوال مساعدة ---
def get_filename(response, url):
    filename = None
    if "Content-Disposition" in response.headers:
        cd = response.headers["Content-Disposition"]
        fnames = re.findall('filename="?([^"]+)"?', cd)
        if fnames:
            filename = fnames[0]
    
    if not filename:
        try:
            filename = url.split("/")[-1].split("?")[0]
            filename = unquote(filename)
        except:
            pass
            
    if not filename or not "." in filename:
        filename = "file.bin"
    return filename

# --- دالة الرفع على Catbox (الخيار الأفضل للبوتات) ---
def upload_to_catbox(target_url):
    try:
        # Catbox يقبل ملفات حتى 200MB
        with requests.get(target_url, stream=True, headers=HEADERS, timeout=20) as r_source:
            r_source.raise_for_status()
            filename = get_filename(r_source, target_url)
            
            m = MultipartEncoder(
                fields={
                    'reqtype': 'fileupload',
                    'fileToUpload': (filename, r_source.raw, r_source.headers.get('Content-Type', 'application/octet-stream'))
                }
            )
            
            response = requests.post(
                "https://catbox.moe/user/api.php",
                data=m,
                headers={'Content-Type': m.content_type, 'User-Agent': HEADERS['User-Agent']},
                timeout=3600
            )
            
            if response.status_code == 200:
                return True, filename, response.text # الرابط يرجع كنص مباشر
            else:
                return False, filename, f"Catbox Error: {response.status_code}"
    except Exception as e:
        return False, "Unknown", str(e)

# --- دالة الرفع على File.io (احتياطي - يحذف الملف بعد تحميله مرة واحدة) ---
def upload_to_fileio(target_url, filename_hint):
    try:
        with requests.get(target_url, stream=True, headers=HEADERS, timeout=20) as r_source:
            r_source.raise_for_status()
            
            m = MultipartEncoder(
                fields={
                    'file': (filename_hint, r_source.raw, r_source.headers.get('Content-Type', 'application/octet-stream'))
                }
            )
            
            response = requests.post(
                "https://file.io",
                data=m,
                headers={'Content-Type': m.content_type, 'User-Agent': HEADERS['User-Agent']},
                timeout=3600
            )
            
            if response.status_code == 200:
                return True, response.json().get('link')
            else:
                return False, f"File.io Error: {response.status_code}"

    except Exception as e:
        return False, str(e)

# --- معالج العمليات ---
def process_upload(url):
    # المحاولة الأولى: Catbox
    success, filename, result = upload_to_catbox(url)
    if success:
        return True, "Catbox.moe", filename, result, "✅ دائم"
    
    # المحاولة الثانية: File.io
    fname_hint = filename if filename != "Unknown" else "file.bin"
    success_io, result_io = upload_to_fileio(url, fname_hint)
    
    if success_io:
        return True, "File.io", fname_hint, result_io, "⚠️ مؤقت (يحذف بعد التحميل)"
    
    return False, "Failed", fname_hint, f"Catbox: {result} | File.io: {result_io}", ""

# --- التفاعلات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **أهلاً بك!**\n\n"
        "أرسل رابط مباشر وسأقوم برفعه على **Catbox** (دائم) أو **File.io** (مؤقت).\n"
        "هذه السيرفرات تعمل بشكل أفضل مع Render.",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ الرابط غير صالح.")
        return

    status_msg = await update.message.reply_text("⏳ **جارٍ الرفع...**\nيتم المحاولة عبر سيرفرات بديلة لتجنب الحظر.", parse_mode='Markdown')

    loop = asyncio.get_running_loop()
    
    try:
        success, host, fname, link, note = await loop.run_in_executor(None, process_upload, url)
        
        if success:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status_msg.message_id,
                text=f"✅ **تم الرفع بنجاح!**\n\n"
                     f"☁️ السيرفر: {host}\n"
                     f"📂 الملف: `{fname}`\n"
                     f"ℹ️ ملاحظة: {note}\n"
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
            text=f"❌ خطأ غير متوقع: {str(e)}"
        )

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    if not TOKEN:
        print("❌ Error: TELEGRAM_TOKEN missing!")
    else:
        application = ApplicationBuilder().token(TOKEN).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        application.run_polling()