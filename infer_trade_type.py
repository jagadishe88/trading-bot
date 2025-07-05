from alert_engine import should_trigger_alert
from telegram_alert import send_telegram_alert

# === Inline replacements for trade_plan module ===

def infer_trade_type(symbol, dte):
    if symbol in ["SPX", "QQQ", "NDX", "SPY"]:
        return "scalp" if dte == 0 else "day"
    elif dte <= 2:
        return "day"
    elif dte >= 7:
        return "swing"
    else:
        return "day"

def generate_trade_plan(entry, stop, style):
    rr = 1.5 if style == "scalp" else 2 if style == "day" else 3
    risk = entry - stop
    tp1 = entry + risk * rr
    return {"entry": entry, "stop": stop, "tp1": round(tp1, 1), "rr": rr}

# === Simulated live values for test ===
symbol = "SPX"
dte = 0
trend = "up"
rvol = 150
candle_body_pct = 2.6
level_proximity = 0.3
mtf_trend = "bullish"
pivot_success = 75
delta = 0.4
iv = 1.2

style = infer_trade_type(symbol, dte)
trade = generate_trade_plan(entry=5953, stop=5943, style=style)

result = should_trigger_alert(
    symbol=symbol,
    dte=dte,
    style=style,
    trend=trend,
    rvol=rvol,
    candle_body_pct=candle_body_pct,
    level_proximity=level_proximity,
    mtf_trend=mtf_trend,
    pivot_success=pivot_success,
    delta=delta,
    iv=iv,
    entry=trade["entry"],
    stop=trade["stop"],
    tp=trade["tp1"],
    bos_long=True,
    bos_short=False
)

if result:
    print(result["message"])
    # send_telegram_alert(result["message"])
else:
    print("❌ No valid alert.")

