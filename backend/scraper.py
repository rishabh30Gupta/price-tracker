import re
import logging
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

# JS to find largest-font \u20b9 element = main selling price
_PRICE_JS = """
() => {
    var re = /^[\u20b9$][\\d,]+$/;
    var best = null, bestSize = 0;
    document.querySelectorAll("*").forEach(function(el) {
        var t = el.textContent.trim();
        if (re.test(t) && el.children.length === 0) {
            var val = parseFloat(t.replace(/[^0-9]/g, ""));
            if (val < 1000) return;
            var fs = parseFloat(window.getComputedStyle(el).fontSize) || 0;
            if (fs > bestSize) { bestSize = fs; best = val; }
        }
    });
    return best;
}
"""


def clean_price(text: str) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        v = float(cleaned)
        return v if v > 0 else None
    except ValueError:
        return None


def get_largest_price(page) -> float | None:
    """Find the main selling price by largest font size on the page."""
    result = page.evaluate(_PRICE_JS)
    return float(result) if result else None


def scrape_product(url: str) -> dict | None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=LAUNCH_ARGS)
            page = browser.new_page(
                user_agent=UA,
                viewport={"width": 1280, "height": 800},
            )
            page.route("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,ttf}", lambda r: r.abort())
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            final_url = page.url

            if "flipkart.com" in final_url:
                result = _parse_flipkart(page, url)
            elif "amazon." in final_url:
                result = _parse_amazon(page, url)
            else:
                result = _parse_generic(page, url)

            browser.close()
            return result

    except Exception as e:
        logger.error(f"scrape_product error for {url}: {e}")
        return None


def _parse_flipkart(page, url) -> dict | None:
    try:
        title = None
        for sel in ["span.VU-ZEz", "span.B_NuCI", "h1"]:
            el = page.query_selector(sel)
            if el:
                title = el.text_content().strip()
                break
        title = title or page.title().split("|")[0].strip()

        price = get_largest_price(page)

        image_url = None
        for sel in ["img.DByuf4", "img._396cs4"]:
            el = page.query_selector(sel)
            if el:
                image_url = el.get_attribute("src")
                break

        if not price:
            return None

        return {"title": title, "price": price, "currency": "INR", "site": "flipkart", "image_url": image_url}
    except Exception as e:
        logger.error(f"Flipkart parse error: {e}")
        return None


def _parse_amazon(page, url) -> dict | None:
    try:
        title_el = page.query_selector("span#productTitle")
        title = title_el.text_content().strip() if title_el else page.title()

        price = None
        for sel in ["span.a-price-whole", "#priceblock_ourprice", "#priceblock_dealprice", "#price_inside_buybox"]:
            el = page.query_selector(sel)
            if el:
                price = clean_price(el.text_content())
                if price:
                    break

        if not price:
            price = get_largest_price(page)

        image_url = None
        img_el = page.query_selector("img#landingImage")
        if img_el:
            image_url = img_el.get_attribute("src")

        if not price:
            return None

        return {"title": title, "price": price, "currency": "INR", "site": "amazon", "image_url": image_url}
    except Exception as e:
        logger.error(f"Amazon parse error: {e}")
        return None


def _parse_generic(page, url) -> dict | None:
    try:
        title_el = page.query_selector("h1")
        og_title = page.query_selector("meta[property=\'og:title\']")
        title = (
            (title_el.text_content().strip() if title_el else None)
            or (og_title.get_attribute("content") if og_title else None)
            or page.title()
        )
        price = get_largest_price(page)
        og_img = page.query_selector("meta[property=\'og:image\']")
        image_url = og_img.get_attribute("content") if og_img else None
        if not price:
            return None
        return {"title": title, "price": price, "currency": "INR", "site": "other", "image_url": image_url}
    except Exception as e:
        logger.error(f"Generic parse error: {e}")
        return None
