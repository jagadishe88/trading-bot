import data_feed
import json
import requests
import sys
from datetime import datetime, timedelta

with open("secrets.json") as f:
    secrets = json.load(f)

TELEGRAM_TOKEN = secrets["telegram_token"]
TELEGRAM_CHAT_ID = secrets["telegram_chat_id"]

# Constants
STOCK_LIST = [
    "QQQ", "SPY", "IWM", "PG", "PEP", "AAPL", "MSFT", "NVDA", "TSLA",
    "META", "AMZN", "GOOGL", "NFLX", "LLY", "COIN", "MSTR", "AMD", "AVGO", "ARM",
    "CRWD", "PANW", "CRM", "BA", "COST", "HD", "ADBE", "SNOW", "LULU", "UNH",
    "CAT", "ANF", "DELL", "DE", "MDB", "GLD", "PDD", "ORCL", "TGT", "FDX",
    "AXP", "CMG", "NKE", "BABA", "WMT", "ROKU"
]
RVOL_LOOKBACK = 20
NORMAL_RVOL = 100
LUNCH_HOUR_START = 12 * 3600 + 30 * 60  # 12:30 PM EST in seconds
LUNCH_HOUR_END = 13 * 3600 + 30 * 60    # 1:30 PM EST in seconds

def send_telegram_alert(message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, json=payload)
        if not r.ok:
            print(f"Telegram error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def get_market_time():
    est_time = datetime.utcnow() - timedelta(hours=9.5)
    return est_time.hour * 3600 + est_time.minute * 60 + est_time.second

def is_trending_market(symbol):
    ma_data = data_feed.get_moving_averages(symbol, [200])
    trends = data_feed.get_trend_data(symbol)
    ema200 = ma_data.get(200, 0)
    mtf_clouds = trends.get('mtf_clouds', {})
    return ema200 > 0 and any(c == 'Bullish' for c in mtf_clouds.values()) if mtf_clouds else False

def generate_alert_improved(symbol, trade_style):
    options_data = data_feed.fetch_option_chain(symbol)
    if options_data['ask_price'] == 0:
        print(f"No valid data for {symbol}, skipping...")
        return
    stock_price = options_data['ask_price']
    rvol = data_feed.calculate_rvol(symbol, RVOL_LOOKBACK) * 100
    pivots = data_feed.get_pivots(symbol)
    ma_data = data_feed.get_moving_averages(symbol, [9, 21, 34, 50, 200])
    trends = data_feed.get_trend_data(symbol)
    mtf_clouds = trends.get('mtf_clouds', {})
    market_time = get_market_time()

    s1, r1 = pivots.get('s1', stock_price * 0.99), pivots.get('r1', stock_price * 1.01)
    pdl, pmh = pivots.get('pdl', s1), pivots.get('pmh', r1)
    pml, pdh = pivots.get('pml', s1), pivots.get('pdh', r1)
    zone_low, zone_high = data_feed.get_5day_zone(symbol)

    is_bullish_9_21 = ma_data.get(9, 0) > ma_data.get(21, 0) and trends.get('9_21', 'Neutral') == 'Bullish' and mtf_clouds.get('1H', 'Neutral') == 'Bullish'
    is_bullish_34_50 = ma_data.get(34, 0) > ma_data.get(50, 0) and trends.get('34_50', 'Neutral') == 'Bullish' and mtf_clouds.get('4H', 'Neutral') == 'Bullish'
    is_neutral_34_50 = trends.get('34_50', 'Neutral') == 'Neutral' and mtf_clouds.get('Daily', 'Neutral') == 'Neutral'
    is_above_200_ema = stock_price > ma_data.get(200, 0)

    sl_pct, tp_pct = {
        'scalp': (1.5, 3.0),
        'day': (2.5, 5.0),
        'swing': (3.0, 6.0)
    }[trade_style]

    atr = data_feed.get_atr(symbol) or stock_price * 0.01
    fib_levels = data_feed.get_fib_levels(symbol) or [0.236, 0.382, 0.5]

    def set_sl_tp(entry):
        if trade_style == 'scalp' and market_time in range(LUNCH_HOUR_START, LUNCH_HOUR_END):
            return None, None
        sl = min(pdl or (entry * (1 - sl_pct / 100)), entry - atr * 1.5)
        tp = max(pmh or (entry * (1 + tp_pct / 100)), entry + atr * fib_levels[0])
        tp = min(tp, entry * 1.1)  # cap TP to +10%
        return sl, tp

    alerts = []
    entry = stock_price

    if trade_style == 'scalp' and is_bullish_9_21 and rvol >= 130 and data_feed.check_tf_alignment(symbol, [3, 5]) and is_above_200_ema:
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"SCALP-C: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif trade_style == 'day' and is_bullish_9_21 and rvol >= 130 and is_trending_market(symbol):
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"DAY-C: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif trade_style == 'swing' and is_bullish_34_50 and rvol >= 135 and data_feed.check_sector_correlation(symbol):
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"SWING-C: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: High")

    elif stock_price > data_feed.get_last_high(symbol) and rvol >= 150 and trends.get('price_action', 'Neutral') == 'Bullish' and is_above_200_ema:
        sl, tp = set_sl_tp(entry)
        if sl and tp and rvol >= 160:
            alerts.append(f"BOS-B: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: High")
        elif sl and tp:
            alerts.append(f"BOS-B: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif stock_price < data_feed.get_last_low(symbol) and rvol >= 150 and trends.get('price_action', 'Neutral') == 'Bearish' and not is_above_200_ema:
        sl, tp = set_sl_tp(entry)
        if sl and tp and rvol >= 160:
            alerts.append(f"BOS-S: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: High")
        elif sl and tp:
            alerts.append(f"BOS-S: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif stock_price <= zone_low and rvol >= 145 and is_above_200_ema:
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"BUY-Z: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif stock_price >= zone_high and rvol >= 155 and not is_above_200_ema:
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"SELL-Z: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif options_data.get('iv', 0) > 1.0 and rvol >= 165 and is_trending_market(symbol):
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"IV-H: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: High")

    elif options_data.get('iv', 0) < 0.8 and rvol < 120 and not is_trending_market(symbol):
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"IV-L: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Low")

    elif options_data.get('delta', 0) < 0.3 and rvol >= 125 and is_above_200_ema:
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"DELTA-L: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Medium")

    elif (stock_price > data_feed.get_last_high(symbol) or stock_price < data_feed.get_last_low(symbol)) and rvol >= 160 and is_trending_market(symbol):
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"BREAK-H: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: High")

    elif abs((stock_price - ma_data.get(50, 0)) / stock_price) <= 0.01 and rvol < 120 and is_neutral_34_50 and not is_trending_market(symbol):
        sl, tp = set_sl_tp(entry)
        if sl and tp:
            alerts.append(f"MEAN-R: {symbol} - Entry: {entry}, SL: {sl}, TP: {tp}, Priority: Low")

    for alert in alerts:
        print(alert)
        send_telegram_alert(alert)

def is_market_open():
    try:
        clock = data_feed.api.get_clock()
        return clock.is_open
    except Exception as e:
        print(f"Error checking market status: {e}")
        return False

if __name__ == "__main__":
    if not is_market_open() and "--force" not in sys.argv:
        print("\ud83d\udeab Market is closed. Skipping alert generation. Use --force to test with historical data.")
    else:
        for symbol in STOCK_LIST:
            generate_alert_improved(symbol, "scalp")
            generate_alert_improved(symbol, "day")
            generate_alert_improved(symbol, "swing")

