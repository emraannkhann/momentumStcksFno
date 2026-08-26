import os
import sys
import asyncio
import requests

from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright


# ============================================================
# CONFIGURATION
# ============================================================

SCANX_URL = (
    "https://scanx.trade/stock-screener/"
    "intraday-alpha-scannner-384541"
)

DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1521804732140752978/Ca-tLLR4z5UiJ1fIsTbmKLmIp_qNqzaYkvJZqWOXJ90yQp9YUsX-fchaydCUlVfdOmCN"
)

IST = ZoneInfo("Asia/Kolkata")

# Scanner starts after 09:45 AM IST
TARGET_EXEC_TIME = dt_time(9, 30)

# How long to wait between checks while waiting for 09:45
WAIT_SECONDS = 60

# Maximum Discord message size
DISCORD_LIMIT = 1900


# ============================================================
# SCANX STOCK EXTRACTION
# ============================================================

async def get_scanx_stocks():

    print("🔄 Opening ScanX screener...")

    stocks = []

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            viewport={
                "width": 1920,
                "height": 1080,
            },
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        try:

            print(f"🌐 URL: {SCANX_URL}")

            await page.goto(
                SCANX_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print("⏳ Waiting for ScanX data...")

            # Allow JS/API data to populate
            await page.wait_for_timeout(5000)

            # ------------------------------------------------
            # Find the table
            # ------------------------------------------------

            tables = page.locator("table")

            table_count = await tables.count()

            print(f"📋 Tables detected: {table_count}")

            result_table = None

            for i in range(table_count):

                table = tables.nth(i)

                try:
                    row_count = await table.locator(
                        "tbody tr"
                    ).count()

                    if row_count > 0:
                        result_table = table
                        print(
                            f"✅ Result table found "
                            f"(table index {i}, "
                            f"{row_count} rows)"
                        )
                        break

                except Exception:
                    continue

            if result_table is None:

                # Save page for debugging
                await page.screenshot(
                    path="scanx_debug.png",
                    full_page=True
                )

                raise RuntimeError(
                    "❌ Could not find populated ScanX table. "
                    "Screenshot saved as scanx_debug.png"
                )

            # ------------------------------------------------
            # Read headers
            # ------------------------------------------------

            headers = []

            header_cells = result_table.locator(
                "thead tr th"
            )

            header_count = await header_cells.count()

            if header_count > 0:

                for i in range(header_count):

                    text = await header_cells.nth(i).inner_text()

                    headers.append(
                        " ".join(text.split()).strip()
                    )

            print("📌 Headers:")
            print(headers)

            # ------------------------------------------------
            # Read rows
            # ------------------------------------------------

            rows = result_table.locator(
                "tbody tr"
            )

            row_count = await rows.count()

            print(
                f"📊 Initial ScanX rows: {row_count}"
            )

            for i in range(row_count):

                cells = rows.nth(i).locator("td")

                cell_count = await cells.count()

                if cell_count < 2:
                    continue

                values = []

                for j in range(cell_count):

                    value = await cells.nth(j).inner_text()

                    value = " ".join(
                        value.split()
                    ).strip()

                    values.append(value)

                # --------------------------------------------
                # ScanX structure
                #
                # Name
                # Price
                # Day Price Change
                # Change %
                # Volume
                # PE Ratio
                # Market Cap
                # EMA (20)
                # Supertrend
                # --------------------------------------------

                if len(values) >= 9:

                    stock = {
                        "name": values[0],
                        "price": values[1],
                        "change": values[2],
                        "change_pct": values[3],
                        "volume": values[4],
                        "pe": values[5],
                        "market_cap": values[6],
                        "ema20": values[7],
                        "supertrend": values[8],
                    }

                    stocks.append(stock)

                else:

                    print(
                        f"⚠️ Skipping malformed row: "
                        f"{values}"
                    )

            # ------------------------------------------------
            # Try to load remaining rows
            #
            # Your screener can show:
            # "Showing 25 of 31 results"
            #
            # Therefore attempt to click possible
            # pagination/load-more controls.
            # ------------------------------------------------

            previous_count = len(stocks)

            for attempt in range(5):

                text = await page.locator(
                    "body"
                ).inner_text()

                if "Showing" not in text:
                    break

                # Look for common buttons
                possible_buttons = [
                    "button:has-text('Load More')",
                    "button:has-text('Show More')",
                    "button:has-text('Next')",
                    "button:has-text('More')",
                    "a:has-text('Next')",
                    "[aria-label='Next']",
                ]

                clicked = False

                for selector in possible_buttons:

                    locator = page.locator(selector)

                    try:

                        count = await locator.count()

                        if count == 0:
                            continue

                        for b in range(count):

                            button = locator.nth(b)

                            if await button.is_visible():

                                print(
                                    f"➡️ Clicking: "
                                    f"{selector}"
                                )

                                await button.click()

                                await page.wait_for_timeout(
                                    1500
                                )

                                clicked = True
                                break

                        if clicked:
                            break

                    except Exception:
                        continue

                if not clicked:
                    break

                # Re-read table
                rows = result_table.locator(
                    "tbody tr"
                )

                new_count = await rows.count()

                print(
                    f"📊 Rows after attempt "
                    f"{attempt + 1}: {new_count}"
                )

                # Extract any new rows
                for i in range(
                    previous_count,
                    new_count
                ):

                    cells = rows.nth(i).locator("td")

                    cell_count = await cells.count()

                    if cell_count < 9:
                        continue

                    values = []

                    for j in range(9):

                        value = await cells.nth(
                            j
                        ).inner_text()

                        values.append(
                            " ".join(
                                value.split()
                            ).strip()
                        )

                    stocks.append({
                        "name": values[0],
                        "price": values[1],
                        "change": values[2],
                        "change_pct": values[3],
                        "volume": values[4],
                        "pe": values[5],
                        "market_cap": values[6],
                        "ema20": values[7],
                        "supertrend": values[8],
                    })

                previous_count = new_count

            # ------------------------------------------------
            # Deduplicate stocks
            # ------------------------------------------------

            unique_stocks = []

            seen = set()

            for stock in stocks:

                key = stock["name"].strip().upper()

                if key not in seen:

                    seen.add(key)

                    unique_stocks.append(
                        stock
                    )

            print(
                f"✅ Total unique stocks: "
                f"{len(unique_stocks)}"
            )

            return unique_stocks

        finally:

            await browser.close()


# ============================================================
# DISCORD
# ============================================================

def send_discord_notifications(stocks):

    if not DISCORD_WEBHOOK_URL:

        raise RuntimeError(
            "DISCORD_WEBHOOK_URL is not configured."
        )

    now = datetime.now(IST)

    header = (
        "📊 **SCANX — INTRADAY ALPHA SCANNER**\n"
        f"🕘 **{now.strftime('%d-%m-%Y %I:%M:%S %p')} IST**\n"
        f"📈 **{len(stocks)} stocks found**\n\n"
    )

    # --------------------------------------------------------
    # No stocks
    # --------------------------------------------------------

    if not stocks:

        payload = {
            "content": (
                "⚠️ **SCANX — INTRADAY ALPHA SCANNER**\n"
                f"No stocks matched the scanner at "
                f"{now.strftime('%I:%M %p')} IST."
            )
        }

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=20,
        )

        print(
            f"Discord response: "
            f"{response.status_code}"
        )

        return

    # --------------------------------------------------------
    # Build messages
    # --------------------------------------------------------

    messages = []

    current_message = header

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        stock_text = (
            f"**{index}. "
            f"{stock['name']}**\n"
            f"💰 Price: **₹{stock['price']}**\n"
            f"📈 Change: **{stock['change']} "
            f"({stock['change_pct']})**\n"
            f"📊 Volume: **{stock['volume']}**\n"
            f"📐 EMA20: **₹{stock['ema20']}**\n"
            f"🚦 Supertrend: "
            f"**₹{stock['supertrend']}**\n"
            f"📊 P/E: **{stock['pe']}**\n"
            f"🏦 Market Cap: "
            f"**{stock['market_cap']} Cr**\n\n"
        )

        if (
            len(current_message)
            + len(stock_text)
            > DISCORD_LIMIT
        ):

            messages.append(
                current_message
            )

            current_message = stock_text

        else:

            current_message += stock_text

    if current_message:

        messages.append(
            current_message
        )

    # --------------------------------------------------------
    # Send to Discord
    # --------------------------------------------------------

    for index, message in enumerate(
        messages,
        start=1
    ):

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": message
            },
            timeout=20,
        )

        if response.status_code not in (
            200,
            204,
        ):

            print(
                f"❌ Discord error "
                f"part {index}: "
                f"{response.status_code}"
            )

            print(response.text)

        else:

            print(
                f"✅ Discord chunk "
                f"{index}/{len(messages)} sent."
            )


# ============================================================
# WAIT UNTIL 09:45 IST
# ============================================================

async def wait_until_0945():

    print(
        "⏳ Scanner initialized."
    )

    print(
        "🎯 Waiting until "
        "09:30 AM IST..."
    )

    while True:

        now = datetime.now(IST)

        if now.time() >= TARGET_EXEC_TIME:

            print(
                f"🎯 09:30 AM IST reached "
                f"({now.strftime('%H:%M:%S')})"
            )

            break

        print(
            f"🕒 Current time: "
            f"{now.strftime('%H:%M:%S')} IST"
        )

        await asyncio.sleep(
            WAIT_SECONDS
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    run_now = (
        "--now" in sys.argv
        or "-n" in sys.argv
    )

    if run_now:

        print(
            "⚡ Immediate execution "
            "triggered (--now)"
        )

    else:

        await wait_until_0945()

    # --------------------------------------------------------
    # Scan ScanX
    # --------------------------------------------------------

    stocks = await get_scanx_stocks()

    print(
        f"✅ ScanX returned "
        f"{len(stocks)} stocks."
    )

    # --------------------------------------------------------
    # Send Discord
    # --------------------------------------------------------

    send_discord_notifications(
        stocks
    )

    print(
        "🏁 Execution completed successfully."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(main())
