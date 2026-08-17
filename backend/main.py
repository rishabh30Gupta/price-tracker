from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
from datetime import datetime

app = FastAPI(title="Price Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get("DB_PATH", "tracker.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            title TEXT,
            current_price REAL,
            initial_price REAL,
            currency TEXT DEFAULT 'INR',
            chat_id TEXT NOT NULL,
            site TEXT,
            image_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_checked TEXT
        );
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            price REAL,
            checked_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
    """)
    conn.commit()
    conn.close()


init_db()


class AddProductRequest(BaseModel):
    url: str
    chat_id: str


class RemoveProductRequest(BaseModel):
    chat_id: str


@app.get("/")
def root():
    return {"status": "Price Tracker API running"}


class ManualProductRequest(BaseModel):
    url: str
    chat_id: str
    title: str
    price: float
    site: str
    image_url: Optional[str] = None
    currency: str = "INR"


@app.post("/products/manual")
def add_product_manual(req: ManualProductRequest):
    """Add a product with pre-scraped data (used by the browser extension)."""
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO products (url, title, current_price, initial_price, currency, chat_id, site, image_url, last_checked)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (req.url, req.title, req.price, req.price,
         req.currency, req.chat_id, req.site,
         req.image_url, datetime.utcnow().isoformat())
    )
    product_id = cur.lastrowid
    conn.execute(
        "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
        (product_id, req.price)
    )
    conn.commit()
    conn.close()
    return {"id": product_id, "title": req.title, "price": req.price, "site": req.site, "image_url": req.image_url}


@app.post("/products")
def add_product(req: AddProductRequest):
    from scraper import scrape_product
    data = scrape_product(req.url)
    if not data:
        raise HTTPException(status_code=400, detail="Could not scrape product. Check the URL.")

    conn = get_db()
    cur = conn.execute(
        """INSERT INTO products (url, title, current_price, initial_price, currency, chat_id, site, image_url, last_checked)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (req.url, data["title"], data["price"], data["price"],
         data.get("currency", "INR"), req.chat_id, data["site"],
         data.get("image_url"), datetime.utcnow().isoformat())
    )
    product_id = cur.lastrowid
    conn.execute(
        "INSERT INTO price_history (product_id, price) VALUES (?, ?)",
        (product_id, data["price"])
    )
    conn.commit()
    conn.close()
    return {"id": product_id, **data}


@app.get("/products/{chat_id}")
def list_products(chat_id: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM products WHERE chat_id = ? ORDER BY created_at DESC",
        (chat_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.delete("/products/{product_id}")
def remove_product(product_id: int, req: RemoveProductRequest):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM products WHERE id = ? AND chat_id = ?",
        (product_id, req.chat_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    conn.execute("DELETE FROM price_history WHERE product_id = ?", (product_id,))
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return {"detail": "Removed successfully"}


@app.get("/products/{product_id}/history")
def price_history(product_id: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT price, checked_at FROM price_history WHERE product_id = ? ORDER BY checked_at ASC",
        (product_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/check")
def trigger_check():
    """Called by GitHub Actions to run price checks."""
    import threading
    from checker import check_prices

    def run():
        check_prices()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return {"detail": "Price check started"}
