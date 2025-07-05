# Complete Live Options Monitoring System
import data_feed
import json
import requests
import sys
import math
from datetime import datetime, timedelta
import threading
import time

class LiveOptionsMonitor:
    def __init__(self):
        self.active_trades = {}  # Store all live trades
        self.monitoring = True
        self.check_interval = 30  # Check every 30 seconds
        
        self.trade_configs = {
            'scalp': {
                'rr_min': 1.2, 'rr_max': 1.3,
                'max_duration_hours': 6.5,
                'rvol_threshold': 150,
                'duration_text': 'Same day before 3:55 PM'
            },
            'day': {
                'rr_min': 2.0, 'rr_max': 3.0,
                'max_duration_days': 2,
                'rvol_threshold': 130,
                'duration_text': '1-2 days maximum'
            },
            'swing': {
                'rr_min': 3.0, 'rr_max': 5.0,
                'max_duration_weeks': 6,
                'min_duration_weeks': 2,
                'rvol_threshold': 120,
                'duration_text': '2-6 weeks maximum'
            }
        }

    def create_live_trade(self, symbol, trade_style, confluence_data, estimated_entry):
        """Create a live trade for monitoring"""
        trade_id = f"{symbol}_{trade_style}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        
        trade = {
            'trade_id': trade_id,
            'symbol': symbol,
            'trade_style': trade_style,
            'status': 'SETUP_READY',  # SETUP_READY -> ENTERED -> MONITORING -> EXITED
            'created_time': datetime.now(),
            'entry_time': None,
            'exit_time': None,
            
            # Entry Data
            'estimated_entry_cost': estimated_entry,
            'actual_entry_cost': None,
            'strike_price': self.calculate_atm_strike(confluence_data['current_price']),
            'expiration_date': self.get_expiration_date(trade_style),
            'contracts': 1,  # Default 1 contract
            
            # Exit Levels (will be calculated when trade is entered)
            'stop_loss_price': None,
            'target_price': None,
            'technical_stop_levels': confluence_data.get('support_levels', []),
            
            # Entry Confluence (for monitoring breakdown)
            'entry_confluences': confluence_data,
            'entry_support_levels': confluence_data.get('support_levels', []),
            'entry_ema_state': confluence_data.get('ema_state', {}),
            'entry_mtf_clouds': confluence_data.get('mtf_clouds', {}),
            
            # Monitoring Flags
            'profit_target_hit': False,
            'technical_invalidated': False,
            'time_limit_reached': False,
            'stop_loss_hit': False,
            
            # Performance Tracking
            'current_option_price': None,
            'current_pnl': 0.0,
            'current_pnl_percent': 0.0,
            'max_profit': 0.0,
            'max_drawdown': 0.0,
        }
        
        self.active_trades[trade_id] = trade
        print(f"📝 Created live trade setup: {trade_id}")
        return trade_id

    def enter_trade_with_real_price(self, trade_id, actual_option_price):
        """Update trade with real market entry price"""
        if trade_id not in self.active_trades:
            return False
        
        trade = self.active_trades[trade_id]
        trade['actual_entry_cost'] = actual_option_price
        trade['entry_time'] = datetime.now()
        trade['status'] = 'ENTERED'
        
        # Calculate dynamic exit levels based on REAL entry price
        trade['stop_loss_price'] = actual_option_price * 0.50  # 50% rule
        
        config = self.trade_configs[trade['trade_style']]
        target_multiplier = config['rr_min']
        risk = actual_option_price - trade['stop_loss_price']
        reward = risk * target_multiplier
        trade['target_price'] = actual_option_price + reward
        
        # Send entry confirmation
        self.send_entry_confirmation(trade)
        
        # Start monitoring
        trade['status'] = 'MONITORING'
        print(f"✅ Trade entered: {trade_id} at ${actual_option_price:.2f}")
        return True

    def monitor_all_trades(self):
        """Main monitoring loop - runs continuously"""
        while self.monitoring:
            try:
                current_time = datetime.now()
                
                for trade_id, trade in list(self.active_trades.items()):
                    if trade['status'] == 'MONITORING':
                        self.check_trade_conditions(trade_id, current_time)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"❌ Error in monitoring loop: {e}")
                time.sleep(5)

    def check_trade_conditions(self, trade_id, current_time):
        """Check all 4 exit conditions for a trade"""
        trade = self.active_trades[trade_id]
        symbol = trade['symbol']
        
        try:
            # Get current market data
            current_stock_price = self.get_current_stock_price(symbol)
            current_option_price = self.get_current_option_price(trade)
            
            if current_option_price is None:
                return
            
            # Update trade performance
            self.update_trade_performance(trade, current_option_price)
            
            # Check all exit conditions
            exit_triggered = False
            exit_reason = ""
            
            # 1. TECHNICAL BREAKDOWN (Priority #1)
            technical_breakdown = self.check_technical_breakdown(trade, current_stock_price)
            if technical_breakdown:
                exit_triggered = True
                exit_reason = f"TECHNICAL BREAKDOWN: {technical_breakdown}"
                trade['technical_invalidated'] = True
            
            # 2. PROFIT TARGETS (Priority #2)
            elif current_option_price >= trade['target_price']:
                exit_triggered = True
                exit_reason = f"PROFIT TARGET HIT: ${current_option_price:.2f} >= ${trade['target_price']:.2f}"
                trade['profit_target_hit'] = True
            
            # 3. TIME-BASED LIMITS (Priority #3)
            elif self.check_time_limits(trade, current_time):
                exit_triggered = True
                exit_reason = "TIME LIMIT REACHED"
                trade['time_limit_reached'] = True
            
            # 4. STOP LOSS (Priority #4 - Last Resort)
            elif current_option_price <= trade['stop_loss_price']:
                exit_triggered = True
                exit_reason = f"STOP LOSS HIT: ${current_option_price:.2f} <= ${trade['stop_loss_price']:.2f}"
                trade['stop_loss_hit'] = True
            
            # Execute exit if any condition triggered
            if exit_triggered:
                self.execute_exit(trade_id, current_option_price, exit_reason)
            
            # Send periodic updates (every 5 minutes)
            elif current_time.minute % 5 == 0 and current_time.second < 30:
                self.send_periodic_update(trade)
                
        except Exception as e:
            print(f"❌ Error checking trade {trade_id}: {e}")

    def check_technical_breakdown(self, trade, current_stock_price):
        """Check for technical confluence breakdown"""
        symbol = trade['symbol']
        
        try:
            # Get current technical data
            current_trends = data_feed.get_trend_data(symbol)
            current_ma_data = data_feed.get_moving_averages(symbol, [9, 21, 34, 50, 200])
            current_pivots = data_feed.get_pivots(symbol)
            
            # Check EMA cloud breakdown
            entry_9_21 = trade['entry_confluences']['trends'].get('9_21', 'Neutral')
            current_9_21 = current_trends.get('9_21', 'Neutral')
            
            if entry_9_21 == 'Bullish' and current_9_21 != 'Bullish':
                return "9/21 EMA cloud turned bearish"
            
            entry_34_50 = trade['entry_confluences']['trends'].get('34_50', 'Neutral')
            current_34_50 = current_trends.get('34_50', 'Neutral')
            
            if entry_34_50 == 'Bullish' and current_34_50 != 'Bullish':
                return "34/50 EMA cloud turned bearish"
            
            # Check support level breaks
            for support_level in trade['entry_support_levels']:
                level_price = support_level.get('level')
                level_name = support_level.get('name')
                
                if level_price and current_stock_price < level_price * 0.995:  # 0.5% buffer
                    return f"{level_name} support broken (${level_price:.2f})"
            
            # Check 50 EMA breakdown (major support)
            if current_stock_price < current_ma_data.get(50, 0) * 0.998:
                return "50 EMA support broken"
            
            # Check multi-timeframe deterioration
            mtf_clouds = current_trends.get('mtf_clouds', {})
            if len([c for c in mtf_clouds.values() if c == 'Bearish']) >= 2:
                return "Multi-timeframe turned bearish"
            
            return None  # No breakdown detected
            
        except Exception as e:
            print(f"Error checking technical breakdown: {e}")
            return None

    def check_time_limits(self, trade, current_time):
        """Check time-based exit conditions"""
        entry_time = trade.get('entry_time')
        if not entry_time:
            return False
        
        config = self.trade_configs[trade['trade_style']]
        
        if trade['trade_style'] == 'scalp':
            # Same day exit before 3:55 PM
            market_close = entry_time.replace(hour=15, minute=55, second=0)
            return current_time >= market_close
            
        elif trade['trade_style'] == 'day':
            # 1-2 days maximum
            max_time = entry_time + timedelta(days=config['max_duration_days'])
            return current_time >= max_time
            
        elif trade['trade_style'] == 'swing':
            # 2-6 weeks maximum
            max_time = entry_time + timedelta(weeks=config['max_duration_weeks'])
            return current_time >= max_time
        
        return False

    def update_trade_performance(self, trade, current_option_price):
        """Update trade P&L and performance metrics"""
        if not trade['actual_entry_cost']:
            return
        
        trade['current_option_price'] = current_option_price
        
        # Calculate P&L
        pnl = current_option_price - trade['actual_entry_cost']
        pnl_percent = (pnl / trade['actual_entry_cost']) * 100
        
        trade['current_pnl'] = pnl
        trade['current_pnl_percent'] = pnl_percent
        
        # Track max profit and drawdown
        if pnl > trade['max_profit']:
            trade['max_profit'] = pnl
        
        drawdown = trade['max_profit'] - pnl
        if drawdown > trade['max_drawdown']:
            trade['max_drawdown'] = drawdown

    def execute_exit(self, trade_id, exit_price, exit_reason):
        """Execute trade exit and send notification"""
        trade = self.active_trades[trade_id]
        trade['status'] = 'EXITED'
        trade['exit_time'] = datetime.now()
        trade['exit_price'] = exit_price
        trade['exit_reason'] = exit_reason
        
        # Calculate final P&L
        final_pnl = exit_price - trade['actual_entry_cost']
        final_pnl_percent = (final_pnl / trade['actual_entry_cost']) * 100
        
        # Send exit alert
        exit_alert = f"""🚨 **TRADE EXIT EXECUTED**

📊 **{trade['symbol']} {trade['trade_style'].upper()}** 
🎫 ${trade['strike_price']} CALL {trade['expiration_date']}

💰 **PERFORMANCE:**
• Entry: ${trade['actual_entry_cost']:.2f}
• Exit: ${exit_price:.2f}
• P&L: ${final_pnl:.2f} ({final_pnl_percent:+.1f}%)
• Max Profit: ${trade['max_profit']:.2f}
• Max Drawdown: ${trade['max_drawdown']:.2f}

🚨 **EXIT REASON:** {exit_reason}

⏰ **TRADE DURATION:** {self.calculate_trade_duration(trade)}

#{trade['symbol']} #EXIT #{trade['trade_style'].upper()}"""

        self.send_telegram_alert(exit_alert)
        print(f"🚪 Trade exited: {trade_id} - {exit_reason}")

    def send_entry_confirmation(self, trade):
        """Send confirmation when trade is entered with real price"""
        config = self.trade_configs[trade['trade_style']]
        
        alert = f"""✅ **TRADE ENTERED - LIVE MONITORING STARTED**

📊 **{trade['symbol']} {trade['trade_style'].upper()}**
🎫 ${trade['strike_price']} CALL exp {trade['expiration_date']}

💰 **REAL ENTRY PRICE:** ${trade['actual_entry_cost']:.2f}
🎯 **Target:** ${trade['target_price']:.2f} ({((trade['target_price']/trade['actual_entry_cost']-1)*100):.0f}% gain)
🛡️ **Stop:** ${trade['stop_loss_price']:.2f} (50% rule)
⏰ **Max Hold:** {config['duration_text']}

🤖 **LIVE MONITORING ACTIVE:**
✅ Technical breakdown detection
✅ Profit target monitoring  
✅ Time limit tracking
✅ Stop loss protection

You will receive automatic exit alerts when any condition triggers.

#{trade['symbol']} #ENTERED #{trade['trade_style'].upper()}"""

        self.send_telegram_alert(alert)

    def send_periodic_update(self, trade):
        """Send periodic P&L updates"""
        if not trade['current_option_price']:
            return
        
        update = f"""📊 **TRADE UPDATE**

{trade['symbol']} {trade['trade_style'].upper()}
Current: ${trade['current_option_price']:.2f}
P&L: ${trade['current_pnl']:.2f} ({trade['current_pnl_percent']:+.1f}%)
Target: ${trade['target_price']:.2f}
Stop: ${trade['stop_loss_price']:.2f}

#{trade['symbol']} #UPDATE"""

        self.send_telegram_alert(update)

    # Helper methods
    def get_current_stock_price(self, symbol):
        try:
            options_data = data_feed.fetch_option_chain(symbol)
            return options_data['ask_price']
        except:
            return None

    def get_current_option_price(self, trade):
        # In real implementation, you'd fetch actual option price from broker/data feed
        # For now, estimate based on stock movement
        try:
            current_stock = self.get_current_stock_price(trade['symbol'])
            if not current_stock:
                return None
            
            # Simple estimation - replace with real option pricing
            stock_change_pct = (current_stock - trade['entry_confluences']['current_price']) / trade['entry_confluences']['current_price']
            leverage = {'scalp': 15, 'day': 20, 'swing': 30}[trade['trade_style']]
            option_change_pct = stock_change_pct * leverage
            
            estimated_price = trade['actual_entry_cost'] * (1 + option_change_pct)
            return max(0.01, estimated_price)  # Options can't go below $0.01
            
        except:
            return None

    def calculate_atm_strike(self, current_price):
        return round(current_price)

    def get_expiration_date(self, trade_style):
        # Simplified - use your existing expiration logic
        if trade_style == 'scalp':
            return (datetime.now() + timedelta(days=1)).strftime("%m/%d/%y")
        elif trade_style == 'day':
            return (datetime.now() + timedelta(days=3)).strftime("%m/%d/%y")
        else:
            return (datetime.now() + timedelta(days=14)).strftime("%m/%d/%y")

    def calculate_trade_duration(self, trade):
        if trade['entry_time'] and trade['exit_time']:
            duration = trade['exit_time'] - trade['entry_time']
            return str(duration).split('.')[0]  # Remove microseconds
        return "Unknown"

    def send_telegram_alert(self, message):
        # Use your existing Telegram function
        send_telegram_alert(message)

# Integration with your existing system
def start_live_monitoring():
    """Start the live monitoring system"""
    monitor = LiveOptionsMonitor()
    
    # Start monitoring in background thread
    monitoring_thread = threading.Thread(target=monitor.monitor_all_trades, daemon=True)
    monitoring_thread.start()
    
    print("🤖 Live Options Monitoring System STARTED")
    print("📊 Monitoring all active trades for exit conditions")
    print("⚡ Real-time alerts for technical breakdown, profit targets, time limits, and stop losses")
    
    return monitor

# Usage example
if __name__ == "__main__":
    # Start live monitoring system
    live_monitor = start_live_monitoring()
    
    # Your existing alert generation would now create monitored trades
    # instead of just sending setup alerts
