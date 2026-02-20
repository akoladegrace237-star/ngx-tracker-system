"""
NGX Equities Price List Scraper
Uses Playwright (headless Chromium) to render the JavaScript-driven
DataTable and extract all equity rows from ngxgroup.com.
"""

import re
import logging
from datetime import datetime

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

logger = logging.getLogger(__name__)

BASE_URL = "https://ngxgroup.com/exchange/data/equities-price-list/"

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_change(change_str: str) -> float:
    """Parse change string like '▲0.62' or '▼1.50' into a signed float."""
    if not change_str or change_str.strip() in ("-", "", "0.00", "0"):
        return 0.0
    is_negative = "▼" in change_str or change_str.strip().startswith("-")
    clean = re.sub(r"[▲▼\s,+\-]", "", change_str)
    try:
        value = float(clean)
        return -abs(value) if is_negative else abs(value)
    except ValueError:
        return 0.0


def parse_number(value_str: str) -> float:
    """Parse numeric strings with commas into float."""
    if not value_str or value_str.strip() in ("-", ""):
        return 0.0
    try:
        return float(value_str.replace(",", "").strip())
    except ValueError:
        return 0.0


# ── Core scraper ──────────────────────────────────────────────────────────────

def _extract_all_rows(page) -> list[list[str]]:
    """
    Click 'All' in the DataTable length-select so every row is visible,
    then collect every <tr> from the tbody.
    Falls back to paginating if 'All' is not available.
    """
    # Try to show ALL rows at once via the DataTable length menu
    try:
        # The DataTable length-select typically has option value "-1" for All
        page.select_option("select[name*='_length']", value="-1", timeout=5000)
        page.wait_for_timeout(2000)
        logger.info("Set DataTable to show all rows.")
    except Exception:
        logger.info("Could not set 'All' rows — will read whatever is visible.")

    rows_data = _read_visible_rows(page)
    logger.info(f"Extracted {len(rows_data)} rows from table.")
    return rows_data


def _read_visible_rows(page) -> list[list[str]]:
    """Read all <td> cells from the visible DataTable tbody."""
    return page.evaluate("""() => {
        const rows = [];
        // Try the primary securities table first
        let trs = document.querySelectorAll(
            'table.dataTable tbody tr, table#example tbody tr, ' +
            'table.wpDataTable tbody tr'
        );
        // If the above is empty, try any large table
        if (trs.length === 0) {
            trs = document.querySelectorAll('table tbody tr');
        }
        for (const tr of trs) {
            const cells = tr.querySelectorAll('td');
            if (cells.length < 6) continue;
            const row = [];
            for (const td of cells) {
                row.push(td.innerText.trim());
            }
            rows.push(row);
        }
        return rows;
    }""")


def _to_dataframe(rows_data: list[list[str]]) -> pd.DataFrame:
    """Convert raw row data into a typed DataFrame."""
    if not rows_data:
        return pd.DataFrame()

    # Pad rows to equal length
    max_cols = max(len(r) for r in rows_data)
    rows_data = [r + [""] * (max_cols - len(r)) for r in rows_data]

    col_map = {
        0: "Company",
        1: "Prev_Close",
        2: "Opening_Price",
        3: "High",
        4: "Low",
        5: "Close",
        6: "Change",
        7: "Trades",
        8: "Volume",
        9: "Value",
        10: "Trade_Date",
    }

    df = pd.DataFrame(rows_data)
    df = df.rename(columns={i: col_map.get(i, f"Col_{i}") for i in df.columns})

    for col in ["Prev_Close", "Opening_Price", "High", "Low", "Close", "Trades", "Volume", "Value"]:
        if col in df.columns:
            df[col] = df[col].apply(parse_number)

    if "Change" in df.columns:
        df["Change"] = df["Change"].apply(parse_change)

    # Percentage change
    df["Pct_Change"] = df.apply(
        lambda r: round((r["Change"] / r["Prev_Close"]) * 100, 2)
        if r.get("Prev_Close", 0) != 0
        else 0.0,
        axis=1,
    )

    df["Fetched_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Remove blank company rows
    df = df[df["Company"].str.strip() != ""].reset_index(drop=True)
    return df


def get_equities_data(url: str = BASE_URL, timeout_ms: int = 60_000) -> pd.DataFrame:
    """
    Launch a headless Chromium browser, load the NGX equities page,
    wait for the DataTable population, and return a DataFrame of all stocks.
    """
    logger.info(f"Launching Playwright to fetch: {url}")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except PWTimeoutError:
            logger.warning("networkidle timed out — trying domcontentloaded fallback.")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(8000)  # give JS time to render
            except Exception as e:
                logger.error(f"Page load failed: {e}")
                browser.close()
                return pd.DataFrame()

        # Wait for at least one data row to appear
        try:
            page.wait_for_selector("table tbody tr td", timeout=30_000)
            logger.info("Data rows detected in DOM.")
        except PWTimeoutError:
            logger.error("No data rows appeared within 30 s. Page may require login or JS is blocked.")
            browser.close()
            return pd.DataFrame()

        # Give DataTable extra time to fully populate
        page.wait_for_timeout(3000)

        rows_data = _extract_all_rows(page)
        browser.close()

    df = _to_dataframe(rows_data)
    logger.info(f"Final DataFrame: {len(df)} stocks.")
    return df


# ── Quick sanity check ────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = get_equities_data()
    if not df.empty:
        print(df[["Company", "Prev_Close", "Close", "Change", "Pct_Change"]].head(20).to_string(index=False))
    else:
        print("No data returned.")
