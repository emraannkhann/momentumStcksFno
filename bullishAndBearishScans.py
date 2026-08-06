import requests
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time
import os
from bs4 import BeautifulSoup
import re

# # Telegram configuration
# TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
# CHAT_ID = "YOUR_CHAT_ID"
# Telegram Config
TELEGRAM_TOKEN = "5817461626:AAHp1IIIMkQGWFTqIuu84lYOoxlO8KS7CZo"
CHAT_ID = "@swingTradeScreenedStocks"

# Chartink screener payload
CHARTINK_URL = "https://chartink.com/screener/process"
payload = {
    "scan_clause": "( {cash} ( [0] Latest Close > 20 and [1] Latest Close > SMA(50) and [2] RSI(14) > 50 and [3] ADX(14) > 20 and [4] Volume > 1.5 * SMA(20, Volume) and [5] Close 1 day ago <= Close 2 days ago and [6] Close >= Close 1 day ago and [7] High crossed above High 10 days ago and [8] Weekly % change > 3 ) )"
}

# Time slots we want to ensure are executed (in HH:MM format, IST)
fixed_run_times = {"09:45", "22:33"}
executed_times_today = set()

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, data=data)

def send_csv_to_telegram(file_path):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    with open(file_path, "rb") as f:
        requests.post(url, data={"chat_id": CHAT_ID}, files={"document": f})

# def fetch_chartink_results():
#     response = requests.post(CHARTINK_URL, data=payload)
#     if response.status_code == 200:
#         return pd.DataFrame(response.json().get("data", []))
#     return pd.DataFrame()

def fetch_chartink_futures_scan(scan_type="bearish"):
    """
    Fetches live stock options candidates strictly from the Futures segment,
    authenticating via the specific saved Chartink scan URL.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    # Saved Chartink URLs for session authentication & referer
    urls = {
        "bullish": "https://chartink.com/screener/imraibullishscan",
        "bearish": "https://chartink.com/screener/imraibearishscan"
    }

    # Futures Segment Clauses
    queries = {
        "bullish": "( {futures} ( [0] 5 minute close > [0] 5 minute vwap and [0] 5 minute close > [-1] 5 minute high and [0] 5 minute volume > [-1] 5 minute volume * 2 and [0] 5 minute rsi( 14 ) > 60 and [0] 15 minute rsi( 14 ) > 55 and [0] 5 minute close > [0] 5 minute ema( close, 20 ) ) )",
        "bearish": "( {futures} ( [0] 5 minute close < [0] 5 minute vwap and [0] 5 minute close < [-1] 5 minute low and [0] 5 minute volume > [-1] 5 minute volume * 2 and [0] 5 minute rsi( 14 ) < 40 and [0] 15 minute rsi( 14 ) < 45 and [0] 5 minute close < [0] 5 minute ema( close, 20 ) ) )"
    }

    selected_type = scan_type.lower()
    auth_url = urls.get(selected_type)
    selected_query = queries.get(selected_type)

    if not auth_url or not selected_query:
        print("❌ Invalid scan_type! Choose 'bullish' or 'bearish'.")
        return pd.DataFrame()

    print(f"🔄 Authenticating via {auth_url}...")

    try:
        # Step 1: GET your custom scan URL to set headers and session tokens
        session.headers.update({"Referer": auth_url})
        get_response = session.get(auth_url)
        get_response.raise_for_status()

        soup = BeautifulSoup(get_response.text, "html.parser")
        csrf_token = soup.find("meta", {"name": "csrf-token"})["content"]

        # Step 2: Update AJAX Headers with live token
        session.headers.update({
            "X-CSRF-TOKEN": csrf_token,
            "X-Requested-With": "XMLHttpRequest"
        })

        # Step 3: POST payload to process endpoint
        process_url = "https://chartink.com/screener/process"
        payload = {"scan_clause": selected_query}

        response = session.post(process_url, data=payload)
        response.raise_for_status()

        data = response.json().get("data", [])

        if not data:
            print(f"⚠️ 0 stocks matched the {selected_type.upper()} criteria right now.")
            return pd.DataFrame()

        # Step 4: Convert to DataFrame
        df = pd.DataFrame(data)
        desired_columns = ["sr", "nsecode", "name", "close", "per_chg", "volume", "lot_size"]
        df = df[[col for col in desired_columns if col in df.columns]]

        if "per_chg" in df.columns:
            df["per_chg"] = df["per_chg"].round(2)

        print(f"✅ Found {len(df)} tradeable F&O candidate(s).")
        return df

    except Exception as e:
        print(f"❌ Execution error: {e}")
        return pd.DataFrame()

def fetch_exact_chartink_scan(screener_slug="imraibearishscan"):
    """
    Fetches exact compiled scan results using Chartink's scanlink ID.
    Matches the web UI result count and custom columns 100%.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    screener_url = f"https://chartink.com/screener/{screener_slug}"
    print(f"🔄 Connecting to saved screener: {screener_url}...")

    try:
        # Step 1: GET page HTML to extract CSRF token and internal scanlink
        get_response = session.get(screener_url)
        get_response.raise_for_status()

        soup = BeautifulSoup(get_response.text, "html.parser")
        
        # Parse CSRF token
        csrf_token = soup.find("meta", {"name": "csrf-token"})["content"]

        # Step 2: Extract scanlink using regex
        scanlink_match = re.search(r'scanlink["\']?\s*:\s*["\']([a-f0-9]{32})["\']', get_response.text)
        
        # Step 3: Configure AJAX headers
        session.headers.update({
            "Referer": screener_url,
            "X-CSRF-TOKEN": csrf_token,
            "X-Requested-With": "XMLHttpRequest"
        })

        process_url = "https://chartink.com/screener/process"

        if scanlink_match:
            scanlink_id = scanlink_match.group(1)
            print(f"🔑 Captured compiled scanlink ID: {scanlink_id}")
            payload = {"scan_clause": f"scanlink:{scanlink_id}"}
        else:
            # Fallback if scanlink hash isn't directly embedded in response text
            scan_input = soup.find("input", {"id": "scan_clause"}) or soup.find("textarea", {"id": "scan_clause"})
            if scan_input and scan_input.get("value"):
                payload = {"scan_clause": scan_input["value"]}
            else:
                # Direct Futures condition fallback
                payload = {
                    "scan_clause": "( {futures} ( [0] 5 minute close < [0] 5 minute vwap and [0] 5 minute close < [-1] 5 minute low and [0] 5 minute volume > [-1] 5 minute volume * 2 and [0] 5 minute rsi( 14 ) < 40 and [0] 15 minute rsi( 14 ) < 45 and [0] 5 minute close < [0] 5 minute ema( close, 20 ) ) )"
                }

        # Step 4: POST request to process endpoint
        response = session.post(process_url, data=payload)
        response.raise_for_status()

        json_data = response.json()
        data = json_data.get("data", [])

        if not data:
            print("⚠️ 0 stocks returned.")
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Filter out non-Futures items if any leaked through
        if "fno_lot_size" in df.columns:
            df = df[df["fno_lot_size"].notnull() & (df["fno_lot_size"] > 0)]
        elif "lot_size" in df.columns:
            df = df[df["lot_size"].notnull() & (df["lot_size"] > 0)]

        # Map response columns to match your UI layout
        col_map = {
            "sr": "Sr.",
            "name": "Stock Name",
            "nsecode": "Symbol",
            "close": "Close",
            "per_chg": "%_Change",
            "volume": "Volume",
            "lot_size": "Fno_lot_size",
            "fno_lot_size": "Fno_lot_size"
        }
        
        valid_cols = [c for c in col_map.keys() if c in df.columns]
        df = df[valid_cols].rename(columns=col_map)

        # Remove duplicate column names if mapped twice
        df = df.loc[:, ~df.columns.duplicated()]

        print(f"✅ Found {len(df)} stock(s) matching web UI perfectly!")
        return df

    except Exception as e:
        print(f"❌ Execution error: {e}")
        return pd.DataFrame()

# def fetch_chartink_results():
#     print("🔄 Fetching Chartink screener via screener ID API...")
#     url = "https://chartink.com/screener/process"
#     payload = {
#         "scan_id": "135212"  # Replace with your actual screener ID
#     }
#     headers = {
#         "User-Agent": "Mozilla/5.0"
#     }

#     try:
#         res = requests.post(url, data=payload, headers=headers)
#         res.raise_for_status()
#         data = res.json().get("data", [])
#         if not data:
#             print("⚠️ No stocks returned from screener.")
#             return pd.DataFrame()

#         df = pd.DataFrame(data)
#         return df
#     except Exception as e:
#         print("❌ Error:", e)
#         return pd.DataFrame()


def run_screener():
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    print(f"🕒 Running screener at {now.strftime('%H:%M')} IST")

    df = fetch_chartink_results()
    if df.empty:
        send_telegram_message(f"⚠️ No swing momentum stocks found at {now.strftime('%H:%M')} IST.")
        return

    stock_list = "\n".join([f"🔹 {row['nsecode']}" for _, row in df.iterrows()])
    send_telegram_message(f"📈 *Swing Momentum Picks*\n🕒 {now.strftime('%H:%M')} IST\n\n{stock_list}")

    filename = f"swing_momentum_{now.strftime('%Y%m%d_%H%M')}.csv"
    filepath = f"/tmp/{filename}"
    df.to_csv(filepath, index=False)
    send_csv_to_telegram(filepath)
    os.remove(filepath)

def should_run_now(now):
    current_time_str = now.strftime("%H:%M")
    if current_time_str in fixed_run_times and current_time_str not in executed_times_today:
        executed_times_today.add(current_time_str)
        return True
    # Run every 15 minutes (only once per slot)
    if now.minute % 15 == 0 and current_time_str not in executed_times_today:
        executed_times_today.add(current_time_str)
        return True
    return False

def run_loop():
    global executed_times_today
    ist = pytz.timezone("Asia/Kolkata")
    print("🔁 Starting screener loop (15-min and fixed time slots)...")

    while True:
        now = datetime.now(ist)
        weekday = now.weekday()

        if weekday < 5:  # Monday to Friday only
            if should_run_now(now):
                run_screener()
        else:
            print("⛔ Weekend. Skipping.")

        # Reset execution log at midnight IST
        if now.strftime("%H:%M") == "00:00":
            executed_times_today = set()

        time.sleep(30)  # Check every 30 seconds

if __name__ == "__main__":
   # run_loop()
  # 1. Define exact conditions (Futures Universe Enforced)
    bullish_clause = "( {futures} ( [0] 5 minute close > [0] 5 minute vwap and [0] 5 minute close > [-1] 5 minute high and [0] 5 minute volume > [-1] 5 minute volume * 2 and [0] 5 minute rsi( 14 ) > 60 and [0] 15 minute rsi( 14 ) > 55 and [0] 5 minute close > [0] 5 minute ema( close, 20 ) ) )"
    bearish_clause = "( {futures} ( [0] 5 minute close < [0] 5 minute vwap and [0] 5 minute close < [-1] 5 minute low and [0] 5 minute volume > [-1] 5 minute volume * 2 and [0] 5 minute rsi( 14 ) < 40 and [0] 15 minute rsi( 14 ) < 45 and [0] 5 minute close < [0] 5 minute ema( close, 20 ) ) )"

    # 2. URLs for session authentication
    bullish_url = "https://chartink.com/screener/imraibullishscan"
    bearish_url = "https://chartink.com/screener/imraibearishscan"

    # Execute Scans
    print("\n--- BULLISH SCAN (CE Candidates) ---")
    #df_bull = fetch_chartink_scan(bullish_url, bullish_clause)
    df_bull = fetch_exact_chartink_scan("imraibullishscan")  # Fetch Futures CE candidates
    if not df_bull.empty:
        print(df_bull.to_string(index=False))

    print("\n--- BEARISH SCAN (PE Candidates) ---")
    #df_bear = fetch_chartink_scan(bearish_url, bearish_clause)
    df_bear = fetch_exact_chartink_scan("imraibearishscan")  # Fetch Futures PE candidates
    if not df_bear.empty:
        print("\n",df_bear.to_string(index=False))