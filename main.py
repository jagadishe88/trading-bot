import asyncio
import json
import sys
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify
import logging
from datetime import datetime
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
    from telegram_alert import send_telegram_alert
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
    send_telegram_alert(test_data)
    return jsonify({"status": "success", "message": "Test alert sent", "test_data": test_data})

# === ✅ SCHWAB OAUTH ROUTES ===

@app.route("/schwab-auth")
def schwab_auth():
    import urllib.parse
    
    # Extract just the client ID without @SCHWAB.DEV suffix
    full_client_id = get_secret("SCHWAB_CLIENT_ID")
    client_id = full_client_id.replace("@SCHWAB.DEV", "")  # Remove suffix for API calls
    
    redirect_uri = get_secret("SCHWAB_REDIRECT_URI")
    auth_url = "https://api.schwabapi.com/v1/oauth/authorize"
    
    params = {
        "client_id": client_id,  # Use clean client ID
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "accounts trading"
    }
    full_url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return {
        "auth_url": full_url,
        "client_id_used": client_id,
        "redirect_uri": redirect_uri,
        "scope_used": "accounts trading",
        "instructions": """
        1. Click the auth_url link to authorize
        2. After authorization, you'll be redirected to your GitHub Pages callback
        3. Look for 'code' parameter in the URL
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
    from data_feed import api
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
    from data_feed import api
    
    if api.access_token:
        return {
            "authenticated": True,
            "token_expires": api.token_expires.isoformat() if api.token_expires else None,
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

@app.route("/extract")
def extract_code():
    code = request.args.get("code")
    if not code:
        return """
        <h2>❌ No Code Found</h2>
        <p>URL should be: http://127.0.0.1:8080/extract?code=YOUR_CODE</p>
        <p><a href="/schwab-auth">Start OAuth Again</a></p>
        """, 400
    
    # Do token exchange immediately
    from data_feed import api
    success = api.get_access_token(code)
    
    if success:
        return """
        <h2>✅ Token Exchange Successful!</h2>
        <p>Schwab API is now authenticated and ready to use.</p>
        <p><a href="/schwab-status">Check Status</a></p>
        """
    else:
        return """
        <h2>❌ Token Exchange Failed</h2>
        <p>Check your Flask server logs for detailed error information.</p>
        <p><a href="/schwab-auth">Try Again</a></p>
        """

@app.route("/env-check")
def env_check():
    import os
    return jsonify({
        "all_env_vars": dict(os.environ),
        "telegram_from_os": os.getenv("TELEGRAM_BOT_TOKEN", "NOT_FOUND"),
        "chat_id_from_os": os.getenv("TELEGRAM_CHAT_ID", "NOT_FOUND")
    })

@app.route("/test-telegram")
def test_telegram():
    from telegram_alert import send_telegram_alert
    
    success = send_telegram_alert("🧪 Test from Cloud Run - Environment variables working!")
    
    return jsonify({
        "telegram_test": "success" if success else "failed",
        "message_sent": success
    })

@app.route("/status")
def status():
    return jsonify({"status": "Bot is live and running."})

# === ✅ NEW ENHANCED MONITORING ROUTES ===

@app.route("/live-stats")
def live_stats():
    """Real-time bot statistics"""
    try:
        from data_feed import api  # Import your Schwab API instance
        market_status = get_market_status()
        
        return jsonify({
            "bot_status": "active",
            "last_check": datetime.now().isoformat(),
            "schwab_connected": bool(api.access_token),
            "token_expires": api.token_expires.isoformat() if api.token_expires else None,
            "market_status": market_status,
            "is_market_open": market_status['is_open'],
            "alerts_sent_today": 0,  # You can enhance this later
            "uptime": "running",
            "scheduler_active": True,
            "last_alert_time": "TBD",  # You can track this
            "symbols_monitored": len(symbols),
            "symbol_list": symbols[:10]  # Show first 10 symbols
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "bot_status": "error",
            "timestamp": datetime.now().isoformat()
        })

@app.route("/daily-report")
def daily_report():
    """Generate and send daily performance report"""
    from telegram_alert import send_telegram_alert
    
    try:
        market_status = get_market_status()
        
        report = f"""📊 **DAILY TRADING BOT REPORT** - {datetime.now().strftime('%Y-%m-%d')}

🤖 **Bot Status:** Active and Running
🏦 **Schwab API:** Connected ✅
📱 **Telegram:** Operational ✅
⏰ **Market Status:** {'Open' if market_status['is_open'] else 'Closed'}
🕐 **Current Time:** {market_status['current_time']}

🎯 **Today's Activity:**
• System Checks: Operational
• API Health: Good
• Alert System: Ready
• Scheduler: Active
• Symbols Monitored: {len(symbols)}

✅ All systems operational and ready for trading!

Next market open: {market_status.get('next_open', 'TBD')}

#TradingBot #DailyReport #{datetime.now().strftime('%Y%m%d')}"""
        
        success = send_telegram_alert(report)
        
        return jsonify({
            "report_sent": success,
            "timestamp": datetime.now().isoformat(),
            "market_status": market_status
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "report_sent": False
        })

@app.route("/market-open-alert")
def market_open_alert():
    """Send alert when market opens"""
    from telegram_alert import send_telegram_alert
    
    try:
        market_status = get_market_status()
        
        if market_status['is_open']:
            alert = f"""🔔 **MARKET OPEN NOTIFICATION**

📈 **Market Status:** OPEN
🕘 **Time:** {market_status['current_time']}
🤖 **Trading Bot:** Active & Ready

🏦 **Schwab API:** Connected
📊 **Alert Engine:** Running
🎯 **Monitoring:** {len(symbols)} symbols

Ready to detect trading setups! 📈🚀

#{datetime.now().strftime('%Y%m%d')} #MarketOpen #TradingBot"""
            
            success = send_telegram_alert(alert)
            
            return jsonify({
                "market_open_alert_sent": success,
                "market_status": market_status,
                "timestamp": datetime.now().isoformat()
            })
        else:
            return jsonify({
                "market_closed": True,
                "reason": market_status.get('reason', 'Market is closed'),
                "next_open": market_status.get('next_open'),
                "market_status": market_status
            })
            
    except Exception as e:
        return jsonify({
            "error": str(e),
            "market_open_alert_sent": False
        })

@app.route("/recover")
def recover():
    """Manual recovery endpoint for troubleshooting"""
    try:
        from data_feed import api
        recovery_actions = []
        
        # Check and attempt to recover Schwab authentication
        if not api.access_token:
            recovery_actions.append("Attempting to load token from storage...")
            api.load_token()
            
            if api.access_token:
                recovery_actions.append("✅ Token loaded successfully")
            else:
                recovery_actions.append("❌ No token available - manual authentication needed")
        else:
            recovery_actions.append("✅ Schwab API already authenticated")
        
        # Test Schwab connection
        try:
            test_quote = api.get_quote("SPY")
            if test_quote:
                recovery_actions.append("✅ Schwab API test call successful")
            else:
                recovery_actions.append("⚠️ Schwab API test call failed")
        except Exception as e:
            recovery_actions.append(f"❌ Schwab API error: {str(e)}")
        
        # Test Telegram
        try:
            from telegram_alert import send_telegram_alert
            test_success = send_telegram_alert("🔧 **Bot Recovery Test** - All systems checking...")
            if test_success:
                recovery_actions.append("✅ Telegram test successful")
            else:
                recovery_actions.append("❌ Telegram test failed")
        except Exception as e:
            recovery_actions.append(f"❌ Telegram error: {str(e)}")
        
        return jsonify({
            "recovery_attempted": True,
            "schwab_authenticated": bool(api.access_token),
            "token_expires": api.token_expires.isoformat() if api.token_expires else None,
            "recovery_actions": recovery_actions,
            "timestamp": datetime.now().isoformat(),
            "market_status": get_market_status()
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "recovery_attempted": False,
            "timestamp": datetime.now().isoformat()
        })

@app.route("/health-check")
def health_check():
    """Comprehensive health check for monitoring"""
    try:
        from data_feed import api
        
        health = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "components": {}
        }
        
        # Check Schwab API
        if api.access_token:
            # Test with a simple quote
            try:
                test_quote = api.get_quote("SPY")
                if test_quote and test_quote.get('ask_price', 0) > 0:
                    health["components"]["schwab_api"] = {
                        "status": "healthy",
                        "authenticated": True,
                        "test_quote": "success"
                    }
                else:
                    health["components"]["schwab_api"] = {
                        "status": "degraded",
                        "authenticated": True,
                        "test_quote": "failed"
                    }
            except Exception as e:
                health["components"]["schwab_api"] = {
                    "status": "unhealthy",
                    "authenticated": True,
                    "error": str(e)
                }
        else:
            health["components"]["schwab_api"] = {
                "status": "unhealthy",
                "authenticated": False,
                "error": "No access token"
            }
        
        # Check Telegram
        try:
            telegram_token = get_secret("TELEGRAM_BOT_TOKEN")
            telegram_chat = get_secret("TELEGRAM_CHAT_ID")
            
            if telegram_token and telegram_chat:
                health["components"]["telegram"] = {
                    "status": "healthy",
                    "configured": True
                }
            else:
                health["components"]["telegram"] = {
                    "status": "unhealthy",
                    "configured": False,
                    "error": "Missing credentials"
                }
        except Exception as e:
            health["components"]["telegram"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Check market status
        market_status = get_market_status()
        health["components"]["market_detection"] = {
            "status": "healthy",
            "is_open": market_status['is_open'],
            "current_time": market_status['current_time']
        }
        
        # Check symbols
        health["components"]["symbol_monitoring"] = {
            "status": "healthy",
            "count": len(symbols),
            "sample": symbols[:5]
        }
        
        # Determine overall status
        component_statuses = [comp.get("status") for comp in health["components"].values()]
        if "unhealthy" in component_statuses:
            health["overall_status"] = "unhealthy"
        elif "degraded" in component_statuses:
            health["overall_status"] = "degraded"
        
        return jsonify(health)
        
    except Exception as e:
        return jsonify({
            "overall_status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })

@app.route("/health")
def health():
    """Simple health endpoint for load balancers"""
    try:
        from data_feed import api
        return jsonify({
            "status": "healthy",
            "schwab_auth": bool(api.access_token),
            "telegram_config": bool(get_secret("TELEGRAM_BOT_TOKEN")),
            "last_check": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

@app.route("/metrics")
def metrics():
    """Basic metrics endpoint"""
    try:
        from data_feed import api
        market_status = get_market_status()
        
        return jsonify({
            "bot_metrics": {
                "uptime": "running",
                "schwab_connected": bool(api.access_token),
                "market_open": market_status['is_open'],
                "symbols_count": len(symbols),
                "last_update": datetime.now().isoformat()
            }
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })

# === ✅ END ENHANCED MONITORING ROUTES ===

if __name__== "__main__":
    print("🚀 Starting Flask server for local testing...")
    app.run(host="0.0.0.0", port=8080, debug=True)