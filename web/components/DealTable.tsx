"use client";

import { useEffect, useMemo, useState } from "react";

import { formatKm, formatPrice, sortDeals, type DealSortKey } from "@/lib/filters";
import type { Listing } from "@/lib/types";

const PAGE_SIZE = 50;

type SortableKey = Extract<
  DealSortKey,
  "year" | "price_eur" | "horsepower" | "mileage_km"
>;

type SortState = {
  key: DealSortKey;
  direction: "asc" | "desc";
};

type Props = {
  listings: Listing[];
};

const SORT_OPTIONS: Array<{ key: SortableKey; label: string }> = [
  { key: "year", label: "Year" },
  { key: "price_eur", label: "Price" },
  { key: "horsepower", label: "Horsepower" },
  { key: "mileage_km", label: "Mileage" },
];

function sortMark(active: boolean, direction: "asc" | "desc") {
  if (!active) return "";
  return direction === "asc" ? " ↑" : " ↓";
}

export function DealTable({ listings }: Props) {
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortState>({
    key: "year",
    direction: "desc",
  });

  const sorted = useMemo(
    () => sortDeals(listings, sort.key, sort.direction),
    [listings, sort],
  );

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));

  useEffect(() => {
    setPage(0);
  }, [listings, sort]);

  const safePage = Math.min(page, pageCount - 1);
  const slice = sorted.slice(
    safePage * PAGE_SIZE,
    safePage * PAGE_SIZE + PAGE_SIZE,
  );

  function toggleSort(key: SortableKey) {
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "year" ? "desc" : "asc" },
    );
  }

  const headerButton =
    "inline-flex items-center whitespace-nowrap font-medium uppercase tracking-wide text-[var(--muted)] hover:text-[var(--fg)]";

  const pager = (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--muted)]">
      <p>
        Showing {slice.length} of {sorted.length}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 disabled:opacity-40"
          disabled={safePage === 0}
          onClick={() => setPage((current) => Math.max(0, current - 1))}
        >
          Prev
        </button>
        <span className="px-1 py-1.5">
          {safePage + 1}/{pageCount}
        </span>
        <button
          type="button"
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 disabled:opacity-40"
          disabled={safePage >= pageCount - 1}
          onClick={() =>
            setPage((current) => Math.min(pageCount - 1, current + 1))
          }
        >
          Next
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-3">
      {/* Mobile: sort controls + cards */}
      <div className="space-y-3 md:hidden">
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <select
            className="rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5 text-sm text-[var(--fg)]"
            value={sort.key}
            onChange={(e) => {
              const key = e.target.value as SortableKey;
              setSort((current) => ({
                key,
                direction:
                  key === current.key
                    ? current.direction
                    : key === "year"
                      ? "desc"
                      : "asc",
              }));
            }}
            aria-label="Sort by"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.key} value={option.key}>
                Sort: {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded-lg border border-[var(--border)] px-3 py-2.5 text-sm text-[var(--fg)]"
            onClick={() =>
              setSort((current) => ({
                ...current,
                direction: current.direction === "asc" ? "desc" : "asc",
              }))
            }
            aria-label="Toggle sort direction"
          >
            {sort.direction === "asc" ? "Asc ↑" : "Desc ↓"}
          </button>
        </div>

        <div className="space-y-2">
          {slice.map((row) => (
            <article
              key={row.listing_id || String(row.id)}
              className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-[var(--fg)]">
                    {row.make} {row.model}
                  </p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    {row.year} · {row.fuel_type} · {row.transmission}
                  </p>
                </div>
                <p className="shrink-0 text-sm font-semibold text-[var(--fg)]">
                  {formatPrice(row.price_eur)}
                </p>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-[var(--muted)]">
                <p>
                  Mileage:{" "}
                  <span className="text-[var(--fg)]">
                    {formatKm(row.mileage_km)}
                  </span>
                </p>
                <p>
                  HP:{" "}
                  <span className="text-[var(--fg)]">{row.horsepower}</span>
                </p>
              </div>
              {row.link ? (
                <a
                  href={row.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex text-sm font-medium text-[var(--accent)]"
                >
                  Open Offer
                </a>
              ) : null}
            </article>
          ))}
        </div>
        {pager}
      </div>

      {/* Desktop: table */}
      <div className="hidden space-y-3 md:block">
        <div className="overflow-x-auto rounded-2xl border border-[var(--border)]">
          <table className="min-w-[720px] w-full text-left text-sm">
            <thead className="bg-[var(--surface-3)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-4 py-3 font-medium">
                  <button
                    type="button"
                    className={headerButton}
                    onClick={() => toggleSort("year")}
                  >
                    Year
                    {sortMark(sort.key === "year", sort.direction)}
                  </button>
                </th>
                <th className="px-4 py-3 font-medium">Brand</th>
                <th className="px-4 py-3 font-medium">Model</th>
                <th className="px-4 py-3 font-medium">
                  <button
                    type="button"
                    className={headerButton}
                    onClick={() => toggleSort("mileage_km")}
                  >
                    Mileage (km)
                    {sortMark(sort.key === "mileage_km", sort.direction)}
                  </button>
                </th>
                <th className="px-4 py-3 font-medium">
                  <button
                    type="button"
                    className={headerButton}
                    onClick={() => toggleSort("horsepower")}
                  >
                    Horsepower
                    {sortMark(sort.key === "horsepower", sort.direction)}
                  </button>
                </th>
                <th className="px-4 py-3 font-medium">Fuel</th>
                <th className="px-4 py-3 font-medium">Transmission</th>
                <th className="px-4 py-3 font-medium">
                  <button
                    type="button"
                    className={headerButton}
                    onClick={() => toggleSort("price_eur")}
                  >
                    Price
                    {sortMark(sort.key === "price_eur", sort.direction)}
                  </button>
                </th>
                <th className="px-4 py-3 font-medium">Offer Link</th>
              </tr>
            </thead>
            <tbody>
              {slice.map((row, index) => (
                <tr
                  key={row.listing_id || String(row.id)}
                  className="border-t border-[var(--border)]"
                  style={{
                    background:
                      index % 2 === 0 ? "var(--table-odd)" : "var(--table-even)",
                  }}
                >
                  <td className="px-4 py-3 text-[var(--fg)]">{row.year}</td>
                  <td className="px-4 py-3 text-[var(--fg)]">{row.make}</td>
                  <td className="px-4 py-3 text-[var(--fg)]">{row.model}</td>
                  <td className="px-4 py-3 text-[var(--fg)]">
                    {formatKm(row.mileage_km)}
                  </td>
                  <td className="px-4 py-3 text-[var(--fg)]">{row.horsepower}</td>
                  <td className="px-4 py-3 text-[var(--fg)]">{row.fuel_type}</td>
                  <td className="px-4 py-3 text-[var(--fg)]">
                    {row.transmission}
                  </td>
                  <td className="px-4 py-3 text-[var(--fg)]">
                    {formatPrice(row.price_eur)}
                  </td>
                  <td className="px-4 py-3">
                    {row.link ? (
                      <a
                        href={row.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-[var(--accent)] hover:opacity-80"
                      >
                        Open Offer
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {pager}
      </div>
    </div>
  );
}
