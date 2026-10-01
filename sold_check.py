import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from scraper import normalize_listing_url

INACTIVE_MARKERS = (
    "търсената от вас обява е изтрита или не е активна",
    "обявата е изтрита или не е активна",
    "обявата е изтрита",
    "обявата не е активна",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "bg-BG,bg;q=0.9,en;q=0.8",
}

_thread_local = threading.local()


def listing_url(item):
    link = normalize_listing_url((item or {}).get("link") or "")
    if link:
        return link
    lid = (item or {}).get("listing_id")
    if lid:
        return f"https://www.mobile.bg/obiava-{lid}"
    return ""


def is_inactive_response(status_code, final_url, html):
    """Only treat 404/410 or explicit inactive copy as sold. Never captcha/errors."""
    if status_code in (404, 410):
        return True
    if status_code >= 400:
        return False
    text = (html or "").strip()
    if not text:
        return False
    lower = text.lower()
    if any(token in lower for token in ("captcha", "cloudflare", "access denied", "cf-browser-verification")):
        return False
    return any(marker in lower for marker in INACTIVE_MARKERS)


def _thread_client(timeout):
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=timeout)
        _thread_local.client = client
    return client


def _check_one(item, timeout):
    lid = str(item.get("listing_id") or "")
    url = listing_url(item)
    if not lid or not url:
        return None
    try:
        response = _thread_client(timeout).get(url)
        if is_inactive_response(response.status_code, str(response.url), response.text):
            return lid
    except httpx.HTTPError:
        return None
    return None


def find_sold_listing_ids(listings, workers=5, timeout=20.0):
    """Return listing_ids whose mobile.bg pages are gone or marked inactive."""
    sold = []
    total = len(listings)
    checked = 0
    print(f"Checking {total} stored listings for sold/inactive ads...")

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_check_one, item, timeout) for item in listings]
            for future in as_completed(futures):
                checked += 1
                sold_id = future.result()
                if sold_id:
                    sold.append(sold_id)
                if checked % 100 == 0 or checked == total:
                    print(f"  Checked {checked}/{total}; sold so far: {len(sold)}")
    finally:
        client = getattr(_thread_local, "client", None)
        if client is not None:
            client.close()

    print(f"Sold check complete. Inactive ads: {len(sold)}")
    return sold
