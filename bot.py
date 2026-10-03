import time
import asyncio
import base64
import json
import re
import secrets
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
TRANSACTIONS_PATH = "/api/v1/proximity-offer/campaigns/{campaign_id}/transactions"

# Handles Cashloot, Breakfast, Morning Loot, and generic referral links
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
    1: {"title": "₹50 FREE Cash", "desc": "On order above ₹199", "tag": "Free Cash"},
    2: {"title": "₹150 OFF Coupon", "desc": "On order above ₹249", "tag": "Coupon"},
    3: {"title": "₹100 OFF + ₹50 Cash", "desc": "On order above ₹249", "tag": "Coupon & Cash"},
    4: {"title": "₹100 OFF Coupon", "desc": "On order above ₹149", "tag": "Coupon"},
}
BREAKFAST_OFFERS = {
    1: {"title": "₹50 FREE Cash", "desc": "On order above ₹199", "tag": "Free Cash"},
    2: {"title": "₹150 OFF Coupon", "desc": "On order above ₹249", "tag": "Coupon"},
    3: {"title": "₹100 OFF + ₹50 Cash", "desc": "On order above ₹249", "tag": "Coupon & Cash"},
    4: {"title": "₹100 OFF Coupon", "desc": "On order above ₹149", "tag": "Coupon"},
}

ALL_AREAS = [
    ("Delhi - Connaught Place", 28.6315, 77.2167),
    ("Delhi - Saket", 28.5245, 77.2066),
    ("Delhi - Hauz Khas", 28.5433, 77.2066),
    ("Delhi - Karol Bagh", 28.6519, 77.1909),
    ("Delhi - Nehru Place", 28.5481, 77.2546),
    ("Delhi - Central", 28.6429, 77.2191),
    ("Delhi - New Delhi", 28.6139, 77.2090),
    ("Delhi - Gurgaon CyberHub", 28.4595, 77.0266),
    ("Delhi - Noida Sector 18", 28.5355, 77.3910),
    ("Delhi - Dwarka Sector 10", 28.5921, 77.0460),
    ("Delhi - Rohini", 28.7495, 77.0565),
    ("Delhi - Pitampura", 28.6899, 77.1180),
    ("Delhi - Janakpuri", 28.6293, 77.0777),
    ("Delhi - Punjabi Bagh", 28.6747, 77.1310),
    ("Delhi - Laxmi Nagar", 28.6300, 77.2430),
    ("Delhi - Mayur Vihar", 28.5989, 77.2795),
    ("Delhi - Vasant Kunj", 28.5200, 77.1591),
    ("Delhi - Aerocity", 28.5445, 77.1610),
    ("Delhi - Greater Noida", 28.4744, 77.5040),
    ("Delhi - Ghaziabad", 28.6692, 77.4538),
    ("Delhi - Faridabad", 28.4089, 77.3178),
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
                sources.append(data["data"])
            for src in sources:
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
                n = str(header.get("name", "")).lower()
                v = header.get("value", "")
                if n in ("token", "tid", "sid", "userid"):
                    session[n] = v
    except Exception:
        pass

    if not session:
        for key in ("token", "tid", "sid", "userid"):
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


def get_night_options_markup():
    keyboard = [
        [
            InlineKeyboardButton("🍔 ₹50 FREE Cash (>₹199)", callback_data="nyo_opt_1"),
            InlineKeyboardButton("🍕 ₹150 OFF (>₹249)", callback_data="nyo_opt_2"),
        ],
        [
            InlineKeyboardButton("🍟 ₹100 OFF + ₹50 Cash", callback_data="nyo_opt_3"),
            InlineKeyboardButton("🥤 ₹100 OFF (>₹149)", callback_data="nyo_opt_4"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_restart"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_breakfast_options_markup():
    keyboard = [
        [
            InlineKeyboardButton("🎁 ₹50 FREE Cash (>₹199)", callback_data="byo_opt_1"),
            InlineKeyboardButton("🏷️ ₹150 OFF (>₹249)", callback_data="byo_opt_2"),
        ],
        [
            InlineKeyboardButton("💰 ₹100 OFF + ₹50 Cash", callback_data="byo_opt_3"),
            InlineKeyboardButton("🎟️ ₹100 OFF (>₹149)", callback_data="byo_opt_4"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_restart"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

# ── AUTO ACCOUNT CLEANUP LOGIC ───────────────────────────────────────────────
async def check_account_validity(session_data: dict, client: aiohttp.ClientSession) -> bool:
    headers = build_spns_headers(session_data)
    payload = {
        "location": {"latitude": 28.6315, "longitude": 77.2167},
        "tid": str(session_data.get("tid", "")),
        "campaignId": DEFAULT_CAMPAIGN_ID,
        "userId": str(session_data.get("userid", "")),
        "isFreshLocation": True,
    }
    try:
        async with client.post(SPNS_BASE_URL + DISCOVER_USERS_PATH, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            # Only return False if token is truly unauthorized (401)
            if resp.status == 401:
                return False
            return True
    except Exception:
        return True

async def process_account_deletion(context: ContextTypes.DEFAULT_TYPE, uid: str, status_msg=None):
    if "saved_accounts" in context.user_data and uid in context.user_data["saved_accounts"]:
        del context.user_data["saved_accounts"][uid]
    if context.user_data.get("swiggy_session", {}).get("userid") == uid:
        context.user_data.pop("swiggy_session", None)
    if status_msg:
        try:
            await status_msg.edit_text("❌ *Account Expired / Invalid!*\nRemoved automatically from Saved Accounts.", parse_mode="Markdown")
        except Exception:
            pass


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
            # Check account validity before starting
            if not await check_account_validity(session_data, client):
                return await process_account_deletion(context, session_data.get("userid"), status_msg)

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

                    # Concurrent API calls for 5 areas at once
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


# ── FEATURE 2: PICK YOUR BREAKFAST OFFER ─────────────────────────────────────
async def request_single_breakfast_lock(session_data: dict, offer_index: int, client: aiohttp.ClientSession):
    device_id = get_random_device_id()
    token = str(session_data.get("token", "")).strip()
    tid = str(session_data.get("tid", "")).strip()
    sid = str(session_data.get("sid", "")).strip()
    uid = str(session_data.get("userid", "")).strip()

    page_headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 4 Build/RD2A.211001.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/83.0.4103.120 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "platform": "Swiggy-Android",
        "version-code": "1795",
        "model-name": "PIXEL 4",
        "manufacturer": "GOOGLE",
        "application_name": "swiggy-app",
        "appversion": "4.113.0",
        "Origin": EVENTS_HOST,
        "Referer": BYO_PAGE_URL,
        "deviceId": device_id,
        "swuid": device_id,
        "token": token,
        "tid": tid,
        "userid": uid,
        "sessionid": sid,
        "Cookie": f"token={token}; tid={tid}; sid={sid}; user_id={uid}; _session_id={sid}",
    }

    last_error = "The offer slot is currently locked/inactive for this account by Swiggy server."

    # Method 1: Events Webview API (Primary)
    endpoints = [
        f"{EVENTS_HOST}/api/book-your-offer-coupon",
        f"{EVENTS_HOST}/api/book-your-offer",
        f"{EVENTS_HOST}/api/pick-your-offer-coupon"
    ]
    for url in endpoints:
        try:
            async with client.post(
                url,
                headers=page_headers,
                json={"campaign": "book-your-offer", "offerIndex": offer_index},
                timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status == 404:
                    continue
                text = await resp.text()
                try:
                    d = json.loads(text)
                    inner = d.get("data", {})
                    if inner.get("end_date"):
                        return True, f"Breakfast Offer Locked! (Valid till {inner.get('end_date')})"
                    msg = d.get("statusMessage") or d.get("message")
                    if msg:
                        if "SUCCESS" in msg.upper():
                            return True, msg
                        last_error = str(msg)
                except Exception:
                    if resp.status == 200 and not text.strip().startswith("<"):
                        return True, "Offer Locked Successfully!"
                    elif resp.status != 200:
                        last_error = f"Events API Error: HTTP {resp.status}"
                if resp.status != 404:
                    break
        except Exception as e:
            last_error = str(e)

    # Method 2: SPNS Proximity Campaign Fallback
    headers = build_spns_headers(session_data)
    spns_payload = {
        "campaignId": "book-your-offer",
        "senderUserId": uid,
        "senderLocation": {"latitude": 28.6315, "longitude": 77.2167},
        "isReferralFlow": False,
        "offerIndex": offer_index,
        "receivers": [{"userId": uid}],
    }
    try:
        async with client.post(
            SPNS_BASE_URL + CREATE_OFFERS_PATH,
            headers=headers,
            json=spns_payload,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            data = await resp.json(content_type=None)
            if isinstance(data, dict):
                inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                results = inner.get("receiverResults") if isinstance(inner.get("receiverResults"), list) else []
                for res in results:
                    for bl, off in (res.get("offersByBL") or {}).items():
                        if off.get("status") == "SUCCESS":
                            val = _parse_amount(off.get("offerValue"))
                            return True, f"Breakfast Offer Locked! (Rs.{val:.0f} via {bl})"
                        else:
                            err = off.get("errorCode") or "Already claimed or slot locked"
                            if "Error creating offers" not in str(err) and "Missing headers" not in str(err):
                                last_error = str(err)
                msg = data.get("statusMessage")
                if msg and "Error creating offers" not in str(msg) and "Missing headers" not in str(msg):
                    last_error = str(msg)
    except Exception:
        pass

    if "Error creating offers" in last_error or "Missing headers" in last_error:
        last_error = "Account not eligible or offer exhausted for today."

    return False, last_error


async def run_single_breakfast_offer(session_data: dict, offer_index: int, status_msg, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["is_running"] = True
    context.user_data["cancel_requested"] = False
    try:
        offer_info = BREAKFAST_OFFERS.get(offer_index, {"title": f"Option {offer_index}", "desc": ""})
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as client:
            if not await check_account_validity(session_data, client):
                return await process_account_deletion(context, session_data.get("userid"), status_msg)

            await status_msg.edit_text(
                f"🍳 *Claiming Breakfast Offer...*\n\n"
                f"🎁 *Deal:* `{offer_info['title']}`\n"
                f"📝 *Details:* {offer_info['desc']}\n"
                f"🎯 *Attempt:* `1/1` (Single Try)\n"
                f"🔗 *Page:* `book-your-offer`",
                parse_mode="Markdown"
            )

            ok, note = await request_single_breakfast_lock(session_data, offer_index, client)

            res = "🧾 *Breakfast Transaction Receipt:*\n\n"
            if context.user_data.get("cancel_requested"):
                res = "🛑 *Breakfast Operation Aborted!*\n\n"
            
            if ok:
                res += "✅ *Status:* `Success!`\n"
                res += f"🎁 *Deal Locked:* `{offer_info['title']}`\n"
                res += f"ℹ️ *Note:* {note}\n\n"
                res += "🎉 Offer has been added to your Swiggy cart / coupons section!\n"
            else:
                res += "❌ *Status:* `Failed / Locked`\n"
                res += f"🎁 *Deal Tried:* `{offer_info['title']}` (1 Try)\n"
                res += f"⚠️ *Reason:* `{note}`\n\n"
                res += "💡 *Tip:* This deal slot is currently inactive or already claimed. Select another offer from the menu.\n"

            if ok:
                res += "\n✧ *crafted by shivansh* ✧"
            await status_msg.edit_text(res, parse_mode="Markdown")
    finally:
        context.user_data["is_running"] = False


async def run_auto_breakfast_all(session_data: dict, status_msg, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["is_running"] = True
    context.user_data["cancel_requested"] = False
    connector = aiohttp.TCPConnector(ssl=False)
    summary = []
    any_success = False

    try:
        async with aiohttp.ClientSession(connector=connector) as client:
            if not await check_account_validity(session_data, client):
                return await process_account_deletion(context, session_data.get("userid"), status_msg)

            for opt in (1, 2, 3, 4):
                if context.user_data.get("cancel_requested"):
                    break

                info = BREAKFAST_OFFERS[opt]
                try:
                    await status_msg.edit_text(
                        f"🍳 *Auto-Trying All 4 Breakfast Deals...*\n\n"
                        f"🎯 Testing: `[{opt}/4] {info['title']}`\n"
                        f"🔗 Mode: `1 Attempt per offer`",
                        reply_markup=get_cancel_button(),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

                ok, note = await request_single_breakfast_lock(session_data, opt, client)
                if ok:
                    any_success = True
                    summary.append(f"• *{info['title']}*: ✅ {note}")
                    break
                else:
                    summary.append(f"• *{info['title']}*: ❌ {note}")

                await asyncio.sleep(0.35)

        if context.user_data.get("cancel_requested"):
            final = "🛑 *Breakfast Auto-Claim Cancelled!*\n\n"
        else:
            final = "🏆 *Breakfast Auto-Claim Finished!*\n\n"
            
        final += "\n".join(summary) + "\n\n"
        
        if any_success:
            final += "🎉 Offer aapke Swiggy account me apply ho gaya hai!\n\n✧ *crafted by shivansh* ✧\n"
        else:
            final += "⚠️ All 4 offers were tested once, but slots are currently unavailable on Swiggy.\n"

        try:
            await status_msg.edit_text(final, parse_mode="Markdown")
        except Exception:
            pass
    finally:
        context.user_data["is_running"] = False



# ── FEATURE 2.5: PICK LATE NIGHT OFFER ─────────────────────────────────────
async def request_single_night_lock(session_data: dict, offer_index: int, client: aiohttp.ClientSession):
    device_id = get_random_device_id()
    token = str(session_data.get("token", "")).strip()
    tid = str(session_data.get("tid", "")).strip()
    sid = str(session_data.get("sid", "")).strip()
    uid = str(session_data.get("userid", "")).strip()

    page_headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 4 Build/RD2A.211001.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/83.0.4103.120 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "platform": "Swiggy-Android",
        "version-code": "1795",
        "model-name": "PIXEL 4",
        "manufacturer": "GOOGLE",
        "application_name": "swiggy-app",
        "appversion": "4.113.0",
        "Origin": EVENTS_HOST,
        "Referer": NYO_PAGE_URL,
        "deviceId": device_id,
        "swuid": device_id,
        "token": token,
        "tid": tid,
        "userid": uid,
        "sessionid": sid,
        "Cookie": f"token={token}; tid={tid}; sid={sid}; user_id={uid}; _session_id={sid}",
    }

    last_error = "The offer slot is currently locked/inactive for this account by Swiggy server."

    # Method 1: Events Webview API (Primary)
    endpoints = [
        f"{EVENTS_HOST}/api/pick-your-late-night-offer",
        f"{EVENTS_HOST}/api/pick-your-late-night-offer-coupon",
        f"{EVENTS_HOST}/api/pick-your-offer-coupon",
        f"{EVENTS_HOST}/api/book-your-offer-coupon"
    ]
    for url in endpoints:
        try:
            async with client.post(
                url,
                headers=page_headers,
                json={"campaign": "pick-your-late-night-offer", "offerIndex": offer_index},
                timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status == 404:
                    continue
                text = await resp.text()
                try:
                    d = json.loads(text)
                    inner = d.get("data", {})
                    if inner.get("end_date"):
                        return True, f"Late Night Offer Locked! (Valid till {inner.get('end_date')})"
                    msg = d.get("statusMessage") or d.get("message")
                    if msg:
                        if "SUCCESS" in msg.upper():
                            return True, msg
                        last_error = str(msg)
                except Exception:
                    if resp.status == 200 and not text.strip().startswith("<"):
                        return True, "Offer Locked Successfully!"
                    elif resp.status != 200:
                        last_error = f"Events API Error: HTTP {resp.status}"
                if resp.status != 404:
                    break
        except Exception as e:
            last_error = str(e)

    # Method 2: SPNS Proximity Campaign Fallback
    headers = build_spns_headers(session_data)
    spns_payload = {
        "campaignId": "pick-your-late-night-offer",
        "senderUserId": uid,
        "senderLocation": {"latitude": 28.6315, "longitude": 77.2167},
        "isReferralFlow": False,
        "offerIndex": offer_index,
        "receivers": [{"userId": uid}],
    }
    try:
        async with client.post(
            SPNS_BASE_URL + CREATE_OFFERS_PATH,
            headers=headers,
            json=spns_payload,
            timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            data = await resp.json(content_type=None)
            if isinstance(data, dict):
                inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                results = inner.get("receiverResults") if isinstance(inner.get("receiverResults"), list) else []
                for res in results:
                    for bl, off in (res.get("offersByBL") or {}).items():
                        if off.get("status") == "SUCCESS":
                            val = _parse_amount(off.get("offerValue"))
                            return True, f"Late Night Offer Locked! (Rs.{val:.0f} via {bl})"
                        else:
                            err = off.get("errorCode") or "Already claimed or slot locked"
                            if "Error creating offers" not in str(err) and "Missing headers" not in str(err):
                                last_error = str(err)
                msg = data.get("statusMessage")
                if msg and "Error creating offers" not in str(msg) and "Missing headers" not in str(msg):
                    last_error = str(msg)
    except Exception:
        pass

    if "Error creating offers" in last_error or "Missing headers" in last_error:
        last_error = "Account not eligible or offer exhausted for today."

    return False, last_error


async def run_single_night_offer(session_data: dict, offer_index: int, status_msg, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["is_running"] = True
    context.user_data["cancel_requested"] = False
    try:
        offer_info = NIGHT_OFFERS.get(offer_index, {"title": f"Option {offer_index}", "desc": ""})
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as client:
            if not await check_account_validity(session_data, client):
                return await process_account_deletion(context, session_data.get("userid"), status_msg)

            await status_msg.edit_text(
                f"🍔 *Claiming Late Night Offer...*\n\n"
                f"🎁 *Deal:* `{offer_info['title']}`\n"
                f"📝 *Details:* {offer_info['desc']}\n"
                f"🎯 *Attempt:* `1/1` (Single Try)\n"
                f"🔗 *Page:* `pick-your-late-night-offer`",
                parse_mode="Markdown"
            )

            ok, note = await request_single_night_lock(session_data, offer_index, client)

            res = "🧾 *Late Night Transaction Receipt:*\n\n"
            if context.user_data.get("cancel_requested"):
                res = "🛑 *Late Night Operation Aborted!*\n\n"
            
            if ok:
                res += "✅ *Status:* `Success!`\n"
                res += f"🎁 *Deal Locked:* `{offer_info['title']}`\n"
                res += f"ℹ️ *Note:* {note}\n\n"
                res += "🎉 Offer has been added to your Swiggy cart / coupons section!\n"
            else:
                res += "❌ *Status:* `Failed / Locked`\n"
                res += f"🎁 *Deal Tried:* `{offer_info['title']}` (1 Try)\n"
                res += f"⚠️ *Reason:* `{note}`\n\n"
                res += "💡 *Tip:* This deal slot is currently inactive or already claimed. Select another offer from the menu.\n"

            if ok:
                res += "\n✧ *crafted by shivansh* ✧"
            await status_msg.edit_text(res, parse_mode="Markdown")
    finally:
        context.user_data["is_running"] = False


async def run_auto_night_all(session_data: dict, status_msg, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["is_running"] = True
    context.user_data["cancel_requested"] = False
    connector = aiohttp.TCPConnector(ssl=False)
    summary = []
    any_success = False

    try:
        async with aiohttp.ClientSession(connector=connector) as client:
            if not await check_account_validity(session_data, client):
                return await process_account_deletion(context, session_data.get("userid"), status_msg)

            for opt in (1, 2, 3, 4):
                if context.user_data.get("cancel_requested"):
                    break

                info = NIGHT_OFFERS[opt]
                try:
                    await status_msg.edit_text(
                        f"🍔 *Auto-Trying All 4 Late Night Deals...*\n\n"
                        f"🎯 Testing: `[{opt}/4] {info['title']}`\n"
                        f"🔗 Mode: `1 Attempt per offer`",
                        reply_markup=get_cancel_button(),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

                ok, note = await request_single_night_lock(session_data, opt, client)
                if ok:
                    any_success = True
                    summary.append(f"• *{info['title']}*: ✅ {note}")
                    break
                else:
                    summary.append(f"• *{info['title']}*: ❌ {note}")

                await asyncio.sleep(0.35)

        if context.user_data.get("cancel_requested"):
            final = "🛑 *Late Night Auto-Claim Cancelled!*\n\n"
        else:
            final = "🏆 *Late Night Auto-Claim Finished!*\n\n"
            
        final += "\n".join(summary) + "\n\n"
        
        if any_success:
            final += "🎉 Offer aapke Swiggy account me apply ho gaya hai!\n\n✧ *crafted by shivansh* ✧\n"
        else:
            final += "⚠️ All 4 offers were tested once, but slots are currently unavailable on Swiggy.\n"

        try:
            await status_msg.edit_text(final, parse_mode="Markdown")
        except Exception:
            pass
    finally:
        context.user_data["is_running"] = False


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
            if not await check_account_validity(session_data, client):
                return await process_account_deletion(context, session_data.get("userid"), status_msg)

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
        [KeyboardButton("🍳 Breakfast Offer (4 Deals)"), KeyboardButton("🍔 Night Offer (4 Deals)")],
        [KeyboardButton("📱 Authentication"), KeyboardButton("📁 Saved Accounts")],
        [KeyboardButton("🔄 Restart System")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def show_login_choice_markup():
    keyboard = [
        [InlineKeyboardButton("📱 Request OTP", callback_data="login_phone_opt")],
        [InlineKeyboardButton("⚙️ Inject JSON", callback_data="login_json_opt")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_inline_main_markup():
    keyboard = [
        [InlineKeyboardButton("⚡ Start Free Cash Loot", callback_data="opt_cash_loot")],
        [InlineKeyboardButton("🍳 Breakfast", callback_data="opt_byo_menu"), InlineKeyboardButton("🍔 Night", callback_data="opt_nyo_menu")],
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

    # Handle Switch Account from Saved Accounts Menu
    if query.data.startswith("switch_acc_"):
        uid = query.data.replace("switch_acc_", "")
        if "saved_accounts" in context.user_data and uid in context.user_data["saved_accounts"]:
            context.user_data["swiggy_session"] = context.user_data["saved_accounts"][uid]
            await query.message.edit_text(f"✅ Successfully switched active account to ID: `{uid}`", parse_mode="Markdown")
        else:
            await query.message.edit_text(f"⚠️ Account not found in saved list.", parse_mode="Markdown")
        return

    # Handle Clean Invalid Accounts from Saved Accounts Menu
    if query.data == "clean_invalid_accs":
        saved = context.user_data.get("saved_accounts", {})
        if not saved:
            await query.message.edit_text("⚠️ No accounts to clean.")
            return
        
        valid_accounts = {}
        removed_count = 0
        await query.message.edit_text("🧹 *Scanning saved accounts for validity...*", parse_mode="Markdown")
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as client:
            for uid, sess in saved.items():
                if await check_account_validity(sess, client):
                    valid_accounts[uid] = sess
                else:
                    removed_count += 1
        
        context.user_data["saved_accounts"] = valid_accounts
        
        # If the currently active session was removed, clear it
        active_uid = context.user_data.get("swiggy_session", {}).get("userid")
        if active_uid and active_uid not in valid_accounts:
            context.user_data.pop("swiggy_session", None)
            
        await query.message.edit_text(f"🧹 Scan complete.\n✅ Kept: `{len(valid_accounts)}` active accounts.\n❌ Removed: `{removed_count}` expired accounts.", parse_mode="Markdown")
        return

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

    elif query.data == "opt_byo_menu":
        if not session or not session.get("token"):
            context.user_data["next_target"] = "byo_menu"
            await query.message.reply_text("⚠️ *Login Required!*\n\nPlease login first to claim the Breakfast offer.", reply_markup=show_login_choice_markup(), parse_mode="Markdown")
            return

        msg_text = (
            "🍳 *Premium Breakfast Selection*\n"
            "🔗 `events.swiggy.com/book-your-offer`\n\n"
            "Select your favorite deal from the 4 options below (1 Single Try):"
        )
        await query.message.reply_text(msg_text, reply_markup=get_breakfast_options_markup(), parse_mode="Markdown")

    elif query.data.startswith("byo_opt_"):
        choice = query.data.replace("byo_opt_", "")
        if not session or not session.get("token"):
            await query.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        if context.user_data.get("is_running"):
            await query.message.reply_text("⚠️ An operation is already in progress. Please 🛑 Stop it first.")
            return

        if choice == "auto":
            status = await query.message.reply_text("⚡ Initializing *Auto-Claim (1 attempt each across 4 deals)*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
            asyncio.create_task(run_auto_breakfast_all(session, status, context))
        else:
            idx = int(choice)
            status = await query.message.reply_text(f"🍳 Locking *Deal {idx}* (1 Try)...", reply_markup=get_cancel_button(), parse_mode="Markdown")
            asyncio.create_task(run_single_breakfast_offer(session, idx, status, context))

    elif query.data == "opt_nyo_menu":
        if not session or not session.get("token"):
            context.user_data["next_target"] = "nyo_menu"
            await query.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        msg_text = (
            "🍔 *Premium Late Night Selection*\n"
            "🔗 `events.swiggy.com/pick-your-late-night-offer`\n\n"
            "Select your favorite deal from the 4 options below (1 Single Try):"
        )
        await query.message.reply_text(msg_text, reply_markup=get_night_options_markup(), parse_mode="Markdown")

    elif query.data.startswith("nyo_opt_"):
        choice = query.data.replace("nyo_opt_", "")
        if not session or not session.get("token"):
            await query.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        if context.user_data.get("is_running"):
            await query.message.reply_text("⚠️ An operation is already in progress. Please 🛑 Stop it first.")
            return

        if choice == "auto":
            status = await query.message.reply_text("⚡ Initializing *Auto-Claim (1 attempt each across 4 deals)*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
            asyncio.create_task(run_auto_night_all(session, status, context))
        else:
            idx = int(choice)
            status = await query.message.reply_text(f"🍔 Locking *Deal {idx}* (1 Try)...", reply_markup=get_cancel_button(), parse_mode="Markdown")
            asyncio.create_task(run_single_night_offer(session, idx, status, context))

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

    # ── SAVED ACCOUNTS MENU HANDLING ──
    if text == "📁 Saved Accounts":
        saved = context.user_data.get("saved_accounts", {})
        if not saved:
            await update.message.reply_text("⚠️ No saved accounts found. Please authenticate to save one.")
            return
        kb = [[InlineKeyboardButton(f"Account: {uid}", callback_data=f"switch_acc_{uid}")] for uid in saved]
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

    if text in ("🍳 Pick Breakfast Offer (4 Deals)", "🍳 Breakfast Offer (4 Deals)"):
        if not session or not session.get("token"):
            context.user_data["next_target"] = "byo_menu"
            await update.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        msg_text = (
            "🍳 *Premium Breakfast Selection*\n"
            "🔗 `events.swiggy.com/book-your-offer`\n\n"
            "Select your deal from the 4 options below (1 Single Try):"
        )
        await update.message.reply_text(msg_text, reply_markup=get_breakfast_options_markup(), parse_mode="Markdown")
        return

    if text == "🍔 Night Offer (4 Deals)":
        if not session or not session.get("token"):
            context.user_data["next_target"] = "nyo_menu"
            await update.message.reply_text("🔒 *Authentication Required*\n\nPlease securely login to your account first:", reply_markup=show_login_choice_markup())
            return
        msg_text = (
            "🍔 *Premium Late Night Selection*\n"
            "🔗 `events.swiggy.com/pick-your-late-night-offer`\n\n"
            "Select your deal from the 4 options below (1 Single Try):"
        )
        await update.message.reply_text(msg_text, reply_markup=get_night_options_markup(), parse_mode="Markdown")
        return

    if text in ("🔄 Restart System", "/start"):
        await cmd_start(update, context)
        return

    if text == "📱 Authentication":
        await update.message.reply_text("🔐 *System Authentication*\n\nTo access premium features, please securely link your Swiggy account. Select a login method below:", reply_markup=show_login_choice_markup())
        return

    # JSON Session Auto-detect & SAVING
    if (text.startswith("{") and text.endswith("}")) or '"token"' in text or state == "awaiting_json":
        try:
            parsed = parse_session_string(text)
            
            # Save account to memory
            uid = parsed.get("userid", "Unknown")
            if "saved_accounts" not in context.user_data: 
                context.user_data["saved_accounts"] = {}
            context.user_data["saved_accounts"][uid] = parsed
            
            context.user_data["swiggy_session"] = parsed
            context.user_data.pop("state", None)

            target = context.user_data.pop("next_target", None)
            reply_msg = f"🔓 *Authentication Successful!*\n👤 *User ID:* `{uid}`\n(Account automatically saved for future use)\n\n✧ *shivansh* ✧\n"
            await update.message.reply_text(reply_msg, parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

            if target == "cash_loot":
                if context.user_data.get("is_running"): return
                status = await update.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
                asyncio.create_task(run_10_live_users_loot(parsed, status, context, target_success=TARGET_SUCCESS_COUNT))
            elif target in ("byo", "byo_menu"):
                msg_text = (
                    "🍳 *Premium Breakfast Selection*\n"
                    "🔗 `events.swiggy.com/book-your-offer`\n\n"
                    "Select from the 4 deals below:"
                )
                await update.message.reply_text(msg_text, reply_markup=get_breakfast_options_markup(), parse_mode="Markdown")
            elif target == "nyo_menu":
                msg_text = (
                    "🍔 *Premium Late Night Selection*\n"
                    "🔗 `events.swiggy.com/pick-your-late-night-offer`\n\n"
                    "Select from the 4 deals below:"
                )
                await update.message.reply_text(msg_text, reply_markup=get_night_options_markup(), parse_mode="Markdown")
            return
        except Exception as e:
            await update.message.reply_text(f"❌ JSON Parse Error: {str(e)}\nPlease paste it in the correct format.")
            return

    # Direct links or referral links in chat
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

    # Phone input state
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

    # OTP input state & SAVING
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
                            "userid": userid, "token": token,
                            "tid": tid, "sid": temp["sid"],
                        }
                        
                        # Save account to memory
                        if "saved_accounts" not in context.user_data: 
                            context.user_data["saved_accounts"] = {}
                        context.user_data["saved_accounts"][userid] = parsed_session
                        
                        context.user_data["swiggy_session"] = parsed_session
                        context.user_data.pop("temp_auth", None)
                        context.user_data.pop("state", None)

                        target = context.user_data.pop("next_target", None)
                        await update.message.reply_text(f"🔓 *Authentication Successful!*\n👤 *User ID:* `{userid}`\n(Account automatically saved for future use)\n\n✧ *shivansh* ✧", parse_mode="Markdown", reply_markup=get_main_reply_keyboard())

                        if target == "cash_loot":
                            if context.user_data.get("is_running"): return
                            status = await update.message.reply_text("⚡ *Initializing Live Loot Engine* ~ *shivansh*...", reply_markup=get_cancel_button(), parse_mode="Markdown")
                            asyncio.create_task(run_10_live_users_loot(parsed_session, status, context, target_success=TARGET_SUCCESS_COUNT))
                        elif target in ("byo", "byo_menu"):
                            msg_text = (
                                "🍳 *Premium Breakfast Selection*\n"
                                "🔗 `events.swiggy.com/book-your-offer`\n\n"
                                "Select from the 4 deals below:"
                            )
                            await update.message.reply_text(msg_text, reply_markup=get_breakfast_options_markup(), parse_mode="Markdown")
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
