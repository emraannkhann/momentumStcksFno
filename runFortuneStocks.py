import os
import sys
import asyncio
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
import requests
from playwright.async_api import async_playwright

CHARTINK_URL = "https://chartink.com/screener/copy-intraday-bullish-1016"
DISCORD_WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1521804732140752978/Ca-tLLR4z5UiJ1fIsTbmKLmIp_qNqzaYkvJZqWOXJ90yQp9YUsX-fchaydCUlVfdOmCN",
)

IST = ZoneInfo("Asia/Kolkata")
TARGET_EXEC_TIME = dt_time(9, 30)


async def get_chartink_stocks():
    print("🔄 Opening Chartink screener in Playwright...")
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

        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        try:
            await page.goto(CHARTINK_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(8000)

            # Locate results table
            tables = page.locator("table")
            table_count = await tables.count()

            result_table = None
            for idx in range(table_count):
                tbl = tables.nth(idx)
                row_count = await tbl.locator("tbody tr").count()
                if row_count > 0:
                    result_table = tbl
                    break

            if result_table is None:
                raise RuntimeError("No populated data table found on Chartink.")

            rows = result_table.locator("tbody tr")
            row_count = await rows.count()
            print(f"📊 Extracted {row_count} table rows.")

            for i in range(row_count):
                cells = rows.nth(i).locator("td")
                cell_count = await cells.count()
                if cell_count < 6:
                    continue

                values = [await cells.nth(j).inner_text() for j in range(cell_count)]
                values = [v.strip() for v in values]

                # Map standard Chartink row structure
                # 0: Rank, 1: Company Name, 2: Symbol, 3: Close, 4: % Change, 5: Volume
                stocks.append({
                    "rank": values[0],
                    "name": values[1],
                    "symbol": values[2],
                    "close": values[3],
                    "change": values[4],
                    "volume": values[5],
                })

            # Deduplicate symbols while preserving order
            unique_stocks = []
            seen = set()
            for s in stocks:
                if s["symbol"] not in seen:
                    seen.add(s["symbol"])
                    unique_stocks.append(s)

            return unique_stocks

        finally:
            await browser.close()


def send_discord_notifications(stocks):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not configured.")

    now = datetime.now(IST)
    header = (
        "📊 **IMR-FortuneStocks Breakout Report**\n"
        f"🕘 **{now.strftime('%d-%m-%Y %I:%M:%S %p')} IST**\n"
        f"📈 **{len(stocks)} stocks found**\n\n"
    )

    if not stocks:
        requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": f"⚠️ **IMR-FortuneStocks**\nNo stocks matched the breakout criteria at {now.strftime('%I:%M %p')} IST."},
            timeout=20,
        )
        return

    messages = []
    current_message = header

    for s in stocks:
        stock_text = (
            f"**{s['rank']}. {s['symbol']}** — {s['name']}\n"
            f"💰 Close: **₹{s['close']}**\n"
            f"📈 Change: **{s['change']}**\n"
            f"📊 Volume: **{s['volume']}**\n\n"
        )

        # Discord 2000 character limit safety margin
        if len(current_message) + len(stock_text) > 1900:
            messages.append(current_message)
            current_message = stock_text
        else:
            current_message += stock_text

    if current_message:
        messages.append(current_message)

    for idx, msg in enumerate(messages, 1):
        resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": msg}, timeout=20)
        if resp.status_code not in (200, 204):
            print(f"❌ Discord error on part {idx}: {resp.status_code} - {resp.text}")
        else:
            print(f"✅ Discord chunk {idx}/{len(messages)} sent.")


async def main():
    run_now = "--now" in sys.argv or "-n" in sys.argv

    if run_now:
        print("⚡ Immediate execution triggered (--now). Bypassing time-gate...")
    else:
        print("⏳ Initialized at 09:15 AM IST. Waiting for 09:45 AM IST...")
        while True:
            now_ist = datetime.now(IST)
            if now_ist.time() >= TARGET_EXEC_TIME:
                print(f"🎯 09:45 AM IST reached ({now_ist.strftime('%H:%M:%S')}). Launching scanner...")
                break

            print(f"🕒 Current Time: {now_ist.strftime('%H:%M:%S')} IST. Checking in 5 minutes...")
            await asyncio.sleep(300)  # Wait 5 minutes (300 seconds)

    stocks = await get_chartink_stocks()
    print(f"✅ Extracted {len(stocks)} stocks.")
    send_discord_notifications(stocks)
    print("🏁 Execution completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
