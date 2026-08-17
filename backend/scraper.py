import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


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
        title_el = (
            soup.find("span", {"class": "VU-ZEz"})
            or soup.find("span", {"class": "B_NuCI"})
            or soup.find("h1", {"class": "_9E25nV"})
        )
        title = title_el.get_text(strip=True) if title_el else "Unknown Product"

        price_el = (
            soup.find("div", {"class": "Nx9bqj CxhGGd"})
            or soup.find("div", {"class": "_30jeq3 _16Jk6d"})
            or soup.find("div", {"class": "_30jeq3"})
        )
        price = clean_price(price_el.get_text()) if price_el else None

        image_el = soup.find("img", {"class": "DByuf4"}) or soup.find("img", {"class": "_396cs4"})
        image_url = image_el["src"] if image_el else None

        if not price:
            return None

        return {
            "title": title,
            "price": price,
            "currency": "INR",
            "site": "flipkart",
            "image_url": image_url,
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
        # Follow redirects to handle short URLs (dl.flipkart.com/s/..., amzn.in, etc.)
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        final_url = resp.url  # use the final URL after redirects
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
