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
SPNS_BASE_URL = "https://spns.swiggy.com"
CREATE_OFFERS_PATH = "/api/v1/proximity-offer/create-offers"
DISCOVER_USERS_PATH = "/api/v1/proximity-offer/discover-users"
TRANSACTIONS_PATH = "/api/v1/proximity-offer/campaigns/{campaign_id}/transactions"

# Handles Cashloot, Morning Loot, and generic referral links
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

ALL_AREAS = [
    ("Delhi - Connaught Place", 28.6315, 77.2167),
    ("Delhi - Saket", 28.5245, 77.2066),
    ("Delhi - Hauz Khas", 28.5433, 77.2066),
    ("Delhi - Karol Bagh", 28.6519, 77.1909),
    ("Delhi - Nehru Place", 28.5481, 77.2546),
    ("Delhi - Central", 28.6429, 77.2191),
    ("Delhi - New Delhi", 28.6139, 77.2090),
    ("Bengaluru - Koramangala", 12.9352, 77.6245),
    ("Bengaluru - Indiranagar", 12.9784, 77.6408),
    ("Bengaluru - Central", 12.9716, 77.5946),
    ("Mumbai - Bandra West", 19.0596, 72.8295),
    ("Mumbai - Andheri West", 19.1363, 72.8277),
    ("Mumbai - South", 19.0760, 72.8777),
    ("Pune - Hinjewadi", 18.5912, 73.7389),
    ("Pune - FC Road", 18.5204, 73.8567),
    ("Hyderabad - Hitec City", 17.4435, 78.3772),
    ("Hyderabad - Central", 17.3850, 78.4867),
    ("Chennai - T Nagar", 13.0418, 80.2341),
    ("Kolkata - Park Street", 22.5526, 88.3539),
    ("Ahmedabad - SG Highway", 23.0225, 72.5714),
    ("Jaipur - Malviya Nagar", 26.9124, 75.7873),
    ("Lucknow - Gomti Nagar", 26.8467, 80.9462),
    ("Chandigarh - Sector 17", 30.7333, 76.7794),
    ("Indore - Vijay Nagar", 22.7196, 75.8577),
    ("Bhopal - MP Nagar", 23.2599, 77.4126),
    ("Patna - Boring Road", 25.5941, 85.1376),
]


# ── SAVED ACCOUNTS SYSTEM ────────────────────────────────────────────────────
ACCOUNTS_FILE = "saved_accounts.json"

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_accounts(data):
    try:
        with open(ACCOUNTS_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

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
                    if "unauthorized" in msg or "token invalid" in msg or "account deleted" in msg:
                        return False
    except Exception:
        pass
    return True

# ─────────────────────────────────────────────────────────────────────────────

def get_random_device_id():
    return secrets.token_hex(8)

def _decode_tid_payload(tid: str) -> dict:
    try:
        parts = tid.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except Exception:
        return {}

def _userid_from_tid(tid: str):
    payload = _decode_tid_payload(tid)
    uid = payload.get("user_id")
    return str(uid) if uid else ""

def _parse_amount(value) -> float:
    if isinstance(value, dict):
        value = value.get("units", value.get("amount", 0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

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
            if isinstance(data.get("data"), dict):
                sources.append(data.get("data"))
            for src in sources:
                if isinstance(src, dict):
                    for k in ("token", "secret_token", "access_token", "tid", "sid", "userid", "customerId", "phone", "mobile"):
                        if k in src and k not in session:
                            session[k] = src[k]
            if "token" not in session:
                for alias in ("secret_token", "access_token"):
                    if session.get(alias):
                        session["token"] = session[alias]
                        break
        elif isinstance(data, list):
            for header in data:
                if isinstance(header, dict):
                    n = str(header.get("name", "")).lower()
                    v = header.get("value", "")
                    if n in ("token", "tid", "sid", "userid", "phone"):
                        session[n] = v
    except Exception:
        pass

    if not session:
        for key in ("token", "tid", "sid", "userid", "phone"):
            m = re.search(r'["\']?' + key + r'["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', cleaned, re.IGNORECASE)
            if m:
                session[key] = m.group(1)

    if not session.get("token") and not session.get("tid"):
        raise ValueError("Invalid Session: Token ya TID nahi mila.")
    uid = session.get("userid") or _userid_from_tid(session.get("tid", ""))
    session["userid"] = str(uid)
    return session

def extract_all_links(text: str):
    tokens = SWIGGY_LINK_RE.findall(text)
    if not tokens:
        tokens = GENERIC_LINK_RE.findall(text)
    seen, results = set(), []
    for token in tokens:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            parts = token.split("-")
            if len(parts) >= 2:
                results.append((parts[0], parts[1], token))
    return results

def get_cancel_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Stop / Cancel", callback_data="cancel_current_task")]
    ])


# ── FEATURE 1: DISCOVER & LOOT (10 SUCCESSFUL LIVE USERS) ────────────────────
async def discover_live_users(session_data: dict, lat: float, lng: float, campaign_id: str, client: aiohttp.ClientSession, seen: list):
    headers = build_spns_headers(session_data)
    payload = {
        "location": {"latitude": lat, "longitude": lng},
        "tid": str(session_data.get("tid", "")),
        "previousNearbyUserIds": seen or [],
        "campaignId": campaign_id,
        "userId": str(session_data.get("userid", "")),
        "isFreshLocation": True,
    }
    try:
        async with client.post(SPNS_BASE_URL + DISCOVER_USERS_PATH, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            data = await resp.json(content_type=None)
            inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            users = inner.get("nearbyUsers") if isinstance(inner.get("nearbyUsers"), list) else []
            return [u for u in users if isinstance(u, dict)], None
    except Exception as e:
        return [], str(e)

async def invite_live_user(session_data: dict, user: dict, lat: float, lng: float, campaign_id: str, client: aiohttp.ClientSession):
    headers = build_spns_headers(session_data)
    payload = {
        "campaignId": campaign_id,
        "senderUserId": str(session_data.get("userid", "")),
        "senderLocation": {"latitude": lat, "longitude": lng},
        "receivers": [{
            "userId": str(user.get("userId") or ""),
            "userName": str(user.get("userName") or ""),
        }],
    }
    try:
        async with client.post(SPNS_BASE_URL + CREATE_OFFERS_PATH, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            data = await resp.json(content_type=None)
            inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            results = inner.get("receiverResults") if isinstance(inner.get("receiverResults"), list) else []
            for res in results:
                if not isinstance(res, dict):
                    continue
                offers = res.get("offersByBL") if isinstance(res.get("offersByBL"), dict) else {}
                for bl, offer in offers.items():
                    if not isinstance(offer, dict):
                        continue
                    status = str(offer.get("status") or "")
                    val = _parse_amount(offer.get("offerValue"))
                    val_str = f"{val:.0f}" if float(val).is_integer() else f"{val:.2f}"
                    if status == "SUCCESS":
                        return True, f"Rs.{val_str} ({bl})"
                    elif status == "FAILURE":
                        return False, offer.get("errorCode") or "Server rejected"
            return False, data.get("statusMessage") or "Offer limit or inactive"
    except Exception as e:
        return False, str(e)

async def run_10_live_users_loot(session_data: dict, status_msg, context: ContextTypes.DEFAULT_TYPE, target_success: int = TARGET_SUCCESS_COUNT):
    context.user_data["is_running"] = True
    context.user_data["cancel_requested"] = False
    connector = aiohttp.TCPConnector(ssl=False)
    joined_count = 0
    fail_count = 0
    tried_ids = set()
    summary_lines = []

    area_scores = {area[0]: 10.0 for area in ALL_AREAS}
    active_areas = list(ALL_AREAS)
    last_ui_update = 0.0
    consecutive_empty_rounds = 0
    hard_failures = 0
    live_action = "Warming up scanner..."

    try:
        async with aiohttp.ClientSession(connector=connector) as client:
            while joined_count < target_success:
                if context.user_data.get("cancel_requested"):
                    break

                active_areas.sort(key=lambda a: area_scores.get(a[0], 0), reverse=True)
                users_found_in_round = False
                batch_size = 5

                for i in range(0, len(active_areas), batch_size):
                    if joined_count >= target_success or context.user_data.get("cancel_requested"):
                        break

                    batch = active_areas[i:i+batch_size]

                    now = time.time()
                    if now - last_ui_update >= 1.5:
                        last_ui_update = now
                        est_sec = (target_success - joined_count) * 4
                        try:
                            scan_zones = ", ".join([b[0].split(" - ")[0] for b in batch[:2]])
                            await status_msg.edit_text(
                                f"✦ *Turbo Live Scan* ~ *shivansh* ✦\n\n"
                                f"📍 *Scanning:* `{scan_zones}...`\n"
                                f"✅ *Successful:* `{joined_count}/{target_success}`\n"
                                f"❌ *Bypassed:* `{fail_count}`\n"
                                f"📡 *Scanned:* `{len(tried_ids)}`\n"
                                f"⏱️ *ETA:* `~{est_sec}s`\n\n"
                                f"👁️ *Live Status:* `{live_action}`",
                                reply_markup=get_cancel_button(),
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass

                    tasks = [discover_live_users(session_data, lat, lng, DEFAULT_CAMPAIGN_ID, client, list(tried_ids)) for _, lat, lng in batch]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for (city, lat, lng), res in zip(batch, results):
                        if joined_count >= target_success or context.user_data.get("cancel_requested"):
                            break

                        if isinstance(res, Exception) or not res[0]:
                            area_scores[city] = max(0.0, area_scores.get(city, 0) - 1.0)
                            live_action = f"⚠️ No active users in {city} right now."
                            continue

                        users = res[0]
                        new_users = [u for u in users if str(u.get("userId", "")) not in tried_ids]

                        if not new_users:
                            area_scores[city] = max(0.0, area_scores.get(city, 0) - 1.0)
                            live_action = f"⚠️ No fresh users in {city} right now."
                            continue

                        users_found_in_round = True
                        area_scores[city] = area_scores.get(city, 0) + (len(new_users) * 0.5)

                        for u in new_users:
                            if joined_count >= target_success or context.user_data.get("cancel_requested"):
                                break
                            
                            uid = str(u.get("userId") or "")
                            name = str(u.get("userName") or uid or "Swiggy User")
                            tried_ids.add(uid)

                            if (u.get("status") or {}).get("isAssociated"):
                                fail_count += 1
                                continue

                            live_action = f"🔄 Trying to lock offer for {name} in {city}..."
                            now = time.time()
                            if now - last_ui_update >= 1.5:
                                last_ui_update = now
                                est_sec = (target_success - joined_count) * 4
                                try:
                                    await status_msg.edit_text(
                                        f"✦ *Looting Active* ~ *shivansh* ✦\n\n"
                                        f"📍 *Target Zone:* `{city}`\n"
                                        f"👤 *Target:* `{name}`\n"
                                        f"✅ *Successful:* `{joined_count}/{target_success}`\n"
                                        f"❌ *Bypassed:* `{fail_count}`\n"
                                        f"📡 *Scanned:* `{len(tried_ids)}`\n"
                                        f"⏱️ *ETA:* `~{est_sec}s`\n\n"
                                        f"👁️ *Live Status:* `{live_action}`",
                                        reply_markup=get_cancel_button(),
                                        parse_mode="Markdown"
                                    )
                                except Exception:
                                    pass

                            ok, note = await invite_live_user(session_data, u, lat, lng, DEFAULT_CAMPAIGN_ID, client)
                            if ok:
                                joined_count += 1
                                hard_failures = 0
                                area_scores[city] += 10.0
                                summary_lines.append(f"• `{name}` ({city}): ✅ Won {note}")
                                live_action = f"🎯 YES! Successfully secured {name}!"
                            else:
                                fail_count += 1
                                summary_lines.append(f"• `{name}`: ❌ {note}")
                                
                                note_lower = str(note).lower()
                                if "alreadyassociated" in note_lower or "already claimed" in note_lower:
                                    area_scores[city] += 1.0
                                    live_action = f"⏩ User {name} already looted. Skipping..."
                                else:
                                    hard_failures += 1
                                    live_action = f"🚫 Failed for {name}: {note}"
                                    if "limit" in note_lower or "inactive" in note_lower or "exhausted" in note_lower:
                                        hard_failures += 3

                            if hard_failures >= 30:
                                live_action = "⏳ Swiggy limit triggered. Pausing to avoid ban..."
                                try:
                                    await status_msg.edit_text(
                                        f"✦ *Turbo Live Scan* ~ *shivansh* ✦\n\n"
                                        f"📍 *Target Zone:* `India Wide`\n"
                                        f"✅ *Successful:* `{joined_count}/{target_success}`\n"
                                        f"❌ *Bypassed:* `{fail_count}`\n"
                                        f"📡 *Scanned:* `{len(tried_ids)}`\n"
                                        f"⏱️ *ETA:* `~Paused`\n\n"
                                        f"👁️ *Live Status:* `{live_action}`",
                                        reply_markup=get_cancel_button(),
                                        parse_mode="Markdown"
                                    )
                                except: pass
                                await asyncio.sleep(5)
                                hard_failures = 0

                            await asyncio.sleep(0.1)

                if not users_found_in_round:
                    consecutive_empty_rounds += 1
                    if consecutive_empty_rounds >= 6:
                        live_action = "🌙 Night mode detected. Resting 5s before India-wide rescan..."
                        try:
                            await status_msg.edit_text(
                                f"✦ *Turbo Live Scan* ~ *shivansh* ✦\n\n"
                                f"📍 *Target Zone:* `India Wide`\n"
                                f"✅ *Successful:* `{joined_count}/{target_success}`\n"
                                f"❌ *Bypassed:* `{fail_count}`\n"
                                f"📡 *Scanned:* `{len(tried_ids)}`\n"
                                f"⏱️ *ETA:* `~Waiting...`\n\n"
                                f"👁️ *Live Status:* `{live_action}`",
                                reply_markup=get_cancel_button(),
                                parse_mode="Markdown"
                            )
                        except: pass
                        
                        for a in area_scores:
                            area_scores[a] = 10.0
                        await asyncio.sleep(5.0)
                        consecutive_empty_rounds = 0

    except Exception as e:
        summary_lines.append(f"⚠️ Internal Error: {str(e)}")
    finally:
        context.user_data["is_running"] = False

    if context.user_data.get("cancel_requested"):
        final_msg = "🛑 *Operation Aborted by User*\n\n"
    else:
        final_msg = "🏆 *Loot Operation Completed Successfully!*\n\n"

    if summary_lines:
        final_msg += "\n".join(summary_lines[:15]) + "\n\n"

    top_winning = sorted(area_scores.items(), key=lambda x: x[1], reverse=True)
    best_areas = [f"{k}" for k, v in top_winning if v > 10.0]
    if best_areas:
        hub_str = ", ".join(best_areas[:3])
        final_msg += f"🔥 *Top Winning Hubs:* {hub_str}\n"

    final_msg += f"✅ *Total Successful:* `{joined_count}/{target_success}`\n"
    final_msg += f"❌ *Total Bypassed:* `{fail_count}`\n"
    final_msg += f"📡 *Total Scanned:* `{len(tried_ids)}`\n\n"
    if joined_count > 0:
        final_msg += "✧ *crafted by shivansh* ✧\n"
    final_msg += "_(Check your wallet in the Swiggy app)_"

    try:
        await status_msg.edit_text(final_msg, parse_mode="Markdown")
    except Exception:
        pass


# ── FEATURE 3: BULK REFERRAL LINK PROCESSING ─────────────────────────────────
async def claim_referral_link(session_data: dict, campaign_id: str, referrer_id: str, client: aiohttp.ClientSession):
    headers = build_spns_headers(session_data)
    payload = {
        "campaignId": campaign_id,
        "senderUserId": referrer_id,
        "isReferralFlow": True,
        "receivers": [{"userId": str(session_data.get("userid", ""))}],
    }
    try:
        async with client.post(
            SPNS_BASE_URL + CREATE_OFFERS_PATH,
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            data = await resp.json(content_type=None)
            inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            res_list = inner.get("receiverResults") if isinstance(inner.get("receiverResults"), list) else []
            for r in res_list:
                for bl, off in (r.get("offersByBL") or {}).items():
                    if off.get("status") == "SUCCESS":
                        val = _parse_amount(off.get("offerValue"))
                        return True, f"Won Rs.{val:.0f} Offer ({bl})"
                    else:
                        return False, off.get("errorCode") or "Already Claimed or Expired"
            return False, data.get("statusMessage") or "Offer not available"
    except Exception as e:
        return False, str(e)


async def run_bulk_links(session_data: dict, status_msg, context: ContextTypes.DEFAULT_TYPE, found_links: list):
    context.user_data["is_running"] = True
    context.user_data["cancel_requested"] = False
    results = []
    connector = aiohttp.TCPConnector(ssl=False)
    try:
        async with aiohttp.ClientSession(connector=connector) as client:
            for idx, (cid, rid, token) in enumerate(found_links, 1):
                if context.user_data.get("cancel_requested"):
                    results.append(f"🛑 *Stopped by User*")
                    break

                try:
                    await status_msg.edit_text(
                        f"⏳ *Processing Links...* (`{idx}/{len(found_links)}`)\n\n"
                        f"🔗 Processing: `{token}`",
                        reply_markup=get_cancel_button(),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

                ok, note = await claim_referral_link(session_data, cid, rid, client)
                mark = "✅" if ok else "❌"
                results.append(f"• `{token}`: {mark} {note}")
                await asyncio.sleep(0.4)

        if context.user_data.get("cancel_requested"):
            final_resp = "🛑 *Links Processing Cancelled!*\n\n"
        else:
            final_resp = "🎯 *Links Processing Finished!*\n\n"
            
        final_resp += "\n".join(results)
        if "✅" in final_resp:
            final_resp += "\n\n✧ *crafted by shivansh* ✧"
        await status_msg.edit_text(final_resp, parse_mode="Markdown")
    finally:
        context.user_data["is_running"] = False


# ── TELEGRAM KEYBOARDS ───────────────────────────────────────────────────────
def get_main_reply_keyboard():
    keyboard = [
        [KeyboardButton("⚡ Free Cash Loot (12 Users)")],
        [KeyboardButton("📱 Authentication"), KeyboardButton("📁 Saved Accounts")],
        [KeyboardButton("🔄 Restart System")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def show_login_choice_markup():
    keyboard = [
        [InlineKeyboardButton("📱 Request OTP", callback_data="login_phone_opt")],
        [InlineKeyboardButton("⚙️ Inject JSON", callback_data="login_json_opt")],
        [InlineKeyboardButton("💾 Saved Accounts", callback_data="login_saved_opt")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_inline_main_markup():
    keyboard = [
        [InlineKeyboardButton("⚡ Start Free Cash Loot", callback_data="opt_cash_loot")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "✦ *SWIGGY TURBO LOOT* ✦\n"
        "✧ *crafted by shivansh* ✧\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please select from the options below:"
    )
    
    target_msg = update.message if update.message else update.callback_query.message
    
    await target_msg.reply_text(msg, reply_markup=get_main_reply_keyboard(), parse_mode="Markdown")
    await target_msg.reply_text("✨ *Quick Actions:*", reply_markup=get_inline_main_markup(), parse_mode="Markdown")


async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = context.user_data.get("swiggy_session")

    if query.data == "cancel_current_task":
        if context.user_data.get("is_running"):
            context.user_data["cancel_requested"] = True
            try:
                await query.answer("🛑 Terminating operation... Please wait a moment.", show_alert=True)
            except Exception:
                pass
        else:
            try:
                await query.answer("No process is currently running.", show_alert=True)
            except Exception:
                pass
        return

    if query.data == "menu_restart":
        await cmd_start(query, context)
        return

    # Handle Saved Accounts Menu
    if query.data == "login_saved_opt":
        chat_id = str(update.effective_chat.id)
        accounts = load_accounts().get(chat_id, [])
        if not accounts:
            await query.message.reply_text("⚠️ You don't have any saved accounts yet. Please login via OTP or JSON first.")
            return
        
        keyboard = []
        for acc in accounts:
            uid = acc.get("userid", "Unknown")
            phone = acc.get("phone", "")
            label = f"👤 {phone if phone else uid}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"use_acc_{uid}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Login Options", callback_data="back_to_login")])
        await query.message.reply_text("💾 *Select a Saved Account:*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    if query.data == "back_to_login":
        await query.message.reply_text("🔐 *System Authentication*\n\nSelect a login method below:", reply_markup=show_login_choice_markup())
        return

    # Handle Login via Saved Account
    if query.data.startswith("use_acc_"):
        uid = query.data.replace("use_acc_", "")
        chat_id = str(update.effective_chat.id)
        accounts = load_accounts().get(chat_id, [])
        selected_acc = next((acc for acc in accounts if str(acc.get("userid")) == uid), None)
        
        if not selected_acc:
            await query.message.reply_text("❌ Account not found in saved list.")
            return
        
        status_msg = await query.message.reply_text("🔄 Validating saved account with Swiggy servers...")
        
        is_valid = await validate_session(selected_acc)
        if not is_valid:
            remove_saved_account(chat_id, uid)
            await status_msg.edit_text("❌ *Account Invalid or Deleted!*\nThis account has been automatically removed from your saved list.", parse_mode="Markdown")
            return
        
        context.user_data["swiggy_session"] = selected_acc
        target = context.user_data.pop("next_target", None)
        
        await status_msg.edit_text(f"🔓 *Login Successful via Saved Account!*\n👤 *User ID:* `{uid}`\n\n✧ *shivansh* ✧", parse_mode="Markdown")
        
        if target == "cash_loot":
            if context.user_data.get("is_running"): return
            status = await query.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
            asyncio.create_task(run_10_live_users_loot(selected_acc, status, context, target_success=TARGET_SUCCESS_COUNT))
        return

    if query.data == "opt_cash_loot":
        if not session or not session.get("token"):
            context.user_data["next_target"] = "cash_loot"
            await query.message.reply_text("⚠️ *Login Required!*\n\nPlease login first to use Free Cash Loot.", reply_markup=show_login_choice_markup(), parse_mode="Markdown")
            return
        if context.user_data.get("is_running"):
            await query.message.reply_text("⚠️ An operation is already in progress. Please 🛑 Stop it first.")
            return

        status = await query.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
        asyncio.create_task(run_10_live_users_loot(session, status, context, target_success=TARGET_SUCCESS_COUNT))

    elif query.data == "login_phone_opt":
        context.user_data["state"] = "awaiting_phone"
        await query.message.reply_text("📱 *OTP Authentication*\n\nPlease enter your 10-digit registered Swiggy mobile number to receive a secure verification code:")

    elif query.data == "login_json_opt":
        context.user_data["state"] = "awaiting_json"
        await query.message.reply_text("⚙️ *Developer JSON Login*\n\nSecurely paste your extracted Swiggy session JSON block below:\n\n*Format:*\n`{\"token\":\"...\",\"tid\":\"...\",\"sid\":\"...\"}`", parse_mode="Markdown")


async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")
    session = context.user_data.get("swiggy_session")
    chat_id = update.effective_chat.id

    if text == "📁 Saved Accounts":
        accounts = load_accounts().get(str(chat_id), [])
        if not accounts:
            await update.message.reply_text("⚠️ No saved accounts found. Please authenticate to save one.")
            return
        kb = []
        for acc in accounts:
            uid = acc.get("userid", "Unknown")
            phone = acc.get("phone", "")
            label = f"👤 {phone if phone else uid}"
            kb.append([InlineKeyboardButton(label, callback_data=f"switch_acc_{uid}")])
        kb.append([InlineKeyboardButton("🧹 Clean Invalid Accounts", callback_data="clean_invalid_accs")])
        await update.message.reply_text("📁 *Your Saved Accounts:*\n\nSelect an account below to switch your active session, or clean up expired ones.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        return

    if text in ("⚡ Free Cash Loot (12 Users)", "🚀 Start Free Cash Loot (20 Users)"):
        if not session or not session.get("token"):
            context.user_data["next_target"] = "cash_loot"
            await update.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        if context.user_data.get("is_running"):
            await update.message.reply_text("⚠️ An operation is already in progress. Please 🛑 Stop it first.")
            return

        status = await update.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
        asyncio.create_task(run_10_live_users_loot(session, status, context, target_success=TARGET_SUCCESS_COUNT))
        return

    if text in ("🔄 Restart System", "/start"):
        await cmd_start(update, context)
        return

    if text == "📱 Authentication":
        await update.message.reply_text("🔐 *System Authentication*\n\nTo access premium features, please securely link your Swiggy account. Select a login method below:", reply_markup=show_login_choice_markup())
        return

    if (text.startswith("{") and text.endswith("}")) or '"token"' in text or state == "awaiting_json":
        try:
            parsed = parse_session_string(text)
            context.user_data["swiggy_session"] = parsed
            context.user_data.pop("state", None)

            add_saved_account(chat_id, parsed)

            target = context.user_data.pop("next_target", None)
            reply_msg = f"🔓 *Authentication Successful & Account Saved!*\n👤 *User ID:* `{parsed.get('userid', 'Unknown')}`\n\n✧ *shivansh* ✧\n"
            await update.message.reply_text(reply_msg, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

            if target == "cash_loot":
                if context.user_data.get("is_running"): return
                status = await update.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
                asyncio.create_task(run_10_live_users_loot(parsed, status, context, target_success=TARGET_SUCCESS_COUNT))
            return
        except Exception as e:
            await update.message.reply_text(f"❌ JSON Parse Error: {str(e)}\nPlease paste it in the correct format.")
            return

    found_links = extract_all_links(text)
    if found_links:
        if not session or not session.get("token"):
            context.user_data["next_target"] = "bulk_links"
            await update.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        if context.user_data.get("is_running"):
            await update.message.reply_text("⚠️ An operation is already in progress. Please 🛑 Stop it first.")
            return

        status = await update.message.reply_text(f"⏳ Processing `{len(found_links)}` link(s)...", reply_markup=get_cancel_button(), parse_mode="Markdown")
        asyncio.create_task(run_bulk_links(session, status, context, found_links))
        return

    if state == "awaiting_phone" or (re.fullmatch(r"\d{10}", text) and not context.user_data.get("temp_auth")):
        phone = re.sub(r"\D", "", text)[-10:]
        dev_id = get_random_device_id()
        headers = {**SWIGGY_APP_HEADERS, "deviceId": dev_id, "swuid": dev_id}
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as client:
            try:
                async with client.get(f"{SMS_OTP_URL}?mobile={phone}", headers=headers) as resp:
                    data = await resp.json(content_type=None)
                    if data.get("statusCode") == 0:
                        context.user_data["temp_auth"] = {
                            "phone": phone, "tid": data.get("tid"),
                            "sid": data.get("sid"), "dev_id": dev_id
                        }
                        context.user_data["state"] = "awaiting_otp"
                        await update.message.reply_text(f"📩 *OTP Sent Successfully*\n\nA verification code has been sent to `+91{phone}`.\nEnter it directly in the chat (e.g. `123456`):", parse_mode="Markdown")
                    else:
                        await update.message.reply_text(f"❌ OTP Send Failed: {data.get('statusMessage', 'Unknown')}")
            except Exception as e:
                await update.message.reply_text(f"❌ Network Error: {str(e)}")
        return

    temp = context.user_data.get("temp_auth")
    if temp and (state == "awaiting_otp" or re.fullmatch(r"\d{4,6}", text)):
        otp = text.strip()
        headers = {
            **SWIGGY_APP_HEADERS,
            "deviceId": temp["dev_id"], "swuid": temp["dev_id"],
            "sid": str(temp["sid"]), "Tid": str(temp["tid"]),
        }
        payload = {
            "cloningSignalsData": {
                "appFilesDirPathInvalid": 0, "developerModeEnabled": 1,
                "deviceModelVmos": 0, "emulatorStatus": 0,
                "packageName": "in.swiggy.android", "workProfileEnabled": 0
            },
            "otp": otp,
        }
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as client:
            try:
                async with client.post(f"{VERIFY_URL}?otp_source=Sms-automatic", headers=headers, json=payload) as resp:
                    data = await resp.json(content_type=None)
                    if data.get("statusCode") == 0:
                        inner = data.get("data") or {}
                        tid = data.get("tid") or inner.get("tid")
                        token = inner.get("token") or inner.get("accessToken")
                        userid = str(_decode_tid_payload(tid).get("user_id"))

                        parsed_session = {
                            "userid": str(userid), "token": token,
                            "tid": tid, "sid": temp["sid"], "phone": temp["phone"]
                        }
                        
                        context.user_data["swiggy_session"] = parsed_session
                        context.user_data.pop("temp_auth", None)
                        context.user_data.pop("state", None)

                        add_saved_account(chat_id, parsed_session)

                        target = context.user_data.pop("next_target", None)
                        await update.message.reply_text(f"🔓 *Authentication Successful & Account Saved!*\n👤 *User ID:* `{userid}`\n\n✧ *shivansh* ✧", parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

                        if target == "cash_loot":
                            if context.user_data.get("is_running"): return
                            status = await update.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
                            asyncio.create_task(run_10_live_users_loot(parsed_session, status, context, target_success=TARGET_SUCCESS_COUNT))
                    else:
                        await update.message.reply_text(f"❌ Login Failed: {data.get('statusMessage')}")
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {str(e)}")
        return

    await update.message.reply_text("Use the persistent button or send `/start` to see the menu.", reply_markup=get_main_reply_keyboard())


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    print("🤖 Swiggy Turbo Bot ~ *shivansh* is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
