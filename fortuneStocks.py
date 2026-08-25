import os
import re
import time
from datetime import datetime, time as dt_time
from bs4 import BeautifulSoup
import pandas as pd
import pytz
import requests
import sys

# -------------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------------
IST = pytz.timezone("Asia/Kolkata")
DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1519223896606249042/MGW78FKpd9bksUcjg78ZehYqPuFb0T_shOaAggqcBPQhxqzHVombxDtXoRn3t-Wzx3qi",
)

SCREENER_SLUG = "imr-fortunestocks"
CHARTINK_URL = f"https://chartink.com/screener/{SCREENER_SLUG}"
PROCESS_URL = "https://chartink.com/screener/process"

SCAN_CLAUSE = (
    "( {cash} ( "
    "[0] daily market cap >= 5000 and "
    "[0] daily volume > 100000 and "
    "[0] daily close > [0] daily ema( [0] daily close , 20 ) and "
    "[0] daily close > [0] daily supertrend( 7 , 3 ) and "
    "( ( [0] daily close - [-1] daily close ) / [-1] daily close * 100 ) > 1.5 "
    ") )"
)

# Target execution gate
TARGET_EXEC_TIME = dt_time(9, 45)


# -------------------------------------------------------------
# DISCORD DISPATCHER
# -------------------------------------------------------------
def send_discord_notification(df, timestamp_str):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ No Discord webhook configured.")
        return

    if df.empty:
        embed = {
            "title": "⚠️ Fortune Stocks Screener — 09:45 AM IST",
            "description": "No stocks matched the breakout criteria this morning.",
            "color": 15158332,
            "footer": {"text": "Fortune Stocks Pipeline"},
            "timestamp": datetime.utcnow().isoformat(),
        }
    else:
        stock_lines = [
            f"• **{row['nsecode']}** — ₹{row['close']} ({'+' if row['per_chg'] > 0 else ''}{row['per_chg']}%) | Vol: {int(row['volume']):,}"
            for _, row in df.iterrows()
        ]
        
        # Keep embed under Discord size limits
        stock_text = "\n".join(stock_lines[:25])
        if len(stock_lines) > 25:
            stock_text += f"\n*...and {len(stock_lines) - 25} more stocks*"

        embed = {
            "title": "🚀 Fortune Stocks Breakout List",
            "color": 3066993,
            "fields": [
                {"name": "Scan Execution Time", "value": f"`{timestamp_str} IST`", "inline": True},
                {"name": "Matched Stocks", "value": str(len(df)), "inline": True},
                {"name": "Filtered Breakouts", "value": stock_text, "inline": False},
            ],
            "footer": {"text": "Fortune Stocks GitHub Runner"},
            "timestamp": datetime.utcnow().isoformat(),
        }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        if resp.status_code in [200, 204]:
            print("✅ Discord alert dispatched successfully.")
        else:
            print(f"❌ Discord error: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Discord transmission exception: {e}")


# -------------------------------------------------------------
# CHARTINK SCRAPER
# -------------------------------------------------------------
def fetch_fortune_stocks():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    })

    try:
        get_resp = session.get(CHARTINK_URL, timeout=12)
        get_resp.raise_for_status()

        soup = BeautifulSoup(get_resp.text, "html.parser")
        csrf_meta = soup.find("meta", {"name": "csrf-token"})
        if not csrf_meta:
            return pd.DataFrame()

        session.headers.update({
            "Referer": CHARTINK_URL,
            "X-CSRF-TOKEN": csrf_meta["content"],
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        })

        scanlink_match = re.search(r'scanlink["\']?\s*:\s*["\']([a-f0-9]{32})["\']', get_resp.text)
        payload = {"scan_clause": f"scanlink:{scanlink_match.group(1)}"} if scanlink_match else {"scan_clause": SCAN_CLAUSE}

        post_resp = session.post(PROCESS_URL, data=payload, timeout=15)
        post_resp.raise_for_status()

        data = post_resp.json().get("data", [])
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        col_map = {"nsecode": "nsecode", "close": "close", "per_chg": "per_chg", "volume": "volume"}
        valid_cols = [c for c in col_map.keys() if c in df.columns]
        df = df[valid_cols]
        df["per_chg"] = df["per_chg"].round(2)
        df["close"] = df["close"].round(2)
        return df

    except Exception as e:
        print(f"❌ Scraper error: {e}")
        return pd.DataFrame()


# -------------------------------------------------------------
# TIME-GATED ENTRYPOINT
# -------------------------------------------------------------
# def main():
#     print("⏳ Time-gate runner initialized. Waiting for 09:45 AM IST...")

#     # Hold execution in a loop until exact 09:45 AM IST
#     while True:
#         now_ist = datetime.now(IST)
        
#         if now_ist.time() >= TARGET_EXEC_TIME:
#             print(f"🎯 09:45 AM IST target reached ({now_ist.strftime('%H:%M:%S')}). Running scan...")
#             break
            
#         print(f"🕒 Current Time: {now_ist.strftime('%H:%M:%S')} IST. Sleeping 10s...")
#         time.sleep(10)

#     time_str = datetime.now(IST).strftime("%d-%m-%Y %H:%M")
#     df = fetch_fortune_stocks()
#     send_discord_notification(df, time_str)
#     print("🏁 Execution complete. Exiting cleanly.")


# if __name__ == "__main__":
#     main()

def main():
    # Check if --now or -n flag is passed via terminal
    run_immediately = "--now" in sys.argv or "-n" in sys.argv

    if run_immediately:
        print("⚡ Immediate test mode triggered. Bypassing 09:45 AM time-gate...")
    else:
        print("⏳ Time-gate runner initialized. Waiting for 09:45 AM IST...")
        while True:
            now_ist = datetime.now(IST)
            if now_ist.time() >= TARGET_EXEC_TIME:
                print(f"🎯 09:45 AM IST target reached ({now_ist.strftime('%H:%M:%S')}). Running scan...")
                break
            print(f"🕒 Current Time: {now_ist.strftime('%H:%M:%S')} IST. Sleeping 10s...")
            time.sleep(10)

    time_str = datetime.now(IST).strftime("%d-%m-%Y %H:%M")
    df = fetch_fortune_stocks()
    send_discord_notification(df, time_str)
    print("🏁 Execution complete. Exiting cleanly.")

if __name__ == "__main__":
    main()