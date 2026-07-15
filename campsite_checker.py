"""
Parks Canada Campsite Availability Checker
==========================================
Checks Lake Louise Soft-sided campground for tent availability.

DECODED availability codes (from comparing known dates):
  0 = AVAILABLE (bookable)
  1 = UNAVAILABLE
  4 = Not Operating / Non-Reservable
"""

import os
import random
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

MAP_ID_PARENT = -2147483646  # Lake Louise Soft-sided (parent map)

SEARCH_CONFIG = {
    "checkin":  "2026-09-22",
    "checkout": "2026-09-23",
}

BOOKING_URL = (
    "https://reservation.pc.gc.ca/create-booking/results"
    "?mapId=-2147483646&searchTabGroupId=0&bookingCategoryId=0"
    "&transactionLocationId=-2147483647&resourceLocationId=-2147483640"
    "&startDate=2026-08-07&endDate=2026-08-08&nights=1&isReserving=true"
    "&equipmentId=-32768&subEquipmentId=-32767"
)

POLL_INTERVAL_BASE = 300  # 5 minutes

# Telegram-specific variables (replaces Twilio config)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# ── Alert ──────────────────────────────────────────────────────────────────────

def send_sms(message: str):
    """
    Keeps the function name intact but routes the message payload
    directly through Telegram's free Bot API.
    """
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
        print(f"⚠️  Telegram not configured — would have sent: {message}")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        print(f"✅ Telegram notification sent!")
    except Exception as e:
        print(f"❌ Telegram alert failed: {e}")

# ── API ────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://reservation.pc.gc.ca/",
    "Origin": "https://reservation.pc.gc.ca",
}

def query_map(map_id, checkin, checkout):
    url = (
        f"https://reservation.pc.gc.ca/api/availability/map"
        f"?mapId={map_id}"
        f"&bookingCategoryId=0"
        f"&startDate={checkin}"
        f"&endDate={checkout}"
        f"&lang=en-CA"
        f"&equipmentId=-32768"
        f"&subEquipmentId=-32767"
        f"&resourceLocationId=-2147483640"
        f"&transactionLocationId=-2147483647"
    )
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()

# ── Checker ────────────────────────────────────────────────────────────────────

def check_availability() -> bool | None:
    checkin  = SEARCH_CONFIG["checkin"]
    checkout = SEARCH_CONFIG["checkout"]

    try:
        print(f"[{now()}] Querying parent map...")
        parent_data = query_map(MAP_ID_PARENT, checkin, checkout)
        sub_maps = list(parent_data.get("mapLinkAvailabilities", {}).keys())
        print(f"[{now()}] Sub-maps: {sub_maps}")

        all_available = []

        for sub_map_id in sub_maps:
            sub_data      = query_map(sub_map_id, checkin, checkout)
            sub_resources = sub_data.get("resourceAvailabilities", {})

            # availability=0 means AVAILABLE (decoded from comparing known dates)
            available = [
                rid for rid, entries in sub_resources.items()
                if isinstance(entries, list)
                and any(
                    isinstance(e, dict) and e.get("availability") == 0
                    for e in entries
                )
            ]

            unavailable = [
                rid for rid, entries in sub_resources.items()
                if isinstance(entries, list)
                and any(
                    isinstance(e, dict) and e.get("availability") == 1
                    for e in entries
                )
            ]

            print(f"[{now()}] Sub-map {sub_map_id}: {len(sub_resources)} sites — "
                  f"{len(available)} available, {len(unavailable)} unavailable")

            if available:
                print(f"[{now()}]   ✅ Available site IDs: {available}")

            all_available.extend(available)

        print(f"[{now()}] Total available sites: {len(all_available)}")
        return len(all_available) > 0

    except Exception as e:
        print(f"[{now()}] ❌ Error: {e}")
        return None

# ── Helpers ────────────────────────────────────────────────────────────────────

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def jitter(base, spread=30):
    return base + random.randint(-spread, spread)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    single_check = os.getenv("SINGLE_CHECK", "false").lower() == "true"

    print("=" * 60)
    print("  Parks Canada Campsite Availability Checker")
    print("=" * 60)
    print(f"  Campground : Lake Louise Soft-sided")
    print(f"  Dates      : {SEARCH_CONFIG['checkin']} → {SEARCH_CONFIG['checkout']}")
    print(f"  Logic      : availability=0 means AVAILABLE")
    print(f"  Mode       : {'single check (GitHub Actions)' if single_check else f'poll every ~{POLL_INTERVAL_BASE // 60} min'}")
    print("=" * 60)

    consecutive_failures = 0

    while True:
        result = check_availability()

        if result is True:
            message = (
                f"CAMPSITE AVAILABLE! Lake Louise Soft-sided "
                f"{SEARCH_CONFIG['checkin']} to {SEARCH_CONFIG['checkout']} "
                f"Book now: {BOOKING_URL}"
            )
            print(f"\n[{now()}] ✅ {message}\n")
            send_sms(message)
            consecutive_failures = 0

        elif result is False:
            print(f"[{now()}] No availability.")
            consecutive_failures = 0

        else:
            consecutive_failures += 1
            print(f"[{now()}] Check failed ({consecutive_failures} in a row).")
            if consecutive_failures >= 5:
                send_sms("Campsite checker failed 5x in a row — check the script.")
                consecutive_failures = 0

        if single_check:
            print(f"[{now()}] Single-check mode — done.")
            break

        wait = jitter(POLL_INTERVAL_BASE)
        print(f"[{now()}] Checking again in {wait // 60}m {wait % 60}s...")
        time.sleep(wait)

if __name__ == "__main__":
    main()
