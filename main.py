try:
    # إنشاء مجلد مؤقت
    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, filename)
        
        # 1. التحميل (تشغيل في Thread منفصل لمنع تجميد البوت)
        await context.bot.edit_message_text("📥 جاري التحميل إلى الخادم...", chat_id, status_msg.message_id)
        loop = asyncio.get_running_loop()
        
        # استخدام run_in_executor لتشغيل الدالة الثقيلة
        file_size_mb = await loop.run_in_executor(None, download_file, url, file_path)
        
        # 2. الرفع إلى Pixeldrain (أيضاً في Thread منفصل)
        await context.bot.edit_message_text("☁️ جاري الرفع إلى Pixeldrain...", chat_id, status_msg.message_id)
        
        download_link = await loop.run_in_executor(None, upload_to_pixeldrain, file_path, filename)
        
        if not download_link:
            raise Exception("فشل الحصول على رابط من Pixeldrain")

        # 3. إرسال النتيجة
        await context.bot.edit_message_text(
            f"✅ **تمت العملية بنجاح!**\n\n"
            f"📄 الاسم: `{filename}`\n"
            f"📦 الحجم: `{file_size_mb:.2f} MB`\n"
            f"🔗 الرابط: {download_link}",
            chat_id,
            status_msg.message_id,
            parse_mode='Markdown'
        )

except Exception as e:
    logger.error(f"Error: {e}")
    await context.bot.edit_message_text(f"❌ حدث خطأ: {str(e)}", chat_id, status_msg.message_id)