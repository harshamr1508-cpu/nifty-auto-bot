import yfinance as yf
import pandas as pd
import time
import datetime
import requests

# ========= TELEGRAM =========
BOT_TOKEN = "7836481326:AAEdb4avdV9SP3Ki4kl0gGcVk3KL9RESObo"
CHAT_ID = "7608325440"

# ========= SETTINGS =========
MAX_TRADES = 10
STOP_LOSS_PCT = 0.05
TARGET_PCT = 0.10
VOLUME_MULTIPLIER = 1.5

trade_count = 0
trades = []
active_trade = None

# ========= TELEGRAM FUNCTION =========

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": msg}
        requests.post(url, data=data)
    except:
        print("Telegram error")


# ========= DATA DOWNLOAD =========

def get_data():

    try:
        df = yf.download("^NSEI", period="1d", interval="5m")

        if df is None or df.empty:
            print("⚠ Data not received")
            time.sleep(30)
            return None

        return df

    except Exception as e:
        print("DATA ERROR:", e)
        time.sleep(30)
        return None


# ========= INDICATORS =========

def add_indicators(df):

    df["EMA9"] = df["Close"].ewm(span=9).mean()
    df["EMA21"] = df["Close"].ewm(span=21).mean()
    df["AVG_VOL"] = df["Volume"].rolling(10).mean()

    return df


# ========= ATM OPTION =========

def get_atm(price):

    strike = round(price / 50) * 50

    call = f"NIFTY {strike} CE"
    put = f"NIFTY {strike} PE"

    return call, put


# ========= SIGNAL =========

def check_signal(df):

    last = df.iloc[-1]

    price = float(last["Close"])
    ema9 = float(last["EMA9"])
    ema21 = float(last["EMA21"])
    vol = float(last["Volume"])
    avg_vol = float(last["AVG_VOL"])

    if avg_vol == 0:
        return None, price

    volume_ok = vol > avg_vol * VOLUME_MULTIPLIER

    if ema9 > ema21 and volume_ok:
        return "CALL", price

    if ema9 < ema21 and volume_ok:
        return "PUT", price

    return None, price


# ========= BOT START =========

send_telegram("🚀 NIFTY AUTO BOT V3 STARTED")

print("BOT STARTED")

# ========= MAIN LOOP =========

while True:

    now = datetime.datetime.now().time()

    if now < datetime.time(9,15):
        time.sleep(60)
        continue

    if now > datetime.time(15,30):

        report = f"📊 DAY END REPORT\n\nTrades: {len(trades)}\n"

        for t in trades:
            report += f"{t}\n"

        send_telegram(report)

        print("Market closed")
        break

    df = get_data()

    if df is None:
        continue

    df = add_indicators(df)

    signal, price = check_signal(df)

    # ===== ENTRY =====

    if signal and trade_count < MAX_TRADES and active_trade is None:

        trade_count += 1

        call, put = get_atm(price)
        option = call if signal == "CALL" else put

        sl = price * (1 - STOP_LOSS_PCT)
        target = price * (1 + TARGET_PCT)

        active_trade = {
            "type": signal,
            "entry": price,
            "sl": sl,
            "target": target,
            "option": option
        }

        msg = f"""
📢 ENTRY {signal}

Option: {option}
Price: {price:.2f}
SL: {sl:.2f}
Target: {target:.2f}

Trade No: {trade_count}
"""

        send_telegram(msg)
        print(msg)


    # ===== EXIT =====

    if active_trade:

        entry = active_trade["entry"]
        sl = active_trade["sl"]
        target = active_trade["target"]

        if price <= sl or price >= target:

            pnl = price - entry

            if active_trade["type"] == "PUT":
                pnl = entry - price

            result = f"""
✅ EXIT TRADE

Option: {active_trade['option']}
Entry: {entry:.2f}
Exit: {price:.2f}
PnL: {pnl:.2f}
"""

            trades.append(result)

            send_telegram(result)
            print(result)

            active_trade = None

    time.sleep(60)
