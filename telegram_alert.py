import requests
from utils import get_secret

# Load credentials securely
TELEGRAM_BOT_TOKEN = get_secret("telegram_token")
TELEGRAM_CHAT_ID = get_secret("telegram_chat_id")

def send_telegram_alert(alert_data):
    """
    Send a formatted trading alert to Telegram
    """
    try:
        if not alert_data:
            print("❌ No alert data to send")
            return False

        # NEW: Check if it's a simple string (from alert_engine.py)
        if isinstance(alert_data, str):
            message = f"🚨 *TRADING ALERT* 🚨\n\n{alert_data}"
            
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                print(f"✅ Alert sent to Telegram successfully!")
                return True
            else:
                print(f"❌ Failed to send Telegram alert. Status: {response.status_code}")
                print(f"Response: {response.text}")
                return False

        # EXISTING: Handle dictionary format (from other parts of your code)
        # Extract fields from alert data with defaults
        symbol = alert_data.get('symbol', 'N/A')
        alert_type = alert_data.get('alert_type', 'N/A')
        price = alert_data.get('price', 0)
        strike = alert_data.get('strike', 'N/A')
        dte = alert_data.get('dte', 'N/A')
        delta = alert_data.get('delta', 0.0)
        iv = alert_data.get('iv', 0.0)
        option_price = alert_data.get('option_price', 0.0)
        trade_type = alert_data.get('trade_type', 'N/A')
        stop_loss = alert_data.get('stop_loss', 0.0)
        take_profit = alert_data.get('take_profit', 0.0)
        rvol = alert_data.get('rvol', 'N/A')
        timestamp = alert_data.get('timestamp', 'N/A')

        # Format message
        message = f"""🚨 *TRADING ALERT* 🚨

📊 *Symbol:* {symbol}
🎯 *Alert Type:* {alert_type}
💰 *Trade Style:* {trade_type}

📈 *Entry Details:*
• Underlying Price: ${price:.2f}
• Strike: {strike}
• Option Price: ${option_price:.2f}
• DTE: {dte}
• Delta: {delta:.4f}
• IV: {iv:.2f}%

🎯 *Targets:*
• Stop Loss: ${stop_loss:.2f}
• Take Profit: ${take_profit:.2f}
• R-Vol: {rvol}

⏰ *Time:* {timestamp}

#TradingBot #{symbol} #{alert_type.replace(' ', '_')}"""

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }

        response = requests.post(url, json=payload)

        if response.status_code == 200:
            print(f"✅ Alert sent to Telegram successfully!")
            return True
        else:
            print(f"❌ Failed to send Telegram alert. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error sending Telegram alert: {e}")
        return False

def test_telegram_connection():
    """
    Test the Telegram bot connection
    """
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        response = requests.get(url)

        if response.status_code == 200:
            bot_info = response.json()
            print(f"✅ Telegram bot connected: {bot_info['result']['first_name']}")
            return True
        else:
            print(f"❌ Failed to connect to Telegram bot. Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error testing Telegram connection: {e}")
        return False

if __name__ == "__main__":
    test_alert = {
        'symbol': 'AAPL',
        'alert_type': 'AUTO-DAY',
        'price': 211.77,
        'strike': 210,
        'dte': 2,
        'delta': 0.55,
        'iv': 24.8,
        'option_price': 0.9,
        'trade_type': 'Day',
        'stop_loss': 207.53,
        'take_profit': 216.01,
        'rvol': 125,
        'timestamp': '2025-07-02 23:30'
    }
    send_telegram_alert(test_alert)
