import { MILEAGE_OVER_KM, type Listing } from "./types";

export type DashboardFilters = {
  make: string;
  model: string;
  yearFrom: number;
  yearTo: number;
  fuels: string[];
  transmissions: string[];
  hpFrom: number;
  hpTo: number;
  maxMileage: number | "any" | "over";
};

export function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) =>
    a.localeCompare(b),
  );
}

export function applyFilters(
  listings: Listing[],
  filters: DashboardFilters,
): Listing[] {
  const fuels = filters.fuels.length ? new Set(filters.fuels) : null;
  const transmissions = filters.transmissions.length
    ? new Set(filters.transmissions)
    : null;

  return listings.filter((row) => {
    if (row.make !== filters.make) return false;
    if (filters.model !== "any" && row.model !== filters.model) return false;
    if (row.year < filters.yearFrom || row.year > filters.yearTo) return false;
    if (fuels && !fuels.has(row.fuel_type)) return false;
    if (transmissions && !transmissions.has(row.transmission)) return false;
    if (row.horsepower < filters.hpFrom || row.horsepower > filters.hpTo) {
      return false;
    }
    if (filters.maxMileage === "over") {
      if (row.mileage_km <= MILEAGE_OVER_KM) return false;
    } else if (
      typeof filters.maxMileage === "number" &&
      row.mileage_km > filters.maxMileage
    ) {
      return false;
    }
    return true;
  });
}

export type DealSortKey = "year" | "price_eur" | "horsepower" | "mileage_km";

export function sortDeals(
  listings: Listing[],
  key: DealSortKey = "year",
  direction: "asc" | "desc" = "desc",
): Listing[] {
  const dir = direction === "asc" ? 1 : -1;
  return [...listings].sort((a, b) => {
    const left = Number(a[key]);
    const right = Number(b[key]);
    if (left !== right) return (left - right) * dir;
    // Tie-break: newer year first, then cheaper.
    if (key !== "year" && a.year !== b.year) return b.year - a.year;
    return a.price_eur - b.price_eur;
  });
}

export function formatPrice(value: number): string {
  return `€${Math.round(value).toLocaleString("en-US")}`;
}

export function formatKm(value: number): string {
  return `${Math.round(value).toLocaleString("en-US")} km`;
}

export function mileageLabel(value: number | "any" | "over"): string {
  if (value === "any") return "Any";
  if (value === "over") return `Over ${MILEAGE_OVER_KM.toLocaleString("en-US")}`;
  return formatKm(value);
}
