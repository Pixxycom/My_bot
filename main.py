import os
import logging
import ccxt
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from flask import Flask, request, jsonify

# ===== CONFIGURATION ===== #
# Verify required environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if not CHAT_ID:
    raise ValueError("TELEGRAM_CHAT_ID environment variable is required")

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")  # Optional (for private data)
BINANCE_SECRET = os.getenv("BINANCE_SECRET")    # Optional

# ===== TRADING SETTINGS ===== #
TRADE_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
TIMEFRAME = "15m"
RISK_PER_TRADE = 0.2  # 20% of $10 account ($2 per trade)
RISK_REWARD_RATIO = 2.5  # 1:2.5 (TP = 2.5x SL)

# ===== INITIALIZE EXCHANGE ===== #
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': { 'defaultType': 'future' }
})

# ===== FLASK APP (FOR RENDER.COM) ===== #
app = Flask(__name__)

# ===== LOGGING ===== #
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== TELEGRAM BOT INITIALIZATION ===== #
updater = Updater(BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# ===== LIQUIDITY-BASED STRATEGY ===== #
def analyze_market(pair):
    """Fetches market data and looks for liquidity-based setups."""
    try:
        ohlcv = exchange.fetch_ohlcv(pair, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Liquidity Zones
        df['liq_high'] = df['high'].rolling(5).max()
        df['liq_low'] = df['low'].rolling(5).min()

        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]

        signals = []

        # Bullish Signal
        if (last_candle['high'] > prev_candle['liq_high']) and (last_candle['close'] > prev_candle['close']):
            entry = last_candle['close']
            sl = prev_candle['liq_low']
            tp = entry + (entry - sl) * RISK_REWARD_RATIO
            
            signals.append({
                'pair': pair,
                'signal': 'BUY',
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'timeframe': TIMEFRAME,
                'reason': 'Liquidity Sweep (Bullish)'
            })

        # Bearish Signal
        if (last_candle['low'] < prev_candle['liq_low']) and (last_candle['close'] < prev_candle['close']):
            entry = last_candle['close']
            sl = prev_candle['liq_high']
            tp = entry - (sl - entry) * RISK_REWARD_RATIO
            
            signals.append({
                'pair': pair,
                'signal': 'SELL',
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'timeframe': TIMEFRAME,
                'reason': 'Liquidity Sweep (Bearish)'
            })

        return signals

    except Exception as e:
        logger.error(f"Error analyzing {pair}: {e}")
        return []

# ===== TELEGRAM BOT FUNCTIONS ===== #
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🚀 **Crypto Day Trading Bot (Liquidity Strategy)** 🚀\n\n"
        "🔹 **Pairs:** BTC, ETH, SOL, XRP, ADA\n"
        "🔹 **Timeframe:** 15m\n"
        "🔹 **Risk-Reward:** 1:2.5\n\n"
        "📌 Commands:\n"
        "/start - Show this menu\n"
        "/scan - Check for new trades\n"
        "/trades - Show recent signals"
    )

def scan_markets(update: Update, context: CallbackContext):
    """Scans all pairs for trading opportunities."""
    for pair in TRADE_PAIRS:
        signals = analyze_market(pair)
        if signals:
            for signal in signals:
                send_signal(update, signal)

def send_signal(update: Update, signal):
    """Sends a trade signal with confirmation buttons."""
    message = (
        f"🔥 **{signal['pair']} {signal['signal']} Signal** 🔥\n"
        f"📊 **Reason:** {signal['reason']}\n"
        f"⏰ **Timeframe:** {signal['timeframe']}\n"
        f"💰 **Entry:** `{signal['entry']:.4f}`\n"
        f"🛑 **Stop Loss:** `{signal['sl']:.4f}`\n"
        f"🎯 **Take Profit:** `{signal['tp']:.4f}`\n"
        f"📈 **Risk-Reward:** 1:{RISK_REWARD_RATIO}\n\n"
        f"⚠️ **Account Risk:** ${RISK_PER_TRADE * 10} (20% of $10)"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Confirm Trade", callback_data=f"confirm_{signal['pair']}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        text=message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def button_handler(update: Update, context: CallbackContext):
    """Handles button presses (trade confirmations)."""
    query = update.callback_query
    query.answer()

    if query.data.startswith('confirm_'):
        pair = query.data.split('_')[1]
        query.edit_message_text(f"✅ **Trade Executed!**\n\n{pair} position opened.")
    elif query.data == "cancel":
        query.edit_message_text("❌ **Trade Canceled**")

# ===== FLASK ROUTES ===== #
@app.route('/webhook', methods=['POST'])
def webhook():
    """Handles Telegram webhook updates."""
    if request.method == "POST":
        update = Update.de_json(request.get_json(), updater.bot)
        dispatcher.process_update(update)
    return jsonify(success=True)

@app.route('/')
def home():
    return "🚀 Crypto Trading Bot is Running!"

@app.route('/health')
def health_check():
    """Health check endpoint for Render"""
    return jsonify(status="healthy"), 200

# ===== START THE BOT ===== #
def run_bot():
    """Initialize and run the bot"""
    # Add command handlers
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('scan', scan_markets))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    # Set webhook
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
    updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.getenv('PORT', 10000)),
        url_path=BOT_TOKEN,
        webhook_url=webhook_url
    )
    logger.info(f"Bot started with webhook URL: {webhook_url}")

if __name__ == '__main__':
    run_bot()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
