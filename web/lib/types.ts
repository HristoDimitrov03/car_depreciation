export type Listing = {
  id: number;
  make: string;
  model: string;
  year: number;
  fuel_type: string;
  transmission: string;
  horsepower: number;
  mileage_km: number;
  price_eur: number;
  link: string;
  listing_id: string;
};

export const FUEL_OPTIONS = [
  "Diesel",
  "Petrol",
  "Electric",
  "Hybrid",
  "Gas/LPG",
] as const;

export const TRANSMISSION_OPTIONS = ["Automatic", "Manual"] as const;

export const MILEAGE_OVER_KM = 300000;

export const MILEAGE_OPTIONS: Array<number | "any" | "over"> = [
  "any",
  10000, 20000, 30000, 40000, 50000, 60000, 70000, 80000, 90000, 100000, 110000,
  120000, 130000, 140000, 150000, 200000, 250000, 300000, "over",
];

export const YEAR_MIN = 1990;
export const YEAR_MAX = 2027;

export const FUEL_COLORS: Record<string, string> = {
  Diesel: "#38bdf8",
  Petrol: "#f59e0b",
  Electric: "#34d399",
  Hybrid: "#a78bfa",
  "Gas/LPG": "#fb7185",
};
