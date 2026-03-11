import time
import datetime
import requests
import pandas as pd
import yfinance as yf
import config

# ===============================
# TELEGRAM
# ===============================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": config.TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.post(url, data=data, timeout=10)
    except:
        pass

# ===============================
# TIME HELPERS
# ===============================
def str_to_time(t):
    return datetime.datetime.strptime(t, "%H:%M").time()

TRADE_START = str_to_time(config.TRADE_START)
FORCE_EXIT = str_to_time(config.FORCE_EXIT)
MARKET_END = str_to_time(config.MARKET_END)

# ===============================
# STATE
# ===============================
trade_count = 0
open_trade = None
trades = []

# ===============================
# DATA FETCH (SAFE)
# ===============================
def fetch_nifty_data():
    try:
        df = yf.download(
            "^NSEI",
            interval=f"{config.TIMEFRAME_MIN}m",
            period="1d",
            progress=False
        )
        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.dropna(inplace=True)
        return df

    except Exception:
        return None

# ===============================
# INDICATORS
# ===============================
def apply_indicators(df):
    df["EMA_FAST"] = df["Close"].ewm(span=config.EMA_FAST, adjust=False).mean()
    df["EMA_SLOW"] = df["Close"].ewm(span=config.EMA_SLOW, adjust=False).mean()
    df["AVG_VOL"] = df["Volume"].rolling(20).mean()
    return df

# ===============================
# POSITION SIZE
# ===============================
def calculate_qty(premium):
    risk_amt = config.TOTAL_CAPITAL * config.RISK_PER_TRADE
    sl_amt = premium * config.STOP_LOSS_PCT * config.LOT_SIZE
    lots = int(risk_amt / sl_amt)
    return max(lots, 1) * config.LOT_SIZE

# ===============================
# ENTRY LOGIC (GUARDED)
# ===============================
def check_entry(df):
    global trade_count, open_trade

    if open_trade or trade_count >= config.MAX_TRADES_PER_DAY:
        return

    if df is None or len(df) < 25:
        return  # not enough data

    last = df.iloc[-1]
    prev = df.iloc[-2]

    ema_fast = float(last["EMA_FAST"])
    ema_slow = float(last["EMA_SLOW"])
    close_price = float(last["Close"])
    volume = float(last["Volume"])

    if pd.isna(last["AVG_VOL"]):
        return

    avg_vol = float(last["AVG_VOL"])

    uptrend = ema_fast > ema_slow
    downtrend = ema_fast < ema_slow

    breakout = close_price > float(prev["High"])
    breakdown = close_price < float(prev["Low"])

    volume_ok = volume > avg_vol * config.VOLUME_MULTIPLIER

    if uptrend and breakout and volume_ok:
        direction = "CALL"
    elif downtrend and breakdown and volume_ok:
        direction = "PUT"
    else:
        return

    premium = round(close_price * 0.012, 2)
    qty = calculate_qty(premium)
    sl = round(premium * (1 - config.STOP_LOSS_PCT), 2)
    target = round(premium * (1 + config.TARGET_PCT), 2)

    open_trade = {
        "direction": direction,
        "entry": premium,
        "sl": sl,
        "target": target,
        "qty": qty,
        "entry_time": datetime.datetime.now()
    }

    trade_count += 1

    send_telegram(
        f"📥 ENTRY {direction}\n"
        f"Trade {trade_count}/{config.MAX_TRADES_PER_DAY}\n"
        f"NIFTY Spot: {round(close_price,2)}\n"
        f"Premium: {premium}\n"
        f"Qty: {qty}\n"
        f"SL: {sl}\n"
        f"Target: {target}\n"
        f"Logic: EMA + Volume + Breakout\n"
        f"Mode: PAPER"
    )

# ===============================
# EXIT LOGIC
# ===============================
def check_exit(df):
    global open_trade

    if open_trade is None or df is None:
        return

    last_price = round(float(df.iloc[-1]["Close"]) * 0.012, 2)

    if last_price <= open_trade["sl"] or last_price >= open_trade["target"]:
        pnl = round((last_price - open_trade["entry"]) * open_trade["qty"], 2)

        trades.append(pnl)

        send_telegram(
            f"📤 EXIT {open_trade['direction']}\n"
            f"Exit Premium: {last_price}\n"
            f"P/L: {pnl}"
        )

        open_trade = None

# ===============================
# MAIN LOOP
# ===============================
send_telegram("🤖 NIFTY AUTO BOT STARTED (SAFE MODE)")

while True:
    now = datetime.datetime.now().time()

    df = fetch_nifty_data()
    if df is not None:
        df = apply_indicators(df)

    if TRADE_START <= now <= FORCE_EXIT:
        check_exit(df)
        check_entry(df)

    if now >= MARKET_END:
        send_telegram("🛑 MARKET CLOSED")
        break

    time.sleep(60)