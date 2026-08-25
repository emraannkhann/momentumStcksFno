import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.async_api import async_playwright

CHARTINK_URL = "https://chartink.com/screener/imr-fortunestocks"

#DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1521804732140752978/Ca-tLLR4z5UiJ1fIsTbmKLmIp_qNqzaYkvJZqWOXJ90yQp9YUsX-fchaydCUlVfdOmCN"

IST = ZoneInfo("Asia/Kolkata")


async def get_chartink_stocks():

    print("Opening Chartink...")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1600,
                "height": 1000
            }
        )

        try:

            await page.goto(
                CHARTINK_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print("Chartink page opened.")

            # Give Chartink time to execute its JS
            await page.wait_for_timeout(5000)

            # Wait for stock table
            try:

                await page.wait_for_selector(
                    "table",
                    timeout=30000
                )

            except Exception:

                print(
                    "WARNING: Could not find table immediately."
                )

            # Give AJAX results additional time
            await page.wait_for_timeout(5000)

            # --------------------------------------------------
            # Find table rows
            # --------------------------------------------------

            rows = await page.locator(
                "table tbody tr"
            ).all()

            print(
                f"Found {len(rows)} table rows."
            )

            stocks = []

            for row in rows:

                cells = await row.locator("td").all()

                if not cells:
                    continue

                values = []

                for cell in cells:

                    text = await cell.inner_text()

                    values.append(
                        text.strip()
                    )

                print("ROW:", values)

                # ------------------------------------------------
                # Look for NSE symbol
                # ------------------------------------------------

                for value in values:

                    value = value.strip().upper()

                    # Ignore obvious non-symbol values
                    if not value:
                        continue

                    if value in [
                        "SYMBOL",
                        "STOCK",
                        "STOCK NAME",
                        "CLOSE",
                        "VOLUME",
                        "% CHANGE"
                    ]:
                        continue

                    # NSE symbols normally don't contain spaces
                    if (
                        " " not in value
                        and len(value) <= 30
                        and any(c.isalpha() for c in value)
                    ):

                        # Avoid numeric values
                        if not value.replace(".", "").isdigit():

                            stocks.append(value)

                            break

            # Remove duplicates
            stocks = list(
                dict.fromkeys(stocks)
            )

            return stocks

        finally:

            await browser.close()

async def get_chartink_stocks_1():

    print("Opening Chartink...")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080
            }
        )

        try:

            await page.goto(
                CHARTINK_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print("Chartink page opened.")

            # --------------------------------------------------
            # Wait for Chartink JavaScript/AJAX
            # --------------------------------------------------

            await page.wait_for_timeout(8000)

            # --------------------------------------------------
            # Find all tables
            # --------------------------------------------------

            tables = page.locator("table")

            table_count = await tables.count()

            print(
                f"Tables found: {table_count}"
            )

            if table_count == 0:

                raise RuntimeError(
                    "No tables found on Chartink page."
                )

            # --------------------------------------------------
            # Inspect every table
            # --------------------------------------------------

            result_table = None

            for table_index in range(table_count):

                table = tables.nth(
                    table_index
                )

                # Don't require table to be visible
                # Just inspect its rows.

                rows = table.locator(
                    "tbody tr"
                )

                row_count = await rows.count()

                print(
                    f"Table {table_index}: "
                    f"{row_count} rows"
                )

                if row_count > 0:

                    result_table = table

                    print(
                        f"Using table {table_index}"
                    )

                    break

            if result_table is None:

                raise RuntimeError(
                    "Could not find Chartink result table."
                )

            # --------------------------------------------------
            # Read headers
            # --------------------------------------------------

            headers = await result_table.locator(
                "thead th"
            ).all_inner_texts()

            headers = [
                h.strip()
                for h in headers
            ]

            print("\nHEADERS:")
            print(headers)

            # --------------------------------------------------
            # Detect columns
            # --------------------------------------------------

            symbol_index = None
            close_index = None
            change_index = None
            volume_index = None

            for index, header in enumerate(
                headers
            ):

                h = (
                    header
                    .lower()
                    .strip()
                    .replace("\n", " ")
                )

                print(
                    f"Column {index}: {header}"
                )

                # Symbol
                if (
                    "symbol" in h
                    or "nsecode" in h
                    or "nse code" in h
                ):

                    symbol_index = index

                # Close
                elif (
                    h == "close"
                    or "close price" in h
                    or "closeprice" in h
                ):

                    close_index = index

                # Percentage change
                elif (
                    "% change" in h
                    or "%change" in h
                    or "change %" in h
                    or "per chg" in h
                    or "percentage change" in h
                ):

                    change_index = index

                # Volume
                elif "volume" in h:

                    volume_index = index

            print("\nDetected columns:")

            print(
                "Symbol :",
                symbol_index
            )

            print(
                "Close  :",
                close_index
            )

            print(
                "Change :",
                change_index
            )

            print(
                "Volume :",
                volume_index
            )

            # --------------------------------------------------
            # Read result rows
            # --------------------------------------------------

            rows = result_table.locator(
                "tbody tr"
            )

            row_count = await rows.count()

            print(
                f"\nResult rows: {row_count}"
            )

            stocks = []

            for i in range(row_count):

                cells = rows.nth(i).locator(
                    "td"
                )

                cell_count = await cells.count()

                values = []

                for j in range(cell_count):

                    value = await cells.nth(
                        j
                    ).inner_text()

                    values.append(
                        value.strip()
                    )

                print(
                    f"ROW {i + 1}:",
                    values
                )

                if not values:
                    continue

                # --------------------------------------------------
                # Safe getter
                # --------------------------------------------------

                def get_value(index):

                    if (
                        index is not None
                        and index < len(values)
                    ):

                        return values[index]

                    return ""

                stock = {

                    "symbol": get_value(
                        symbol_index
                    ),

                    "close": get_value(
                        close_index
                    ),

                    "change": get_value(
                        change_index
                    ),

                    "volume": get_value(
                        volume_index
                    )

                }

                if stock["symbol"]:

                    stocks.append(
                        stock
                    )

            # --------------------------------------------------
            # Remove duplicates
            # --------------------------------------------------

            unique_stocks = []

            seen = set()

            for stock in stocks:

                symbol = stock["symbol"]

                if symbol not in seen:

                    seen.add(symbol)

                    unique_stocks.append(
                        stock
                    )

            print("\n====================================")
            print("FINAL STOCK DATA")
            print("====================================")

            for stock in unique_stocks:

                print(
                    f"{stock['symbol']} | "
                    f"Close: {stock['close']} | "
                    f"Change: {stock['change']} | "
                    f"Volume: {stock['volume']}"
                )

            print(
                f"\nTotal stocks: "
                f"{len(unique_stocks)}"
            )

            return unique_stocks

        finally:

            await browser.close()

async def get_chartink_stocks_new():

    print("Opening Chartink...")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080
            }
        )

        await page.goto(
            CHARTINK_URL,
            wait_until="networkidle",
            timeout=60000
        )

        print("Page loaded.")

        await page.wait_for_timeout(8000)

        # Get the first table
        table = page.locator("table").first

        headers = await table.locator(
            "thead th"
        ).all_inner_texts()

        headers = [h.strip() for h in headers]

        print("\nHEADERS:")
        print(headers)

        # Find columns
        symbol_index = None
        close_index = None
        change_index = None
        volume_index = None

        for index, header in enumerate(headers):

            h = header.lower().strip()

            if "symbol" in h or "nsecode" in h or "nse code" in h:
                symbol_index = index

            elif "close" in h:
                close_index = index

            elif (
                "% change" in h
                or "%change" in h
                or "change %" in h
                or "per chg" in h
            ):
                change_index = index

            elif "volume" in h:
                volume_index = index

        print("\nDetected columns:")
        print("Symbol :", symbol_index)
        print("Close  :", close_index)
        print("Change :", change_index)
        print("Volume :", volume_index)

        # Get rows
        rows = table.locator("tbody tr")

        count = await rows.count()

        print(f"\nRows found: {count}")

        stocks = []

        for i in range(count):

            cells = rows.nth(i).locator("td")

            cell_count = await cells.count()

            values = []

            for j in range(cell_count):

                value = await cells.nth(j).inner_text()

                values.append(value.strip())

            print("ROW:", values)

            if not values:
                continue

            def get_value(index):

                if index is not None and index < len(values):
                    return values[index]

                return ""

            stock = {
                "symbol": get_value(symbol_index),
                "close": get_value(close_index),
                "change": get_value(change_index),
                "volume": get_value(volume_index),
            }

            if stock["symbol"]:
                stocks.append(stock)

        await browser.close()

        return stocks

async def get_chartink_stocks_2():

    print("Opening Chartink...")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080
            }
        )

        try:

            await page.goto(
                CHARTINK_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print("Chartink page opened.")

            # Allow Chartink JS/AJAX to populate results
            await page.wait_for_timeout(8000)

            # --------------------------------------------------
            # Find tables
            # --------------------------------------------------

            tables = page.locator("table")

            table_count = await tables.count()

            print(
                f"Tables found: {table_count}"
            )

            result_table = None

            for table_index in range(
                table_count
            ):

                table = tables.nth(
                    table_index
                )

                rows = table.locator(
                    "tbody tr"
                )

                row_count = await rows.count()

                print(
                    f"Table {table_index}: "
                    f"{row_count} rows"
                )

                if row_count > 0:

                    result_table = table

                    print(
                        f"Using table {table_index}"
                    )

                    break

            if result_table is None:

                raise RuntimeError(
                    "Could not find Chartink result table."
                )

            # --------------------------------------------------
            # Get rows
            # --------------------------------------------------

            rows = result_table.locator(
                "tbody tr"
            )

            row_count = await rows.count()

            print(
                f"\nResult rows: {row_count}"
            )

            stocks = []

            for i in range(
                row_count
            ):

                cells = rows.nth(
                    i
                ).locator("td")

                cell_count = await cells.count()

                values = []

                for j in range(
                    cell_count
                ):

                    text = await cells.nth(
                        j
                    ).inner_text()

                    values.append(
                        text.strip()
                    )

                print(
                    f"ROW {i + 1}:",
                    values
                )

                # --------------------------------------------------
                # Expected Chartink structure
                #
                # 0 = Rank
                # 1 = Company Name
                # 2 = Symbol
                # 3 = Close
                # 4 = % Change
                # 5 = Volume
                # 6 = Extra
                # --------------------------------------------------

                if len(values) < 6:

                    print(
                        f"Skipping malformed row: "
                        f"{values}"
                    )

                    continue

                stock = {

                    "rank": values[0],

                    "name": values[1],

                    "symbol": values[2],

                    "close": values[3],

                    "change": values[4],

                    "volume": values[5]

                }

                stocks.append(
                    stock
                )

            # --------------------------------------------------
            # Remove duplicate symbols
            # --------------------------------------------------

            unique_stocks = []

            seen = set()

            for stock in stocks:

                symbol = stock["symbol"]

                if symbol not in seen:

                    seen.add(symbol)

                    unique_stocks.append(
                        stock
                    )

            # --------------------------------------------------
            # Print final result
            # --------------------------------------------------

            print(
                "\n===================================="
            )

            print(
                "FINAL STOCK DATA"
            )

            print(
                "===================================="
            )

            for stock in unique_stocks:

                print(
                    f"{stock['rank']}. "
                    f"{stock['symbol']} | "
                    f"Close: {stock['close']} | "
                    f"Change: {stock['change']} | "
                    f"Volume: {stock['volume']}"
                )

            print(
                f"\nTotal stocks: "
                f"{len(unique_stocks)}"
            )

            return unique_stocks

        finally:

            await browser.close()


def send_discord(stocks):

    if not DISCORD_WEBHOOK_URL:

        raise RuntimeError(
            "DISCORD_WEBHOOK_URL is not configured"
        )

    now = datetime.now(IST)

    message = (
        "📊 **IMR-FortuneStocks**\n"
        f"🕘 **{now.strftime('%d-%m-%Y %I:%M:%S %p')} IST**\n"
        f"📈 **{len(stocks)} stocks found**\n\n"
    )

    for i, stock in enumerate(stocks, 1):

        message += (
            f"**{i}. {stock['symbol']}**\n"
            f"💰 Close: **{stock['close']}**\n"
            f"📈 Change: **{stock['change']}**\n"
            f"📊 Volume: **{stock['volume']}**\n\n"
        )

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={
            "content": message
        },
        timeout=20
    )

    response.raise_for_status()

    print("✅ Discord notification sent.")

def send_discord_1(stocks):

    if not DISCORD_WEBHOOK_URL:

        raise RuntimeError(
            "DISCORD_WEBHOOK_URL is not configured"
        )

    now = datetime.now(IST)

    # --------------------------------------------------
    # Build Discord message
    # --------------------------------------------------

    lines = [

        "📊 **IMR-FortuneStocks**",

        f"🕘 **{now.strftime('%d-%m-%Y %I:%M:%S %p')} IST**",

        f"📈 **{len(stocks)} stocks found**",

        ""

    ]

    for i, stock in enumerate(
        stocks,
        start=1
    ):

        lines.extend([

            f"**{i}. {stock['symbol']}**",

            f"💰 Close: **{stock['close']}**",

            f"📈 Change: **{stock['change']}**",

            f"📊 Volume: **{stock['volume']}**",

            ""

        ])

    message = "\n".join(lines)

    # --------------------------------------------------
    # Discord message size limit
    # --------------------------------------------------

    max_length = 1900

    chunks = [

        message[i:i + max_length]

        for i in range(
            0,
            len(message),
            max_length
        )

    ]

    # --------------------------------------------------
    # Send
    # --------------------------------------------------

    for chunk in chunks:

        response = requests.post(

            DISCORD_WEBHOOK_URL,

            json={
                "content": chunk
            },

            timeout=20

        )

        if response.status_code not in (
            200,
            204
        ):

            print(
                "Discord error:",
                response.status_code,
                response.text
            )

            response.raise_for_status()

    print(
        "✅ Discord notification sent."
    )

def send_discord_old(stocks):

    if not DISCORD_WEBHOOK_URL:

        raise RuntimeError(
            "DISCORD_WEBHOOK_URL is not configured"
        )

    now = datetime.now(IST)

    message = (
        "📊 **IMR-FortuneStocks**\n"
        f"🕘 **{now.strftime('%d-%m-%Y %I:%M:%S %p')} IST**\n"
        f"📈 **{len(stocks)} stocks found**\n\n"
    )

    for i, stock in enumerate(stocks, 1):

        message += (
            f"**{i}. {stock['symbol']}**\n"
            f"💰 Close: **{stock['close']}**\n"
            f"📈 Change: **{stock['change']}**\n"
            f"📊 Volume: **{stock['volume']}**\n\n"
        )

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={
            "content": message
        },
        timeout=20
    )

    response.raise_for_status()

    print("✅ Discord notification sent.")

def send_discord_2(stocks):

    if not DISCORD_WEBHOOK_URL:

        raise RuntimeError(
            "DISCORD_WEBHOOK_URL is not configured"
        )

    now = datetime.now(IST)

    # --------------------------------------------------
    # Header
    # --------------------------------------------------

    header = (
        "📊 **IMR-FortuneStocks**\n"
        f"🕘 **{now.strftime('%d-%m-%Y %I:%M:%S %p')} IST**\n"
        f"📈 **{len(stocks)} stocks found**\n\n"
    )

    messages = []
    current_message = header

    # --------------------------------------------------
    # Add stocks
    # --------------------------------------------------

    for stock in stocks:

        stock_text = (
            f"**{stock['rank']}. {stock['symbol']}** "
            f"— {stock['name']}\n"
            f"💰 Close: **₹{stock['close']}**\n"
            f"📈 Change: **{stock['change']}**\n"
            f"📊 Volume: **{stock['volume']}**\n\n"
        )

        # Discord has a 2000 character limit
        if (
            len(current_message)
            + len(stock_text)
            > 1900
        ):

            messages.append(
                current_message
            )

            current_message = stock_text

        else:

            current_message += stock_text

    # Add remaining
    if current_message:

        messages.append(
            current_message
        )

    # --------------------------------------------------
    # Send messages
    # --------------------------------------------------

    for message in messages:

        response = requests.post(

            DISCORD_WEBHOOK_URL,

            json={
                "content": message
            },

            timeout=20
        )

        if response.status_code not in (
            200,
            204
        ):

            print(
                "Discord error:",
                response.status_code,
                response.text
            )

            response.raise_for_status()

    print(
        f"✅ Discord notification sent "
        f"({len(messages)} message(s)).")


async def main():

    now = datetime.now(IST)

    print("\n====================================")
    print("Chartink FortuneStocks Scanner")
    print("====================================")

    print(
        "Current IST:",
        now.strftime("%Y-%m-%d %H:%M:%S")
    )

    stocks = await get_chartink_stocks_2()

    print("\n====================================")
    print("STOCKS FOUND")
    print("====================================")

    for stock in stocks:

        print(
            f"{stock['symbol']} | "
            f"Close: {stock['close']} | "
            f"Change: {stock['change']} | "
            f"Volume: {stock['volume']}"
        )

    if stocks:

        send_discord_2(stocks)

    else:

        print(
            "⚠️ No stocks found."
        )


if __name__ == "__main__":

    asyncio.run(main())


# import asyncio
# from datetime import datetime
# import os
# from zoneinfo import ZoneInfo
# from playwright.async_api import async_playwright
# import requests

# CHARTINK_URL = "https://chartink.com/screener/imr-fortunestocks"

# DISCORD_WEBHOOK_URL = os.environ.get(
#     "DISCORD_WEBHOOK_URL",
#     "https://discord.com/api/webhooks/1519223896606249042/MGW78FKpd9bksUcjg78ZehYqPuFb0T_shOaAggqcBPQhxqzHVombxDtXoRn3t-Wzx3qi",
# )

# IST = ZoneInfo("Asia/Kolkata")


# async def get_chartink_stocks():
#     print("🔄 Opening Chartink screener in Playwright...")
#     stocks = []

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(
#             headless=True,
#             args=[
#                 "--no-sandbox",
#                 "--disable-setuid-sandbox",
#                 "--disable-dev-shm-usage",
#                 "--disable-gpu",
#             ],
#         )

#         page = await browser.new_page(viewport={"width": 1920, "height": 1080})

#         try:
#             await page.goto(CHARTINK_URL, wait_until="networkidle", timeout=60000)

#             # Wait for data table rows to render
#             await page.wait_for_selector("table tbody tr", timeout=25000)
#             await page.wait_for_timeout(3000)

#             # Detect table headers
#             table = page.locator("table").first
#             headers = await table.locator("thead th").all_inner_texts()
#             headers = [h.strip().lower() for h in headers]

#             symbol_idx = None
#             close_idx = None
#             change_idx = None
#             volume_idx = None

#             for idx, h in enumerate(headers):
#                 if any(k in h for k in ["symbol", "nsecode", "nse code"]):
#                     symbol_idx = idx
#                 elif "close" in h:
#                     close_idx = idx
#                 elif any(k in h for k in ["% change", "%change", "change %", "per chg"]):
#                     change_idx = idx
#                 elif "volume" in h:
#                     volume_idx = idx

#             # Fallback column indices if headers are custom styled
#             if symbol_idx is None:
#                 symbol_idx = 2
#             if close_idx is None:
#                 close_idx = 3
#             if change_idx is None:
#                 change_idx = 4
#             if volume_idx is None:
#                 volume_idx = 5

#             rows = table.locator("tbody tr")
#             count = await rows.count()
#             print(f"📊 Found {count} rendered rows.")

#             for i in range(count):
#                 cells = rows.nth(i).locator("td")
#                 cell_count = await cells.count()
#                 if cell_count < 4:
#                     continue

#                 values = [await cells.nth(j).inner_text() for j in range(cell_count)]
#                 values = [v.strip() for v in values]

#                 def safe_get(idx):
#                     return values[idx] if idx is not None and idx < len(values) else "N/A"

#                 symbol = safe_get(symbol_idx)
#                 close = safe_get(close_idx).replace(",", "")
#                 change = safe_get(change_idx).replace("%", "").replace("+", "").strip()
#                 volume = safe_get(volume_idx).replace(",", "")

#                 # Validate non-empty symbol row
#                 if symbol and symbol.upper() not in ["SYMBOL", "STOCK"]:
#                     try:
#                         clean_change = float(change)
#                     except ValueError:
#                         clean_change = 0.0

#                     stocks.append({
#                         "symbol": symbol,
#                         "close": close,
#                         "change": f"{clean_change:+.2f}%",
#                         "change_val": clean_change,
#                         "volume": f"{int(volume):,}" if volume.isdigit() else volume,
#                     })

#             # Sort by percentage change descending
#             stocks.sort(key=lambda x: x["change_val"], reverse=True)

#         except Exception as e:
#             print(f"⚠️ Scraper Error: {e}")
#         finally:
#             await browser.close()

#     return stocks


# def send_discord_notification(stocks):
#     if not DISCORD_WEBHOOK_URL:
#         print("❌ DISCORD_WEBHOOK_URL not found.")
#         return

#     now_t = datetime.now(IST).strftime("%d-%m-%Y %I:%M:%S %p")

#     if not stocks:
#         embed = {
#             "title": "⚠️ IMR-FortuneStocks Screener",
#             "description": f"No matching breakout stocks found at `{now_t} IST`.",
#             "color": 15158332,
#             "timestamp": datetime.utcnow().isoformat(),
#         }
#         requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
#         return

#     # Format into compact, high-density blocks
#     formatted_lines = [
#         f"`{i:>2}.` **{s['symbol']}** | ₹{s['close']} | `{s['change']}` | Vol: `{s['volume']}`"
#         for i, s in enumerate(stocks, 1)
#     ]

#     # Chunk into 25 stocks per embed to respect Discord limits
#     chunk_size = 25
#     for chunk_idx, i in enumerate(range(0, len(formatted_lines), chunk_size), 1):
#         chunk = formatted_lines[i : i + chunk_size]
#         embed = {
#             "title": f"🌟 IMR-FortuneStocks Breakout Alert (Part {chunk_idx})",
#             "url": CHARTINK_URL,
#             "color": 3066993,
#             "fields": [
#                 {"name": "Scan Time (IST)", "value": f"`{now_t}`", "inline": True},
#                 {"name": "Total Matches", "value": f"**{len(stocks)} Stocks**", "inline": True},
#                 {"name": "Symbol | Close | % Change | Volume", "value": "\n".join(chunk), "inline": False},
#             ],
#             "footer": {"text": "Chartink Live Screener Engine"},
#             "timestamp": datetime.utcnow().isoformat(),
#         }

#         resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
#         if resp.status_code in [200, 204]:
#             print(f"✅ Discord notification part {chunk_idx} sent.")
#         else:
#             print(f"❌ Discord transmission error: {resp.status_code} - {resp.text}")


# async def main():
#     now = datetime.now(IST)
#     print("====================================")
#     print("Chartink FortuneStocks Scanner")
#     print("====================================")
#     print("Current IST:", now.strftime("%Y-%m-%d %H:%M:%S"))

#     stocks = await get_chartink_stocks()

#     print("\n====================================")
#     print(f"STOCKS FOUND ({len(stocks)})")
#     print("====================================")
#     for s in stocks[:10]:
#         print(f"{s['symbol']} | Close: {s['close']} | % Chg: {s['change']} | Vol: {s['volume']}")

#     if len(stocks) > 10:
#         print(f"... and {len(stocks) - 10} more.")

#     send_discord_notification(stocks)


if __name__ == "__main__":
    asyncio.run(main())