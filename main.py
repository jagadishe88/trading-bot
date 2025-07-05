import asyncio
import json
import sys
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
import logging
from utils import is_market_open, get_market_status, get_secret

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)

# Add some sample symbols for testing - replace with your actual symbols
symbols = ["QQQ", "SPY", "IWM", "PG", "PEP", "AAPL", "MSFT", "NVDA", "TSLA",
           "META", "AMZN", "GOOGL", "NFLX", "LLY", "COIN", "MSTR", "AMD", "AVGO", "ARM",
           "CRWD", "PANW", "CRM", "BA", "COST", "HD", "ADBE", "SNOW", "LULU", "UNH",
           "CAT", "ANF", "DELL", "DE", "MDB", "GLD", "PDD", "ORCL", "TGT", "FDX",
           "AXP", "CMG", "NKE", "BABA", "WMT", "ROKU"]

async def process_symbol(symbol):
    logger.info(f"📡 Running alerts for {symbol}")
    try:
        from alert_engine import generate_alert_improved
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, generate_alert_improved, symbol, "scalp")
        await loop.run_in_executor(executor, generate_alert_improved, symbol, "day")
        await loop.run_in_executor(executor, generate_alert_improved, symbol, "swing")
        logger.info(f"✅ Completed processing {symbol}")
    except Exception as e:
        logger.error(f"❌ Error processing {symbol}: {e}")

async def run_alerts():
    logger.info("🚀 Starting Alert Engine...\n")
    try:
        batch_size = 5
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            await asyncio.gather(*(process_symbol(sym) for sym in batch))
            await asyncio.sleep(0.5)
        logger.info("✅ All alerts completed successfully")
    except Exception as e:
        logger.error(f"❌ Error in run_alerts: {e}")

def run_alerts_background():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_alerts())
        loop.close()
    except Exception as e:
        logger.error(f"❌ Error running alerts: {e}")

@app.route("/")
def index():
    force = request.args.get("force", "false").lower() == "true"
    logger.info(f"📥 Received request: force={force}")

    market_status = get_market_status()
    if not force and not market_status["is_open"]:
        return jsonify({
            "status": "skipped",
            "reason": market_status.get("reason", "Market closed"),
            "market_status": market_status
        }), 200

    threading.Thread(target=run_alerts_background).start()
    return jsonify({
        "status": "started",
        "message": "Alert engine started in background",
        "market_status": market_status,
        "force": force
    }), 200

@app.route("/test-alert")
def test_alert():
    from telegram_alert import send_alert
    test_data = {
        "symbol": "AAPL",
        "price": 211.77,
        "strike": "C $210.00",
        "option_price": 0.90,
        "dte": 2,
        "delta": 0.55,
        "iv": 24.8,
        "rvol": 125,
        "stop_loss": 207.53,
        "take_profit": 216.01,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "alert_type": "TEST-ALERT",
        "trade_type": "Day"
    }
    send_alert(test_data)
    return jsonify({"status": "success", "message": "Test alert sent", "test_data": test_data})

# === ✅ UPDATED SCHWAB OAUTH ROUTES ===

@app.route("/schwab-auth")
def schwab_auth():
    import urllib.parse
    from utils import get_secret

    client_id = get_secret("SCHWAB_CLIENT_ID")
    redirect_uri = "https://postman-echo.com/get"  # Match the registered callback URL
    auth_url = "https://api.schwabapi.com/v1/oauth/authorize"
    
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "readonly"
    }
    full_url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return {
        "auth_url": full_url,
        "instructions": """
        1. Click the auth_url link to authorize
        2. After authorization, you'll be redirected to https://postman-echo.com/get
        3. Look for 'code' parameter in the URL or response
        4. Copy that code value and use it with /schwab-token endpoint
        """
    }

@app.route("/schwab-token")
def schwab_token():
    """Endpoint to exchange authorization code for access token"""
    code = request.args.get("code")
    if not code:
        return {"error": "Missing authorization code. Use /schwab-auth first."}, 400
    
    # Initialize the Schwab API and get token
    from data_feed import SchwabAPI
    api = SchwabAPI()
    if api.get_access_token(code):
        return {
            "status": "success",
            "message": "Schwab API authenticated successfully!",
            "token_saved": True
        }
    else:
        return {
            "status": "error", 
            "message": "Failed to get access token"
        }, 400

@app.route("/schwab-status")
def schwab_status():
    """Check Schwab API authentication status"""
    from data_feed import SchwabAPI
    api = SchwabAPI()
    
    if api.access_token:
        # Test with a sample quote (assuming get_quote is implemented)
        test_quote = {"symbol": "AAPL", "price": "Placeholder"}  # Replace with actual get_quote logic
        return {
            "authenticated": True,
            "token_expires": api.token_expires.isoformat() if api.token_expires else None,
            "test_quote": test_quote,
            "status": "Ready for trading"
        }
    else:
        return {
            "authenticated": False,
            "message": "Not authenticated. Use /schwab-auth to start authentication."
        }

@app.route("/schwab-callback")
def schwab_callback():
    code = request.args.get("code")
    if not code:
        return {"error": "Missing authorization code"}, 400
    return {
        "message": "Authorization code received!",
        "code": code,
        "next_step": f"Use this URL to complete: /schwab-token?code={code}"
    }

# === ✅ END SCHWAB OAUTH ROUTES ===

@app.route("/status")
def status():
    return jsonify({"status": "Bot is live and running."})

if __name__ == "__main__":
    print("🚀 Starting Flask server for local testing...")
    app.run(host="0.0.0.0", port=8080, debug=True)


@app.route("/test-secrets")
def test_secrets():
    secrets = load_all_secrets()
    return jsonify({"secrets": secrets, "validation": validate_secrets()})
