import { Dashboard } from "@/components/Dashboard";
import { fetchAllListings, fetchDataFreshness } from "@/lib/listings";

export const revalidate = 300;

export default async function Home() {
  try {
    const [listings, freshness] = await Promise.all([
      fetchAllListings(),
      fetchDataFreshness(),
    ]);
    if (listings.length === 0) {
      return (
        <div className="mx-auto max-w-3xl px-4 py-24 text-center">
          <h1 className="text-2xl font-semibold text-[var(--fg)]">
            No data found in Supabase
          </h1>
          <p className="mt-3 text-[var(--muted)]">
            Check the Python uploader and confirm listings exist in
            public.car_listings.
          </p>
        </div>
      );
    }
    return <Dashboard listings={listings} freshness={freshness} />;
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown data load error";
    return (
      <div className="mx-auto max-w-3xl px-4 py-24 text-center">
        <h1 className="text-2xl font-semibold text-[var(--fg)]">
          Could not load listings
        </h1>
        <p className="mt-3 text-[var(--muted)]">{message}</p>
      </div>
    );
  }
}
