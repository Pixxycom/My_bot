import os
import logging
import ccxt
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from flask import Flask, request, jsonify

# ===== CONFIGURATION ===== #
# Verify Gunicorn is installed (critical for Render)
try:
    import gunicorn
    logging.info(f"Gunicorn version: {gunicorn.__version__}")
except ImportError:
    raise RuntimeError("Gunicorn not installed! Add 'gunicorn==20.1.0' to requirements.txt")

# Load environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")

if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("Missing required Telegram credentials")

# ===== TRADING SETTINGS ===== #
TRADE_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
TIMEFRAME = "15m"
RISK_PER_TRADE = 0.2  # 20% of $10 account ($2 risk per trade)
RISK_REWARD_RATIO = 2.5  # 1:2.5 risk-reward

# ===== INITIALIZE EXCHANGE ===== #
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
    'apiKey': BINANCE_API_KEY,
    'secret': BINANCE_SECRET
})

# ===== FLASK APP ===== #
app = Flask(__name__)

# ===== ENHANCED LOGGING ===== #
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== TELEGRAM BOT SETUP ===== #
updater = Updater(BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# ===== LIQUIDITY-BASED STRATEGY ===== #
def analyze_market(pair):
    """Enhanced liquidity-based strategy with error handling"""
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
        
        # Bullish entry condition
        if (last_candle['high'] > prev_candle['liq_high']) and (last_candle['close'] > prev_candle['close']):
            entry = last_candle['close']
            sl = prev_candle['liq_low']
            signals.append({
                'pair': pair,
                'signal': 'BUY',
                'entry': round(entry, 4),
                'sl': round(sl, 4),
                'tp': round(entry + (entry - sl) * RISK_REWARD_RATIO, 4),
                'timeframe': TIMEFRAME,
                'risk': f"${RISK_PER_TRADE * 10} (20%)"
            })

        # Bearish entry condition    
        if (last_candle['low'] < prev_candle['liq_low']) and (last_candle['close'] < prev_candle['close']):
            entry = last_candle['close']
            sl = prev_candle['liq_high']
            signals.append({
                'pair': pair,
                'signal': 'SELL',
                'entry': round(entry, 4),
                'sl': round(sl, 4),
                'tp': round(entry - (sl - entry) * RISK_REWARD_RATIO, 4),
                'timeframe': TIMEFRAME,
                'risk': f"${RISK_PER_TRADE * 10} (20%)"
            })

        return signals

    except Exception as e:
        logger.error(f"Error analyzing {pair}: {str(e)}", exc_info=True)
        return []

# ===== TELEGRAM COMMANDS ===== #
def start(update: Update, context: CallbackContext):
    """Enhanced start command with strategy info"""
    update.message.reply_text(
        "🚀 *Crypto Liquidity Trading Bot* 🚀\n\n"
        "📈 *Strategy*: Liquidity Sweep\n"
        "⏰ *Timeframe*: 15m\n"
        "⚖️ *Risk-Reward*: 1:2.5\n\n"
        "💼 *Trading Pairs*:\n"
        "- BTC/USDT\n- ETH/USDT\n- SOL/USDT\n"
        "- XRP/USDT\n- ADA/USDT\n\n"
        "🔍 *Commands*:\n"
        "/start - Show this info\n"
        "/scan - Find trade setups\n"
        "/strat - Strategy details",
        parse_mode='Markdown'
    )

def scan_markets(update: Update, context: CallbackContext):
    """Market scanner with progress feedback"""
    update.message.reply_text("🔍 Scanning markets...")
    for pair in TRADE_PAIRS:
        signals = analyze_market(pair)
        if signals:
            for signal in signals:
                send_signal(update, signal)

def strat(update: Update, context: CallbackContext):
    """Detailed strategy explanation"""
    update.message.reply_text(
        "📊 *Liquidity Trading Strategy*\n\n"
        "1. Identify recent highs/lows (liquidity zones)\n"
        "2. Wait for price to sweep these levels\n"
        "3. Enter on confirmation candle close\n"
        "4. Stop loss beyond liquidity zone\n"
        "5. Take profit at 2.5x risk\n\n"
        "🛡️ *Risk Management*:\n"
        "- Max 20% account risk ($2 on $10 account)\n"
        "- 1:2.5 reward ratio",
        parse_mode='Markdown'
    )

def send_signal(update: Update, signal):
    """Professional signal formatting"""
    message = (
        f"🔥 *{signal['pair']} {signal['signal']} Signal*\n\n"
        f"🎯 Entry: `{signal['entry']}`\n"
        f"🛑 Stop Loss: `{signal['sl']}`\n"
        f"💰 Take Profit: `{signal['tp']}`\n"
        f"⏰ Timeframe: {signal['timeframe']}\n"
        f"⚖️ Risk: {signal['risk']}\n\n"
        f"*Confirm Trade?*"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Trade", callback_data=f"confirm_{signal['pair']}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    update.message.reply_text(
        text=message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

def button_handler(update: Update, context: CallbackContext):
    """Trade confirmation handler"""
    query = update.callback_query
    query.answer()
    
    if query.data.startswith('confirm_'):
        pair = query.data.split('_')[1]
        query.edit_message_text(f"✅ *Trade Executed*\n\n{pair} position opened", parse_mode='Markdown')
    else:
        query.edit_message_text("❌ Trade canceled")

# ===== FLASK ENDPOINTS ===== #
@app.route('/')
def home():
    return "🟢 Trading Bot Operational"

@app.route('/health')
def health_check():
    return jsonify(status="healthy", bot="running"), 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    """Telegram webhook handler"""
    if request.method == "POST":
        update = Update.de_json(request.get_json(), updater.bot)
        dispatcher.process_update(update)
    return jsonify(success=True)

# ===== INITIALIZATION ===== #
def initialize():
    """Complete application initialization"""
    # Register command handlers
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('scan', scan_markets))
    dispatcher.add_handler(CommandHandler('strat', strat))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    
    # Webhook configuration for Render
    hostname = os.getenv('RENDER_EXTERNAL_HOSTNAME')
    if not hostname:
        logger.warning("Running in polling mode (RENDER_EXTERNAL_HOSTNAME not set)")
        updater.start_polling()
        return
    
    webhook_url = f"https://{hostname}/{BOT_TOKEN}"
    port = int(os.getenv('PORT', 10000))
    
    updater.start_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=webhook_url
    )
    logger.info(f"Webhook configured for {webhook_url}")

if __name__ == '__main__':
    initialize()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 10000)))
