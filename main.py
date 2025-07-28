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
    return "SMC Telegram Bot is Running..."

# ------------------- SMC Strategy -------------------
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

def detect_order_block(df):
    # Simple bullish OB: A big down candle followed by bullish BOS
    last = df.iloc[-5:]
    if all(last['close'].iloc[i] < last['open'].iloc[i] for i in range(2)) and last['close'].iloc[-1] > last['high'].iloc[-2]:
        return True
    return False

def detect_bos(df):
    highs = df['high']
    return highs.iloc[-1] > max(highs.iloc[-5:-1])

def detect_fvg(df):
    prev_high = df['high'].iloc[-2]
    curr_low = df['low'].iloc[-1]
    return curr_low > prev_high  # Fair Value Gap

def detect_trend(df):
    ma50 = ta.trend.sma_indicator(df['close'], window=50)
    ma200 = ta.trend.sma_indicator(df['close'], window=200)
    return ma50.iloc[-1] > ma200.iloc[-1]  # Uptrend

def analyze_smc_and_send_signal():
    pairs = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'AVAXUSDT']
    interval = '15m'
    
    for pair in pairs:
        df = fetch_ohlcv(pair, interval)

        if detect_order_block(df) and detect_bos(df) and detect_fvg(df) and detect_trend(df):
            time_now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            message = f"📈 *A+ SMC Trade Signal!*\n\n📌 Pair: {pair}\n🕒 Time: {time_now}\n\nSMC Confluence:\n✅ Order Block Hit\n✅ BOS\n✅ Fair Value Gap\n✅ Uptrend\n\n👉 Confirm setup and enter wisely."
            send_telegram(message)

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

# ------------------- Bot Loop -------------------
def bot_loop():
    while True:
        try:
            print("Running SMC analysis...")
            analyze_smc_and_send_signal()
        except Exception as err:
            print(f"Error in bot loop: {err}")
        print("Sleeping for 30 minutes...")
        time.sleep(1800)  # 30 minutes

# ------------------- Start Everything -------------------
threading.Thread(target=bot_loop).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
