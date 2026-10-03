"use client";

import { useEffect, useMemo, useState } from "react";

import { DealTable } from "@/components/DealTable";
import { Filters } from "@/components/Filters";
import { Metrics } from "@/components/Metrics";
import { ScatterChart } from "@/components/ScatterChart";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  applyFilters,
  uniqueSorted,
  type DashboardFilters,
} from "@/lib/filters";
import { formatSyncTime, type DataFreshness } from "@/lib/listings";
import {
  FUEL_OPTIONS,
  TRANSMISSION_OPTIONS,
  YEAR_MAX,
  YEAR_MIN,
  type Listing,
} from "@/lib/types";

function defaultFilters(listings: Listing[]): DashboardFilters {
  const brands = uniqueSorted(listings.map((row) => row.make));
  const make = brands.includes("Skoda") ? "Skoda" : (brands[0] ?? "");
  return {
    make,
    model: "any",
    yearFrom: YEAR_MIN,
    yearTo: YEAR_MAX,
    fuels: [...FUEL_OPTIONS],
    transmissions: [...TRANSMISSION_OPTIONS],
    hpFrom: 0,
    hpTo: null,
    maxMileage: "any",
  };
}

export function Dashboard({
  listings,
  freshness,
}: {
  listings: Listing[];
  freshness: DataFreshness;
}) {
  const [filters, setFilters] = useState<DashboardFilters>(() =>
    defaultFilters(listings),
  );
  const [chartTab, setChartTab] = useState<"year" | "mileage">("year");

  const brands = uniqueSorted(listings.map((row) => row.make));
  const models = uniqueSorted(
    listings
      .filter((row) => row.make === filters.make)
      .map((row) => row.model),
  );

  const modelKey = models.join("|");

  useEffect(() => {
    if (filters.model === "any") return;
    const available = modelKey.split("|").filter(Boolean);
    if (available.length === 0) return;
    if (!available.includes(filters.model)) {
      setFilters((current) => ({
        ...current,
        model: "any",
      }));
    }
  }, [filters.model, modelKey]);

  const filtered = useMemo(
    () => applyFilters(listings, filters),
    [listings, filters],
  );

  const avgPrice =
    filtered.reduce((sum, row) => sum + Number(row.price_eur || 0), 0) /
    (filtered.length || 1);
  const avgMileage =
    filtered.reduce((sum, row) => sum + Number(row.mileage_km || 0), 0) /
    (filtered.length || 1);

  return (
    <div className="mx-auto w-full max-w-7xl px-3 py-4 sm:px-4 sm:py-8">
      <header className="mb-5 sm:mb-6">
        <div className="flex items-start justify-between gap-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)] sm:text-xs sm:tracking-[0.2em]">
            Car market tracker
          </p>
          <ThemeToggle />
        </div>
        <h1 className="mt-2 text-2xl font-semibold leading-tight text-[var(--fg)] sm:text-4xl">
          Bulgarian Used Car Market: Skoda
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--muted)] sm:mt-3 sm:text-base">
          Live depreciation tracking for Skoda listings from mobile.bg.
        </p>
        <p
          className="mt-3 inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-1 rounded-full border border-[var(--chip-border)] bg-[var(--chip-bg)] px-3 py-1.5 text-xs text-[var(--chip-fg)] sm:mt-4"
          title={
            freshness.lastSyncedAt
              ? `Newest last_seen_at in Supabase: ${freshness.lastSyncedAt}`
              : "No last_seen_at values found"
          }
        >
          <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
          <span>
            Last sync:{" "}
            <span className="font-medium text-[var(--chip-strong)]">
              {formatSyncTime(freshness.lastSyncedAt)}
            </span>
          </span>
          <span className="opacity-40">·</span>
          <span>
            <span className="font-medium text-[var(--chip-strong)]">
              {freshness.liveCount.toLocaleString("en-US")}
            </span>{" "}
            live ads
          </span>
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-6">
        <Filters
          brands={brands}
          models={models}
          filters={filters}
          onChange={setFilters}
        />

        <main className="min-w-0 space-y-5 sm:space-y-8">
          {filtered.length === 0 ? (
            <div className="rounded-2xl border border-[var(--empty-border)] bg-[var(--empty-bg)] p-4 text-sm text-[var(--empty-fg)] sm:p-6 sm:text-base">
              No listings match the current filters. Please adjust your
              criteria.
            </div>
          ) : (
            <>
              <Metrics
                count={filtered.length}
                avgPrice={avgPrice}
                avgMileage={avgMileage}
              />

              <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-3 sm:p-6">
                <div className="mb-3 flex flex-col gap-3 sm:mb-4 sm:flex-row sm:items-end sm:justify-between">
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-[var(--fg)] sm:text-lg">
                      Depreciation Curves
                    </h2>
                    <p className="mt-1 text-xs text-[var(--muted)] sm:text-sm">
                      Tap a circle to open its mobile.bg offer. Pinch to zoom,
                      drag to move.
                    </p>
                    <p className="mt-1 hidden text-sm text-[var(--muted)] sm:block">
                      Drag to move the chart. Double-click to reset.
                    </p>
                  </div>
                  <div className="grid w-full grid-cols-2 gap-1 rounded-lg border border-[var(--border)] p-1 sm:flex sm:w-auto">
                    <button
                      type="button"
                      className={`rounded-md px-2 py-2 text-center text-xs sm:px-3 sm:py-1.5 sm:text-sm ${
                        chartTab === "year"
                          ? "bg-[var(--tab-active-bg)] text-[var(--tab-active-fg)]"
                          : "text-[var(--muted-strong)]"
                      }`}
                      onClick={() => setChartTab("year")}
                    >
                      vs Year
                    </button>
                    <button
                      type="button"
                      className={`rounded-md px-2 py-2 text-center text-xs sm:px-3 sm:py-1.5 sm:text-sm ${
                        chartTab === "mileage"
                          ? "bg-[var(--tab-active-bg)] text-[var(--tab-active-fg)]"
                          : "text-[var(--muted-strong)]"
                      }`}
                      onClick={() => setChartTab("mileage")}
                    >
                      vs Mileage
                    </button>
                  </div>
                </div>

                <div className="min-w-0 overflow-hidden">
                  {chartTab === "year" ? (
                    <ScatterChart
                      listings={filtered}
                      x="year"
                      title="Price vs Year"
                      xTitle="Year"
                    />
                  ) : (
                    <ScatterChart
                      listings={filtered}
                      x="mileage_km"
                      title="Price vs Mileage"
                      xTitle="Mileage (km)"
                    />
                  )}
                </div>
              </section>

              <section className="min-w-0">
                <h2 className="text-base font-semibold text-[var(--fg)] sm:text-lg">
                  Deal Finder
                </h2>
                <p className="mb-3 mt-1 text-xs text-[var(--muted)] sm:mb-4 sm:text-sm">
                  Sort by year, price, horsepower, or mileage.
                </p>
                <DealTable listings={filtered} />
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
