from infer_trade_type import infer_trade_type
from datetime import datetime, timedelta
from time import time
import random

# === Simulated Trend Table ===
def get_trend_table(symbol):
    return {
        "Price Action": "Bearish",
        "5/12 Cloud": "Bearish",
        "9/21 Cloud": "Bearish",
        "34/50 Cloud": "Choppy",
        "D MTF 20/21": "Bearish",
        "MTF 50/65": "Choppy"
    }

def get_table_based_trend(symbol):
    trend_table = get_trend_table(symbol)
    bullish_count = sum(1 for val in trend_table.values() if "Bullish" in val)
    bearish_count = sum(1 for val in trend_table.values() if "Bearish" in val)

    if bullish_count >= 3 and bearish_count <= 2:
        return {"execution_tf_trend": "Bullish", "confirmation_tf_trend": "Bullish"}
    elif bearish_count >= 3 and bullish_count <= 2:
        return {"execution_tf_trend": "Bearish", "confirmation_tf_trend": "Bearish"}
    else:
        return {"execution_tf_trend": "Choppy", "confirmation_tf_trend": "Choppy"}

def detect_bos(symbol):
    return True

def get_rvol(symbol):
    return random.randint(100, 200)

def get_candle_body_pct(symbol):
    return random.uniform(1.0, 4.0)

def get_level_proximity(symbol):
    return random.uniform(0.1, 1.0)

def get_atr(symbol):
    return 10 if symbol in ["SPX"] else 2.5 if symbol in ["QQQ"] else 1.5

# === Structural SL/TP with Smart R:R Evaluation ===
def get_best_sl_tp(symbol, entry):
    levels = {
        "PMH": entry + 1.0,
        "PML": entry - 1.0,
        "PDH": entry + 0.75,
        "PDL": entry - 0.75,
        "EMA200": entry - 0.9,
        "MTF_Cloud": entry + 1.25
    }
    atr = get_atr(symbol)
    fallback_sl = round(entry + atr * 0.5, 2)
    fallback_tp = round(entry - atr * 0.75, 2)
    min_rr = 1.3

    best_pair = (None, None)
    best_rr = 0
    reason = ""

    valid_sl_levels = {k: v for k, v in levels.items() if v > entry}
    valid_tp_levels = {k: v for k, v in levels.items() if v < entry}

    for sl_key, sl_val in valid_sl_levels.items():
        for tp_key, tp_val in valid_tp_levels.items():
            sl = round(sl_val, 2)
            tp = round(tp_val, 2)
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            if risk == 0:
                continue
            rr = reward / risk
            if rr >= min_rr and rr > best_rr:
                best_pair = (sl, tp)
                best_rr = rr
                reason = f"SL based on {sl_key}, TP based on {tp_key} (R:R = {round(rr, 2)})"

    if best_pair == (None, None):
        reason = "Fallback to ATR/Fib levels (no structural R:R found)"
        return fallback_sl, fallback_tp, reason
    return best_pair[0], best_pair[1], reason

def calculate_sl_tp(entry_price, trade_type, symbol):
    entry_price = float(entry_price)
    return get_best_sl_tp(symbol, entry_price)

alert_cache = {}

def generate_alert(symbol, data, trade_type, alert_type, rvol):
    cache_key = f"{symbol}_{alert_type}"
    now = time()
    if cache_key in alert_cache and now - alert_cache[cache_key] < 60:
        return None
    alert_cache[cache_key] = now

    sl, tp, rationale = calculate_sl_tp(data["price"], trade_type, symbol)
    if sl is None or tp is None:
        return None

    entry_price = float(data["price"])
    if trade_type.endswith("Long") and sl > entry_price:
        return None
    if trade_type.endswith("Short") and sl < entry_price:
        return None

    strike_price = data.get("strike", "N/A")
    # Parse strike from option code (e.g., "250703C00143000" -> 143.00)
    if isinstance(strike_price, str) and len(strike_price) > 8:
        strike_float = float(strike_price[-8:]) / 1000  # Last 8 digits as cents
    elif strike_price != "N/A":
        strike_float = float(strike_price)
    else:
        strike_float = entry_price  # Fallback to entry price

    option_type = "P" if trade_type.endswith("Short") and strike_float > entry_price else "C"
    formatted_strike = f"{option_type} ${strike_float:.2f}" if strike_price != "N/A" else "N/A"

    option_price = data.get("option_price", 0)
    is_index = symbol in ["SPX", "SPXW"]
    is_etf = symbol in ["QQQ", "SPY", "IWM"]

    if is_index:
        if option_price < 150 or option_price > 1000:
            return None
    elif is_etf:
        if option_price < 80 or option_price > 350:
            return None
    else:
        if option_price < 15:
            return None

    buy_date = datetime.now()
    expiry_date = buy_date + timedelta(days=data["dte"])

    if "HIGHIVALERT" in alert_type:
        base_rationale = "due to a confirmed break of structure and extremely high implied volatility."
    elif "LOWIVALERT" in alert_type:
        base_rationale = "due to a confirmed break of structure and low implied volatility."
    else:
        base_rationale = "due to a confirmed break of structure and market conditions."

    rationale = (
        f"We are entering this {trade_type.lower()} trade {base_rationale} "
        f"The stop loss is set at {sl} to limit risk, and the take profit is at {tp} to capture the expected move with a good risk-reward ratio."
    )

    return {
        "symbol": symbol,
        "price": data["price"],
        "dte": data["dte"],
        "strike": formatted_strike,
        "delta": data["delta"],
        "iv": round(data["iv"] * 100, 2),
        "option_type": option_type,
        "option_price": option_price,
        "trade_type": trade_type,
        "alert_type": alert_type,
        "rvol": rvol,
        "stop_loss": sl,
        "take_profit": tp,
        "rationale": rationale,
        "option_buy_date": buy_date.strftime("%Y-%m-%d"),
        "option_expiry_date": expiry_date.strftime("%Y-%m-%d"),
        "timestamp": buy_date.strftime("%Y-%m-%d %H:%M:%S")
    }

# === Alert Evaluation ===
def evaluate_bundled_alert(data):
    symbol = data.get("symbol")
    if not symbol or not data.get("price"):
        return None

    trade_type = infer_trade_type(symbol, int(data["dte"])).capitalize()
    trend = get_table_based_trend(symbol)

    if trend["execution_tf_trend"] != trend["confirmation_tf_trend"]:
        return None
    if trend["execution_tf_trend"] == "Choppy":
        return None

    tags = []
    rvol = get_rvol(symbol)

    if detect_bos(symbol):
        if trend["execution_tf_trend"] == "Bullish":
            tags.append("BOSLONGCONFIRMED")
        elif trend["execution_tf_trend"] == "Bearish":
            tags.append("BOSSHORTCONFIRMED")
        else:
            return None

    if trade_type == "Scalp" and rvol >= 125:
        tags.append("SCALPLONGCONFIRMED" if trend["execution_tf_trend"] == "Bullish" else "SCALPSHORTCONFIRMED")
    elif trade_type == "Day" and rvol >= 125:
        tags.append("DAYTRADELONGCONFIRMED" if trend["execution_tf_trend"] == "Bullish" else "DAYTRADESHORTCONFIRMED")
    elif trade_type == "Swing" and rvol >= 125:
        tags.append("SWINGTRADELONGCONFIRMED" if trend["execution_tf_trend"] == "Bullish" else "SWINGTRADESHORTCONFIRMED")

    if get_level_proximity(symbol) <= 0.5:
        tags.append("BUYZONEALERT")
        tags.append("SELLZONEALERT")

    if data["iv"] > 1.5:
        tags.append("HIGHIVALERT")
    elif data["iv"] < 0.8:
        tags.append("LOWIVALERT")

    if data["delta"] < 0.3:
        tags.append("LOWDELTAALERT")

    if rvol >= 150:
        tags.append("BREAKOUTRVOLALERT")

    if rvol < 120 and get_candle_body_pct(symbol) > 3:
        tags.append("MEANREVERSIONALERT")

    if not tags:
        return None

    alert_type = " + ".join(tags)
    return generate_alert(symbol, data, trade_type, alert_type, rvol)
