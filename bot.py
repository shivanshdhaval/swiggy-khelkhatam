import os
import time
import asyncio
import base64
import json
import re
import secrets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import aiohttp
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

# ── RENDER DUMMY HTTP SERVER (PORT BINDING FOR UPTIMEROBOT) ──────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is ALIVE and RUNNING 24/7!")
        
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()

    def log_message(self, format, *args):
        return  # Suppress console log clutter

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"🌐 HTTP Port {port} successfully bound for Render & UptimeRobot.")
    server.serve_forever()

# ── BOT CONFIG ───────────────────────────────────────────────────────────────
BOT_TOKEN = "8918993850:AAG-svWDI3GFH1b0cDuozIH-UHlvvgj1QWY"

SMS_OTP_URL = "https://profile.swiggy.com/api/v3/app/sms_otp"
VERIFY_URL = "https://profile.swiggy.com/api/v3/app/login/verify"
EVENTS_HOST = "https://events.swiggy.com"
NOTIFY_URL = f"{EVENTS_HOST}/api/notify"
PYO_COUPON_URL = f"{EVENTS_HOST}/api/pick-your-offer-coupon"
BYO_COUPON_URL = f"{EVENTS_HOST}/api/book-your-offer-coupon"
NYO_COUPON_URL = f"{EVENTS_HOST}/api/pick-your-late-night-offer-coupon"
BYO_PAGE_URL = f"{EVENTS_HOST}/book-your-offer?utm_source=app&utm_medium=share"
NYO_PAGE_URL = f"{EVENTS_HOST}/pick-your-late-night-offer"

SPNS_BASE_URL = "https://spns.swiggy.com"
CREATE_OFFERS_PATH = "/api/v1/proximity-offer/create-offers"
DISCOVER_USERS_PATH = "/api/v1/proximity-offer/discover-users"

SWIGGY_LINK_RE = re.compile(
    r"r\.swiggy\.com/(?:cashloot|breakfast|breakfastloot|morningloot|offer|loot)/([A-Za-z0-9_-]+)",
    re.IGNORECASE
)
GENERIC_LINK_RE = re.compile(
    r"r\.swiggy\.com/[a-zA-Z0-9_.-]+/([A-Za-z0-9_]+-[A-Za-z0-9_]+)",
    re.IGNORECASE
)

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

NIGHT_OFFERS = {
    1: {"title": "₹50 FREE Cash", "desc": "On order above ₹199"},
    2: {"title": "₹150 OFF Coupon", "desc": "On order above ₹249"},
    3: {"title": "₹100 OFF + ₹50 Cash", "desc": "On order above ₹249"},
    4: {"title": "₹100 OFF Coupon", "desc": "On order above ₹149"},
}
BREAKFAST_OFFERS = {
    1: {"title": "₹50 FREE Cash", "desc": "On order above ₹199"},
    2: {"title": "₹150 OFF Coupon", "desc": "On order above ₹249"},
    3: {"title": "₹100 OFF + ₹50 Cash", "desc": "On order above ₹249"},
    4: {"title": "₹100 OFF Coupon", "desc": "On order above ₹149"},
}

ALL_AREAS = [
    ("Delhi - Connaught Place", 28.6315, 77.2167),
    ("Delhi - Saket", 28.5245, 77.2066),
    ("Delhi - Karol Bagh", 28.6519, 77.1909),
    ("Delhi - Laxmi Nagar", 28.6300, 77.2430),
    ("Bengaluru - Koramangala", 12.9352, 77.6245),
    ("Bengaluru - Indiranagar", 12.9784, 77.6408),
    ("Mumbai - Bandra West", 19.0596, 72.8295),
    ("Mumbai - Andheri West", 19.1363, 72.8277),
    ("Pune - Hinjewadi", 18.5912, 73.7389),
    ("Hyderabad - Hitec City", 17.4435, 78.3772),
]

def get_random_device_id():
    return secrets.token_hex(8)

def _decode_tid_payload(tid: str) -> dict:
    try:
        parts = tid.split(".")
        if len(parts) < 2: return {}
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except Exception: return {}

def _userid_from_tid(tid: str):
    return str(_decode_tid_payload(tid).get("user_id") or "")

def _parse_amount(value) -> float:
    if isinstance(value, dict): value = value.get("units", value.get("amount", 0))
    try: return float(value)
    except Exception: return 0.0

def build_spns_headers(session_data: dict) -> dict:
    return {
        "Content-Type": "application/json",
        "user-agent": SWIGGY_APP_HEADERS["user-agent"],
        "userAgent": SWIGGY_APP_HEADERS["user-agent"],
        "platform": "Swiggy-Android",
        "versionCode": SWIGGY_APP_HEADERS["version-code"],
        "tid": str(session_data.get("tid", "")),
        "token": str(session_data.get("token", "")),
        "userId": str(session_data.get("userid", "")),
    }

def parse_session_string(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    session = {}
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            sources = [data]
            if isinstance(data.get("data"), dict): sources.append(data["data"])
            for src in sources:
                for k in ("token", "secret_token", "access_token", "tid", "sid", "userid", "customerId", "phone", "mobile"):
                    if k in src and k not in session: session[k] = src[k]
            if "token" not in session:
                for alias in ("secret_token", "access_token"):
                    if session.get(alias): session["token"] = session[alias]; break
        elif isinstance(data, list):
            for header in data:
                n, v = str(header.get("name", "")).lower(), header.get("value", "")
                if n in ("token", "tid", "sid", "userid"): session[n] = v
    except Exception: pass
    if not session:
        for key in ("token", "tid", "sid", "userid"):
            m = re.search(r'["\']?' + key + r'["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', cleaned, re.IGNORECASE)
            if m: session[key] = m.group(1)
    if not session.get("token") and not session.get("tid"): raise ValueError("Invalid Session")
    session["userid"] = str(session.get("userid") or _userid_from_tid(session.get("tid", "")))
    return session

def extract_all_links(text: str):
    tokens = SWIGGY_LINK_RE.findall(text) or GENERIC_LINK_RE.findall(text)
    seen, results = set(), []
    for token in tokens:
        if token.lower() not in seen:
            seen.add(token.lower())
            parts = token.split("-")
            if len(parts) >= 2: results.append((parts[0], parts[1], token))
    return results

def get_cancel_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop / Cancel", callback_data="cancel_current_task")]])

def get_night_options_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍔 ₹50 FREE Cash", callback_data="nyo_opt_1"), InlineKeyboardButton("🍕 ₹150 OFF", callback_data="nyo_opt_2")],
        [InlineKeyboardButton("🍟 ₹100 OFF + ₹50 Cash", callback_data="nyo_opt_3"), InlineKeyboardButton("🥤 ₹100 OFF", callback_data="nyo_opt_4")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_restart")],
    ])

def get_breakfast_options_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 ₹50 FREE Cash", callback_data="byo_opt_1"), InlineKeyboardButton("🏷️ ₹150 OFF", callback_data="byo_opt_2")],
        [InlineKeyboardButton("💰 ₹100 OFF + ₹50 Cash", callback_data="byo_opt_3"), InlineKeyboardButton("🎟️ ₹100 OFF", callback_data="byo_opt_4")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_restart")],
    ])

async def check_account_validity(session_data: dict, client: aiohttp.ClientSession) -> bool:
    try:
        headers = build_spns_headers(session_data)
        payload = {"location": {"latitude": 28.6315, "longitude": 77.2167}, "tid": str(session_data.get("tid", "")), "campaignId": DEFAULT_CAMPAIGN_ID, "userId": str(session_data.get("userid", "")), "isFreshLocation": True}
        async with client.post(SPNS_BASE_URL + DISCOVER_USERS_PATH, headers=headers, json=payload, timeout=5) as resp:
            return resp.status != 401
    except Exception: return True

async def process_account_deletion(context: ContextTypes.DEFAULT_TYPE, uid: str, status_msg=None):
    if "saved_accounts" in context.user_data and uid in context.user_data["saved_accounts"]:
        del context.user_data["saved_accounts"][uid]
    if context.user_data.get("swiggy_session", {}).get("userid") == uid:
        context.user_data.pop("swiggy_session", None)
    if status_msg:
        try: await status_msg.edit_text("❌ *Account Expired / Invalid!*\nRemoved automatically.", parse_mode="Markdown")
        except Exception: pass

async def discover_live_users(session_data: dict, lat: float, lng: float, campaign_id: str, client: aiohttp.ClientSession, seen: list):
    try:
        payload = {"location": {"latitude": lat, "longitude": lng}, "tid": str(session_data.get("tid", "")), "previousNearbyUserIds": seen or [], "campaignId": campaign_id, "userId": str(session_data.get("userid", "")), "isFreshLocation": True}
        async with client.post(SPNS_BASE_URL + DISCOVER_USERS_PATH, headers=build_spns_headers(session_data), json=payload, timeout=6) as resp:
            data = await resp.json(content_type=None)
            users = (data.get("data") or {}).get("nearbyUsers", [])
            return [u for u in users if isinstance(u, dict)], None
    except Exception as e: return [], str(e)

async def invite_live_user(session_data: dict, user: dict, lat: float, lng: float, campaign_id: str, client: aiohttp.ClientSession):
    try:
        payload = {"campaignId": campaign_id, "senderUserId": str(session_data.get("userid", "")), "senderLocation": {"latitude": lat, "longitude": lng}, "receivers": [{"userId": str(user.get("userId") or ""), "userName": str(user.get("userName") or "")}]}
        async with client.post(SPNS_BASE_URL + CREATE_OFFERS_PATH, headers=build_spns_headers(session_data), json=payload, timeout=6) as resp:
            data = await resp.json(content_type=None)
            results = (data.get("data") or {}).get("receiverResults", [])
            for res in results:
                for bl, offer in (res.get("offersByBL") or {}).items():
                    status, val = str(offer.get("status") or ""), _parse_amount(offer.get("offerValue"))
                    if status == "SUCCESS": return True, f"Rs.{val:.0f} ({bl})"
                    elif status == "FAILURE": return False, offer.get("errorCode") or "Rejected"
            return False, data.get("statusMessage") or "Inactive"
    except Exception as e: return False, str(e)

async def run_10_live_users_loot(session_data: dict, status_msg, context: ContextTypes.DEFAULT_TYPE, target_success: int = TARGET_SUCCESS_COUNT):
    context.user_data["is_running"], context.user_data["cancel_requested"] = True, False
    joined_count, fail_count, tried_ids, summary_lines = 0, 0, set(), []
    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as client:
            if not await check_account_validity(session_data, client): return await process_account_deletion(context, session_data.get("userid"), status_msg)
            while joined_count < target_success:
                if context.user_data.get("cancel_requested"): break
                for city, lat, lng in ALL_AREAS:
                    if joined_count >= target_success or context.user_data.get("cancel_requested"): break
                    users, _ = await discover_live_users(session_data, lat, lng, DEFAULT_CAMPAIGN_ID, client, list(tried_ids))
                    new_users = [u for u in users if str(u.get("userId", "")) not in tried_ids]
                    for u in new_users:
                        if joined_count >= target_success or context.user_data.get("cancel_requested"): break
                        uid, name = str(u.get("userId") or ""), str(u.get("userName") or "User")
                        tried_ids.add(uid)
                        if (u.get("status") or {}).get("isAssociated"): fail_count += 1; continue
                        ok, note = await invite_live_user(session_data, u, lat, lng, DEFAULT_CAMPAIGN_ID, client)
                        if ok:
                            joined_count += 1
                            summary_lines.append(f"• `{name}`: ✅ {note}")
                        else:
                            fail_count += 1
                            summary_lines.append(f"• `{name}`: ❌ {note}")
                        try:
                            await status_msg.edit_text(f"✦ *Hyper-Scan Loot Active* ✦\n\n✅ *Successful:* `{joined_count}/{target_success}`\n❌ *Bypassed:* `{fail_count}`\n📡 *Scanned:* `{len(tried_ids)}`", reply_markup=get_cancel_button(), parse_mode="Markdown")
                        except Exception: pass
                        await asyncio.sleep(0.3)
                await asyncio.sleep(2.0)
    except Exception as e: summary_lines.append(f"⚠️ Error: {str(e)}")
    finally: context.user_data["is_running"] = False
    final_msg = f"🏆 *Loot Completed!*\n\n{chr(10).join(summary_lines[:15])}\n\n✅ *Total Successful:* `{joined_count}/{target_success}`"
    try: await status_msg.edit_text(final_msg, parse_mode="Markdown")
    except Exception: pass

def get_main_reply_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("⚡ Free Cash Loot (12 Users)")], [KeyboardButton("🍳 Breakfast Offer (4 Deals)"), KeyboardButton("🍔 Night Offer (4 Deals)")], [KeyboardButton("📱 Authentication"), KeyboardButton("📁 Saved Accounts")], [KeyboardButton("🔄 Restart System")]], resize_keyboard=True)

def show_login_choice_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("📱 Request OTP", callback_data="login_phone_opt")], [InlineKeyboardButton("⚙️ Inject JSON", callback_data="login_json_opt")]])

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.message or update.callback_query.message
    await target.reply_text("✦ *SWIGGY TURBO LOOT BOT* ✦\n\nSelect an option below:", reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("swiggy_session")

    if query.data.startswith("switch_acc_"):
        uid = query.data.replace("switch_acc_", "")
        if uid in context.user_data.get("saved_accounts", {}):
            context.user_data["swiggy_session"] = context.user_data["saved_accounts"][uid]
            await query.message.edit_text(f"✅ Switched active account to ID: `{uid}`", parse_mode="Markdown")
        return
    if query.data == "cancel_current_task":
        context.user_data["cancel_requested"] = True
        return
    if query.data == "menu_restart": return await cmd_start(update, context)

    if query.data == "opt_cash_loot":
        if not session: return await query.message.reply_text("⚠️ Login Required!", reply_markup=show_login_choice_markup())
        status = await query.message.reply_text("⚡ Starting Engine...", reply_markup=get_cancel_button())
        asyncio.create_task(run_10_live_users_loot(session, status, context))
    elif query.data == "login_phone_opt":
        context.user_data["state"] = "awaiting_phone"
        await query.message.reply_text("📱 Enter 10-digit registered number:")
    elif query.data == "login_json_opt":
        context.user_data["state"] = "awaiting_json"
        await query.message.reply_text("⚙️ Paste your Swiggy session JSON block:")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, state, session = (update.message.text or "").strip(), context.user_data.get("state"), context.user_data.get("swiggy_session")

    if text == "📁 Saved Accounts":
        saved = context.user_data.get("saved_accounts", {})
        if not saved: return await update.message.reply_text("⚠️ No saved accounts found.")
        kb = [[InlineKeyboardButton(f"Account: {uid}", callback_data=f"switch_acc_{uid}")] for uid in saved]
        return await update.message.reply_text("📁 *Saved Accounts:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    if text == "⚡ Free Cash Loot (12 Users)":
        if not session: return await update.message.reply_text("🔒 Login Required", reply_markup=show_login_choice_markup())
        status = await update.message.reply_text("⚡ Initializing Loot Engine...", reply_markup=get_cancel_button())
        asyncio.create_task(run_10_live_users_loot(session, status, context))
        return

    if text in ("🔄 Restart System", "/start"): return await cmd_start(update, context)
    if text == "📱 Authentication": return await update.message.reply_text("🔐 Authentication:", reply_markup=show_login_choice_markup())

    if (text.startswith("{") and text.endswith("}")) or '"token"' in text or state == "awaiting_json":
        try:
            parsed = parse_session_string(text)
            uid = parsed.get("userid", "Unknown")
            if "saved_accounts" not in context.user_data: context.user_data["saved_accounts"] = {}
            context.user_data["saved_accounts"][uid] = parsed
            context.user_data["swiggy_session"] = parsed
            context.user_data.pop("state", None)
            return await update.message.reply_text(f"🔓 Authentication Successful! ID: `{uid}`", reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")
        except Exception as e: return await update.message.reply_text(f"❌ JSON Error: {str(e)}")

def main():
    # 1. Start Render HTTP port binding in background thread
    t = threading.Thread(target=run_http_server, daemon=True)
    t.start()

    # 2. Start Telegram Bot Polling
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))

    print("🤖 Swiggy Turbo Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
