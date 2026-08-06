import asyncio
import pandas as pd
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
# ---------------------------------------------------------
# CONFIGURATION
# Replace with your actual Discord Webhook URL
# ---------------------------------------------------------
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1519223896606249042/MGW78FKpd9bksUcjg78ZehYqPuFb0T_shOaAggqcBPQhxqzHVombxDtXoRn3t-Wzx3qi"


def send_discord_notification(df, scan_name="Scan"):
    if df.empty:
        return

    embed_color = 3066993 if scan_name.lower() == "bullish" else 15158332
    title_emoji = "🟢" if scan_name.lower() == "bullish" else "🔴"

    lines = ["```text"]
    lines.append(f"{'SYMBOL':<6} | {'PRICE':<4} | {'%CHG':<4} | {'VOLUME':<5} | {'LOTS':<4}")
    lines.append("-" * 18)

    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "N/A"))[:10]
        price = f"{float(row.get('price', 0)):.2f}"
        chg = f"{float(row.get('%change', 0)):+.2f}%"
        vol = f"{int(row.get('volume', 0)):,}"
        lots = str(row.get("fno_lots", "N/A"))

        lines.append(f"{symbol:<11} | {price:<8} | {chg:<7} | {vol:<10} | {lots:<6}")

    lines.append("```")

    payload = {
        "username": "Chartink Options Bot",
        "embeds": [
            {
                "title": f"{title_emoji} {scan_name.upper()} MOMENTUM CANDIDATES",
                "description": "\n".join(lines),
                "color": embed_color
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            print("🚀 Discord notification sent successfully!")
        else:
            print(f"❌ Discord API error: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Discord notification error: {e}")


# async def fetch_chartink_json(url, scan_name="Scan"):
#     print(f"\n🔄 Launching Playwright Network Interceptor for {scan_name.upper()}...")
#     print(f"🔗 Target: {url}")

#     captured_json = {}

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(
#             headless=True,
#             args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
#         )
#         context = await browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#         )
#         page = await context.new_page()

#         # Intercept background API call sent to /screener/process
#         async def handle_response(response):
#             if "screener/process" in response.url and response.status == 200:
#                 try:
#                     nonlocal captured_json
#                     captured_json = await response.json()
#                 except Exception:
#                     pass

#         page.on("response", handle_response)

#         try:
#             await page.goto(url, wait_until="networkidle", timeout=60000)

#             if not captured_json.get("data"):
#                 try:
#                     run_btn = page.locator("button:has-text('Run Scan')")
#                     if await run_btn.is_visible():
#                         await run_btn.click()
#                         await page.wait_for_timeout(3000)
#                 except Exception:
#                     pass

#             await browser.close()

#             data = captured_json.get("data", [])
#             if not data:
#                 print(f"⚠️ 0 stocks returned for {scan_name}.")
#                 return pd.DataFrame()

#             df = pd.DataFrame(data)

#             # Unify lot size column
#             if "fno_lot_size" not in df.columns and "lot_size" in df.columns:
#                 df["fno_lot_size"] = df["lot_size"]

#             # Column mapping
#             column_mapping = {
#                 "nsecode": "Symbol",
#                 "per_chg": "%change",
#                 "close": "price",
#                 "volume": "volume",
#                 "fno_lot_size": "fno_lots"
#             }

#             desired_order = ["Symbol", "%change", "price", "volume", "fno_lots"]
#             available_cols = [col for col in column_mapping.keys() if col in df.columns]
#             df = df[available_cols].rename(columns=column_mapping)
#             print(f"ℹ️ Columns after renaming: {list(df.columns)}")
#             final_cols = [c for c in desired_order if c in df.columns]
#             df = df[final_cols]

#             print(f"✅ Successfully captured {len(df)} {scan_name} stock(s)!")
#             return df

#         except Exception as e:
#             print(f"❌ Error during execution: {e}")
#             await browser.close()
#             return pd.DataFrame()

async def scrape_chartink_dom(url, scan_name="Scan"):
    print(f"\n🔄 Launching Playwright DOM Scraper for {scan_name.upper()}...")
    print(f"🔗 Target: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for data rows with nsecode attribute to render in DOM
            print("⏳ Waiting for table rows to populate...")
            await page.wait_for_selector("tbody tr", timeout=35000)

            content = await page.content()
            await browser.close()

            soup = BeautifulSoup(content, "html.parser")
            rows = soup.select("tbody tr")

            if not rows:
                print(f"⚠️ 0 stocks returned for {scan_name}.")
                return pd.DataFrame()

            extracted_data = []

            for row in rows:
                # 1. Symbol
                symbol_elem = row.select_one("div[data-result-column-key='nsecode']")
                symbol = symbol_elem.get_text(strip=True) if symbol_elem else "N/A"

                # 2. Close Price
                price_elem = row.select_one("div[data-result-column-key='default-close']")
                price_text = price_elem.get_text(strip=True).replace(",", "") if price_elem else "0"
                try:
                    price = float(price_text)
                except ValueError:
                    price = 0.0

                # 3. % Change
                chg_elem = row.select_one("div[data-result-column-key='default-percent-change']")
                chg_text = chg_elem.get_text(strip=True).replace("%", "").replace(",", "") if chg_elem else "0"
                try:
                    pct_change = float(chg_text)
                except ValueError:
                    pct_change = 0.0

                # 4. Volume
                vol_elem = row.select_one("div[data-result-column-key='default-volume']")
                vol_text = vol_elem.get_text(strip=True).replace(",", "") if vol_elem else "0"
                try:
                    volume = int(vol_text)
                except ValueError:
                    volume = 0

                # 5. F&O Lot Size
                # Look for custom column divs (excluding default system keys)
                lot_elem = row.select_one("td[data-field^='scan-column-_'] div[data-result-column-key]")
                if not lot_elem:
                    # Fallback to last numeric td element before the add_column button
                    td_elems = row.select("td")
                    if len(td_elems) >= 7:
                        lot_elem = td_elems[6]  # Index 6 is the 7th column (Fno_lot_size)

                lot_text = lot_elem.get_text(strip=True).replace(",", "") if lot_elem else "0"
                try:
                    fno_lots = int(lot_text)
                except ValueError:
                    fno_lots = "N/A"

                extracted_data.append({
                    "Symbol": symbol,
                    "%change": pct_change,
                    "price": price,
                    "volume": volume,
                    "fno_lots": fno_lots
                })

            df = pd.DataFrame(extracted_data)
            print(f"✅ Successfully extracted {len(df)} {scan_name} stock(s) from DOM!")
            return df

        except Exception as e:
            print(f"❌ DOM Scrape Error: {e}")
            await browser.close()
            return pd.DataFrame()

async def fetch_chartink_json(url, scan_name="Scan"):
    print(f"\n🔄 Launching Playwright Network Interceptor for {scan_name.upper()}...")
    print(f"🔗 Target: {url}")

    captured_json = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Intercept background API call to /screener/process
        async def handle_response(response):
            if "screener/process" in response.url and response.status == 200:
                try:
                    nonlocal captured_json
                    captured_json = await response.json()
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)

            if not captured_json.get("data"):
                try:
                    run_btn = page.locator("button:has-text('Run Scan')")
                    if await run_btn.is_visible():
                        await run_btn.click()
                        await page.wait_for_timeout(3000)
                except Exception:
                    pass

            await browser.close()

            data = captured_json.get("data", [])
            if not data:
                print(f"⚠️ 0 stocks returned for {scan_name}.")
                return pd.DataFrame()

            df = pd.DataFrame(data)

            # Debug: Print raw API keys to console for verification
            print(f"ℹ️ Raw API Keys Received: {list(df.columns)}")

            # ---------------------------------------------------------
            # DIRECT DOM SPAN KEY MAPPING
            # ---------------------------------------------------------

            # 1. Symbol (nsecode)
            symbol_col = next((c for c in ["nsecode", "symbol", "Stock Name"] if c in df.columns), None)
            df["Symbol"] = df[symbol_col] if symbol_col else "N/A"

            # 2. Price / Close (close / default-close)
            price_col = next((c for c in ["close", "default-close", "price"] if c in df.columns), None)
            if price_col:
                df["price"] = pd.to_numeric(df[price_col], errors="coerce").fillna(0.0)
            else:
                df["price"] = 0.0

            # 3. % Change (%_change / per_chg / default-percent-change)
            chg_col = next((c for c in ["%_change", "per_chg", "default-percent-change", "p_chg"] if c in df.columns), None)
            if chg_col:
                df["%change"] = pd.to_numeric(df[chg_col], errors="coerce").fillna(0.0)
            else:
                df["%change"] = 0.0

            # 4. Volume (volume / default-volume)
            vol_col = next((c for c in ["volume", "default-volume", "vol"] if c in df.columns), None)
            if vol_col:
                df["volume"] = pd.to_numeric(df[vol_col], errors="coerce").fillna(0).astype(int)
            else:
                df["volume"] = 0

            # 5. F&O Lot Size (fno_lot_size / fno_lots / lot_size)
            lot_col = next((c for c in ["fno_lot_size", "fno_lots", "lot_size", "_46a03"] if c in df.columns), None)

            # Fallback: Detect unmapped custom columns
            if not lot_col:
                mapped_keys = {"sr", "nsecode", "name", "close", "per_chg", "volume", 
                               "%_change", "default-close", "default-percent-change", 
                               "default-volume", "Symbol", "price", "%change"}
                candidate_cols = [c for c in df.columns if c not in mapped_keys]

                for col in candidate_cols:
                    col_vals = pd.to_numeric(df[col], errors="coerce").dropna()
                    if not col_vals.empty:
                        # F&O Lot sizes are positive integers (< 20,000)
                        if (col_vals < 20000).all() and (col_vals > 50).all():
                            lot_col = col
                            break

            if lot_col:
                df["fno_lots"] = pd.to_numeric(df[lot_col], errors="coerce").fillna(0).astype(int)
            else:
                df["fno_lots"] = "N/A"

            # Filter and order required final columns
            final_columns = ["Symbol", "%change", "price", "volume", "fno_lots"]
            df = df[final_columns]

            print(f"✅ Successfully mapped {len(df)} {scan_name} stock(s)!")
            return df

        except Exception as e:
            print(f"❌ Error during execution: {e}")
            await browser.close()
            return pd.DataFrame()


async def main():
    bullish_url = "https://chartink.com/screener/imraibullishscan"
    bearish_url = "https://chartink.com/screener/imraibearishscan"

    # Bearish Execution
    df_bearish = await scrape_chartink_dom(bearish_url, scan_name="Bearish")
    if not df_bearish.empty:
        print("\n=== BEARISH STOCKS (PE) ===")
        print(df_bearish.to_string(index=False))
        send_discord_notification(df_bearish, scan_name="Bearish")

    # Bullish Execution
    df_bullish = await scrape_chartink_dom(bullish_url, scan_name="Bullish")
    if not df_bullish.empty:
        print("\n=== BULLISH STOCKS (CE) ===")
        print(df_bullish.to_string(index=False))
        send_discord_notification(df_bullish, scan_name="Bullish")


if __name__ == "__main__":
    asyncio.run(main())