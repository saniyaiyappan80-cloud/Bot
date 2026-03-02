import logging
import asyncio
import aiohttp
import aiosqlite
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes
)

# ==========================================
# ⚙️ الإعدادات الأساسية
# ==========================================
BOT_TOKEN = "2017218286:AAGh_0CO3bOyOJ-UkPDGJvITYwguA25icw4"
ADMIN_ID = 1148510962
ADMIN_USER = "@M1000j"
INSTA_FOLLOW_LINK = "https://instagram.com/user98eh70s2"
DB_FILE = "bot_database_v3.db"

logging.basicConfig(level=logging.INFO)

# ==========================================
# 🗄️ إدارة قاعدة البيانات
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, username TEXT, name TEXT, 
                  attempts INTEGER DEFAULT 0, last_use TEXT, is_vip INTEGER DEFAULT 0, state TEXT)''')
        await db.execute('CREATE TABLE IF NOT EXISTS hidden (target TEXT PRIMARY KEY)')
        await db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        # إضافة مفتاح API افتراضي إذا لم يوجد
        await db.execute('INSERT OR IGNORE INTO settings VALUES ("api_key", "fc2b9d4e-1618-4483-b9f7-309011e57713")')
        await db.commit()

async def db_exec(query, params=(), fetch=None):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(query, params)
        if fetch == "one": return await cursor.fetchone()
        if fetch == "all": return await cursor.fetchall()
        await db.commit()
        return None

# ==========================================
# 🔍 محرك البحث (HasData API)
# ==========================================
async def get_comments(target):
    # التحقق من الإخفاء
    is_hidden = await db_exec("SELECT 1 FROM hidden WHERE target = ?", (target.lower(),), fetch="one")
    if is_hidden: return "HIDDEN"

    api_key_data = await db_exec("SELECT value FROM settings WHERE key = 'api_key'", fetch="one")
    api_key = api_key_data[0] if api_key_data else ""

    url = "https://api.hasdata.com/scrape/google/serp"
    query = f'site:instagram.com "{target}"'
    params = {'q': query, 'num': 100, 'deviceType': 'mobile'}
    headers = {'x-api-key': api_key}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, params=params, timeout=35) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw = data.get('organicResults', []) + data.get('videoResults', [])
                    results = []
                    for item in raw:
                        link = item.get('link', '').split('?')[0].rstrip('/')
                        if "/p/" in link or "/reel/" in link:
                            snippet = item.get('snippet', '').replace("...", "").strip()
                            results.append({"text": snippet, "link": link})
                    return results
                elif resp.status == 401: return "KEY_EXPIRED"
                return []
        except: return []

# ==========================================
# 🤖 التعامل مع التدفق (Flow)
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # إشعار الأدمن بدخول شخص جديد
    is_new = await db_exec("SELECT 1 FROM users WHERE user_id = ?", (user.id,), fetch="one")
    if not is_new:
        await db_exec("INSERT INTO users (user_id, username, name, state) VALUES (?, ?, ?, ?)", 
                      (user.id, user.username, user.full_name, "START"))
        await context.bot.send_message(ADMIN_ID, f"🔔 <b>دخول مستخدم جديد:</b>\nالاسم: {user.full_name}\nاليوزر: @{user.username}\nالآيدي: <code>{user.id}</code>", parse_mode="HTML")

    msg = "⚠️ <b>تنبيه هام:</b>\nهذا البوت مخصص للاستخدام التعليمي والبحث العلني فقط. أنت المسؤول عن سوء استخدام البيانات."
    kb = [[InlineKeyboardButton("✅ موافق وأتعهد", callback_data="flow_agree")]]
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data == "flow_agree":
        msg = "🚀 <b>خطوة أخيرة:</b>\nلاستخدام البوت، يجب متابعة حساب صاحب البوت أولاً."
        kb = [[InlineKeyboardButton("📸 اضغط هنا لمتابعتي", url=INSTA_FOLLOW_LINK)],
              [InlineKeyboardButton("✅ تم المتابعة", callback_data="flow_followed")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif data == "flow_followed":
        u = await db_exec("SELECT is_vip FROM users WHERE user_id = ?", (user_id,), fetch="one")
        limit = 30 if u and u[0] else 3
        msg = f"✅ <b>تم التحقق!</b>\nلديك {limit} محاولات بحث يومية مجانية.\n\n(يتم تصفير المحاولات كل 24 ساعة)"
        kb = [[InlineKeyboardButton("🚀 ابدأ البحث الآن", callback_data="flow_start_search")]]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

    elif data == "flow_start_search":
        await query.edit_message_text("📝 <b>أرسل الآن يوزر الشخص المطلوب بدون @:</b>", parse_mode="HTML")
        await db_exec("UPDATE users SET state = 'WAITING_USER' WHERE user_id = ?", (user_id,))

    # أوامر الأدمن (التحكم)
    elif data.startswith("adm_"):
        if user_id != ADMIN_ID: return
        action = data.split("_")[1]
        if action == "setkey": await query.message.reply_text("أرسل مفتاح API HasData الجديد:")
        elif action == "hide": await query.message.reply_text("أرسل اليوزر الذي تريد إخفاءه:")
        elif action == "vip": await query.message.reply_text("أرسل آيدي الشخص لتفعيله VIP:")
        elif action == "unvip": await query.message.reply_text("أرسل آيدي الشخص لإزالة VIP:")
        elif action == "bc": await query.message.reply_text("أرسل الرسالة التي تريد إذاعتها:")
        context.user_data['adm_action'] = action

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # معالجة أوامر الأدمن
    if user_id == ADMIN_ID and 'adm_action' in context.user_data:
        action = context.user_data.pop('adm_action')
        if action == "setkey":
            await db_exec("UPDATE settings SET value = ? WHERE key = 'api_key'", (text,))
            await update.message.reply_text("✅ تم تحديث مفتاح API بنجاح.")
        elif action == "hide":
            await db_exec("INSERT OR IGNORE INTO hidden VALUES (?)", (text.lower().replace("@",""),))
            await update.message.reply_text(f"✅ تم إخفاء اليوزر {text} بنجاح.")
        elif action == "vip":
            await db_exec("UPDATE users SET is_vip = 1 WHERE user_id = ?", (text,))
            await update.message.reply_text(f"✅ تم تفعيل VIP للآيدي {text}.")
        elif action == "unvip":
            await db_exec("UPDATE users SET is_vip = 0 WHERE user_id = ?", (text,))
            await update.message.reply_text(f"✅ تم إلغاء VIP للآيدي {text}.")
        elif action == "bc":
            users = await db_exec("SELECT user_id FROM users", fetch="all")
            for u in users:
                try: await context.bot.send_message(u[0], f"📢 <b>إعلان من الإدارة:</b>\n\n{text}", parse_mode="HTML")
                except: pass
            await update.message.reply_text("✅ تمت الإذاعة.")
        return

    # معالجة البحث للمستخدمين
    u_state = await db_exec("SELECT state, attempts, last_use, is_vip FROM users WHERE user_id = ?", (user_id,), fetch="one")
    if u_state and u_state[0] == 'WAITING_USER':
        target = text.lower().replace("@", "")
        att, last, is_vip = u_state[1], u_state[2], u_state[3]
        limit = 30 if is_vip else 3
        now = datetime.now()

        # التصفير اليومي
        if last and datetime.strptime(last, '%Y-%m-%d %H:%M:%S') + timedelta(days=1) < now:
            att = 0

        if att >= limit:
            return await update.message.reply_text(f"❌ انتهت محاولاتك اليومية ({limit}).\nتواصل مع {ADMIN_USER} لزيادة المحاولات.")

        loading = await update.message.reply_text(f"⏳ <b>جاري البحث عن تعليقات {target}...</b>", parse_mode="HTML")
        
        results = await get_comments(target)

        if results == "HIDDEN":
            await loading.edit_text(f"🚫 تم إخفاء هذا اليوزر عبر الإدارة.\nلإخفاء يوزرك تواصل مع: {ADMIN_USER}")
        elif results == "KEY_EXPIRED":
            await loading.edit_text("⚠️ عذراً، انتهت صلاحية مفتاح البحث. تم إخطار الأدمن.")
            await context.bot.send_message(ADMIN_ID, "🚨 <b>تنبيه:</b> مفتاح HasData API انتهى أو غير صالح!")
        elif results:
            await loading.delete()
            for i, res in enumerate(results[:10], 1): # عرض أول 10 نتائج
                msg = f"💬 <b>التعليق {i}:</b>\n{res['text']}\n\n🔗 <b>رابط المنشور:</b> {res['link']}\n\n"
                msg += f"👨‍💻 المطور: {ADMIN_USER}"
                await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
            await db_exec("UPDATE users SET attempts = ?, last_use = ? WHERE user_id = ?", (att+1, now.strftime('%Y-%m-%d %H:%M:%S'), user_id))
        else:
            await loading.edit_text("❌ لم يتم العثور على نتائج عامة لهذا اليوزر.")

# ==========================================
# 🛠️ لوحة الأدمن
# ==========================================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    kb = [
        [InlineKeyboardButton("🔑 تحديث API Key", callback_data="adm_setkey")],
        [InlineKeyboardButton("🛡️ إخفاء يوزر", callback_data="adm_hide")],
        [InlineKeyboardButton("🌟 تفعيل VIP", callback_data="adm_vip"), InlineKeyboardButton("❌ إلغاء VIP", callback_data="adm_unvip")],
        [InlineKeyboardButton("📢 إذاعة جماعية", callback_data="adm_bc")]
    ]
    await update.message.reply_text("📊 <b>لوحة تحكم المدير:</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

# ==========================================
# 🚀 الإطلاق
# ==========================================
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('admin', admin_panel))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    print("🚀 البوت الاحترافي يعمل الآن...")
    app.run_polling()
      
