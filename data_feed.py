# Updated data_feed.py - Replace your existing file with this
import requests
import json
import base64
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import urllib.parse
import os
import logging
from utils import get_secret

# Add Google Secret Manager imports
try:
    from google.cloud import secretmanager
    SECRET_MANAGER_AVAILABLE = True
except ImportError:
    SECRET_MANAGER_AVAILABLE = False
    print("⚠️ Google Cloud Secret Manager not available - using file fallback")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CloudSecretManager:
    def __init__(self):
        self.project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'tradingbotproject-464317')
        self.enabled = False
        
        if SECRET_MANAGER_AVAILABLE:
            try:
                self.client = secretmanager.SecretManagerServiceClient()
                self.enabled = True
                logger.info("✅ Google Secret Manager initialized")
            except Exception as e:
                logger.warning(f"⚠️ Secret Manager not available: {e}")
                self.enabled = False
        else:
            logger.info("📦 Secret Manager library not installed, using file fallback")
    
    def save_schwab_token(self, token_data):
        """Save Schwab token to Secret Manager or file"""
        if not self.enabled:
            return self._save_to_file(token_data)
        
        try:
            secret_name = f"projects/{self.project_id}/secrets/schwab-token"
            
            # Check if secret exists, create if not
            try:
                self.client.get_secret(name=secret_name)
                logger.info("📝 Using existing schwab-token secret")
            except Exception:
                # Create the secret
                try:
                    parent = f"projects/{self.project_id}"
                    self.client.create_secret(
                        parent=parent, 
                        secret_id="schwab-token", 
                        secret={}
                    )
                    logger.info("🆕 Created new schwab-token secret")
                except Exception as create_error:
                    logger.error(f"❌ Could not create secret: {create_error}")
                    return self._save_to_file(token_data)
            
            # Add new version
            payload = json.dumps(token_data).encode('utf-8')
            response = self.client.add_secret_version(
                parent=secret_name,
                payload={'data': payload}
            )
            
            logger.info(f"✅ Schwab token saved to Secret Manager")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error saving token to Secret Manager: {e}")
            return self._save_to_file(token_data)
    
    def load_schwab_token(self):
        """Load Schwab token from Secret Manager or file"""
        if not self.enabled:
            return self._load_from_file()
        
        try:
            secret_name = f"projects/{self.project_id}/secrets/schwab-token/versions/latest"
            
            response = self.client.access_secret_version(name=secret_name)
            secret_data = response.payload.data.decode('utf-8')
            token_data = json.loads(secret_data)
            
            logger.info("✅ Schwab token loaded from Secret Manager")
            return token_data
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load from Secret Manager: {e}")
            return self._load_from_file()
    
    def _save_to_file(self, token_data):
        """Fallback: save to local file"""
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/schwab_token.json", 'w') as f:
                json.dump(token_data, f)
            logger.info("📁 Token saved to local file")
            return True
        except Exception as e:
            logger.error(f"❌ Error saving to file: {e}")
            return False
    
    def _load_from_file(self):
        """Fallback: load from local file"""
        try:
            if os.path.exists("data/schwab_token.json"):
                with open("data/schwab_token.json", 'r') as f:
                    token_data = json.load(f)
                logger.info("📁 Token loaded from local file")
                return token_data
        except Exception as e:
            logger.error(f"❌ Error loading from file: {e}")
        return None

# Updated SchwabAPI class (replace your existing one)
class SchwabAPI:
    def __init__(self):
        # Extract just the client ID without @SCHWAB.DEV suffix
        full_client_id = get_secret("SCHWAB_CLIENT_ID")
        self.client_id = full_client_id.replace("@SCHWAB.DEV", "") if full_client_id else None
        self.client_secret = get_secret("SCHWAB_CLIENT_SECRET")
        self.redirect_uri = get_secret("SCHWAB_REDIRECT_URI")
        self.base_url = "https://api.schwabapi.com"
        self.access_token = None
        self.refresh_token = None
        self.token_expires = None
        
        # Initialize Secret Manager
        self.secret_manager = CloudSecretManager()
        
        logger.info(f"🔧 Initialized SchwabAPI with client_id: {self.client_id}")
        logger.info(f"🔧 Redirect URI: {self.redirect_uri}")
        
        # Try to load existing token
        self.load_token()
    
    def save_token(self):
        """Save token using Secret Manager"""
        try:
            token_data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires': self.token_expires.isoformat() if self.token_expires else None,
                'saved_at': datetime.now().isoformat()
            }
            
            success = self.secret_manager.save_schwab_token(token_data)
            if success:
                logger.info("✅ Token saved successfully")
            return success
        except Exception as e:
            logger.error(f"❌ Error saving token: {e}")
            return False
    
    def load_token(self):
        """Load existing token using Secret Manager"""
        try:
            token_data = self.secret_manager.load_schwab_token()
            
            if not token_data:
                logger.info("ℹ️ No existing token found - will need to authenticate")
                return
            
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')
            
            expires_str = token_data.get('expires')
            if expires_str:
                self.token_expires = datetime.fromisoformat(expires_str)
                
                # Check if token is expired
                if datetime.now() >= self.token_expires:
                    logger.warning("⚠️ Token expired, will need to refresh")
                    self.access_token = None
                else:
                    logger.info("✅ Loaded existing valid token")
                    
        except Exception as e:
            logger.error(f"❌ Error loading token: {e}")
    
    def get_auth_url(self):
        """Get authorization URL for initial setup"""
        params = {
            'client_id': self.client_id,  # Use clean client ID
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'accounts trading'
        }
        
        query_string = urllib.parse.urlencode(params)
        auth_url = f"{self.base_url}/v1/oauth/authorize?{query_string}"
        
        return auth_url
    
    def get_access_token(self, authorization_code):
        """Exchange authorization code for access token"""
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
            logger.info("🔄 Requesting access token...")
            logger.info(f"📍 Token URL: {token_url}")
            logger.info(f"🔑 Using client_id: {self.client_id}")
            logger.info(f"🔗 Using redirect_uri: {self.redirect_uri}")
            logger.info(f"📝 Authorization code: {authorization_code[:30]}...")
            
            response = requests.post(token_url, headers=headers, data=data, timeout=30)
            
            logger.info(f"📊 Token response status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data.get('refresh_token')
                
                # Calculate expiration
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires = datetime.now() + timedelta(seconds=expires_in)
                
                self.save_token()
                logger.info("✅ Schwab API authenticated successfully!")
                return True
            else:
                logger.error(f"❌ Token error: {response.status_code}")
                logger.error(f"❌ Error response: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception during token exchange: {e}")
            return False
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            logger.error("❌ No refresh token available")
            return False
            
        token_url = f"{self.base_url}/v1/oauth/token"
        
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        
        try:
            logger.info("🔄 Refreshing access token...")
            response = requests.post(token_url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires = datetime.now() + timedelta(seconds=expires_in)
                
                self.save_token()
                logger.info("✅ Token refreshed successfully!")
                return True
            else:
                logger.error(f"❌ Refresh error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error refreshing token: {e}")
            return False
    
    def ensure_authenticated(self):
        """Ensure we have a valid access token"""
        if not self.access_token:
            logger.error("❌ No access token available")
            return False
        
        # Check if token is about to expire (refresh 5 minutes early)
        if self.token_expires and datetime.now() >= (self.token_expires - timedelta(minutes=5)):
            logger.warning("⚠️ Token expiring soon, refreshing...")
            return self.refresh_access_token()
        
        return True
    
    def get_quote(self, symbol):
        """Get real-time quote"""
        if not self.ensure_authenticated():
            logger.error(f"❌ Authentication failed for {symbol}")
            return None
        
        endpoint = f"{self.base_url}/marketdata/v1/{symbol}/quotes"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if symbol in data:
                    quote = data[symbol]
                    return {
                        'ask_price': quote.get('askPrice', quote.get('lastPrice', 0)),
                        'bid_price': quote.get('bidPrice', quote.get('lastPrice', 0)),
                        'last_price': quote.get('lastPrice', 0),
                        'volume': quote.get('totalVolume', 0),
                        'source': 'schwab_api'
                    }
            elif response.status_code == 401:
                logger.error("❌ Authentication expired, need to re-authenticate")
                self.access_token = None
            else:
                logger.error(f"❌ Quote error for {symbol}: {response.status_code}")
                
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting quote for {symbol}: {e}")
            return None
    
    # Keep all your existing methods for price history, etc.
    def get_price_history(self, symbol, period_type="day", period=5, 
                         frequency_type="minute", frequency=5, need_extended=False):
        """Get price history with custom timeframes"""
        if not self.ensure_authenticated():
            return pd.DataFrame()
        
        endpoint = f"{self.base_url}/marketdata/v1/{symbol}/pricehistory"
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
        
        params = {
            'periodType': period_type,
            'period': period,
            'frequencyType': frequency_type,
            'frequency': frequency,
            'needExtendedHoursData': str(need_extended).lower()
        }
        
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if 'candles' in data and data['candles']:
                    return self.format_price_data(data['candles'])
            elif response.status_code == 401:
                logger.error("❌ Authentication expired, need to re-authenticate")
                self.access_token = None
            else:
                logger.error(f"❌ Price history error for {symbol}: {response.status_code}")
                
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"❌ Error getting price history for {symbol}: {e}")
            return pd.DataFrame()
    
    def format_price_data(self, candles):
        """Format Schwab price data to pandas DataFrame"""
        data = []
        
        for candle in candles:
            data.append({
                'datetime': datetime.fromtimestamp(candle['datetime']/1000),
                'o': candle['open'],
                'h': candle['high'],
                'l': candle['low'],
                'c': candle['close'],
                'volume': candle['volume']
            })
        
        df = pd.DataFrame(data)
        if not df.empty:
            df.set_index('datetime', inplace=True)
        
        return df

# Global Schwab API instance
api = SchwabAPI()

# Keep all your existing interface functions exactly the same
def fetch_option_chain(symbol):
    """Get current stock price (replaces option chain for now)"""
    try:
        quote = api.get_quote(symbol)
        
        if quote and quote['ask_price'] > 0:
            return {
                'ask_price': quote['ask_price'],
                'bid_price': quote['bid_price'],
                'last_price': quote['last_price'],
                'volume': quote['volume'],
                'iv': 0.5,  # Placeholder until we add options data
                'delta': 0.4,  # Placeholder
                'source': quote.get('source', 'unknown')
            }
        else:
            # Fallback to price history if quote fails
            df = api.get_price_history(symbol, period_type="day", period=1, 
                                     frequency_type="minute", frequency=5)
            
            if not df.empty:
                price = df['c'].iloc[-1]
                return {
                    'ask_price': price,
                    'bid_price': price * 0.999,
                    'last_price': price,
                    'volume': df['volume'].iloc[-1],
                    'iv': 0.5,
                    'delta': 0.4,
                    'source': 'schwab_history'
                }
            
            # Final fallback with updated prices
            fallback_prices = {
                'AAPL': 213.55, 'QQQ': 556.22, 'SPY': 625.34, 'MSFT': 498.84,
                'NVDA': 159.34, 'TSLA': 315.35, 'META': 719.01, 'AMZN': 3500.0,
                'GOOGL': 2850.0, 'NFLX': 680.0
            }
            
            price = fallback_prices.get(symbol, 500.0)
            return {
                'ask_price': price,
                'bid_price': price * 0.999,
                'last_price': price,
                'volume': 1000000,
                'iv': 0.5,
                'delta': 0.4,
                'source': 'fallback'
            }
            
    except Exception as e:
        logger.error(f"❌ Error fetching data for {symbol}: {e}")
        return {'ask_price': 500.0, 'bid_price': 499.0, 'last_price': 500.0, 'volume': 1000000, 'iv': 0.5, 'delta': 0.4, 'source': 'error_fallback'}

# Keep all other existing functions unchanged
def get_moving_averages(symbol, periods, timeframe_minutes=5):
    """Calculate moving averages using Schwab data"""
    try:
        # Map timeframe to Schwab frequency
        if timeframe_minutes not in [1, 5, 10, 15, 30]:
            timeframe_minutes = 5  # Default to 5min
        
        # Get enough data for largest MA period
        days_needed = max(max(periods) // 100, 5)  # At least 5 days
        
        df = api.get_price_history(
            symbol, 
            period_type="day",
            period=days_needed,
            frequency_type="minute", 
            frequency=timeframe_minutes
        )
        
        if df.empty:
            logger.warning(f"⚠️ No MA data for {symbol}, using fallback")
            current_price = fetch_option_chain(symbol)['ask_price']
            return {p: current_price * (1 - 0.01 * (p / 200)) for p in periods}
        
        # Calculate moving averages
        ma_dict = {}
        for period in periods:
            if len(df) >= period:
                ma_dict[period] = df['c'].rolling(window=period).mean().iloc[-1]
            else:
                # Not enough data, use available data average
                ma_dict[period] = df['c'].mean()
        
        return ma_dict
        
    except Exception as e:
        logger.error(f"❌ Error calculating MAs for {symbol}: {e}")
        current_price = fetch_option_chain(symbol)['ask_price']
        return {p: current_price * (1 - 0.01 * (p / 200)) for p in periods}

# Keep all other existing functions exactly as they are...
def get_trend_data(symbol):
    """Get trend data using moving averages"""
    ma_data = get_moving_averages(symbol, [9, 21, 34, 50, 200])
    
    mtf_clouds = {
        '1H': 'Bullish',
        '4H': 'Bullish', 
        'Daily': 'Neutral'
    }
    
    trends = {
        '9_21': 'Bullish' if ma_data[9] > ma_data[21] else 'Bearish' if ma_data[9] < ma_data[21] else 'Neutral',
        '34_50': 'Bullish' if ma_data[34] > ma_data[50] else 'Bearish' if ma_data[34] < ma_data[50] else 'Neutral',
        'price_action': 'Bullish',
        'mtf_clouds': mtf_clouds
    }
    
    return trends

def calculate_rvol(symbol, lookback=20):
    """Calculate relative volume using Schwab data"""
    try:
        # Get daily data for RVOL calculation
        df = api.get_price_history(
            symbol,
            period_type="day",
            period=lookback + 5,  # Extra days for calculation
            frequency_type="daily",
            frequency=1
        )
        
        if df.empty or len(df) < 2:
            logger.warning(f"⚠️ Insufficient data for RVOL calculation: {symbol}")
            return 1.5  # Return 150% as reasonable default
        
        # Calculate RVOL
        volumes = df['volume']
        current_volume = volumes.iloc[-1]
        avg_volume = volumes.iloc[:-1].mean()  # Exclude current day from average
        
        if avg_volume > 0:
            rvol = current_volume / avg_volume
            return min(rvol, 5.0)  # Cap at 500% for sanity
        else:
            return 1.5
            
    except Exception as e:
        logger.error(f"❌ Error calculating RVOL for {symbol}: {e}")
        return 1.5

def get_pivots(symbol):
    """Calculate pivot points using Schwab data"""
    try:
        df = api.get_price_history(
            symbol,
            period_type="day", 
            period=10,
            frequency_type="daily",
            frequency=1
        )
        
        if df.empty or len(df) < 3:
            current_price = fetch_option_chain(symbol)['ask_price']
            return {
                's1': current_price - 2.5, 'r1': current_price + 2.5,
                'pdl': current_price - 3.5, 'pdh': current_price + 3.5,
                'pml': current_price - 4.5, 'pmh': current_price + 4.5
            }
        
        # Calculate pivot points
        high = df['h'].iloc[-1]
        low = df['l'].iloc[-1] 
        close = df['c'].iloc[-1]
        
        pivot = (high + low + close) / 3
        s1 = (2 * pivot) - high
        r1 = (2 * pivot) - low
        
        # Previous day levels
        pdl = df['l'].iloc[-2]
        pdh = df['h'].iloc[-2]
        
        # Previous month levels (approximate with 5-day min/max)
        pml = df['l'].rolling(window=min(5, len(df))).min().iloc[-1]
        pmh = df['h'].rolling(window=min(5, len(df))).max().iloc[-1]
        
        return {'s1': s1, 'r1': r1, 'pdl': pdl, 'pdh': pdh, 'pml': pml, 'pmh': pmh}
        
    except Exception as e:
        logger.error(f"❌ Error calculating pivots for {symbol}: {e}")
        current_price = fetch_option_chain(symbol)['ask_price']
        return {
            's1': current_price - 2.5, 'r1': current_price + 2.5,
            'pdl': current_price - 3.5, 'pdh': current_price + 3.5,
            'pml': current_price - 4.5, 'pmh': current_price + 4.5
        }

# Keep all other existing functions unchanged...
def get_5day_zone(symbol):
    """Get 5-day high/low zone"""
    try:
        df = api.get_price_history(
            symbol,
            period_type="day",
            period=10,
            frequency_type="daily", 
            frequency=1
        )
        
        if df.empty:
            current_price = fetch_option_chain(symbol)['ask_price']
            return current_price - 3.5, current_price + 3.5
        
        zone_low = df['l'].min()
        zone_high = df['h'].max()
        
        return zone_low, zone_high
        
    except Exception as e:
        logger.error(f"❌ Error calculating 5-day zone for {symbol}: {e}")
        current_price = fetch_option_chain(symbol)['ask_price']
        return current_price - 3.5, current_price + 3.5

def get_atr(symbol, period=14):
    """Calculate Average True Range"""
    try:
        df = api.get_price_history(
            symbol,
            period_type="day",
            period=30,
            frequency_type="daily",
            frequency=1
        )
        
        if df.empty or len(df) < period:
            return 2.0  # Default ATR
        
        high = df['h']
        low = df['l']
        close = df['c']
        
        high_low = high - low
        high_close = np.abs(high - close.shift())
        low_close = np.abs(low - close.shift())
        
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        return atr if not pd.isna(atr) else 2.0
        
    except Exception as e:
        logger.error(f"❌ Error calculating ATR for {symbol}: {e}")
        return 2.0

def get_fib_levels(symbol):
    """Calculate Fibonacci retracement levels"""
    try:
        df = api.get_price_history(
            symbol,
            period_type="day",
            period=40,
            frequency_type="daily",
            frequency=1
        )
        
        if df.empty:
            current_price = fetch_option_chain(symbol)['ask_price']
            return [current_price - 2.5, current_price - 1.5, current_price + 0.5]
        
        high = df['h'].max()
        low = df['l'].min()
        range_ = high - low
        
        return [
            low + range_ * 0.236,
            low + range_ * 0.382,
            low + range_ * 0.5
        ]
        
    except Exception as e:
        logger.error(f"❌ Error calculating Fib levels for {symbol}: {e}")
        current_price = fetch_option_chain(symbol)['ask_price']
        return [current_price - 2.5, current_price - 1.5, current_price + 0.5]

def check_tf_alignment(symbol, timeframes):
    """Check timeframe alignment"""
    try:
        alignments = {}
        
        for tf in timeframes:
            # Convert to minutes if needed
            tf_minutes = tf if isinstance(tf, int) else 5
            
            df = api.get_price_history(
                symbol,
                period_type="day",
                period=5,
                frequency_type="minute",
                frequency=tf_minutes
            )
            
            if df.empty or len(df) < 21:
                alignments[f'{tf}Min'] = True  # Default to aligned
                continue
            
            close = df['c']
            ma9 = close.rolling(window=9).mean().iloc[-1]
            ma21 = close.rolling(window=21).mean().iloc[-1]
            
            alignments[f'{tf}Min'] = ma9 > ma21
        
        return all(alignments.values())
        
    except Exception as e:
        logger.error(f"❌ Error checking TF alignment for {symbol}: {e}")
        return True

def check_sector_correlation(symbol):
    """Check sector correlation"""
    try:
        # Simplified sector correlation check
        sector_symbols = {"XLK": ["AAPL", "MSFT", "NVDA"], "XLF": ["JPM", "BAC"]}
        
        for sector, stocks in sector_symbols.items():
            if symbol in stocks:
                return True
        
        return True  # Default to correlated
        
    except Exception as e:
        logger.error(f"❌ Error checking sector correlation for {symbol}: {e}")
        return True

def get_last_high(symbol):
    """Get last high price"""
    try:
        df = api.get_price_history(symbol, period_type="day", period=5, 
                                 frequency_type="daily", frequency=1)
        
        if df.empty or len(df) < 2:
            current_price = fetch_option_chain(symbol)['ask_price']
            return current_price + 0.5
        
        return df['h'].iloc[-2]
        
    except Exception as e:
        logger.error(f"❌ Error getting last high for {symbol}: {e}")
        current_price = fetch_option_chain(symbol)['ask_price']
        return current_price + 0.5

def get_last_low(symbol):
    """Get last low price"""
    try:
        df = api.get_price_history(symbol, period_type="day", period=5,
                                 frequency_type="daily", frequency=1)
        
        if df.empty or len(df) < 2:
            current_price = fetch_option_chain(symbol)['ask_price']
            return current_price - 0.5
        
        return df['l'].iloc[-2]
        
    except Exception as e:
        logger.error(f"❌ Error getting last low for {symbol}: {e}")
        current_price = fetch_option_chain(symbol)['ask_price']
        return current_price - 0.5

# Authentication helper functions
def authenticate_schwab():
    """Helper function to authenticate Schwab API"""
    if not api.access_token:
        logger.info("🔐 Schwab API requires authentication")
        auth_url = api.get_auth_url()
        logger.info(f"🔗 Go to: {auth_url}")
        logger.info("📋 Copy the 'code' parameter from the callback URL")
        
        code = input("Enter authorization code: ").strip()
        
        if api.get_access_token(code):
            logger.info("✅ Authentication successful!")
            return True
        else:
            logger.error("❌ Authentication failed!")
            return False
    
    return True

if __name__ == "__main__":
    print("🏦 Schwab Data Feed - Testing...")
    
    # Test authentication
    if authenticate_schwab():
        # Test functions
        print("\n📊 Testing data functions:")
        print("AAPL Quote:", fetch_option_chain("AAPL"))
        print("AAPL MAs:", get_moving_averages("AAPL", [9, 21, 200]))
        print("AAPL RVOL:", calculate_rvol("AAPL"))
        print("\n✅ Schwab data feed ready!")