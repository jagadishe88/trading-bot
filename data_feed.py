# Rewriting the updated data_feed.py file to persist after kernel reset
updated_data_feed_path = "data/data_feed_updated.py"  # Changed to local data directory

updated_data_feed = """
import asyncio
import json
import sys
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
import logging
import base64
import requests
from datetime import datetime, timedelta
from utils import is_market_open, get_market_status, get_secret

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=10)

symbols = [
    "QQQ", "SPY", "IWM", "PG", "PEP", "AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "GOOGL",
    "NFLX", "LLY", "COIN", "MSTR", "AMD", "AVGO", "ARM", "CRWD", "PANW", "CRM", "BA", "COST",
    "HD", "ADBE", "SNOW", "LULU", "UNH", "CAT", "ANF", "DELL", "DE", "MDB", "GLD", "PDD",
    "ORCL", "TGT", "FDX", "AXP", "CMG", "NKE", "BABA", "WMT", "ROKU"
]

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

class SchwabAPI:
    def __init__(self):
        self.client_id = get_secret("SCHWAB_CLIENT_ID")
        self.client_secret = get_secret("SCHWAB_CLIENT_SECRET")
        self.redirect_uri = "https://postman-echo.com/get"  # Match the registered callback URL
        self.base_url = "https://api.schwabapi.com"
        self.access_token = None
        self.refresh_token = None
        self.token_expires = None
        self.token_file = "data/schwab_token.json"  # Changed to local data directory
        self.load_token()
    
    def load_token(self):
        try:
            if os.path.exists(self.token_file):
                with open(self.token_file, "r") as f:
                    token_data = json.load(f)
                    self.access_token = token_data.get("access_token")
                    self.refresh_token = token_data.get("refresh_token")
                    self.token_expires = datetime.fromisoformat(token_data.get("token_expires")) if token_data.get("token_expires") else None
                    logger.info("✅ Loaded token from file")
        except Exception as e:
            logger.error(f"❌ Error loading token: {e}")
    
    def save_token(self):
        try:
            token_data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_expires": self.token_expires.isoformat() if self.token_expires else None
            }
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            with open(self.token_file, "w") as f:
                json.dump(token_data, f)
            logger.info("✅ Saved token to file")
        except Exception as e:
            logger.error(f"❌ Error saving token: {e}")

    def get_auth_url(self):
        import urllib.parse
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'readonly'
        }
        query_string = urllib.parse.urlencode(params)
        return f"{self.base_url}/v1/oauth/authorize?{query_string}"
    
    def get_access_token(self, authorization_code):
        token_url = f"{self.base_url}/v1/oauth/token"
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': self.redirect_uri
        }
        try:
            response = requests.post(token_url, headers=headers, data=data)
            logger.info(f"Schwab token response: {response.status_code} - {response.text}")
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data.get('refresh_token')
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires = datetime.now() + timedelta(seconds=expires_in)
                self.save_token()
                logger.info("✅ Schwab API authenticated successfully!")
                return True
            else:
                logger.error(f"❌ Token error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"❌ Error getting access token: {e}")
            return False

@app.route("/schwab-auth")
def schwab_auth():
    api = SchwabAPI()
    return {
        "auth_url": api.get_auth_url(),
        "instructions": """
        1. Click the auth_url link to authorize
        2. After authorization, you'll be redirected to https://postman-echo.com/get
        3. Look for 'code' parameter in the URL or response
        4. Copy that code value and use it with /schwab-token endpoint
        """
    }

@app.route("/schwab-callback")
def schwab_callback():
    code = request.args.get("code")
    if not code:
        return {"error": "Missing authorization code"}, 400
    return {
        "message": "Authorization code received!",
        "code": code
    }

@app.route("/status")
def status():
    return jsonify({"status": "Bot is live and running."})

if __name__ == "__main__":
    print("🚀 Starting Flask server for local testing...")
    app.run(host="0.0.0.0", port=8080)
"""

# Save updated file
with open(updated_data_feed_path, "w") as f:
    f.write(updated_data_feed)

updated_data_feed_path
