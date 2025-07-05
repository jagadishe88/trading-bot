from strategy_logic import evaluate_bullish_bos_alert

mock_data = {
    "symbol": "AAPL",
    "price": 185.45,
    "dte": 1,
    "option_type": "CALL",
    "strike": 185,
    "delta": 0.33,
    "iv": 1.8,
    "option_price": 2.15,
    "timestamp": "2025-06-26 15:00:00"
}

alert = evaluate_bullish_bos_alert(mock_data)

if alert:
    print("✅ Alert Triggered:")
    for key, value in alert.items():
        print(f"{key}: {value}")
else:
    print("❌ No alert - Conditions not met.")

