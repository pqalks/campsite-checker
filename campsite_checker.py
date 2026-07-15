"""
Parks Canada - Code Detective Script
Queries the J+K loop for both available and unavailable dates
and prints ALL site IDs and codes so we can identify K6 and K7.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
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

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def main():
    single_check = os.getenv("SINGLE_CHECK", "false").lower() == "true"

    print("=" * 60)
    print("  CODE DETECTIVE — Finding K6 and K7 site IDs")
    print("=" * 60)

    MAP_JK = -2147483642  # J+K loop

    # Query Sep 22-23 (known available — K7 is green)
    print(f"\n[{now()}] Querying Sep 22-23 (K7 = AVAILABLE, K6 = UNAVAILABLE)...")
    try:
        data_sep = query_map(MAP_JK, "2026-09-22", "2026-09-23")
        resources_sep = data_sep.get("resourceAvailabilities", {})
        print(f"Total sites in J+K loop: {len(resources_sep)}")
        print(f"\nAll sites — Sep 22-23:")
        for rid, codes in sorted(resources_sep.items(), key=lambda x: int(x[0])):
            print(f"  Site ID {rid}: codes={codes}")
    except Exception as e:
        print(f"Error: {e}")
        resources_sep = {}

    # Query Aug 7-8 (known unavailable)
    print(f"\n[{now()}] Querying Aug 7-8 (all UNAVAILABLE)...")
    try:
        data_aug = query_map(MAP_JK, "2026-08-07", "2026-08-08")
        resources_aug = data_aug.get("resourceAvailabilities", {})
        print(f"\nAll sites — Aug 7-8:")
        for rid, codes in sorted(resources_aug.items(), key=lambda x: int(x[0])):
            print(f"  Site ID {rid}: codes={codes}")
    except Exception as e:
        print(f"Error: {e}")
        resources_aug = {}

    # Compare — find sites where codes differ
    print(f"\n[{now()}] Sites where codes DIFFER between the two dates:")
    all_ids = set(resources_sep.keys()) | set(resources_aug.keys())
    for rid in sorted(all_ids, key=lambda x: int(x)):
        c_aug = resources_aug.get(rid, "missing")
        c_sep = resources_sep.get(rid, "missing")
        if c_aug != c_sep:
            print(f"  *** Site {rid}: Aug 7-8={c_aug}  Sep 22-23={c_sep}  ← DIFFERENT")
        else:
            print(f"      Site {rid}: Aug 7-8={c_aug}  Sep 22-23={c_sep}  (same)")

    if single_check:
        print(f"\n[{now()}] Done. Check the output above, then tell me which site IDs are K6 and K7!")

if __name__ == "__main__":
    main()
