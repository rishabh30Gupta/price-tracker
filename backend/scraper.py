import requests
from bs4 import BeautifulSoup
import re
import logging
import json

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"',
}


def get_session(site: str) -> requests.Session:
    """Create a session that mimics a real browser visit."""
    session = requests.Session()
    session.headers.update(HEADERS)

    if site == "flipkart":
        # Visit homepage first to get cookies (bypasses initial bot check)
        try:
            session.get("https://www.flipkart.com", timeout=10)
        except Exception:
            pass
    elif site == "amazon":
        try:
            session.get("https://www.amazon.in", timeout=10)
        except Exception:
            pass

    return session


def clean_price(text: str) -> float | None:
    """Extract numeric price from a string like ₹1,23,456 or $99.99"""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except ValueError:
        return None


def scrape_amazon(soup, url) -> dict | None:
    try:
        title_el = soup.find("span", {"id": "productTitle"})
        title = title_el.get_text(strip=True) if title_el else "Unknown Product"

        # Try multiple price selectors Amazon uses
        price = None
        selectors = [
            ("span", {"class": "a-price-whole"}),
            ("span", {"id": "priceblock_ourprice"}),
            ("span", {"id": "priceblock_dealprice"}),
            ("span", {"class": "a-offscreen"}),
        ]
        for tag, attrs in selectors:
            el = soup.find(tag, attrs)
            if el:
                price = clean_price(el.get_text())
                if price:
                    break

        image_el = soup.find("img", {"id": "landingImage"})
        image_url = image_el["src"] if image_el else None

        if not price:
            return None

        return {
            "title": title,
            "price": price,
            "currency": "INR",
            "site": "amazon",
            "image_url": image_url,
        }
    except Exception as e:
        logger.error(f"Amazon scrape error: {e}")
        return None


def scrape_flipkart(soup, url) -> dict | None:
    try:
        # First try: extract from embedded JSON (most reliable)
        for script in soup.find_all("script"):
            text = script.string or ""
            # Look for finalPrice or selling price in JSON blobs
            prices = re.findall(r'"(?:finalPrice|sellingPrice|price)"\s*:\s*\{[^}]*"value"\s*:\s*(\d+)', text)
            if not prices:
                prices = re.findall(r'"(?:finalPrice|sellingPrice)"\s*:\s*(\d+)', text)
            if prices:
                price = float(prices[0])
                # Get title from JSON too
                titles = re.findall(r'"title"\s*:\s*"([^"]{10,})"', text)
                title = titles[0] if titles else None
                if not title:
                    title_el = soup.find("span", {"class": "VU-ZEz"}) or soup.find("span", {"class": "B_NuCI"})
                    title = title_el.get_text(strip=True) if title_el else "Flipkart Product"
                image_el = soup.find("img", {"class": "DByuf4"}) or soup.find("img", {"class": "_396cs4"})
                return {
                    "title": title,
                    "price": price,
                    "currency": "INR",
                    "site": "flipkart",
                    "image_url": image_el["src"] if image_el else None,
                }

        # Second try: CSS selectors
        title_el = (
            soup.find("span", {"class": "VU-ZEz"})
            or soup.find("span", {"class": "B_NuCI"})
            or soup.find("h1", {"class": "_9E25nV"})
        )
        title = title_el.get_text(strip=True) if title_el else "Flipkart Product"

        price_el = (
            soup.find("div", {"class": "Nx9bqj CxhGGd"})
            or soup.find("div", {"class": "Nx9bqj"})
            or soup.find("div", {"class": "_30jeq3 _16Jk6d"})
            or soup.find("div", {"class": "_30jeq3"})
        )
        price = clean_price(price_el.get_text()) if price_el else None

        # Third try: find ₹ in raw text
        if not price:
            matches = re.findall(r'₹\s*([\d,]+)', soup.get_text())
            if matches:
                price = clean_price(matches[0])

        image_el = soup.find("img", {"class": "DByuf4"}) or soup.find("img", {"class": "_396cs4"})

        if not price:
            return None

        return {
            "title": title,
            "price": price,
            "currency": "INR",
            "site": "flipkart",
            "image_url": image_el["src"] if image_el else None,
        }
    except Exception as e:
        logger.error(f"Flipkart scrape error: {e}")
        return None


def scrape_generic(soup, url) -> dict | None:
    """Best-effort scrape for other sites using common patterns."""
    try:
        title = None
        for selector in [
            soup.find("h1"),
            soup.find("meta", {"property": "og:title"}),
        ]:
            if selector:
                title = selector.get("content") or selector.get_text(strip=True)
                break
        title = title or "Unknown Product"

        price = None
        # Look for elements that contain currency symbols
        for el in soup.find_all(string=re.compile(r"[₹$€£]\s*[\d,]+")):
            price = clean_price(el)
            if price:
                break

        image_url = None
        og_img = soup.find("meta", {"property": "og:image"})
        if og_img:
            image_url = og_img.get("content")

        if not price:
            return None

        return {
            "title": title,
            "price": price,
            "currency": "INR",
            "site": "other",
            "image_url": image_url,
        }
    except Exception as e:
        logger.error(f"Generic scrape error: {e}")
        return None


def scrape_product(url: str) -> dict | None:
    try:
        # Determine site first for session setup
        if "amazon." in url:
            site = "amazon"
        elif "flipkart.com" in url:
            site = "flipkart"
        else:
            site = "other"

        session = get_session(site)
        resp = session.get(url, timeout=20, allow_redirects=True)
        resp.raise_for_status()
        final_url = resp.url

        # Check if we got a captcha page
        if "recaptcha" in resp.text.lower() and len(resp.text) < 5000:
            logger.warning(f"reCAPTCHA hit for {url}")
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        if "amazon." in final_url:
            return scrape_amazon(soup, final_url)
        elif "flipkart.com" in final_url:
            return scrape_flipkart(soup, final_url)
        else:
            return scrape_generic(soup, final_url)
    except Exception as e:
        logger.error(f"scrape_product error for {url}: {e}")
        return None
