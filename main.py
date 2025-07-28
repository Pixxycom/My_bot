import os
import requests
import pandas as pd
import time
import telebot
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TELEGRAM_API_KEY = os.getenv("TELEGRAM_API_KEY")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_API_KEY)

# Config
PAIRS = ["bitcoin", "ethereum", "solana", "cardano", "binancecoin"]
TIMEFRAME = "1h"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/{}/market_chart?vs_currency=usd&days=2&interval=hourly"


def get_price_data(coin_id):
    try:
        url = COINGECKO_URL.format(coin_id)
        response = requests.get(url)
        prices = response.json()["prices"]

        df = pd.DataFrame(prices, columns=["timestamp", "price"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df["price"] = df["price"].astype(float)
        return df
    except Exception as e:
        print(f"[{coin_id}] Error fetching data: {e}")
        return None


def detect_bos_and_ob(df):
    df["high"] = df["price"].rolling(window=3).max()
    df["low"] = df["price"].rolling(window=3).min()
    df.dropna(inplace=True)

    recent_high = df["high"].iloc[-2]
    recent_low = df["low"].iloc[-2]
    current_price = df["price"].iloc[-1]

    bos_up = current_price > recent_high
    bos_down = current_price < recent_low

    trend = "ranging"
    if bos_up:
        trend = "uptrend"
    elif bos_down:
        trend = "downtrend"

    ob_zone = None
    if trend == "uptrend":
        ob_zone = df["low"].iloc[-3]
    elif trend == "downtrend":
        ob_zone = df["high"].iloc[-3]

    return trend, bos_up or bos_down, ob_zone


def send_signal(coin, trend, ob_zone):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    message = f"""
📊 *{coin.upper()} Signal* — {now}

Trend: *{trend.upper()}*
Order Block Zone: `{ob_zone:.2f}`

_Trade with trend. Avoid ranging markets._
    """
    bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")


def run_bot():
    for coin in PAIRS:
        df = get_price_data(coin)
        if df is None:
            continue

        trend, bos_detected, ob_zone = detect_bos_and_ob(df)

        if trend != "ranging" and bos_detected and ob_zone:
            send_signal(coin, trend, ob_zone)
        else:
            print(f"[{coin}] No valid structure — skipped.")


if __name__ == "__main__":
    while True:
        try:
            print("🔄 Running bot cycle...")
            run_bot()
            print("✅ Done. Waiting 30 minutes...\n")
        except Exception as e:
            print(f"❌ Bot crashed: {e}")
        time.sleep(1800)  # Wait 30 mins (1800 seconds)
