import os
import logging
import ccxt
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from flask import Flask, request, jsonify

# ===== CONFIGURATION ===== #
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

# Validate required environment variables
if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing required environment variables")

# ===== TRADING SETTINGS ===== #
TRADE_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
TIMEFRAME = "15m"
RISK_PER_TRADE = 0.2
RISK_REWARD_RATIO = 2.5

# ===== INITIALIZE EXCHANGE ===== #
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET
})

# ===== FLASK APP ===== #
app = Flask(__name__)

# ===== LOGGING ===== #
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== TELEGRAM BOT SETUP ===== #
def initialize_bot():
    """Initialize Telegram bot components"""
    updater = Updater(BOT_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # Register handlers
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('scan', scan_markets))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    
    return updater

# ===== TRADING STRATEGY ===== #
def analyze_market(pair):
    """Analyze market data for trading signals"""
    try:
        ohlcv = exchange.fetch_ohlcv(pair, TIMEFRAME, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Calculate liquidity zones
        df['liq_high'] = df['high'].rolling(5).max()
        df['liq_low'] = df['low'].rolling(5).min()
        
        last_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]
        
        signals = []
        
        # Trading logic
        if (last_candle['high'] > prev_candle['liq_high']) and (last_candle['close'] > prev_candle['close']):
            entry = last_candle['close']
            sl = prev_candle['liq_low']
            signals.append({
                'pair': pair,
                'signal': 'BUY',
                'entry': entry,
                'sl': sl,
                'tp': entry + (entry - sl) * RISK_REWARD_RATIO,
                'timeframe': TIMEFRAME,
                'reason': 'Bullish Liquidity Sweep'
            })
            
        if (last_candle['low'] < prev_candle['liq_low']) and (last_candle['close'] < prev_candle['close']):
            entry = last_candle['close']
            sl = prev_candle['liq_high']
            signals.append({
                'pair': pair,
                'signal': 'SELL',
                'entry': entry,
                'sl': sl,
                'tp': entry - (sl - entry) * RISK_REWARD_RATIO,
                'timeframe': TIMEFRAME,
                'reason': 'Bearish Liquidity Sweep'
            })
            
        return signals
        
    except Exception as e:
        logger.error(f"Error analyzing {pair}: {str(e)}")
        return []

# ===== TELEGRAM HANDLERS ===== #
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🚀 Crypto Trading Bot\n\n"
        "Available commands:\n"
        "/start - Show this menu\n"
        "/scan - Check for trades"
    )

def scan_markets(update: Update, context: CallbackContext):
    for pair in TRADE_PAIRS:
        signals = analyze_market(pair)
        for signal in signals:
            send_signal(update, signal)

def send_signal(update: Update, signal):
    message = (
        f"🔥 {signal['pair']} {signal['signal']}\n"
        f"Entry: {signal['entry']:.4f}\n"
        f"SL: {signal['sl']:.4f}\n"
        f"TP: {signal['tp']:.4f}\n"
        f"Reason: {signal['reason']}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{signal['pair']}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    update.message.reply_text(
        text=message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    if query.data.startswith('confirm_'):
        query.edit_message_text("✅ Trade confirmed")
    else:
        query.edit_message_text("❌ Trade canceled")

# ===== FLASK ROUTES ===== #
@app.route('/')
def home():
    return "Trading Bot Running"

@app.route('/health')
def health_check():
    return jsonify(status="OK"), 200

# ===== APPLICATION STARTUP ===== #
def run_app():
    """Main application startup"""
    port = int(os.getenv('PORT', 10000))
    
    # Initialize bot components
    updater = initialize_bot()
    
    # Configure webhook
    hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')
    webhook_url = f"https://{hostname}/{BOT_TOKEN}"
    
    updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=webhook_url
    )
    logger.info(f"Bot started on port {port}")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    run_app()
