import os
import time
import asyncio
import base64
import json
import re
import secrets
import aiohttp
import aiohttp.web
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ── RENDER HEALTHCHECK SERVER (PORT BINDING) ─────────────────────────────────
async def health_check(request):
    return aiohttp.web.Response(text="Bot is ALIVE and RUNNING 24/7!")

async def start_web_server():
    app = aiohttp.web.Application()
    app.router.add_get('/', health_check)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = aiohttp.web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 HTTP Port {port} successfully bound for Render & UptimeRobot.")

# ── BOT CONFIG ───────────────────────────────────────────────────────────────
BOT_TOKEN = "8918993850:AAG-svWDI3GFH1b0cDuozIH-UHlvvgj1QWY"

SMS_OTP_URL = "https://profile.swiggy.com/api/v3/app/sms_otp"
VERIFY_URL = "https://profile.swiggy.com/api/v3/app/login/verify"
SPNS_BASE_URL = "https://spns.swiggy.com"
CREATE_OFFERS_PATH = "/api/v1/proximity-offer/create-offers"
DISCOVER_USERS_PATH = "/api/v1/proximity-offer/discover-users"

DEFAULT_CAMPAIGN_ID = "ydiHi75"
TARGET_SUCCESS_COUNT = 12

SWIGGY_APP_HEADERS = {
    "user-agent": "Swiggy-Android",
    "content-type": "application/json; charset=utf-8",
    "accept": "application/json; charset=utf-8",
    "version-code": "1795",
    "app-version": "4.113.0",
    "manufacturer": "MOTOROLA",
    "model-name": "MOTO G(60)",
}

ALL_AREAS = [
    ("Delhi - Connaught Place", 28.6315, 77.2167),
    ("Delhi - Saket", 28.5245, 77.2066),
    ("Delhi - Hauz Khas", 28.5433, 77.2066),
    ("Delhi - Karol Bagh", 28.6519, 77.1909),
    ("Bengaluru - Koramangala", 12.9352, 77.6245),
    ("Bengaluru - Indiranagar", 12.9784, 77.6408),
    ("Mumbai - Bandra West", 19.0596, 72.8295),
    ("Mumbai - Andheri West", 19.1363, 72.8277),
    ("Pune - Hinjewadi", 18.5912, 73.7389),
    ("Hyderabad - Hitec City", 17.4435, 78.3772),
    ("Chennai - T Nagar", 13.0418, 80.2341),
    ("Kolkata - Park Street", 22.5526, 88.3539),
    ("Ahmedabad - SG Highway", 23.0225, 72.5714),
]

# ── SAVED ACCOUNTS SYSTEM ────────────────────────────────────────────────────
ACCOUNTS_FILE = "saved_accounts.json"

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {}

def save_accounts(data):
    try:
        with open(ACCOUNTS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except: pass

def add_saved_account(chat_id, session_data):
    chat_id = str(chat_id)
    accounts = load_accounts()
    if chat_id not in accounts:
        accounts[chat_id] = []
    accounts[chat_id] = [acc for acc in accounts[chat_id] if str(acc.get("userid")) != str(session_data.get("userid"))]
    accounts[chat_id].append(session_data)
    save_accounts(accounts)

def remove_saved_account(chat_id, userid):
    chat_id = str(chat_id)
    accounts = load_accounts()
    if chat_id in accounts:
        initial_len = len(accounts[chat_id])
        accounts[chat_id] = [acc for acc in accounts[chat_id] if str(acc.get("userid")) != str(userid)]
        if len(accounts[chat_id]) < initial_len:
            save_accounts(accounts)
            return True
    return False

async def validate_session(session_data: dict) -> bool:
    headers = build_spns_headers(session_data)
    payload = {
        "location": {"latitude": 28.6315, "longitude": 77.2167},
        "tid": str(session_data.get("tid", "")),
        "campaignId": DEFAULT_CAMPAIGN_ID,
        "userId": str(session_data.get("userid", "")),
        "isFreshLocation": True,
    }
    try:
        async with aiohttp.ClientSession() as client:
            async with client.post(SPNS_BASE_URL + DISCOVER_USERS_PATH, headers=headers, json=payload, timeout=5) as resp:
                if resp.status in (401, 403):
                    return False
                data = await resp.json(content_type=None)
                if isinstance(data, dict):
                    msg = str(data.get("statusMessage", "")).lower()
                    if "unauthorized" in msg or "token invalid" in msg:
                        return False
    except: pass
    return True

# ── HELPER FUNCTIONS ─────────────────────────────────────────────────────────
def get_random_device_id():
    return secrets.token_hex(8)

def _decode_tid_payload(tid: str) -> dict:
    try:
        parts = tid.split(".")
        if len(parts) < 2: return {}
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except: return {}

def _userid_from_tid(tid: str):
    return str(_decode_tid_payload(tid).get("user_id") or "")

def _parse_amount(value) -> float:
    if isinstance(value, dict): value = value.get("units", value.get("amount", 0))
    try: return float(value)
    except: return 0.0

def build_spns_headers(session_data: dict) -> dict:
    return {
        "Content-Type": "application/json",
        "user-agent": SWIGGY_APP_HEADERS["user-agent"],
        "platform": "Swiggy-Android",
        "versionCode": SWIGGY_APP_HEADERS["version-code"],
        "tid": str(session_data.get("tid", "")),
        "token": str(session_data.get("token", "")),
        "userId": str(session_data.get("userid", "")),
    }

def parse_session_string(raw: str) -> dict:
    cleaned = re.sub(r"^```[a-zA-Z]*\n?|```\s*$", "", raw.strip()).strip()
    session = {}
    try:
        data = json.loads(cleaned)
        sources = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
        if isinstance(data, dict) and isinstance(data.get("data"), dict): sources.append(data.get("data"))
        
        for src in sources:
            if isinstance(src, dict):
                for k in ("token", "tid", "sid", "userid", "phone"):
                    if k in src and k not in session: session[k] = src[k]
                if "token" not in session and src.get("access_token"): session["token"] = src["access_token"]
            elif isinstance(src, list):
                for header in src:
                    if isinstance(header, dict) and str(header.get("name", "")).lower() in ("token", "tid", "sid", "userid", "phone"):
                        session[str(header.get("name", "")).lower()] = header.get("value", "")
    except: pass

    if not session:
        for key in ("token", "tid", "sid", "userid", "phone"):
            m = re.search(r'["\']?' + key + r'["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', cleaned, re.IGNORECASE)
            if m: session[key] = m.group(1)

    if not session.get("token") and not session.get("tid"):
        raise ValueError("Invalid Session: Token ya TID nahi mila.")
    session["userid"] = str(session.get("userid") or _userid_from_tid(session.get("tid", "")))
    return session

def get_cancel_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop / Cancel", callback_data="cancel_current_task")]])

# ── FEATURE 1: DISCOVER & LOOT ───────────────────────────────────────────────
async def discover_live_users(session_data: dict, lat: float, lng: float, client: aiohttp.ClientSession, seen: list):
    payload = {"location": {"latitude": lat, "longitude": lng}, "tid": str(session_data.get("tid", "")), "previousNearbyUserIds": seen or [], "campaignId": DEFAULT_CAMPAIGN_ID, "userId": str(session_data.get("userid", "")), "isFreshLocation": True}
    try:
        async with client.post(SPNS_BASE_URL + DISCOVER_USERS_PATH, headers=build_spns_headers(session_data), json=payload, timeout=6) as resp:
            data = await resp.json(content_type=None)
            users = (data.get("data") or {}).get("nearbyUsers", [])
            return [u for u in users if isinstance(u, dict)], None
    except Exception as e: return [], str(e)

async def invite_live_user(session_data: dict, user: dict, lat: float, lng: float, client: aiohttp.ClientSession):
    payload = {"campaignId": DEFAULT_CAMPAIGN_ID, "senderUserId": str(session_data.get("userid", "")), "senderLocation": {"latitude": lat, "longitude": lng}, "receivers": [{"userId": str(user.get("userId") or ""), "userName": str(user.get("userName") or "")}]}
    try:
        async with client.post(SPNS_BASE_URL + CREATE_OFFERS_PATH, headers=build_spns_headers(session_data), json=payload, timeout=6) as resp:
            data = await resp.json(content_type=None)
            for res in ((data.get("data") or {}).get("receiverResults") or []):
                for bl, offer in (res.get("offersByBL") or {}).items():
                    if str(offer.get("status") or "") == "SUCCESS":
                        return True, f"Rs.{_parse_amount(offer.get('offerValue')):.0f} ({bl})"
                    elif str(offer.get("status") or "") == "FAILURE":
                        return False, offer.get("errorCode") or "Server rejected"
            return False, data.get("statusMessage") or "Offer limit or inactive"
    except Exception as e: return False, str(e)

async def run_10_live_users_loot(session_data: dict, status_msg, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["is_running"], context.user_data["cancel_requested"] = True, False
    joined_count, fail_count, tried_ids, summary_lines = 0, 0, set(), []
    area_scores = {area[0]: 10.0 for area in ALL_AREAS}
    active_areas = list(ALL_AREAS)

    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as client:
            while joined_count < TARGET_SUCCESS_COUNT:
                if context.user_data.get("cancel_requested"): break
                active_areas.sort(key=lambda a: area_scores.get(a[0], 0), reverse=True)
                
                for i in range(0, len(active_areas), 5):
                    if joined_count >= TARGET_SUCCESS_COUNT or context.user_data.get("cancel_requested"): break
                    batch = active_areas[i:i+5]
                    
                    try: await status_msg.edit_text(f"✦ *Loot Engine Running* ✦\n\n📍 *Scanning:* `{batch[0][0]}...`\n✅ *Successful:* `{joined_count}/{TARGET_SUCCESS_COUNT}`\n❌ *Bypassed:* `{fail_count}`\n📡 *Scanned:* `{len(tried_ids)}`", reply_markup=get_cancel_button(), parse_mode="Markdown")
                    except: pass

                    tasks = [discover_live_users(session_data, lat, lng, client, list(tried_ids)) for _, lat, lng in batch]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for (city, lat, lng), res in zip(batch, results):
                        if joined_count >= TARGET_SUCCESS_COUNT or context.user_data.get("cancel_requested"): break
                        if isinstance(res, Exception) or not res[0]: continue

                        new_users = [u for u in res[0] if str(u.get("userId", "")) not in tried_ids]
                        for u in new_users:
                            if joined_count >= TARGET_SUCCESS_COUNT or context.user_data.get("cancel_requested"): break
                            uid, name = str(u.get("userId") or ""), str(u.get("userName") or "Swiggy User")
                            tried_ids.add(uid)

                            if (u.get("status") or {}).get("isAssociated"): fail_count += 1; continue

                            ok, note = await invite_live_user(session_data, u, lat, lng, client)
                            if ok: joined_count += 1; summary_lines.append(f"✅ `{name}`: Won {note}"); area_scores[city] += 10.0
                            else: fail_count += 1; summary_lines.append(f"❌ `{name}`: {note}")

                            if "limit" in note.lower() or "exhausted" in note.lower(): await asyncio.sleep(5)
                            await asyncio.sleep(0.1)
                await asyncio.sleep(2)
    except Exception as e: summary_lines.append(f"⚠️ Error: {str(e)}")
    finally: context.user_data["is_running"] = False

    final_msg = "🛑 *Operation Aborted*\n\n" if context.user_data.get("cancel_requested") else "🏆 *Loot Completed!*\n\n"
    final_msg += "\n".join(summary_lines[:15]) + f"\n\n✅ *Total Successful:* `{joined_count}/{TARGET_SUCCESS_COUNT}`\n✧ *crafted by shivansh* ✧"
    try: await status_msg.edit_text(final_msg, parse_mode="Markdown")
    except: pass


# ── TELEGRAM HANDLERS ────────────────────────────────────────────────────────
def get_main_reply_keyboard():
    return ReplyKeyboardMarkup([["⚡ Free Cash Loot (12 Users)"], ["📱 Authentication", "📁 Saved Accounts"]], resize_keyboard=True)

def show_login_choice_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Request OTP", callback_data="login_phone_opt")],
        [InlineKeyboardButton("⚙️ Inject JSON", callback_data="login_json_opt")],
        [InlineKeyboardButton("💾 Saved Accounts", callback_data="login_saved_opt")]
    ])

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "✦ *SWIGGY TURBO LOOT* ✦\n✧ *crafted by shivansh* ✧\n━━━━━━━━━━━━━━━━━━━━\n\nPlease select an option:"
    await (update.message or update.callback_query.message).reply_text(msg, reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("swiggy_session")
    chat_id = str(update.effective_chat.id)

    if query.data == "cancel_current_task":
        if context.user_data.get("is_running"): context.user_data["cancel_requested"] = True
        return

    if query.data == "login_saved_opt":
        accounts = load_accounts().get(chat_id, [])
        if not accounts: return await query.message.reply_text("⚠️ No saved accounts found.")
        kb = [[InlineKeyboardButton(f"👤 {acc.get('phone', acc.get('userid'))}", callback_data=f"use_acc_{acc.get('userid')}")] for acc in accounts]
        return await query.message.reply_text("💾 *Select a Saved Account:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    if query.data.startswith("use_acc_"):
        uid = query.data.replace("use_acc_", "")
        acc = next((a for a in load_accounts().get(chat_id, []) if str(a.get("userid")) == uid), None)
        if not acc: return await query.message.reply_text("❌ Account not found.")
        status_msg = await query.message.reply_text("🔄 Validating account...")
        if not await validate_session(acc):
            remove_saved_account(chat_id, uid)
            return await status_msg.edit_text("❌ *Account Expired!* Removed from saved list.", parse_mode="Markdown")
        context.user_data["swiggy_session"] = acc
        await status_msg.edit_text(f"🔓 *Login Successful!*\n👤 *User ID:* `{uid}`", parse_mode="Markdown")
        return

    if query.data == "login_phone_opt":
        context.user_data["state"] = "awaiting_phone"
        await query.message.reply_text("📱 Enter 10-digit registered number:")
    elif query.data == "login_json_opt":
        context.user_data["state"] = "awaiting_json"
        await query.message.reply_text("⚙️ Paste your Swiggy session JSON block:")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")
    session = context.user_data.get("swiggy_session")
    chat_id = str(update.effective_chat.id)

    if text == "📁 Saved Accounts":
        accounts = load_accounts().get(chat_id, [])
        if not accounts: return await update.message.reply_text("⚠️ No saved accounts found.")
        kb = [[InlineKeyboardButton(f"👤 {a.get('phone', a.get('userid'))}", callback_data=f"use_acc_{a.get('userid')}")] for a in accounts]
        return await update.message.reply_text("📁 *Saved Accounts:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    if text == "⚡ Free Cash Loot (12 Users)":
        if not session: return await update.message.reply_text("🔒 *Login Required*", reply_markup=show_login_choice_markup(), parse_mode="Markdown")
        if context.user_data.get("is_running"): return await update.message.reply_text("⚠️ Operation already running.")
        status = await update.message.reply_text("⚡ Starting Engine...", reply_markup=get_cancel_button())
        asyncio.create_task(run_10_live_users_loot(session, status, context))
        return

    if text == "📱 Authentication":
        return await update.message.reply_text("🔐 Login method:", reply_markup=show_login_choice_markup())

    if (text.startswith("{") and text.endswith("}")) or '"token"' in text or state == "awaiting_json":
        try:
            parsed = parse_session_string(text)
            context.user_data["swiggy_session"] = parsed
            context.user_data.pop("state", None)
            add_saved_account(chat_id, parsed)
            return await update.message.reply_text(f"🔓 *Authentication Successful!*\n👤 *ID:* `{parsed.get('userid')}`", reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")
        except Exception as e: return await update.message.reply_text(f"❌ JSON Error: {str(e)}")

    if state == "awaiting_phone" or (re.fullmatch(r"\d{10}", text) and not context.user_data.get("temp_auth")):
        phone = re.sub(r"\D", "", text)[-10:]
        dev_id = get_random_device_id()
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as client:
            try:
                async with client.get(f"{SMS_OTP_URL}?mobile={phone}", headers={**SWIGGY_APP_HEADERS, "deviceId": dev_id, "swuid": dev_id}) as resp:
                    data = await resp.json()
                    if data.get("statusCode") == 0:
                        context.user_data["temp_auth"] = {"phone": phone, "tid": data.get("tid"), "sid": data.get("sid"), "dev_id": dev_id}
                        context.user_data["state"] = "awaiting_otp"
                        await update.message.reply_text(f"📩 OTP Sent to `+91{phone}`. Enter it below:", parse_mode="Markdown")
                    else: await update.message.reply_text(f"❌ OTP Failed: {data.get('statusMessage')}")
            except Exception as e: await update.message.reply_text(f"❌ Network Error: {str(e)}")
        return

    temp = context.user_data.get("temp_auth")
    if temp and (state == "awaiting_otp" or re.fullmatch(r"\d{4,6}", text)):
        headers = {**SWIGGY_APP_HEADERS, "deviceId": temp["dev_id"], "swuid": temp["dev_id"], "sid": str(temp["sid"]), "Tid": str(temp["tid"])}
        payload = {"cloningSignalsData": {"appFilesDirPathInvalid": 0, "developerModeEnabled": 1, "deviceModelVmos": 0, "emulatorStatus": 0, "packageName": "in.swiggy.android", "workProfileEnabled": 0}, "otp": text.strip()}
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as client:
            try:
                async with client.post(f"{VERIFY_URL}?otp_source=Sms-automatic", headers=headers, json=payload) as resp:
                    data = await resp.json()
                    if data.get("statusCode") == 0:
                        inner = data.get("data") or {}
                        tid, token = data.get("tid") or inner.get("tid"), inner.get("token") or inner.get("accessToken")
                        parsed = {"userid": str(_decode_tid_payload(tid).get("user_id")), "token": token, "tid": tid, "sid": temp["sid"], "phone": temp["phone"]}
                        context.user_data["swiggy_session"] = parsed
                        context.user_data.pop("temp_auth", None); context.user_data.pop("state", None)
                        add_saved_account(chat_id, parsed)
                        await update.message.reply_text(f"🔓 *Login Successful!*\n👤 *ID:* `{parsed['userid']}`", reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")
                    else: await update.message.reply_text(f"❌ Login Failed: {data.get('statusMessage')}")
            except Exception as e: await update.message.reply_text(f"❌ Error: {str(e)}")
        return

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    loop.create_task(start_web_server())
    print("🤖 Swiggy Loot Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
