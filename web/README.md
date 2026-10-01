# Skoda Market Tracker (Next.js)

Public dashboard for Skoda listings scraped from mobile.bg. The Python scraper stays at the repo root; this app only **reads** `public.car_listings` with the Supabase anon key.

## Local run

1. Copy `.env.example` to `.env.local` in this folder and fill:

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

Do not put `SUPABASE_SERVICE_ROLE_KEY` here. That key is only for the Python daily sync in the project-root `.env`.

2. Install and start:

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Vercel deploy

1. Import the GitHub repo in Vercel.
2. Set **Root Directory** to `web`.
3. Add environment variables (Project Settings → Environment Variables):
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
4. Deploy. Do not add the service role key to Vercel.

The anon key is a public frontend key. Safety comes from Row Level Security: anonymous clients can **SELECT** only.
