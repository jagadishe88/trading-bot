import json
import os
from typing import Optional
import datetime
import pytz
from datetime import date, time as dt_time
import logging

# Configure logging
logger = logging.getLogger(__name__)

def get_secret(key: str) -> Optional[str]:
    """
    Get secret from environment variables or secrets.json file
    Priority: Environment variables > secrets.json > None
    """
    try:
        # First, try to get from environment variables (preferred for production)
        env_value = os.getenv(key)
        if env_value:
            logger.info(f"Retrieved secret '{key}' from environment variables")
            return env_value
        
        # Fallback to secrets.json file
        # Use absolute path relative to the project root (trading-bot directory)
        secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'secrets.json')
        if os.path.exists(secrets_path):
            with open(secrets_path, 'r') as f:
                secrets = json.load(f)
                value = secrets.get(key)
                if value:
                    logger.info(f"Retrieved secret '{key}' from secrets.json")
                    return value
                else:
                    logger.warning(f"Secret '{key}' not found in secrets.json")
                    return None
        else:
            logger.warning(f"secrets.json not found at {secrets_path}")
            return None
        
    except Exception as e:
        logger.error(f"Error loading secret '{key}': {e}")
        return None

def load_all_secrets() -> dict:
    """
    Load all secrets from available sources
    """
    secrets = {}
    
    # Try to load from secrets.json
    secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'secrets.json')
    if os.path.exists(secrets_path):
        try:
            with open(secrets_path, 'r') as f:
                file_secrets = json.load(f)
                secrets.update(file_secrets)
                logger.info("Loaded secrets from secrets.json")
        except Exception as e:
            logger.error(f"Error loading secrets.json: {e}")
    
    # Override with environment variables
    env_keys = [
        'APCA_API_KEY_ID',
        'APCA_API_SECRET_KEY', 
        'telegram_token',
        'telegram_chat_id',
        'SCHWAB_CLIENT_ID',
        'SCHWAB_CLIENT_SECRET'
    ]
    
    for key in env_keys:
        env_value = os.getenv(key)
        if env_value:
            secrets[key] = env_value
            logger.info(f"Overridden secret '{key}' with environment variable")
    
    return secrets

def validate_secrets() -> bool:
    """
    Validate that all required secrets are available
    """
    required_secrets = [
        'APCA_API_KEY_ID',
        'APCA_API_SECRET_KEY',
        'telegram_token',
        'telegram_chat_id',
        'SCHWAB_CLIENT_ID',
        'SCHWAB_CLIENT_SECRET'
    ]
    
    missing = []
    for secret in required_secrets:
        if not get_secret(secret):
            missing.append(secret)
    
    if missing:
        logger.error(f"Missing required secrets: {', '.join(missing)}")
        return False
    
    logger.info("✅ All required secrets are available")
    return True

def get_market_holidays_2025():
    """
    Get US stock market holidays for 2025
    """
    return [
        date(2025, 1, 1),   # New Year's Day
        date(2025, 1, 20),  # Martin Luther King Jr. Day
        date(2025, 2, 17),  # Presidents' Day
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 26),  # Memorial Day
        date(2025, 6, 19),  # Juneteenth
        date(2025, 7, 4),   # Independence Day
        date(2025, 9, 1),   # Labor Day
        date(2025, 11, 27), # Thanksgiving
        date(2025, 12, 25), # Christmas
    ]

def get_early_close_dates_2025():
    """
    Get dates when market closes early (1:00 PM ET) for 2025
    """
    return [
        date(2025, 7, 3),   # Day before Independence Day
        date(2025, 11, 28), # Day after Thanksgiving (Black Friday)
        date(2025, 12, 24), # Christmas Eve
    ]

def is_market_open(current_time: Optional[datetime.datetime] = None) -> bool:
    """
    Enhanced market open check that handles holidays, weekends, and early closures
    Returns True if market is open, False otherwise
    """
    if current_time is None:
        # Get current time in Eastern Time
        et_tz = pytz.timezone('America/New_York')
        current_time = datetime.datetime.now(et_tz)
    
    # Convert to Eastern Time if not already
    if current_time.tzinfo is None:
        et_tz = pytz.timezone('America/New_York')
        current_time = et_tz.localize(current_time)
    elif current_time.tzinfo != pytz.timezone('America/New_York'):
        et_tz = pytz.timezone('America/New_York')
        current_time = current_time.astimezone(et_tz)
    
    current_date = current_time.date()
    current_time_only = current_time.time()
    
    # Check if it's a weekend
    if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Check if it's a holiday
    if current_date in get_market_holidays_2025():
        return False
    
    # Define market hours
    market_open = dt_time(9, 30)  # 9:30 AM
    market_close = dt_time(16, 0)  # 4:00 PM
    early_close = dt_time(13, 0)   # 1:00 PM for early close days
    
    # Check if it's an early close day
    if current_date in get_early_close_dates_2025():
        return market_open <= current_time_only < early_close
    
    # Normal trading hours
    return market_open <= current_time_only < market_close

def get_next_market_open() -> datetime.datetime:
    """
    Get the next market open datetime
    """
    et_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(et_tz)
    
    # Start checking from tomorrow if market is closed today
    check_date = now.date()
    if is_market_open(now):
        # If market is currently open, next open is tomorrow
        check_date = now.date() + datetime.timedelta(days=1)
    
    # Find next market open day
    while True:
        # Create datetime for 9:30 AM on check_date
        market_open_time = datetime.datetime.combine(check_date, dt_time(9, 30))
        market_open_time = et_tz.localize(market_open_time)
        
        # Check if this is a valid market day
        if (check_date.weekday() < 5 and  # Not weekend
            check_date not in get_market_holidays_2025()):  # Not holiday
            return market_open_time
        
        # Check next day
        check_date += datetime.timedelta(days=1)

def get_market_status() -> dict:
    """
    Get detailed market status information
    """
    et_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(et_tz)
    today = now.date()
    
    status = {
        "is_open": is_market_open(now),
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "next_open": get_next_market_open().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "is_weekend": now.weekday() >= 5,
        "is_holiday": today in get_market_holidays_2025(),
        "is_early_close": today in get_early_close_dates_2025(),
    }
    
    # Add reason if market is closed
    if not status["is_open"]:
        if status["is_weekend"]:
            status["reason"] = "Weekend"
        elif status["is_holiday"]:
            status["reason"] = "Holiday"
        elif status["is_early_close"] and now.time() >= dt_time(13, 0):
            status["reason"] = "Early close day (market closed at 1:00 PM)"
        elif now.time() < dt_time(9, 30):
            status["reason"] = "Before market hours (opens at 9:30 AM)"
        elif now.time() >= dt_time(16, 0):
            status["reason"] = "After market hours (closed at 4:00 PM)"
        else:
            status["reason"] = "Market closed"
    
    return status
