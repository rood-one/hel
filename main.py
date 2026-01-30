import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8520726911:AAGVdtBEtNDrD8cdjldPfmtMjSXDzyqJ4ls"
TARGET_CHANNEL = "@uplovid"

# رفع ملف إلى GoFile
def upload_to_gofile(file_path):
    server = requests.get("https://api.gofile.io/servers").json()["data"]["servers"][0]["name"]

    url = f"https://{server}.gofile.io/uploadFile"
    with open(file_path, "rb") as f:
        response = requests.post(url, files={"file": f}).json()

    return response["data"]["downloadPage"]

# استقبال الفيديو من القناة
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.channel_post
    if message.chat.username != TARGET_CHANNEL.replace("@",""):
        return

    file = await message.video.get_file()
    file_path = f"{message.video.file_unique_id}.mp4"
    await file.download_to_drive(file_path)

    link = upload_to_gofile(file_path)

    print("Uploaded:", link)

# تشغيل البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.CHANNEL, handle_video))

print("Bot running...")
app.run_polling()