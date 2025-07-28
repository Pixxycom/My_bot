import os
import requests
import pandas as pd
import ta
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PAIRS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']
TIMEFRAME = '15m'

BINANCE_ENDPOINT = 'https://api.binance.com/api/v3/klines'

# Fetch live candle data from Binance
def fetch_candles(symbol, interval='15m', limit=150):
    try:
        url = f"{BINANCE_ENDPOINT}?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'trades', 'tbbav', 'tbqav', 'ignore'
        ])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df = df[['time', 'open', 'high', 'low', 'close']]
        df = df.astype(float)
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

# Trend Detection using EMA50
def detect_trend(df):
    df['ema50'] = ta.trend.ema_indicator(df['close'], window=50).fillna(0)
    if df['close'].iloc[-1] > df['ema50'].iloc[-1]:
        return 'bullish'
    elif df['close'].iloc[-1] < df['ema50'].iloc[-1]:
        return 'bearish'
    else:
        return 'sideways'

# Fair Value Gap (FVG) Detection
def detect_fvg(df):
    gaps = []
    for i in range(2, len(df)):
        if df['low'].iloc[i] > df['high'].iloc[i-2]:
            gaps.append(('bullish', df['high'].iloc[i-2], df['low'].iloc[i]))
        elif df['high'].iloc[i] < df['low'].iloc[i-2]:
            gaps.append(('bearish', df['low'].iloc[i-2], df['high'].iloc[i]))
    return gaps

# Liquidity Sweep Detection (simplified wick logic)
def swept_liquidity(df, trend):
    if trend == 'bullish':
        wick = df['low'].iloc[-2]
        body = min(df['open'].iloc[-2], df['close'].iloc[-2])
        return wick < body
    elif trend == 'bearish':
        wick = df['high'].iloc[-2]
        body = max(df['open'].iloc[-2], df['close'].iloc[-2])
        return wick > body
    return False

# Order Block Detection + A+ Setup Logic
def detect_a_plus_setup(df, trend):
    if trend == 'bullish':
        # Look for last down candle before BOS
        for i in range(len(df)-6, len(df)-2):
            if df['close'].iloc[i] < df['open'].iloc[i] and df['high'].iloc[i+1] > df['high'].iloc[i-1]:
                ob = {
                    'entry': df['open'].iloc[i],
                    'sl': df['low'].iloc[i] - 0.001 * df['low'].iloc[i],
                    'bos': True
                }
                current_price = df['close'].iloc[-1]
                if ob['entry'] - 0.001 < current_price < ob['entry'] + 0.001:
                    fvg = detect_fvg(df)
                    if fvg and swept_liquidity(df, trend):
                        tp = ob['entry'] + (ob['entry'] - ob['sl']) * 2.5
                        return {
                            'side': 'buy',
                            'entry': round(ob['entry'], 2),
                            'sl': round(ob['sl'], 2),
                            'tp': round(tp, 2),
                            'bos': True
                        }
    elif trend == 'bearish':
        for i in range(len(df)-6, len(df)-2):
            if df['close'].iloc[i] > df['open'].iloc[i] and df['low'].iloc[i+1] < df['low'].iloc[i-1]:
                ob = {
                    'entry': df['open'].iloc[i],
                    'sl': df['high'].iloc[i] + 0.001 * df['high'].iloc[i],
                    'bos': True
                }
                current_price = df['close'].iloc[-1]
                if ob['entry'] - 0.001 < current_price < ob['entry'] + 0.001:
                    fvg = detect_fvg(df)
                    if fvg and swept_liquidity(df, trend):
                        tp = ob['entry'] - (ob['sl'] - ob['entry']) * 2.5
                        return {
                            'side': 'sell',
                            'entry': round(ob['entry'], 2),
                            'sl': round(ob['sl'], 2),
                            'tp': round(tp, 2),
                            'bos': True
                        }
    return None

# Telegram Alert
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
        print(f"Telegram error: {e}")

# Market Analysis
def analyze_market():
    for symbol in PAIRS:
        df = fetch_candles(symbol)
        if df is None:
            continue

        trend = detect_trend(df)
        if trend == 'sideways':
            continue

        signal = detect_a_plus_setup(df, trend)
        if signal:
            message = f"""
📊 *SMC Trade Signal - {symbol}*
🕒 Timeframe: 15m
📈 Trend: *{trend.upper()}*
🔹 Setup: BOS + OB + FVG + Liquidity Sweep
🎯 Entry: {signal['entry']}
🛑 SL: {signal['sl']}
🏁 TP: {signal['tp']}
📊 R:R = 1:2.5
✅ Status: A+ Setup Confirmed
            """
            send_telegram(message.strip())

# Flask route for Render ping
@app.route('/webhook', methods=['GET'])
def webhook():
    analyze_market()
    return "SMC scan complete ✅"

if __name__ == '__main__':
    app.run(debug=True)
