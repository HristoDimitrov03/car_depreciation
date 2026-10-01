import json
import re
import time
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

from config import CLEANED_CSV_FILE, RAW_LISTINGS_FILE, SKODA_MODELS

MIN_YEAR = 1970
MAX_YEAR = datetime.now().year + 1
MAX_MILEAGE = 1_000_000
MIN_PRICE_EUR = 100
MIN_HP = 20
MAX_HP = 700
# Series Skoda models never exceed this; higher values are typos or tuned cars.
MAX_PLAUSIBLE_HP = 400
# A car older than this many years with fewer km than the floor is a typo
# (e.g. "228 км" entered instead of 228 000 км).
MIN_KM_FOR_OLD_CAR = 1000
OLD_CAR_AGE_YEARS = 3
KW_TO_HP = 1.35962
MAX_SPEC_LEN = 40

BG_MONTHS = (
    "януари|февруари|март|април|май|юни|"
    "юли|август|септември|октомври|ноември|декември"
)

EN_MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december"
)
DATE_IN_CELL_RE = re.compile(
    rf"(?:{BG_MONTHS}|{EN_MONTHS})\s+(19\d{{2}}|20[0-3]\d)(?:\s*г\.?)?",
    re.IGNORECASE,
)
# A cell that is only a numeric date (08.2022 / 08/2022) or only a year (2022 г.).
NUMERIC_DATE_CELL_RE = re.compile(
    r"^(?:0?[1-9]|1[0-2])\s*[./]\s*(19\d{2}|20[0-3]\d)(?:\s*г\.?)?$",
    re.IGNORECASE,
)
BARE_YEAR_CELL_RE = re.compile(r"^(19\d{2}|20[0-3]\d)\s*г\.?$", re.IGNORECASE)
MILEAGE_CELL_RE = re.compile(
    r"^([\d\s\u00a0\u2009.]+)\s*(?:км|km)\.?$",
    re.IGNORECASE,
)
HP_CELL_RE = re.compile(
    r"(\d{2,4})\s*(?:к\.?\s*с\.?|кс|hp|bhp|ps|ks|kc)(?![\w])",
    re.IGNORECASE,
)
KW_CELL_RE = re.compile(
    r"(\d{2,4}(?:[.,]\d+)?)\s*kW\b",
    re.IGNORECASE,
)
PRICE_EUR_RE = re.compile(
    r"(\d{1,3}(?:[.\s\u00a0\u2009]\d{3})+(?:[.,]\d{1,2})?|"
    r"\d+(?:[.,]\d{1,2})?)\s*(?:€|\bEUR\b)",
    re.IGNORECASE,
)
PRICE_BGN_RE = re.compile(
    r"(\d{1,3}(?:[.\s\u00a0\u2009]\d{3})+(?:[.,]\d{1,2})?|"
    r"\d+(?:[.,]\d{1,2})?)\s*(?:лв|\bBGN\b)",
    re.IGNORECASE,
)
META_FIELD_RE = re.compile(
    r"^(нова обява|не се начислява ддс|цената е с включено ддс|"
    r"цената е без ддс|топ обява)$",
    re.IGNORECASE,
)
PRICE_JS_RE = re.compile(
    r"showpricechange\(\s*'[^']*'\s*,\s*'(\d+)'\s*,\s*'(EUR|BGN)'",
    re.IGNORECASE,
)
WARRANTY_RE = re.compile(
    r"гаранция|\bдо\s+\d{1,2}[./]\s*(?:19|20)\d{2}",
    re.IGNORECASE,
)

FUEL_RULES = (
    (re.compile(r"plug[\s\-]?in|\bphev\b", re.IGNORECASE), "Hybrid"),
    (re.compile(r"хибрид|\bhybrid\b|\bm?hev\b|mild", re.IGNORECASE), "Hybrid"),
    (re.compile(r"електрическ|\belectric\b", re.IGNORECASE), "Electric"),
    (re.compile(r"дизел|\bdiesel\b", re.IGNORECASE), "Diesel"),
    (
        re.compile(
            r"метан|\bcng\b|\btgi\b|бензин\s*[-/+]?\s*(?:и\s*)?газ|\bгаз\b|\blpg\b|\bгаз[\s/+-]*бензин",
            re.IGNORECASE,
        ),
        "Gas/LPG",
    ),
    (re.compile(r"бензин|\bpetrol\b|\bgasoline\b", re.IGNORECASE), "Petrol"),
)
AUTO_RE = re.compile(
    r"автоматичн|полуавтоматичн|\bdsg\b|s[\s\-]?tronic|tiptronic|steptronic",
    re.IGNORECASE,
)
MANUAL_RE = re.compile(r"ръчн|\bmanual\b", re.IGNORECASE)
EURO_CELL_RE = re.compile(r"^евро\s*\d", re.IGNORECASE)
DISPLACEMENT_RE = re.compile(
    r"куб\.?\s*см|\bcm\s*3\b|\bkwh\b",
    re.IGNORECASE,
)

REQUIRED_FIELDS = (
    "year",
    "mileage_km",
    "horsepower",
    "fuel_type",
    "transmission",
    "price_eur",
)


def _parts(text):
    return [p.strip() for p in re.split(r"\s*\|\s*", text or "") if p.strip()]


def _as_record(source):
    if isinstance(source, dict):
        return source
    return {"raw_text": source or ""}


def _empty(value):
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _int_from_grouped(raw):
    amount = _amount_from_grouped(raw, allow_cents=False)
    return int(amount) if amount is not None else None


def _amount_from_grouped(raw, allow_cents=True):
    s = (
        str(raw)
        .replace("\xa0", "")
        .replace("\u2009", "")
        .replace(" ", "")
        .strip()
    )
    if not s:
        return None
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        return int(s.replace(".", ""))
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):
        return int(s.replace(",", ""))
    if allow_cents and re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d{1,2}", s):
        whole, cents = s.rsplit(",", 1)
        return float(f"{whole.replace('.', '')}.{cents}")
    if allow_cents and re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d{1,2}", s):
        whole, cents = s.rsplit(".", 1)
        return float(f"{whole.replace(',', '')}.{cents}")
    if allow_cents and re.fullmatch(r"\d+[.,]\d{1,2}", s):
        return float(s.replace(",", "."))
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


NUMERIC_MODELS = ("100", "105", "110", "120", "1000")


def extract_model(text):
    """Pick the model named first in the title; longer names win ties.

    Numeric models (105 / 120) only count when no named model is present,
    because "105 к.с." or "120 PS" often appears in titles of other cars.
    """
    text = text or ""
    best = None
    for model in SKODA_MODELS:
        if model in NUMERIC_MODELS:
            continue
        match = re.search(rf"\b{re.escape(model)}\b", text, re.IGNORECASE)
        if match and (best is None or (match.start(), -len(model)) < best[0]):
            best = ((match.start(), -len(model)), model)
    if best:
        return best[1]
    for model in NUMERIC_MODELS:
        if re.search(rf"(?<![\w.,])(?:skoda\s+)?{model}(?![\w.,])", text, re.IGNORECASE):
            return model
    return "Other"


def _title_of(record):
    rec = _as_record(record)
    if rec.get("title"):
        return rec["title"]
    parts = _parts(rec.get("raw_text") or "")
    return parts[0] if parts else ""


def year_from_cell(text):
    text = (text or "").strip()
    if not text or WARRANTY_RE.search(text):
        return None
    match = (
        DATE_IN_CELL_RE.search(text)
        or NUMERIC_DATE_CELL_RE.match(text)
        or BARE_YEAR_CELL_RE.match(text)
    )
    if not match:
        return None
    prefix = text[: match.start()].lower().rstrip()
    if prefix.endswith("до") or "гаранция" in prefix:
        return None
    year = int(match.group(1))
    if MIN_YEAR <= year <= MAX_YEAR:
        return year
    return None


def mileage_from_cell(text):
    text = (text or "").strip()
    match = MILEAGE_CELL_RE.match(text)
    if not match:
        return None
    value = _int_from_grouped(match.group(1))
    if value is not None and 0 <= value <= MAX_MILEAGE:
        return value
    return None


def mileage_from_labeled(text):
    """Mileage chip or techData value whose label is already Пробег [км]."""
    mileage = mileage_from_cell(text)
    if mileage is not None:
        return mileage
    value = _int_from_grouped(text or "")
    if value is not None and 0 <= value <= MAX_MILEAGE:
        return value
    return None


def hp_from_cell(text):
    text = (text or "").strip()
    if not text or DISPLACEMENT_RE.search(text):
        return None
    match = HP_CELL_RE.search(text)
    if match:
        hp = int(match.group(1))
        return hp if MIN_HP <= hp <= MAX_HP else None
    match_kw = KW_CELL_RE.search(text)
    if match_kw:
        kw = float(match_kw.group(1).replace(",", "."))
        hp = int(round(kw * KW_TO_HP))
        return hp if MIN_HP <= hp <= MAX_HP else None
    return None


def fuel_from_cell(text):
    text = (text or "").strip()
    if not text or len(text) > MAX_SPEC_LEN:
        return None
    if EURO_CELL_RE.match(text) or DISPLACEMENT_RE.search(text):
        return None
    if mileage_from_cell(text) is not None or hp_from_cell(text) is not None:
        return None
    for pattern, label in FUEL_RULES:
        if pattern.search(text):
            return label
    return None


def transmission_from_cell(text):
    text = (text or "").strip()
    if not text or len(text) > MAX_SPEC_LEN:
        return None
    if AUTO_RE.search(text):
        return "Automatic"
    if MANUAL_RE.search(text):
        return "Manual"
    return None


def price_from_text(text):
    if text is None or not isinstance(text, str) or not text:
        return None
    chunk = text.replace("\u2009", " ")
    match_eur = PRICE_EUR_RE.search(chunk)
    if match_eur:
        value = _amount_from_grouped(match_eur.group(1), allow_cents=True)
        if value is not None and value >= MIN_PRICE_EUR:
            return float(value)
    match_bgn = PRICE_BGN_RE.search(chunk)
    if match_bgn:
        value = _amount_from_grouped(match_bgn.group(1), allow_cents=True)
        if value is not None:
            euros = round(value / 1.95583, 2)
            if euros >= MIN_PRICE_EUR:
                return euros
    return None


def _spec_params_from_raw(text):
    """Rebuild short spec chips from a pipe-separated card. Never keep the description."""
    parts = _parts(text)
    specs = []
    for i, part in enumerate(parts):
        if i == 0:
            continue
        if price_from_text(part) is not None or META_FIELD_RE.match(part):
            continue
        lower = part.lower()
        if lower.startswith("особености") or lower.startswith("регион"):
            break
        if len(part) > MAX_SPEC_LEN and year_from_cell(part) is None:
            break
        specs.append(part)
    return specs


def spec_fields(record):
    rec = _as_record(record)
    params = rec.get("params")
    if isinstance(params, list) and params:
        return [str(p).strip() for p in params if str(p).strip()]
    return _spec_params_from_raw(rec.get("raw_text") or "")


def _tech_value(tech, *needles):
    if not isinstance(tech, dict):
        return None
    for key, value in tech.items():
        label = str(key).lower()
        if any(needle in label for needle in needles):
            return str(value).strip()
    return None


def decode_mobile_html(content, content_type=""):
    """mobile.bg pages are usually Windows-1251 unless a charset says otherwise."""
    if isinstance(content, str):
        return content
    hint = f"{content_type} {content[:2500].decode('ascii', 'ignore')}".lower()
    preferred = ("utf-8", "cp1251") if "utf-8" in hint and "windows-1251" not in hint else ("cp1251", "utf-8")
    last = content.decode("cp1251", errors="replace")
    for encoding in preferred:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        last = text
        if "techData" in text or "Дата на производство" in text or "obiava" in text.lower():
            return text
    return last


def parse_detail_html(html):
    """Read labeled techData rows from an offer page. Ignore description text."""
    if isinstance(html, bytes):
        html = decode_mobile_html(html)
    soup = BeautifulSoup(html or "", "html.parser")
    tech = {}
    for item in soup.select("div.techData div.items > div.item"):
        divs = item.find_all("div", recursive=False)
        if len(divs) < 2:
            continue
        label = divs[0].get_text(" ", strip=True)
        value = divs[1].get_text(" ", strip=True)
        if label and value:
            tech[label] = value
    price_text = ""
    js_price = PRICE_JS_RE.search(html or "")
    if js_price:
        amount = int(js_price.group(1))
        currency = js_price.group(2).upper()
        if currency == "BGN":
            price_text = f"{amount} лв"
        else:
            price_text = f"{amount} €"
    if not price_text:
        # Detail pages use div.Price (capital P); search cards use div.price.
        price_el = soup.select_one("div.Price") or soup.select_one("div.price")
        if price_el:
            own_text = " ".join(
                s.strip() for s in price_el.find_all(string=True, recursive=False) if s.strip()
            )
            price_text = own_text or price_el.get_text(" ", strip=True)
    title = ""
    title_el = soup.select_one("h1")
    if title_el:
        title = re.split(r"\s*Обява:", title_el.get_text(" ", strip=True), maxsplit=1)[0].strip()
    return {"tech_data": tech, "price_text": price_text, "title": title}


def extract_year(record):
    for part in spec_fields(record):
        year = year_from_cell(part)
        if year is not None:
            return year
    rec = _as_record(record)
    tech_year = year_from_cell(_tech_value(rec.get("tech_data"), "дата на производство"))
    if tech_year is not None:
        return tech_year
    return np.nan


def extract_mileage(record):
    for part in spec_fields(record):
        mileage = mileage_from_cell(part)
        if mileage is not None:
            return mileage
    rec = _as_record(record)
    value = _tech_value(rec.get("tech_data"), "пробег")
    mileage = mileage_from_labeled(value or "")
    if mileage is not None:
        return mileage
    return np.nan


def extract_hp(record):
    for part in spec_fields(record):
        hp = hp_from_cell(part)
        if hp is not None:
            return hp
    rec = _as_record(record)
    value = _tech_value(rec.get("tech_data"), "мощност")
    hp = hp_from_cell(value or "")
    if hp is not None:
        return hp
    return np.nan


def extract_fuel(record):
    for part in spec_fields(record):
        fuel = fuel_from_cell(part)
        if fuel is not None:
            return fuel
    rec = _as_record(record)
    value = _tech_value(rec.get("tech_data"), "двигател")
    fuel = fuel_from_cell(value or "")
    if fuel is not None:
        return fuel
    return np.nan


def extract_transmission(record):
    for part in spec_fields(record):
        trans = transmission_from_cell(part)
        if trans is not None:
            return trans
    rec = _as_record(record)
    value = _tech_value(rec.get("tech_data"), "скоростна")
    trans = transmission_from_cell(value or "")
    if trans is not None:
        return trans
    return np.nan


def extract_price(record):
    rec = _as_record(record)
    priced = price_from_text(rec.get("price_text") or "")
    if priced is not None:
        return priced
    if "price_text" in rec or isinstance(rec.get("params"), list):
        # Structured record: the price cell is the only source. Never scan text.
        return np.nan
    parts = _parts(rec.get("raw_text") or "")
    for part in parts[1:]:
        if year_from_cell(part) is not None:
            break
        if part.lower().startswith("особености") or part.lower().startswith("регион"):
            break
        if len(part) > MAX_SPEC_LEN:
            break
        priced = price_from_text(part)
        if priced is not None:
            return priced
    return np.nan


def parse_listing(record):
    rec = _as_record(record)
    title = _title_of(rec)
    return {
        "model": extract_model(title),
        "year": extract_year(rec),
        "mileage_km": extract_mileage(rec),
        "horsepower": extract_hp(rec),
        "fuel_type": extract_fuel(rec),
        "transmission": extract_transmission(rec),
        "price_eur": extract_price(rec),
    }


def parse_listing_text(text):
    return parse_listing({"raw_text": text})


def is_complete(parsed):
    return all(not _empty(parsed.get(field)) for field in REQUIRED_FIELDS)


def needs_detail(record):
    return not is_complete(parse_listing(record))


def enrich_incomplete(listings, fetch_html, delay=0.35):
    """Fetch offer pages only when spec chips are missing a required field."""
    filled = 0
    cache = {}
    for item in listings:
        if not needs_detail(item):
            continue
        url = item.get("link") or ""
        lid = str(item.get("listing_id") or "")
        if not url:
            continue
        html = cache.get(lid)
        if html is None:
            try:
                html = fetch_html(url)
            except Exception:
                html = None
            cache[lid] = html
            time.sleep(delay)
        if not html:
            continue
        extra = parse_detail_html(html)
        if not extra.get("tech_data"):
            # Error page, captcha, or a layout without labeled specs: ignore it.
            continue
        item["tech_data"] = extra["tech_data"]
        detail_title = extra.get("title") or ""
        if (
            re.search(r"skoda|шкода", detail_title, re.IGNORECASE)
            and (not item.get("title") or extract_model(_title_of(item)) == "Other")
        ):
            item["title"] = detail_title
        detail_price = extra.get("price_text") or ""
        if detail_price and price_from_text(item.get("price_text") or "") is None:
            item["price_text"] = detail_price
        filled += 1
    if filled:
        print(f"Filled spec gaps from {filled} detail pages.")
    return listings


def drop_reasons(parsed):
    reasons = []
    for field in REQUIRED_FIELDS:
        if _empty(parsed.get(field)):
            reasons.append(field)
    price = parsed.get("price_eur")
    if not _empty(price) and price < MIN_PRICE_EUR:
        reasons.append("price_below_min")
    hp = parsed.get("horsepower")
    if not _empty(hp) and hp > MAX_PLAUSIBLE_HP:
        reasons.append("hp_implausible")
    year, km = parsed.get("year"), parsed.get("mileage_km")
    if (
        not _empty(year)
        and not _empty(km)
        and km < MIN_KM_FOR_OLD_CAR
        and year <= datetime.now().year - OLD_CAR_AGE_YEARS
    ):
        reasons.append("mileage_implausible")
    return reasons


def listings_to_dataframe(raw_data, verbose=True):
    rows = []
    dropped = 0
    reason_counts = Counter()
    for item in raw_data or []:
        rec = item if isinstance(item, dict) else {"raw_text": item}
        parsed = parse_listing(rec)
        reasons = drop_reasons(parsed)
        if reasons:
            dropped += 1
            reason_counts.update(reasons)
            continue
        rows.append(
            {
                "listing_id": rec.get("listing_id") or "",
                "make": "Skoda",
                "model": parsed["model"],
                "year": int(parsed["year"]),
                "fuel_type": parsed["fuel_type"],
                "transmission": parsed["transmission"],
                "horsepower": int(parsed["horsepower"]),
                "mileage_km": int(parsed["mileage_km"]),
                "price_eur": float(parsed["price_eur"]),
                "link": rec.get("link") or "",
            }
        )

    if verbose and dropped:
        reason_txt = ", ".join(f"{k}={v}" for k, v in reason_counts.most_common())
        print(f"Dropped {dropped} listings with missing or invalid spec fields ({reason_txt}).")

    df_clean = pd.DataFrame(rows)
    if df_clean.empty:
        return df_clean
    return df_clean.drop_duplicates(subset=["listing_id"])


def process_data(input_file=RAW_LISTINGS_FILE, output_file=CLEANED_CSV_FILE, fetch_details=False):
    print(f"Loading data from {input_file}...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print("Run scraper.py first.")
        return pd.DataFrame()

    if fetch_details:
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
        }
        with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
            def fetch_html(url):
                response = client.get(url)
                if response.status_code >= 400:
                    return None
                return decode_mobile_html(
                    response.content,
                    response.headers.get("content-type", ""),
                )

            enrich_incomplete(raw_data, fetch_html)

    df_final = listings_to_dataframe(raw_data)
    if df_final.empty:
        print("No usable rows after parsing.")
        return df_final

    df_final.to_csv(output_file, index=False, encoding="utf-8")
    print("-" * 50)
    print(f"Extraction complete! Cleaned rows: {len(df_final)} / raw {len(raw_data)}")
    print("-" * 50)
    print(df_final[["model", "year", "price_eur", "listing_id"]].head(5))
    return df_final


def _self_check():
    warranty_card = (
        "Skoda Octavia IV Combi 1.5 TSI, гаранция до 08.2027, 62000 км. | "
        "19 500 € | Не се начислява ДДС | "
        "август 2022 г. | 62 200 км | Т.зелен | Бензинов | 150 к.с. | "
        "Евро 6 | 1500 куб.см | Ръчна | Комби | "
        "Колата има оставаща фабрична гаранцията до Август 2027г."
    )
    card = parse_listing_text(warranty_card)
    assert card["year"] == 2022, card
    assert card["mileage_km"] == 62200, card
    assert card["horsepower"] == 150, card
    assert card["fuel_type"] == "Petrol", card
    assert card["transmission"] == "Manual", card
    assert card["price_eur"] == 19500, card

    dotted = parse_listing(
        {
            "title": "Skoda Octavia",
            "price_text": "19.500 €",
            "params": [
                "август 2022 г.",
                "62.200 км",
                "Т.зелен",
                "Бензинов",
                "150 к.с",
                "Евро 6",
                "Ръчна",
                "Комби",
            ],
        }
    )
    assert dotted["mileage_km"] == 62200, dotted
    assert dotted["price_eur"] == 19500, dotted
    assert dotted["horsepower"] == 150, dotted

    euro_in_title = parse_listing_text(
        "Skoda Octavia 2012Euro 5B | 3 900 € | Не се начислява ДДС | "
        "юли 2012 г. | 240 000 км | Черен | Дизелов | 105 к.с. | Евро 5 | Ръчна | Комби"
    )
    assert euro_in_title["year"] == 2012, euro_in_title
    assert euro_in_title["price_eur"] == 3900, euro_in_title

    dsg = parse_listing(
        {
            "title": "Skoda Kodiaq",
            "price_text": "26 999 €",
            "params": [
                "ноември 2023 г.",
                "137 100 км",
                "Сив",
                "Дизелов",
                "150 к.с.",
                "DSG",
                "Джип",
            ],
        }
    )
    assert dsg["transmission"] == "Automatic", dsg

    semi = parse_listing_text(
        "Skoda Kodiaq | 26 999 € | ноември 2023 г. | 137 100 км | "
        "Сив | Дизелов | 150 к.с. | Полуавтоматична | Джип"
    )
    assert semi["transmission"] == "Automatic", semi

    kw_only = parse_listing(
        {
            "title": "Skoda Enyaq",
            "price_text": "33 600 €",
            "params": [
                "януари 2023 г.",
                "97 000 км",
                "Зелен",
                "Електрически",
                "110 kW",
                "Автоматична",
                "Джип",
            ],
        }
    )
    assert kw_only["horsepower"] == 150, kw_only
    assert kw_only["fuel_type"] == "Electric", kw_only

    no_date = parse_listing_text(
        "Skoda Octavia | 19 500 € | Не се начислява ДДС | "
        "Продавам колата. Остатък по лизинга 16 014 евро на месец 235 евро. "
        "Гаранция до Август 2027г."
    )
    assert pd.isna(no_date["year"]), no_date
    assert no_date["price_eur"] == 19500, no_date
    assert pd.isna(no_date["horsepower"]), no_date

    assert extract_model("Skoda 105") == "105"
    assert extract_model("Skoda 120") == "120"
    assert extract_model("Skoda Rapid Spaceback") == "Rapid Spaceback"
    assert extract_model("Skoda Enyaq Coupe") == "Enyaq Coupe"

    missing_hp = parse_listing(
        {
            "title": "Skoda Roomster",
            "price_text": "2 200 €",
            "params": [
                "януари 2009 г.",
                "226 247 км",
                "Газ",
                "Евро 4",
                "Ръчна",
                "Ван",
            ],
        }
    )
    assert pd.isna(missing_hp["horsepower"]), missing_hp
    assert missing_hp["fuel_type"] == "Gas/LPG", missing_hp
    assert not is_complete(missing_hp)

    lpg = parse_listing(
        {
            "title": "Skoda Octavia TGI",
            "price_text": "5 500 €",
            "params": ["септември 2017 г.", "185 487 км", "Сив", "Метан", "110 к.с.", "Автоматична"],
        }
    )
    assert lpg["fuel_type"] == "Gas/LPG", lpg

    petrol = parse_listing(
        {
            "title": "Skoda Octavia",
            "price_text": "19 500 €",
            "params": ["август 2022 г.", "62200 км", "Бензинов", "150 к.с.", "Ръчна"],
        }
    )
    assert petrol["fuel_type"] == "Petrol", petrol
    assert petrol["mileage_km"] == 62200, petrol
    assert hp_from_cell("1400 к.с.") is None
    assert hp_from_cell("1900 к.с.") is None
    assert extract_model("Skoda Forman Pick-up LX") == "Forman"

    dropped = listings_to_dataframe(
        [
            {
                "listing_id": "1",
                "title": "Skoda Roomster",
                "price_text": "2200 €",
                "params": ["януари 2009 г.", "226 247 км", "Газ", "Ръчна"],
                "link": "https://www.mobile.bg/obiava-1",
            }
        ],
        verbose=False,
    )
    assert dropped.empty

    tech = parse_listing(
        {
            "title": "Skoda Octavia IV Combi 1.5 TSI, гаранция до 08.2027, 62000 км.",
            "price_text": "19500 €",
            "params": [],
            "tech_data": {
                "Дата на производство": "август 2022",
                "Двигател": "Бензинов",
                "Мощност": "150 к.с. (110 kW)",
                "Скоростна кутия": "Ръчна",
                "Пробег [км]": "62.200",
            },
        }
    )
    assert tech["year"] == 2022, tech
    assert tech["mileage_km"] == 62200, tech
    assert tech["horsepower"] == 150, tech
    assert tech["fuel_type"] == "Petrol", tech
    assert tech["transmission"] == "Manual", tech

    cents = parse_listing(
        {
            "title": "Skoda Rapid 1.4 TDI",
            "price_text": "9 198.14 €",
            "params": [
                "ноември 2016 г.",
                "144 000 км",
                "Дизелов",
                "90 к.с.",
                "Ръчна",
            ],
        }
    )
    assert cents["price_eur"] == 9198.14, cents
    assert cents["year"] == 2016, cents

    # Title km (118км, 100км, 163.000km) must never become the mileage.
    for title, km in (
        ("Skoda Octavia 1.6TDi 105кс * 118км* * Сервизна история*", 118000),
        ("Skoda Octavia Обслужен преди 100км, 2.0TDI DSG", 301000),
        ("Skoda Octavia 2.0-TDI-AUTOMAT-163.000km-ПЪЛЕН СЕРВИЗ", 163000),
    ):
        from_tech = parse_listing(
            {
                "title": title,
                "price_text": "7 990 €",
                "params": [],
                "tech_data": {
                    "Дата на производство": "март 2015",
                    "Двигател": "Дизелов",
                    "Мощност": "105 к.с.",
                    "Скоростна кутия": "Ръчна",
                    "Пробег [км]": f"{km} км",
                },
            }
        )
        assert from_tech["mileage_km"] == km, from_tech
        assert from_tech["horsepower"] == 105, from_tech

    # Seller typed displacement into the power field: drop, never repair.
    absurd_hp = parse_listing(
        {
            "title": "Skoda Octavia",
            "price_text": "1 400 €",
            "params": ["юли 2002 г.", "225 000 км", "Дизелов", "1896 к.с.", "Ръчна"],
        }
    )
    assert pd.isna(absurd_hp["horsepower"]), absurd_hp
    assert not is_complete(absurd_hp)

    # Detail-page price lives in div.Price, not div.price.
    detail = parse_detail_html(
        '<div class="Price">\n  7 990 €\n  <span title="x"></span>\n</div>'
        '<div class="techData"><div class="items">'
        '<div class="item"><div>Пробег [км]</div><div>118000 км</div></div>'
        "</div></div>"
    )
    assert price_from_text(detail["price_text"]) == 7990, detail
    assert detail["tech_data"]["Пробег [км]"] == "118000 км", detail

    # Date variants, unit variants, fuel variants.
    assert year_from_cell("08.2022") == 2022
    assert year_from_cell("2022 г.") == 2022
    assert year_from_cell("August 2022") == 2022
    assert year_from_cell("лизинг, август 2022 г.") == 2022
    assert year_from_cell("гаранция до 08.2027") is None
    assert year_from_cell("до август 2027 г.") is None
    assert mileage_from_cell("62.200 км") == 62200
    assert mileage_from_cell("62\u00a0200 km") == 62200
    assert hp_from_cell("150 к.с") == 150
    assert hp_from_cell("150кс") == 150
    assert hp_from_cell("170 KS") == 170
    assert hp_from_cell("1500 куб.см") is None
    assert hp_from_cell("82 kWh") is None
    assert fuel_from_cell("Бензин/газ") == "Gas/LPG"
    assert fuel_from_cell("Бензин + газ") == "Gas/LPG"
    assert fuel_from_cell("Plug-in хибрид") == "Hybrid"
    assert fuel_from_cell("MHEV") == "Hybrid"
    assert fuel_from_cell("Металик") is None
    assert fuel_from_cell("Евро 6") is None
    assert transmission_from_cell("6 степени") is None
    assert transmission_from_cell("S-tronic") == "Automatic"

    # Model: first model named in the title wins; 105/120 never beat a named model.
    assert extract_model("Skoda Octavia 120 PS") == "Octavia"
    assert extract_model("Skoda Octavia 1.6TDi 105кс") == "Octavia"
    assert extract_model("Skoda Superb вместо Octavia") == "Superb"
    assert extract_model("Skoda 120 L") == "120"
    assert extract_model("Skoda 100 S") == "100"
    assert extract_model("Skoda Fabia 1.0 110 PS") == "Fabia"

    typo_km = parse_listing(
        {
            "title": "Skoda Octavia VRS",
            "price_text": "4 600 €",
            "params": ["декември 2008 г.", "228 км", "Дизелов", "170 к.с.", "Ръчна"],
        }
    )
    assert "mileage_implausible" in drop_reasons(typo_km), typo_km
    tuned = parse_listing(
        {
            "title": "Skoda Superb",
            "price_text": "35 000 €",
            "params": ["септември 2017 г.", "81 000 км", "Бензинов", "570 к.с.", "Автоматична"],
        }
    )
    assert "hp_implausible" in drop_reasons(tuned), tuned
    new_car = parse_listing(
        {
            "title": "Skoda Kodiaq",
            "price_text": "48 800 €",
            "params": [f"януари {datetime.now().year} г.", "200 км", "Бензинов", "204 к.с.", "Автоматична"],
        }
    )
    assert drop_reasons(new_car) == [], new_car

    # Structured record without a price cell: never scan other text for euros.
    no_price = parse_listing(
        {
            "title": "Skoda Octavia",
            "price_text": "Запитване",
            "params": ["август 2022 г.", "62 200 км", "Бензинов", "150 к.с.", "Ръчна"],
            "raw_text": "Skoda Octavia | Запитване | остатък по лизинга 16 014 евро 235 €",
        }
    )
    assert pd.isna(no_price["price_eur"]), no_price

    print("parser self-check passed")


if __name__ == "__main__":
    _self_check()
    process_data()
