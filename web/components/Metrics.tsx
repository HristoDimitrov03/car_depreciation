import type { ReactNode } from "react";

import { formatKm, formatPrice } from "@/lib/filters";

type Props = {
  count: number;
  avgPrice: number;
  avgMileage: number;
};

function Card({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3 sm:rounded-2xl sm:p-5">
      <p className="text-[10px] font-medium uppercase tracking-wide text-[var(--muted)] sm:text-xs">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-[var(--fg)] sm:mt-2 sm:text-2xl">
        {value}
      </p>
    </div>
  );
}

export function Metrics({ count, avgPrice, avgMileage }: Props) {
  const mileageCompact =
    avgMileage >= 1000
      ? `${Math.round(avgMileage / 1000).toLocaleString("en-US")}k km`
      : formatKm(avgMileage);

  return (
    <div className="grid grid-cols-3 gap-2 sm:gap-4">
      <Card label="Listings" value={count.toLocaleString("en-US")} />
      <Card label="Avg Price" value={formatPrice(avgPrice)} />
      <Card
        label="Avg Mileage"
        value={
          <>
            <span className="sm:hidden">{mileageCompact}</span>
            <span className="hidden sm:inline">{formatKm(avgMileage)}</span>
          </>
        }
      />
    </div>
  );
}
