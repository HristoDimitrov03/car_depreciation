import { createClient } from "@supabase/supabase-js";

import type { Listing } from "./types";

const PAGE_SIZE = 1000;

const LISTING_COLUMNS =
  "id,make,model,year,fuel_type,transmission,horsepower,mileage_km,price_eur,link,listing_id";

export type DataFreshness = {
  lastSyncedAt: string | null;
  liveCount: number;
};

function publicClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY.",
    );
  }
  return createClient(url, key);
}

export async function fetchAllListings(): Promise<Listing[]> {
  const supabase = publicClient();
  const rows: Listing[] = [];
  let start = 0;

  while (true) {
    const { data, error } = await supabase
      .from("car_listings")
      .select(LISTING_COLUMNS)
      .order("id", { ascending: true })
      .range(start, start + PAGE_SIZE - 1);

    if (error) {
      throw new Error(`Could not load listings: ${error.message}`);
    }

    const batch = (data ?? []) as Listing[];
    rows.push(...batch);
    if (batch.length < PAGE_SIZE) {
      break;
    }
    start += PAGE_SIZE;
  }

  return rows;
}

export async function fetchDataFreshness(): Promise<DataFreshness> {
  const supabase = publicClient();
  const { data, error, count } = await supabase
    .from("car_listings")
    .select("last_seen_at", { count: "exact" })
    .order("last_seen_at", { ascending: false, nullsFirst: false })
    .limit(1);

  if (error) {
    throw new Error(`Could not load data freshness: ${error.message}`);
  }

  const lastSyncedAt =
    data && data.length > 0
      ? ((data[0] as { last_seen_at?: string | null }).last_seen_at ?? null)
      : null;

  return {
    lastSyncedAt,
    liveCount: count ?? 0,
  };
}

export function formatSyncTime(iso: string | null): string {
  if (!iso) return "unknown";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "unknown";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}
