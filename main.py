import os
import logging
import requests
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- إعدادات البوت ---
# سنقوم بجلب التوكن من متغيرات البيئة في Render للحفاظ على الأمان
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- إعدادات Flask (لإبقاء السيرفر يعمل على Render) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

# --- دوال مساعدة لاستخراج اسم الملف ---
def get_filename_from_url(url):
    try:
        if url.find('/'):
            return url.rsplit('/', 1)[1]
    except:
        pass
    return "unknown_file.bin"

# --- دالة الرفع على Pixeldrain ---
def upload_to_pixeldrain(file_url, filename):
    try:
        # نبدأ تحميل الملف كـ Stream (تدفق) لعدم استهلاك الرام
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            
            # إرسال الملف مباشرة إلى Pixeldrain
            response = requests.put(
                f"https://pixeldrain.com/api/file/{filename}",
                data=r.iter_content(chunk_size=1024*1024), # رفع 1 ميجا في كل دفعة
                auth=('', '') # مصادقة فارغة مطلوبة أحياناً
            )
            
            if response.status_code == 201: # تم الإنشاء بنجاح
                data = response.json()
                file_id = data.get('id')
                return True, f"https://pixeldrain.com/u/{file_id}"
            else:
                return False, f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return False, str(e)

# --- دالة الرفع على GoFile (الخيار البديل) ---
def upload_to_gofile(file_url, filename):
    try:
        # 1. الحصول على أفضل سيرفر للرفع
        server_req = requests.get("https://api.gofile.io/getServer")
        server_data = server_req.json()
        
        if server_data['status'] != 'ok':
            return False, "Could not get GoFile server"
            
        server = server_data['data']['server']
        
        # 2. تحميل ورفع الملف
        with requests.get(file_url, stream=True) as r:
            r.raise_for_status()
            
            # GoFile يتطلب Multipart Upload، وهذا معقد قليلاً مع Stream مباشر
            # لكن سنحاول رفعه كملف
            upload_url = f"https://{server}.gofile.io/uploadFile"
            files = {'file': (filename, r.raw, r.headers.get('content-type', 'application/octet-stream'))}
            
            response = requests.post(upload_url, files=files)
            resp_json = response.json()
            
            if resp_json['status'] == 'ok':
                return True, resp_json['data']['downloadPage']
            else:
                return False, "GoFile Upload Failed"
                
    except Exception as e:
        return False, str(e)

# --- معالجة رسائل التليجرام ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً بك!\n"
        "أرسل لي رابط تحميل مباشر (Direct Link)، وسأقوم برفعه لك على Pixeldrain.\n"
        "إذا فشل، سأرفعه على GoFile تلقائياً."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ الرجاء إرسال رابط صالح يبدأ بـ http أو https.")
        return

    await update.message.reply_text("⏳ **جارٍ المعالجة...**\nيتم سحب الملف ورفعه (بدون استهلاك باقتك).", parse_mode='Markdown')

    filename = get_filename_from_url(url)
    
    # المحاولة الأولى: Pixeldrain
    success, link = upload_to_pixeldrain(url, filename)
    
    if success:
        await update.message.reply_text(
            f"✅ **تم الرفع بنجاح على Pixeldrain!**\n\n"
            f"📂 اسم الملف: `{filename}`\n"
            f"🔗 الرابط: {link}",
            parse_mode='Markdown'
        )
    else:
        # المحاولة الثانية: GoFile
        await update.message.reply_text(f"⚠️ فشل Pixeldrain، جاري المحاولة على GoFile...\nالسبب: {link}")
        
        success_go, link_go = upload_to_gofile(url, filename)
        
        if success_go:
            await update.message.reply_text(
                f"✅ **تم الرفع بنجاح على GoFile!**\n\n"
                f"📂 اسم الملف: `{filename}`\n"
                f"🔗 الرابط: {link_go}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ فشل الرفع على كلا الموقعين.\nخطأ GoFile: {link_go}")

# --- تشغيل البوت ---
if __name__ == '__main__':
    # تشغيل سيرفر Flask في خيط منفصل (Background Thread)
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # تشغيل البوت
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN not found!")
    else:
        application = ApplicationBuilder().token(TOKEN).build()
        
        start_handler = CommandHandler('start', start)
        message_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
        
        application.add_handler(start_handler)
        application.add_handler(message_handler)
        
        # Run polling (blokcing)
        application.run_polling()
