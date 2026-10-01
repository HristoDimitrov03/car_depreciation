import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

os.environ.setdefault("PYTHONUNBUFFERED", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

from config import LAST_SYNC_FILE, ROOT_DIR
from parser import listings_to_dataframe
from scraper import ingest_mobile_bg, skoda_model_urls, skoda_search_urls
from sold_check import find_sold_listing_ids
from uploader import (
    delete_listing_ids,
    fetch_existing_listing_ids,
    fetch_existing_listings,
    remove_sold_listings,
    upsert_records,
)

TASK_NAME = "SkodaMobileBgDailySync"


def write_sync_log(payload):
    with open(LAST_SYNC_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_sync_log():
    if not os.path.exists(LAST_SYNC_FILE):
        return {}
    try:
        with open(LAST_SYNC_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def already_ran_today(mode):
    log = read_sync_log()
    if not log.get("ok"):
        return False
    finished = str(log.get("finished_at") or "")
    today = datetime.now(timezone.utc).date().isoformat()
    return finished.startswith(today) and log.get("mode") == mode


def upsert_scraped_listings(listings, return_ids=False):
    df = listings_to_dataframe(listings)
    records = df.to_dict(orient="records")
    uploaded = upsert_records(records)
    if return_ids:
        return uploaded, len(records), [str(r["listing_id"]) for r in records]
    return uploaded, len(records)


def run_full_sync(headless=True):
    """Scrape every Skoda search, upsert live ads, delete ads no longer listed."""
    os.chdir(ROOT_DIR)
    started = datetime.now(timezone.utc).isoformat()
    print("Starting full Skoda catalog scrape...")
    listings = ingest_mobile_bg(
        search_urls=skoda_model_urls(),
        known_ids=None,
        headless=headless,
        scan_unlisted_models=True,
    )
    live_ids = [item["listing_id"] for item in listings if item.get("listing_id")]

    if not live_ids:
        write_sync_log({"started_at": started, "ok": False, "error": "scrape_empty"})
        raise SystemExit("Scrape returned no listings; database was not changed.")

    uploaded, parsed, valid_ids = upsert_scraped_listings(listings, return_ids=True)
    # Only ads that passed validation stay. Live ads with missing specs are
    # removed too, because a stored row with wrong values is worse than none.
    removed = remove_sold_listings(valid_ids)

    result = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "mode": "full",
        "scraped": len(listings),
        "parsed": parsed,
        "upserted": uploaded,
        "removed_sold": removed,
    }
    write_sync_log(result)
    print(json.dumps(result, indent=2))
    return result


def run_daily_sync(headless=True, skip_if_done=False):
    """Once per day: ingest newly posted Skodas, then drop sold/inactive ads."""
    os.chdir(ROOT_DIR)
    if skip_if_done and already_ran_today("daily"):
        print("Daily sync already completed today. Skipping.")
        return read_sync_log()

    print("Loading known listing IDs from the database...")
    known_ids = fetch_existing_listing_ids()
    if not known_ids:
        print("Database is empty; running a full catalog scrape first.")
        return run_full_sync(headless=headless)

    started = datetime.now(timezone.utc).isoformat()
    print(f"Starting daily new-listing scrape ({len(known_ids)} known ads)...")
    listings = ingest_mobile_bg(
        search_urls=skoda_search_urls(newest_first=True),
        known_ids=known_ids,
        headless=headless,
    )
    new_raw = [item for item in listings if item.get("listing_id") not in known_ids]
    # Upsert every scanned card, not only new ones, so edited prices and specs on
    # already-known ads are refreshed too.
    uploaded, parsed = upsert_scraped_listings(listings) if listings else (0, 0)
    print(f"New ads scraped: {len(new_raw)}; scanned ads upserted: {uploaded}.")

    stored = fetch_existing_listings()
    sold_ids = find_sold_listing_ids(stored)
    if stored and len(sold_ids) > max(50, int(len(stored) * 0.4)):
        print(
            f"Sold check flagged {len(sold_ids)} of {len(stored)} ads. "
            "Too many to treat as real sales; skipping deletion."
        )
        removed = 0
    else:
        removed = delete_listing_ids(sold_ids) if sold_ids else 0

    result = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "mode": "daily",
        "scraped": len(listings),
        "new_listings": len(new_raw),
        "parsed": parsed,
        "upserted": uploaded,
        "removed_sold": removed,
    }
    write_sync_log(result)
    print(json.dumps(result, indent=2))
    return result


def install_windows_daily_task(hour="06:30"):
    python = sys.executable
    script = os.path.join(ROOT_DIR, "daily_sync.py")
    tr = f'cmd /c cd /d "{ROOT_DIR}" && "{python}" "{script}" --daily --once-per-day'
    cmd = [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/TR",
        tr,
        "/SC",
        "DAILY",
        "/ST",
        hour,
        "/F",
    ]
    print("Installing Windows Task Scheduler job:")
    print(" ".join(cmd))
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr)
        raise SystemExit("Could not create the scheduled task. Run the terminal as Administrator if needed.")
    print(completed.stdout or "Scheduled task created.")
    print(f"The scraper will run once per day at {hour}.")


def main():
    parser = argparse.ArgumentParser(description="Skoda mobile.bg catalog sync")
    parser.add_argument("--full", action="store_true", help="Scrape every Skoda listing")
    parser.add_argument("--daily", action="store_true", help="Daily new + sold sync")
    parser.add_argument("--once-per-day", action="store_true", help="Skip if daily sync already succeeded today")
    parser.add_argument("--install-task", action="store_true", help="Register the Windows daily task")
    parser.add_argument("--time", default="06:30", help="Daily run time for --install-task (HH:MM)")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()
    headless = not args.headed

    if args.install_task:
        install_windows_daily_task(hour=args.time)
        return
    if args.full:
        run_full_sync(headless=headless)
        return
    run_daily_sync(headless=headless, skip_if_done=args.once_per_day)


if __name__ == "__main__":
    main()
