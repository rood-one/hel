import os
import logging
import requests
import threading
import tempfile
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import TelegramError
from urllib.parse import urlparse

# --- إعدادات البوت ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN غير موجود في متغيرات البيئة!")

# --- إعدادات Flask (لإبقاء السيرفر يعمل على Render) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!"

def run_flask():
    """تشغيل Flask في خيط منفصل"""
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False, threaded=True)

# --- إعداد التسجيل للأخطاء ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- دوال مساعدة لاستخراج اسم الملف ---
def get_filename_from_url(url):
    """استخراج اسم الملف من الرابط"""
    try:
        parsed_url = urlparse(url)
        path = parsed_url.path
        if path:
            filename = path.split('/')[-1]
            if filename and '.' in filename:
                return filename
        
        # إذا لم نجد اسم ملف، نستخدم اسمًا افتراضيًا
        return "downloaded_file.bin"
    except Exception as e:
        logger.error(f"خطأ في استخراج اسم الملف: {e}")
        return "unknown_file.bin"

def is_valid_url(url):
    """التحقق من صحة الرابط"""
    try:
        parsed = urlparse(url)
        return all([parsed.scheme in ['http', 'https'], parsed.netloc])
    except:
        return False

# --- دالة الرفع على Pixeldrain ---
def upload_to_pixeldrain(file_url, filename):
    """رفع الملف على Pixeldrain"""
    try:
        # إضافة user-agent لتجنب الحجب
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # تحميل الملف مع stream
        with requests.get(file_url, stream=True, headers=headers, timeout=30) as r:
            r.raise_for_status()
            
            # إنشاء ملف مؤقت
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                
                tmp_file_path = tmp_file.name
            
            # رفع الملف إلى Pixeldrain
            with open(tmp_file_path, 'rb') as f:
                response = requests.put(
                    f"https://pixeldrain.com/api/file/{filename}",
                    data=f,
                    auth=('', ''),  # مصادقة فارغة
                    headers={'User-Agent': 'Telegram-Bot'},
                    timeout=60
                )
            
            # تنظيف الملف المؤقت
            os.unlink(tmp_file_path)
            
            if response.status_code in [200, 201]:
                data = response.json()
                file_id = data.get('id')
                return True, f"https://pixeldrain.com/u/{file_id}"
            else:
                return False, f"خطأ Pixeldrain: {response.status_code}"
                
    except requests.exceptions.RequestException as e:
        return False, f"خطأ في الاتصال: {str(e)}"
    except Exception as e:
        logger.error(f"خطأ غير متوقع في Pixeldrain: {e}")
        return False, f"خطأ داخلي: {str(e)}"

# --- دالة الرفع على GoFile (الخيار البديل) ---
def upload_to_gofile(file_url, filename):
    """رفع الملف على GoFile"""
    try:
        # 1. الحصول على أفضل سيرفر
        server_req = requests.get("https://api.gofile.io/getServer", timeout=10)
        server_data = server_req.json()
        
        if server_data.get('status') != 'ok':
            return False, "تعذر الحصول على خادم GoFile"
            
        server = server_data['data']['server']
        
        # 2. تحميل الملف إلى ملف مؤقت
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(file_url, stream=True, headers=headers, timeout=30) as r:
            r.raise_for_status()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='_'+filename) as tmp_file:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                tmp_file_path = tmp_file.name
        
        # 3. رفع الملف إلى GoFile
        upload_url = f"https://{server}.gofile.io/uploadFile"
        
        with open(tmp_file_path, 'rb') as f:
            files = {'file': (filename, f)}
            response = requests.post(upload_url, files=files, timeout=60)
        
        # تنظيف الملف المؤقت
        os.unlink(tmp_file_path)
        
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get('status') == 'ok':
                return True, resp_json['data']['downloadPage']
            else:
                return False, "فشل رفع GoFile"
        else:
            return False, f"خطأ GoFile: {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        return False, f"خطأ في الاتصال: {str(e)}"
    except Exception as e:
        logger.error(f"خطأ غير متوقع في GoFile: {e}")
        return False, f"خطأ داخلي: {str(e)}"

# --- معالجة رسائل التليجرام ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أمر /start"""
    welcome_text = """
👋 **أهلاً بك في بوت رفع الملفات!**

📤 **كيفية الاستخدام:**
1. أرسل لي رابط تحميل مباشر (Direct Link)
2. سأقوم برفعه لك على Pixeldrain
3. إذا فشل، سأرفعه على GoFile تلقائياً

⚡ **مميزات البوت:**
- رفع الملفات الكبيرة دون استهلاك باقتك
- دعم جميع أنواع الملفات
- روابط دائمة

🔗 **مثال:**
`https://example.com/file.zip`

🚀 ابدأ الآن بإرسال رابط!
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الروابط المرسلة"""
    url = update.message.text.strip()
    
    if not is_valid_url(url):
        await update.message.reply_text(
            "❌ **رابط غير صالح!**\n"
            "الرجاء إرسال رابط يبدأ بـ http:// أو https://",
            parse_mode='Markdown'
        )
        return
    
    # إعلام المستخدم ببدء المعالجة
    status_msg = await update.message.reply_text(
        "⏳ **جارٍ معالجة طلبك...**\n"
        "1️⃣ جاري سحب الملف من الرابط\n"
        "2️⃣ سيتم رفعه على Pixeldrain",
        parse_mode='Markdown'
    )
    
    filename = get_filename_from_url(url)
    
    # المحاولة الأولى: Pixeldrain
    await status_msg.edit_text(
        "⏳ **جارٍ معالجة طلبك...**\n"
        "✅ تم سحب الملف بنجاح\n"
        "⬆️ جاري الرفع على Pixeldrain...",
        parse_mode='Markdown'
    )
    
    success, link = upload_to_pixeldrain(url, filename)
    
    if success:
        await status_msg.edit_text(
            f"✅ **تم الرفع بنجاح على Pixeldrain!**\n\n"
            f"📂 **اسم الملف:** `{filename}`\n"
            f"🔗 **الرابط:** {link}\n"
            f"📊 **المشاركة:** شارك الرابط مع أصدقائك!",
            parse_mode='Markdown'
        )
    else:
        # المحاولة الثانية: GoFile
        await status_msg.edit_text(
            "⏳ **جارٍ معالجة طلبك...**\n"
            "⚠️ فشل Pixeldrain\n"
            "🔄 جاري المحاولة على GoFile...",
            parse_mode='Markdown'
        )
        
        success_go, link_go = upload_to_gofile(url, filename)
        
        if success_go:
            await status_msg.edit_text(
                f"✅ **تم الرفع بنجاح على GoFile!**\n\n"
                f"📂 **اسم الملف:** `{filename}`\n"
                f"🔗 **الرابط:** {link_go}\n"
                f"📊 **المشاركة:** شارك الرابط مع أصدقائك!",
                parse_mode='Markdown'
            )
        else:
            await status_msg.edit_text(
                f"❌ **فشل الرفع على كلا الموقعين**\n\n"
                f"**تفاصيل الخطأ:**\n"
                f"• Pixeldrain: {link}\n"
                f"• GoFile: {link_go}\n\n"
                f"⚠️ **تلميحات:**\n"
                f"1. تأكد من صحة الرابط\n"
                f"2. حاول برابط ملف أصغر\n"
                f"3. جرب رابطًا آخر",
                parse_mode='Markdown'
            )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأخطاء العامة"""
    logger.error(f"حدث خطأ: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى لاحقاً."
            )
        except:
            pass

# --- تشغيل البوت ---
def main():
    """الدالة الرئيسية لتشغيل البوت"""
    # تشغيل Flask في خيط منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("🚀 بدء تشغيل بوت التليجرام...")
    
    # إنشاء تطبيق البوت
    application = ApplicationBuilder() \
        .token(TOKEN) \
        .connect_timeout(30) \
        .read_timeout(30) \
        .write_timeout(30) \
        .build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # إضافة معالج الأخطاء
    application.add_error_handler(error_handler)
    
    # تشغيل البوت
    logger.info("🤖 البوت يعمل الآن...")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=20,
        poll_interval=0.5
    )

if __name__ == '__main__':
    main()