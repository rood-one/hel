# Telegram Video to GoFile Bot

هذا البوت يقوم بمراقبة قناة تلجرام معينة، وعند تحويل أو إرسال فيديو إليها، يقوم بتحميله ورفعه تلقائياً إلى موقع GoFile ثم يرسل رابط التحميل.

## المميزات
- متوافق مع استضافة **Render** المجانية.
- استهلاك منخفض جداً للذاكرة (RAM) بفضل استخدام الـ Streaming.
- حذف تلقائي للملفات بعد الرفع لتوفير مساحة القرص.

## الإعدادات
يجب عليك ضبط المتغيرات التالية في ملف `main.py` أو كمتغيرات بيئية:
1. `API_ID`: احصل عليه من [my.telegram.org](https://my.telegram.org).
2. `API_HASH`: احصل عليه من [my.telegram.org](https://my.telegram.org).
3. `BOT_TOKEN`: من [@BotFather](https://t.me/BotFather).
4. `TARGET_CHANNEL`: معرف القناة (مثلاً `@mychannel`).

## التشغيل على Render
1. ارفع الكود إلى مستودع GitHub الخاص بك.
2. أنشئ "Web Service" أو "Worker" جديد في Render.
3. اختر المستودع الخاص بك.
4. استخدم الأمر `python main.py` للتشغيل.
