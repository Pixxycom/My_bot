import os
import time
import threading
import requests
from flask import Flask
import pandas as pd
import ta
from dotenv import load_dotenv
import datetime

# ------------------- Load Secrets -------------------
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ------------------- Flask Web App -------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "SMC Telegram Bot with Bullish & Bearish OB is Running..."

# ------------------- Globals -------------------
bullish_obs = {}  # {'BTCUSDT': (low, high)}
bearish_obs = {}  # {'BTCUSDT': (high, low)}

# ------------------- Fetch Market Data -------------------
def fetch_ohlcv(symbol='BTCUSDT', interval='15m', limit=100):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    response = requests.get(url)
    data = response.json()
    df = pd.DataFrame(data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return df

# ------------------- OB Detection -------------------
def find_bullish_ob(df):
    last = df.iloc[-5:]
    if all(last['close'].iloc[i] < last['open'].iloc[i] for i in range(2)):
        if last['close'].iloc[-1] > last['high'].iloc[-2]:
            return (last['low'].iloc[-2], last['high'].iloc[-2])
    return None

def find_bearish_ob(df):
    last = df.iloc[-5:]
    if all(last['close'].iloc[i] > last['open'].iloc[i] for i in range(2)):
        if last['close'].iloc[-1] < last['low'].iloc[-2]:
            return (last['high'].iloc[-2], last['low'].iloc[-2])
    return None

# ------------------- Confluences -------------------
def detect_bos_bullish(df):
    highs = df['high']
    return highs.iloc[-1] > max(highs.iloc[-5:-1])

def detect_bos_bearish(df):
    lows = df['low']
    return lows.iloc[-1] < min(lows.iloc[-5:-1])

def detect_fvg_bullish(df):
    prev_high = df['high'].iloc[-2]
    curr_low = df['low'].iloc[-1]
    return curr_low > prev_high

def detect_fvg_bearish(df):
    prev_low = df['low'].iloc[-2]
    curr_high = df['high'].iloc[-1]
    return curr_high < prev_low

def detect_trend_bullish(df):
    ma50 = ta.trend.sma_indicator(df['close'], window=50)
    ma200 = ta.trend.sma_indicator(df['close'], window=200)
    return ma50.iloc[-1] > ma200.iloc[-1]

def detect_trend_bearish(df):
    ma50 = ta.trend.sma_indicator(df['close'], window=50)
    ma200 = ta.trend.sma_indicator(df['close'], window=200)
    return ma50.iloc[-1] < ma200.iloc[-1]

# ------------------- Telegram -------------------
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ------------------- Main Logic -------------------
def analyze_and_track_order_blocks():
    global bullish_obs, bearish_obs
    pairs = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'AVAXUSDT']
    interval = '15m'

    for pair in pairs:
        df = fetch_ohlcv(pair, interval)

        # 🔵 Detect new Bullish OB
        new_bullish = find_bullish_ob(df)
        if new_bullish:
            bullish_obs[pair] = new_bullish
            print(f"[{pair}] 🟢 Bullish OB detected: {new_bullish}")

        # 🔴 Detect new Bearish OB
        new_bearish = find_bearish_ob(df)
        if new_bearish:
            bearish_obs[pair] = new_bearish
            print(f"[{pair}] 🔴 Bearish OB detected: {new_bearish}")

        # 🔵 Check Bullish OB Tap
        if pair in bullish_obs:
            ob_low, ob_high = bullish_obs[pair]
            current_low = df['low'].iloc[-1]
            if ob_low <= current_low <= ob_high:
                if detect_bos_bullish(df) and detect_fvg_bullish(df) and detect_trend_bullish(df):
                    time_now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                    message = f"📈 *Bullish SMC Signal!*\n\n📌 Pair: {pair}\n🕒 {time_now}\n\n🟢 OB Zone: {ob_low:.2f} - {ob_high:.2f}\n\n✅ BOS\n✅ FVG\n✅ Uptrend\n\n📥 Consider long entry."
                    send_telegram(message)
                    del bullish_obs[pair]

        # 🔴 Check Bearish OB Tap
        if pair in bearish_obs:
            ob_high, ob_low = bearish_obs[pair]
            current_high = df['high'].iloc[-1]
            if ob_low <= current_high <= ob_high:
                if detect_bos_bearish(df) and detect_fvg_bearish(df) and detect_trend_bearish(df):
                    time_now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
                    message = f"📉 *Bearish SMC Signal!*\n\n📌 Pair: {pair}\n🕒 {time_now}\n\n🔴 OB Zone: {ob_high:.2f} - {ob_low:.2f}\n\n✅ BOS\n✅ FVG\n✅ Downtrend\n\n📤 Consider short entry."
                    send_telegram(message)
                    del bearish_obs[pair]

# ------------------- Bot Loop -------------------
def bot_loop():
    while True:
        try:
            print("Running full SMC OB detection...")
            analyze_and_track_order_blocks()
        except Exception as err:
            print(f"Error in bot loop: {err}")
        print("Sleeping for 30 minutes...")
        time.sleep(1800)

# ------------------- Start Everything -------------------
threading.Thread(target=bot_loop).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
