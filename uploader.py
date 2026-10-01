from datetime import datetime, timezone

import pandas as pd
from supabase import Client, create_client

from config import CLEANED_CSV_FILE, require_env

UPSERT_BATCH = 200
DELETE_BATCH = 100
PAGE_SIZE = 1000


def get_client() -> Client:
    url = require_env("SUPABASE_URL")
    key = require_env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def fetch_existing_listings(supabase=None):
    supabase = supabase or get_client()
    listings = []
    start = 0
    while True:
        resp = (
            supabase.table("car_listings")
            .select("listing_id,link")
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        rows = resp.data or []
        listings.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return listings


def fetch_existing_listing_ids(supabase=None):
    return {
        str(row["listing_id"])
        for row in fetch_existing_listings(supabase)
        if row.get("listing_id")
    }


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def upsert_records(records, supabase=None):
    supabase = supabase or get_client()
    seen_at = datetime.now(timezone.utc).isoformat()
    payload = []
    for rec in records:
        row = dict(rec)
        lid = row.get("listing_id")
        if not lid or (isinstance(lid, float) and pd.isna(lid)):
            continue
        row["listing_id"] = str(lid).split(".")[0] if str(lid).endswith(".0") else str(lid)
        row["last_seen_at"] = seen_at
        row["year"] = int(row["year"])
        row["horsepower"] = int(row["horsepower"])
        row["mileage_km"] = int(row["mileage_km"])
        row["price_eur"] = float(row["price_eur"])
        payload.append(row)

    uploaded = 0
    for batch in _chunk(payload, UPSERT_BATCH):
        supabase.table("car_listings").upsert(batch, on_conflict="listing_id").execute()
        uploaded += len(batch)
        print(f"Upserted {uploaded}/{len(payload)} listings.")
    return uploaded


def remove_sold_listings(live_listing_ids, supabase=None, min_live_ratio=0.4):
    """Delete DB rows whose listing_id was not seen in the latest full scrape."""
    supabase = supabase or get_client()
    live = {str(x) for x in live_listing_ids if x}
    existing = fetch_existing_listing_ids(supabase)

    if not live:
        print("No live listing IDs from scrape; skipping sold removal.")
        return 0

    if existing and len(live) < max(50, int(len(existing) * min_live_ratio)):
        print(
            f"Scrape found {len(live)} IDs vs {len(existing)} in DB. "
            "Too few to treat as a full catalog; skipping sold removal."
        )
        return 0

    missing = [lid for lid in existing if lid not in live]
    removed = 0
    for batch in _chunk(missing, DELETE_BATCH):
        supabase.table("car_listings").delete().in_("listing_id", batch).execute()
        removed += len(batch)
        print(f"Removed {removed}/{len(missing)} sold listings.")

    supabase.table("car_listings").delete().is_("listing_id", "null").execute()
    print(f"Sold cleanup complete. Removed {removed} listings.")
    return removed


def delete_listing_ids(listing_ids, supabase=None):
    supabase = supabase or get_client()
    ids = [str(x) for x in listing_ids if x]
    removed = 0
    for batch in _chunk(ids, DELETE_BATCH):
        supabase.table("car_listings").delete().in_("listing_id", batch).execute()
        removed += len(batch)
        print(f"Removed {removed}/{len(ids)} sold listings.")
    return removed


def upload_to_supabase(csv_file=CLEANED_CSV_FILE, replace_all=False):
    print("Connecting to Supabase...")
    supabase = get_client()
    df = pd.read_csv(csv_file)
    records = df.to_dict(orient="records")

    if replace_all:
        print("Clearing table (replace_all=True)...")
        try:
            supabase.rpc("truncate_and_restart_cars").execute()
        except Exception as e:
            print(f"RPC reset notice: {e}. Falling back to row delete.")
            supabase.table("car_listings").delete().neq("make", "PlaceholderToWipeAll").execute()

    uploaded = upsert_records(records, supabase=supabase)
    print(f"Upload complete: {uploaded} listings.")
    return uploaded


if __name__ == "__main__":
    upload_to_supabase()
