import json
import re
import time
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from config import (
    NEWEST_SORT_QUERY,
    RAW_LISTINGS_FILE,
    SKODA_BRAND_URL,
    SKODA_MODEL_SLUGS,
)
from parser import enrich_incomplete

LISTING_ID_RE = re.compile(r"obiava-(\d+)", re.IGNORECASE)
SKODA_TITLE_RE = re.compile(r"skoda|шкода", re.IGNORECASE)
RESULTS_TOTAL_RE = re.compile(r"от\s+общо\s+([\d\s\u00a0]+)", re.IGNORECASE)
CARDS_PER_PAGE = 20
MAX_PAGES_PER_SEARCH = 1000
DETAIL_DELAY_SEC = 0.35


def listing_id_from_url(url):
    if not url:
        return None
    match = LISTING_ID_RE.search(url)
    return match.group(1) if match else None


def normalize_listing_url(href):
    if not href:
        return ""
    href = href.strip()
    if href.startswith("javascript") or href.startswith("#"):
        return ""
    href = href.replace("https://www.mobile.bg//www.mobile.bg", "https://www.mobile.bg")
    href = href.replace("http://www.mobile.bg//www.mobile.bg", "https://www.mobile.bg")
    if href.startswith("//"):
        href = "https:" + href
    elif href.startswith("/"):
        href = "https://www.mobile.bg" + href
    elif href.startswith("www.mobile.bg"):
        href = "https://" + href
    parsed = urlparse(href)
    if not parsed.netloc:
        href = urljoin("https://www.mobile.bg/", href)
        parsed = urlparse(href)
    clean = parsed._replace(query="", fragment="")
    return urlunparse(clean)


def _text(node):
    return node.get_text(" ", strip=True) if node else ""


def _in_similar_ads(item):
    for parent in item.parents:
        classes = parent.get("class") or []
        joined = " ".join(classes).lower()
        if "podobni" in joined:
            return True
    return False


def _listing_from_search_card(item):
    """Read title, price, and spec chips from a mobile.bg search card."""
    card_id = item.get("id") or ""
    listing_id = card_id[3:] if card_id.startswith("ida") else None

    title_el = item.select_one("a.title")
    title = _text(title_el)
    href = ""
    if title_el and title_el.has_attr("href"):
        href = normalize_listing_url(title_el["href"])
    if not href:
        for a in item.select("a[href]"):
            href = normalize_listing_url(a.get("href"))
            if listing_id_from_url(href):
                break
            href = ""

    listing_id = listing_id or listing_id_from_url(href)
    if not listing_id:
        return None

    price_el = item.select_one("div.price")
    price_first = price_el.find("div") if price_el else None
    price_text = _text(price_first or price_el)

    if title and not SKODA_TITLE_RE.search(title):
        return None

    # Empty chips are kept on purpose: the detail page fills them later.
    params = [_text(span) for span in item.select("div.params span")]
    params = [p for p in params if p]

    raw_parts = [title, price_text] + params
    return {
        "listing_id": listing_id,
        "title": title,
        "price_text": price_text,
        "params": params,
        "raw_text": " | ".join(p for p in raw_parts if p),
        "link": href,
    }


def _next_results_url(soup, current_url):
    pager = soup.select_one(".pagination, .pagination-wrapper")
    next_link = None
    if pager:
        next_link = pager.find("a", string=lambda t: t and "Напред" in t)
        if not next_link:
            next_span = pager.find("span", string=lambda t: t and "Напред" in t)
            if next_span and next_span.parent and next_span.parent.name == "a":
                next_link = next_span.parent
        if not next_link:
            next_link = pager.select_one("a.next")
    if next_link and next_link.has_attr("href"):
        href = next_link["href"]
        next_url = href if href.startswith("http") else urljoin("https://www.mobile.bg/", href)
        if next_url != current_url:
            return next_url
    return None


def extract_listings_from_html(html, current_url=""):
    """Collect one search-card per listing from structured spec cells."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for item in soup.select("div.item[id^=ida]"):
        if _in_similar_ads(item):
            continue
        row = _listing_from_search_card(item)
        if row:
            found[row["listing_id"]] = row

    next_url = _next_results_url(soup, current_url)
    return list(found.values()), next_url


def results_total(html):
    """Read the site's own result count ("1 - 20 от общо 3475") for sanity checks."""
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select(".resultsInfo, .pagination, .pagination-wrapper, .filterInfo"):
        match = RESULTS_TOTAL_RE.search(el.get_text(" ", strip=True))
        if match:
            digits = re.sub(r"\D", "", match.group(1))
            if digits:
                return int(digits)
    match = RESULTS_TOTAL_RE.search(soup.get_text(" ", strip=True)[:4000])
    if match:
        digits = re.sub(r"\D", "", match.group(1))
        if digits:
            return int(digits)
    return None


def _accept_cookies(page):
    try:
        btn = page.locator('button:has-text("ПРИЕМЕТЕ ВСИЧКИ"), text="ПРИЕМЕТЕ ВСИЧКИ"').last
        if btn.is_visible(timeout=4000):
            btn.click(force=True)
            page.wait_for_timeout(800)
    except Exception:
        pass


def _load_listings(page):
    try:
        page.wait_for_selector("div.item[id^=ida], div.params", timeout=15000)
    except Exception:
        pass
    for _ in range(6):
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(250)
    page.wait_for_timeout(800)


def scrape_search_url(page, start_url, known_ids=None, stop_after_known_streak=3):
    """Scrape one search until the last page.

    If known_ids is set, stop after several consecutive pages that only
    contain already stored listing IDs (used for the daily new-car pass).
    """
    collected = {}
    current_url = start_url
    known_streak = 0
    expected_total = None
    hit_page_cap = False

    for page_no in range(1, MAX_PAGES_PER_SEARCH + 1):
        if page_no == MAX_PAGES_PER_SEARCH:
            hit_page_cap = True
        print(f"  Page {page_no}: {current_url}")
        page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
        if page_no == 1:
            _accept_cookies(page)
        _load_listings(page)

        html = page.content()
        listings, next_url = extract_listings_from_html(html, current_url)
        if next_url and len(listings) < CARDS_PER_PAGE:
            # A middle page should be full. Reload once in case lazy loading was slow.
            page.wait_for_timeout(1500)
            _load_listings(page)
            html_retry = page.content()
            retry_listings, retry_next = extract_listings_from_html(html_retry, current_url)
            if len(retry_listings) > len(listings):
                html, listings, next_url = html_retry, retry_listings, retry_next
        if page_no == 1:
            expected_total = results_total(html)
        new_on_page = 0
        for item in listings:
            lid = item["listing_id"]
            if lid in collected:
                continue
            collected[lid] = item
            if known_ids is not None and lid in known_ids:
                pass
            else:
                new_on_page += 1

        print(f"  Captured {len(listings)} cards ({new_on_page} new). Running total: {len(collected)}")

        if known_ids is not None:
            if listings and new_on_page == 0:
                known_streak += 1
            else:
                known_streak = 0
            if known_streak >= stop_after_known_streak:
                print("  Reached already-known listings; stopping this search.")
                break

        if not next_url or next_url == current_url:
            print("  Last page reached.")
            break
        current_url = next_url
        time.sleep(0.4)

    if hit_page_cap:
        print(f"  WARNING: stopped at the {MAX_PAGES_PER_SEARCH}-page cap; results may be incomplete.")
    if known_ids is None and expected_total:
        missing = expected_total - len(collected)
        if missing > max(3, int(expected_total * 0.02)):
            print(
                f"  WARNING: site reports {expected_total} ads but only {len(collected)} "
                "were captured. Pages may have loaded incompletely."
            )
        else:
            print(f"  Count check OK: {len(collected)} captured of {expected_total} reported.")

    return collected


def with_newest_sort(url):
    if "sort=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{NEWEST_SORT_QUERY}"


def skoda_model_urls(newest_first=False):
    urls = [f"{SKODA_BRAND_URL}/{slug}" for slug in SKODA_MODEL_SLUGS]
    if newest_first:
        return [with_newest_sort(url) for url in urls]
    return urls


def skoda_search_urls(newest_first=False):
    urls = [SKODA_BRAND_URL] + skoda_model_urls()
    if newest_first:
        return [with_newest_sort(url) for url in urls]
    return urls


MODEL_SLUG_RE = re.compile(r"/obiavi/avtomobili-dzhipove/skoda/([a-z0-9][a-z0-9\-]*)")


def discover_extra_model_urls(page, already_scraped_urls):
    """Return model search URLs offered by the site that we are not scraping yet."""
    page.goto(SKODA_BRAND_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(800)
    slugs = set(MODEL_SLUG_RE.findall(page.content()))
    known = {url.rstrip("/").rsplit("/", 1)[-1] for url in already_scraped_urls}
    return [
        f"{SKODA_BRAND_URL}/{slug}"
        for slug in sorted(slugs)
        if slug not in known and not re.fullmatch(r"p-\d+", slug)
    ]


def _fetch_detail_html(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("div.techData", timeout=8000)
    except Exception:
        pass
    return page.content()


def ingest_mobile_bg(
    search_urls=None,
    known_ids=None,
    output_file=RAW_LISTINGS_FILE,
    headless=True,
    scan_unlisted_models=False,
):
    search_urls = search_urls or skoda_model_urls()
    all_listings = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(30000)

        for url in search_urls:
            print(f"Scraping {url}")
            batch = scrape_search_url(page, url, known_ids=known_ids)
            before = len(all_listings)
            all_listings.update(batch)
            print(f"  Added {len(all_listings) - before} unique listings from this search.")

        if scan_unlisted_models:
            # The brand search is capped at 3000 results, so also scrape every model
            # slug the site itself offers that is missing from our config.
            for extra_url in discover_extra_model_urls(page, search_urls):
                print(f"Scraping site-listed model not in config: {extra_url}")
                extra_batch = scrape_search_url(page, extra_url)
                for lid, row in extra_batch.items():
                    all_listings.setdefault(lid, row)
            seen = set(all_listings.keys())
            print(f"Scanning brand search for models not in the slug list ({len(seen)} already captured)...")
            # Walk every brand page (no known-streak stop): unlisted models can sit
            # anywhere in the brand results, not only on the first pages.
            leftover = scrape_search_url(page, SKODA_BRAND_URL, known_ids=None)
            before = len(all_listings)
            for lid, row in leftover.items():
                if lid not in all_listings:
                    all_listings[lid] = row
            print(f"  Added {len(all_listings) - before} leftover listings from the brand search.")

        rows = list(all_listings.values())
        print("Fetching detail pages for cards with missing spec chips...")
        enrich_incomplete(
            rows,
            lambda url: _fetch_detail_html(page, url),
            delay=DETAIL_DELAY_SEC,
        )
        browser.close()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"Ingestion complete. Saved {len(rows)} listings to {output_file}.")
    return rows


if __name__ == "__main__":
    ingest_mobile_bg()
