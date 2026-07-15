"""
Parks Canada Campsite Availability Checker
==========================================
Uses Parks Canada's internal API directly — no browser, no scraping.
Much faster and more reliable than Playwright.

The mapId=-2147483646 is the Lake Louise Soft-sided Campground map ID,
discovered from the URL: reservation.pc.gc.ca/create-booking/results?mapId=-2147483646

Setup:
  pip install requests twilio python-dotenv

Create a .env file with:
  TWILIO_ACCOUNT_SID=your_account_sid
  TWILIO_AUTH_TOKEN=your_auth_token
  TWILIO_FROM=+1xxxxxxxxxx
  TWILIO_TO=+1xxxxxxxxxx
"""

import os
import random
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

# mapId for Lake Louise Soft-sided Campground
# Source: reservation.pc.gc.ca/create-booking/results?mapId=-2147483646
MAP_ID = -2147483646

SEARCH_CONFIG = {
    "checkin":    "2026-08-07",   # YYYY-MM-DD
    "checkout":   "2026-08-08",   # YYYY-MM-DD
}

BOOKING_URL = f"https://reservation.pc.gc.ca/create-booking/results?mapId={MAP_ID}&searchTabGroupId=0&bookingCategoryId=0"

# How often to check in server mode (seconds)
POLL_INTERVAL_BASE = 300

# Twilio
TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM  = os.getenv("TWILIO_FROM")
TWILIO_TO    = os.getenv("TWILIO_TO")

# ── Alert ──────────────────────────────────────────────────────────────────────

def send_sms(message: str):
    if not all([TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_TO]):
        print(f"⚠️  Twilio not configured — would have sent: {message}")
        return
    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=message, from_=TWILIO_FROM, to=TWILIO_TO)
        print(f"✅ SMS sent!")
    except Exception as e:
        print(f"❌ SMS failed: {e}")

# ── Checker ────────────────────────────────────────────────────────────────────

def check_availability() -> bool | None:
    """
    Calls Parks Canada's availability API directly.
    Returns True if available, False if not, None if check failed.
    """
    checkin  = SEARCH_CONFIG["checkin"]
    checkout = SEARCH_CONFIG["checkout"]

    # Parks Canada's internal availability API endpoint
    # Parameters extracted from the real booking URL
    api_url = (
        f"https://reservation.pc.gc.ca/api/availability/map"
        f"?mapId={MAP_ID}"
        f"&bookingCategoryId=0"
        f"&startDate={checkin}"
        f"&endDate={checkout}"
        f"&lang=en-CA"
        f"&equipmentId=-32768"          # tent
        f"&subEquipmentId=-32767"       # medium tent
        f"&resourceLocationId=-2147483640"   # Lake Louise Campground
        f"&transactionLocationId=-2147483647" # Banff-Lake Louise park
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-CA,en;q=0.9",
        "Referer": "https://reservation.pc.gc.ca/",
        "Origin": "https://reservation.pc.gc.ca",
    }

    try:
        print(f"[{now()}] Checking Parks Canada API...")
        resp = requests.get(api_url, headers=headers, timeout=15)
        print(f"[{now()}] Response status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"[{now()}] ⚠️  Unexpected status code: {resp.status_code}")
            print(f"[{now()}] Response: {resp.text[:300]}")
            return None

        data = resp.json()
        print(f"[{now()}] API response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        print(f"[{now()}] Full response (first 500 chars): {str(data)[:500]}")

        # Parks Canada API returns availability per resource (campsite)
        # Look for any site that is available
        if isinstance(data, list):
            available = [item for item in data if item.get("availability") == 1 or item.get("isAvailable") == True]
            print(f"[{now()}] Total sites: {len(data)}, Available: {len(available)}")
            return len(available) > 0

        if isinstance(data, dict):
            # The top-level map just groups sub-maps (campground loops).
            # Real availability is in resourceAvailabilities (individual sites).
            # We need to query each sub-map to get resourceAvailabilities.
            link_avail = data.get("mapLinkAvailabilities", {})
            resource_avail = data.get("resourceAvailabilities", {})

            print(f"[{now()}] Sub-maps found: {list(link_avail.keys())}")
            print(f"[{now()}] Top-level resources: {resource_avail}")

            # If top-level already has resource availability, check it
            # availability code 1 = available, 0 = closed, 2 = unavailable, 3 = non-reservable
            if resource_avail:
                available_sites = [rid for rid, codes in resource_avail.items()
                                   if isinstance(codes, list) and 1 in codes]
                print(f"[{now()}] Available sites at top level: {available_sites}")
                if available_sites:
                    return True

            # Drill into each sub-map (campground loop) to find actual site availability
            all_available = []
            for sub_map_id in link_avail.keys():
                sub_url = (
                    f"https://reservation.pc.gc.ca/api/availability/map"
                    f"?mapId={sub_map_id}"
                    f"&bookingCategoryId=0"
                    f"&startDate={checkin}"
                    f"&endDate={checkout}"
                    f"&lang=en-CA"
                    f"&equipmentId=-32768"
                    f"&subEquipmentId=-32767"
                    f"&resourceLocationId=-2147483640"
                    f"&transactionLocationId=-2147483647"
                )
                try:
                    sub_resp = requests.get(sub_url, headers=headers, timeout=10)
                    if sub_resp.status_code == 200:
                        sub_data = sub_resp.json()
                        sub_resources = sub_data.get("resourceAvailabilities", {})
                        available = [rid for rid, codes in sub_resources.items()
                                     if isinstance(codes, list) and 1 in codes]
                        print(f"[{now()}] Sub-map {sub_map_id}: {len(sub_resources)} sites, {len(available)} available")
                        all_available.extend(available)
                except Exception as e:
                    print(f"[{now()}] Sub-map {sub_map_id} error: {e}")

            print(f"[{now()}] Total available sites: {len(all_available)}")
            return len(all_available) > 0

        print(f"[{now()}] ⚠️  Unexpected response format: {type(data)}")
        return None

    except requests.exceptions.Timeout:
        print(f"[{now()}] ❌ Request timed out")
        return None
    except Exception as e:
        print(f"[{now()}] ❌ Error: {e}")
        return None

# ── Helpers ────────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def jitter(base: int, spread: int = 30) -> int:
    return base + random.randint(-spread, spread)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    cfg = SEARCH_CONFIG
    single_check = os.getenv("SINGLE_CHECK", "false").lower() == "true"

    print("=" * 60)
    print("  Parks Canada Campsite Availability Checker")
    print("=" * 60)
    print(f"  Campground : Lake Louise Soft-sided (mapId={MAP_ID})")
    print(f"  Dates      : {cfg['checkin']} → {cfg['checkout']}")
    print(f"  Mode       : {'single check (GitHub Actions)' if single_check else f'poll every ~{POLL_INTERVAL_BASE // 60} min'}")
    print("=" * 60)

    consecutive_failures = 0

    while True:
        result = check_availability()

        if result is True:
            message = (
                f"🏕️ CAMPSITE AVAILABLE! Lake Louise Soft-sided "
                f"{cfg['checkin']} → {cfg['checkout']} "
                f"— Book now: {BOOKING_URL}"
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
                send_sms("⚠️ Campsite checker failed 5x in a row — check the script.")
                consecutive_failures = 0

        if single_check:
            print(f"[{now()}] Single-check mode — done.")
            break

        wait = jitter(POLL_INTERVAL_BASE)
        print(f"[{now()}] Checking again in {wait // 60}m {wait % 60}s...")
        time.sleep(wait)

if __name__ == "__main__":
    main()
