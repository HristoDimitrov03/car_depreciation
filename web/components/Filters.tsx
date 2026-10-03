"use client";

import { useState } from "react";

import {
  FUEL_OPTIONS,
  MILEAGE_OPTIONS,
  TRANSMISSION_OPTIONS,
  YEAR_MAX,
  YEAR_MIN,
} from "@/lib/types";
import type { DashboardFilters } from "@/lib/filters";
import { mileageLabel } from "@/lib/filters";

type Props = {
  brands: string[];
  models: string[];
  filters: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
};

const selectClass =
  "w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5 text-sm text-[var(--fg)] outline-none focus:border-[var(--accent)] sm:py-2";

const labelClass =
  "mb-1 block text-xs font-medium uppercase tracking-wide text-[var(--muted)]";

function HorsepowerInput({
  id,
  label,
  initial,
  placeholder,
  onValue,
}: {
  id: string;
  label: string;
  initial: string;
  placeholder: string;
  onValue: (value: number | null) => void;
}) {
  const [text, setText] = useState(initial);

  return (
    <div>
      <label className={labelClass} htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={0}
        step={1}
        placeholder={placeholder}
        className={selectClass}
        value={text}
        onChange={(e) => {
          const raw = e.target.value;
          setText(raw);
          if (raw.trim() === "") {
            onValue(null);
            return;
          }
          const parsed = Number(raw);
          if (Number.isFinite(parsed)) onValue(parsed);
        }}
      />
    </div>
  );
}

export function Filters({ brands, models, filters, onChange }: Props) {
  const [open, setOpen] = useState(false);

  const yearsTo = Array.from(
    { length: YEAR_MAX - filters.yearFrom + 1 },
    (_, i) => filters.yearFrom + i,
  );

  function toggle(list: string[], value: string): string[] {
    return list.includes(value)
      ? list.filter((item) => item !== value)
      : [...list, value];
  }

  const activeBits = [
    filters.model !== "any" ? filters.model : null,
    filters.maxMileage !== "any"
      ? mileageLabel(filters.maxMileage)
      : null,
  ].filter(Boolean);

  return (
    <aside className="h-fit rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-3 sm:p-4 lg:sticky lg:top-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-wide text-[var(--muted-strong)]">
            Filters
          </h2>
          {!open && activeBits.length > 0 ? (
            <p className="mt-0.5 truncate text-xs text-[var(--muted)] lg:hidden">
              {filters.make}
              {activeBits.length ? ` · ${activeBits.join(" · ")}` : ""}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          className="shrink-0 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--fg)] lg:hidden"
          onClick={() => setOpen((current) => !current)}
          aria-expanded={open}
        >
          {open ? "Hide" : "Show"}
        </button>
      </div>

      <div
        className={`mt-3 space-y-3 ${open ? "block" : "hidden"} lg:block`}
      >
        <div>
          <label className={labelClass} htmlFor="brand">
            Car Brand
          </label>
          <select
            id="brand"
            className={selectClass}
            value={filters.make}
            onChange={(e) =>
              onChange({ ...filters, make: e.target.value, model: "any" })
            }
          >
            {brands.map((brand) => (
              <option key={brand} value={brand}>
                {brand}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={labelClass} htmlFor="model">
            Car Model
          </label>
          <select
            id="model"
            className={selectClass}
            value={filters.model}
            onChange={(e) => onChange({ ...filters, model: e.target.value })}
          >
            <option value="any">Any</option>
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelClass} htmlFor="yearFrom">
              Year From
            </label>
            <select
              id="yearFrom"
              className={selectClass}
              value={filters.yearFrom}
              onChange={(e) => {
                const yearFrom = Number(e.target.value);
                onChange({
                  ...filters,
                  yearFrom,
                  yearTo: Math.max(filters.yearTo, yearFrom),
                });
              }}
            >
              {Array.from(
                { length: YEAR_MAX - YEAR_MIN + 1 },
                (_, i) => YEAR_MIN + i,
              ).map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="yearTo">
              Year To
            </label>
            <select
              id="yearTo"
              className={selectClass}
              value={filters.yearTo}
              onChange={(e) =>
                onChange({ ...filters, yearTo: Number(e.target.value) })
              }
            >
              {yearsTo.map((year) => (
                <option key={year} value={year}>
                  {year}
                </option>
              ))}
            </select>
          </div>
        </div>

        <fieldset>
          <legend className={labelClass}>Fuel Type</legend>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            {FUEL_OPTIONS.map((fuel) => (
              <label
                key={fuel}
                className="flex items-center gap-2 text-sm text-[var(--fg)]"
              >
                <input
                  type="checkbox"
                  className="accent-[var(--accent)]"
                  checked={filters.fuels.includes(fuel)}
                  onChange={() =>
                    onChange({ ...filters, fuels: toggle(filters.fuels, fuel) })
                  }
                />
                {fuel}
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className={labelClass}>Transmission</legend>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            {TRANSMISSION_OPTIONS.map((item) => (
              <label
                key={item}
                className="flex items-center gap-2 text-sm text-[var(--fg)]"
              >
                <input
                  type="checkbox"
                  className="accent-[var(--accent)]"
                  checked={filters.transmissions.includes(item)}
                  onChange={() =>
                    onChange({
                      ...filters,
                      transmissions: toggle(filters.transmissions, item),
                    })
                  }
                />
                {item}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <HorsepowerInput
            id="hpFrom"
            label="HP From"
            initial="0"
            placeholder="0"
            onValue={(value) =>
              onChange({ ...filters, hpFrom: value == null ? 0 : value })
            }
          />
          <HorsepowerInput
            id="hpTo"
            label="HP To"
            initial=""
            placeholder="Any"
            onValue={(value) => onChange({ ...filters, hpTo: value })}
          />
        </div>

        <div>
          <label className={labelClass} htmlFor="mileage">
            Max Mileage
          </label>
          <select
            id="mileage"
            className={selectClass}
            value={String(filters.maxMileage)}
            onChange={(e) => {
              const value = e.target.value;
              onChange({
                ...filters,
                maxMileage:
                  value === "any" || value === "over" ? value : Number(value),
              });
            }}
          >
            {MILEAGE_OPTIONS.map((option) => (
              <option key={String(option)} value={String(option)}>
                {mileageLabel(option)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </aside>
  );
}
