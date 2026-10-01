import os

from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT_DIR, ".env"))


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def require_env(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Add it to the project-root .env file "
            "(see .env.example). Never put keys in source code."
        )
    return value


SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_ANON_KEY = _env("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY")

SKODA_BRAND_URL = "https://www.mobile.bg/obiavi/avtomobili-dzhipove/skoda"
NEWEST_SORT_QUERY = "sort=6"
SKODA_MODEL_SLUGS = [
    "octavia",
    "fabia",
    "superb",
    "rapid",
    "roomster",
    "yeti",
    "citigo",
    "scala",
    "kamiq",
    "karoq",
    "kodiaq",
    "enyaq",
    "elroq",
    "felicia",
    "favorit",
    "praktik",
    "kylaq",
    "forman",
    "pickup",
    "100",
    "105",
    "120",
    "1000",
]

SKODA_MODELS = [
    "Rapid Spaceback",
    "Enyaq Coupe",
    "Octavia",
    "Superb",
    "Fabia",
    "Kodiaq",
    "Karoq",
    "Kamiq",
    "Scala",
    "Rapid",
    "Roomster",
    "Yeti",
    "Citigo",
    "Felicia",
    "Favorit",
    "Praktik",
    "Enyaq",
    "Elroq",
    "Kylaq",
    "Forman",
    "Pickup",
    "100",
    "105",
    "110",
    "120",
    "1000",
]

RAW_LISTINGS_FILE = os.path.join(ROOT_DIR, "raw_mobile_listings.json")
CLEANED_CSV_FILE = os.path.join(ROOT_DIR, "cleaned_listings.csv")
LAST_SYNC_FILE = os.path.join(ROOT_DIR, "last_sync.json")
PAGE_SIZE = 1000
