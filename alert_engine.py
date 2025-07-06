# Complete Alert Engine with Performance Tracking and Alert Generation
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np
import pandas as pd

class TradingPerformanceTracker:
    def __init__(self):
        self.performance_file = "data/trading_performance.json"
        self.trades_history = []
        self.daily_stats = defaultdict(dict)
        self.load_performance_data()
    
    def load_performance_data(self):
        """Load existing performance data"""
        try:
            if os.path.exists(self.performance_file):
                with open(self.performance_file, 'r') as f:
                    data = json.load(f)
                    self.trades_history = data.get('trades', [])
                    self.daily_stats = defaultdict(dict, data.get('daily_stats', {}))
        except Exception as e:
            print(f"Error loading performance data: {e}")
    
    def save_performance_data(self):
        """Save performance data to file"""
        try:
            os.makedirs(os.path.dirname(self.performance_file), exist_ok=True)
            data = {
                'trades': self.trades_history,
                'daily_stats': dict(self.daily_stats),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.performance_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving performance data: {e}")
    
    def record_trade_setup(self, trade_data):
        """Record when a trade setup is detected"""
        setup_record = {
            'setup_id': f"{trade_data['symbol']}_{trade_data['trade_style']}_{datetime.now().strftime('%Y%m%d_%H%M')}",
            'symbol': trade_data['symbol'],
            'trade_style': trade_data['trade_style'],
            'setup_time': datetime.now().isoformat(),
            'estimated_entry': trade_data.get('estimated_entry_cost'),
            'confluence_score': self.calculate_confluence_score(trade_data),
            'market_conditions': self.get_market_conditions(),
            'status': 'SETUP_DETECTED'
        }
        
        self.trades_history.append(setup_record)
        self.save_performance_data()
        return setup_record['setup_id']
    
    def record_trade_entry(self, setup_id, actual_entry_price):
        """Record when a trade is actually entered"""
        for trade in self.trades_history:
            if trade.get('setup_id') == setup_id:
                trade.update({
                    'entry_time': datetime.now().isoformat(),
                    'actual_entry': actual_entry_price,
                    'status': 'ENTERED',
                    'slippage': actual_entry_price - trade.get('estimated_entry', actual_entry_price)
                })
                break
        self.save_performance_data()
    
    def record_trade_exit(self, setup_id, exit_price, exit_reason):
        """Record when a trade is exited"""
        for trade in self.trades_history:
            if trade.get('setup_id') == setup_id:
                entry_price = trade.get('actual_entry', trade.get('estimated_entry', 0))
                pnl = exit_price - entry_price if entry_price > 0 else 0
                pnl_percent = (pnl / entry_price * 100) if entry_price > 0 else 0
                
                trade.update({
                    'exit_time': datetime.now().isoformat(),
                    'exit_price': exit_price,
                    'exit_reason': exit_reason,
                    'pnl': pnl,
                    'pnl_percent': pnl_percent,
                    'status': 'CLOSED',
                    'trade_duration': self.calculate_duration(
                        trade.get('entry_time', trade.get('setup_time')),
                        datetime.now().isoformat()
                    )
                })
                
                # Update daily statistics
                self.update_daily_stats(trade)
                break
        
        self.save_performance_data()
    
    def calculate_confluence_score(self, trade_data):
        """Calculate confluence score for trade quality"""
        score = 0
        
        confluences = trade_data.get('entry_confluences', {})
        
        # EMA alignment
        trends = confluences.get('trends', {})
        if trends.get('9_21') == 'Bullish':
            score += 20
        if trends.get('34_50') == 'Bullish':
            score += 15
        
        # Volume
        rvol = confluences.get('rvol', 1.0)
        if rvol > 1.5:
            score += 25
        elif rvol > 1.3:
            score += 15
        elif rvol > 1.1:
            score += 5
        
        # Multi-timeframe
        mtf_clouds = trends.get('mtf_clouds', {})
        bullish_tf_count = sum(1 for v in mtf_clouds.values() if v == 'Bullish')
        score += bullish_tf_count * 10
        
        # Support levels
        support_levels = confluences.get('support_levels', [])
        score += len(support_levels) * 5
        
        return min(score, 100)  # Cap at 100
    
    def get_market_conditions(self):
        """Get current market conditions snapshot"""
        return {
            'timestamp': datetime.now().isoformat(),
            'market_open': True,  # You can integrate with your market hours check
            'vix_level': 'Normal',  # Integrate with VIX data if available
            'market_trend': 'Bullish'  # Integrate with market trend analysis
        }
    
    def calculate_duration(self, start_time, end_time):
        """Calculate trade duration in minutes"""
        try:
            start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration = end - start
            return duration.total_seconds() / 60  # Return minutes
        except:
            return 0
    
    def update_daily_stats(self, trade):
        """Update daily performance statistics"""
        trade_date = datetime.fromisoformat(trade.get('entry_time', trade.get('setup_time'))).date().isoformat()
        
        if trade_date not in self.daily_stats:
            self.daily_stats[trade_date] = {
                'trades_count': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0,
                'total_pnl_percent': 0,
                'avg_confluence_score': 0,
                'trade_styles': defaultdict(int)
            }
        
        daily = self.daily_stats[trade_date]
        daily['trades_count'] += 1
        
        pnl = trade.get('pnl', 0)
        if pnl > 0:
            daily['wins'] += 1
        elif pnl < 0:
            daily['losses'] += 1
        
        daily['total_pnl'] += pnl
        daily['total_pnl_percent'] += trade.get('pnl_percent', 0)
        
        # Update confluence score average
        confluence_score = trade.get('confluence_score', 0)
        daily['avg_confluence_score'] = (
            (daily['avg_confluence_score'] * (daily['trades_count'] - 1) + confluence_score) 
            / daily['trades_count']
        )
        
        # Track trade styles
        trade_style = trade.get('trade_style', 'unknown')
        daily['trade_styles'][trade_style] += 1
    
    def get_performance_summary(self, days=30):
        """Get performance summary for last N days"""
        cutoff_date = (datetime.now() - timedelta(days=days)).date()
        
        recent_trades = [
            t for t in self.trades_history 
            if (t.get('status') == 'CLOSED' and 
                datetime.fromisoformat(t.get('entry_time', t.get('setup_time'))).date() >= cutoff_date)
        ]
        
        if not recent_trades:
            return {"error": "No completed trades in the specified period"}
        
        total_trades = len(recent_trades)
        wins = sum(1 for t in recent_trades if t.get('pnl', 0) > 0)
        losses = sum(1 for t in recent_trades if t.get('pnl', 0) < 0)
        
        total_pnl = sum(t.get('pnl', 0) for t in recent_trades)
        total_pnl_percent = sum(t.get('pnl_percent', 0) for t in recent_trades)
        
        avg_confluence = np.mean([t.get('confluence_score', 0) for t in recent_trades])
        
        # Trade style breakdown
        style_performance = defaultdict(lambda: {'count': 0, 'pnl': 0, 'wins': 0})
        for trade in recent_trades:
            style = trade.get('trade_style', 'unknown')
            style_performance[style]['count'] += 1
            style_performance[style]['pnl'] += trade.get('pnl', 0)
            if trade.get('pnl', 0) > 0:
                style_performance[style]['wins'] += 1
        
        return {
            'period_days': days,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / total_trades * 100) if total_trades > 0 else 0,
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(total_pnl / total_trades, 2) if total_trades > 0 else 0,
            'total_pnl_percent': round(total_pnl_percent, 1),
            'avg_pnl_percent': round(total_pnl_percent / total_trades, 1) if total_trades > 0 else 0,
            'avg_confluence_score': round(avg_confluence, 1),
            'style_breakdown': dict(style_performance),
            'best_trade': max(recent_trades, key=lambda x: x.get('pnl', 0)) if recent_trades else None,
            'worst_trade': min(recent_trades, key=lambda x: x.get('pnl', 0)) if recent_trades else None
        }
    
    def generate_performance_report(self):
        """Generate a comprehensive performance report"""
        weekly_summary = self.get_performance_summary(7)
        monthly_summary = self.get_performance_summary(30)
        
        report = f"""📊 **TRADING PERFORMANCE REPORT**

🗓️ **7-DAY SUMMARY:**
• Total Trades: {weekly_summary.get('total_trades', 0)}
• Win Rate: {weekly_summary.get('win_rate', 0):.1f}%
• Total P&L: ${weekly_summary.get('total_pnl', 0):.2f}
• Avg P&L per Trade: ${weekly_summary.get('avg_pnl_per_trade', 0):.2f}
• Avg Confluence Score: {weekly_summary.get('avg_confluence_score', 0):.1f}/100

📅 **30-DAY SUMMARY:**
• Total Trades: {monthly_summary.get('total_trades', 0)}
• Win Rate: {monthly_summary.get('win_rate', 0):.1f}%
• Total P&L: ${monthly_summary.get('total_pnl', 0):.2f}
• Avg P&L per Trade: ${monthly_summary.get('avg_pnl_per_trade', 0):.2f}
• Total P&L %: {monthly_summary.get('total_pnl_percent', 0):.1f}%

🎯 **TRADE STYLE BREAKDOWN (30d):**"""
        
        style_breakdown = monthly_summary.get('style_breakdown', {})
        for style, data in style_breakdown.items():
            win_rate = (data['wins'] / data['count'] * 100) if data['count'] > 0 else 0
            report += f"\n• {style.title()}: {data['count']} trades, {win_rate:.1f}% win rate, ${data['pnl']:.2f} P&L"
        
        best_trade = monthly_summary.get('best_trade')
        if best_trade:
            report += f"\n\n🏆 **BEST TRADE (30d):**\n• {best_trade['symbol']} {best_trade['trade_style']}: +${best_trade['pnl']:.2f} ({best_trade['pnl_percent']:+.1f}%)"
        
        return report

# Global performance tracker instance
performance_tracker = TradingPerformanceTracker()

# ===== ALERT GENERATION FUNCTIONS =====

def generate_alert_improved(symbol, trade_type):
    """
    Generate trading alerts - main function called by main.py
    This function analyzes symbols and sends alerts when setups are detected
    """
    try:
        print(f"🔍 Analyzing {symbol} for {trade_type} strategy")
        
        # Get market data using your data_feed
        import data_feed
        from telegram_alert import send_telegram_alert
        
        quote_data = data_feed.fetch_option_chain(symbol)
        if not quote_data:
            print(f"❌ No data available for {symbol}")
            return
        
        current_price = quote_data['ask_price']
        
        # Get technical indicators
        ma_data = data_feed.get_moving_averages(symbol, [9, 21, 34, 50, 200])
        rvol = data_feed.calculate_rvol(symbol)
        trend_data = data_feed.get_trend_data(symbol)
        pivots = data_feed.get_pivots(symbol)
        
        # Create confluence data structure
        confluence_data = {
            'current_price': current_price,
            'trends': trend_data,
            'ma_data': ma_data,
            'rvol': rvol,
            'pivots': pivots,
            'support_levels': [
                {'name': 'S1 Pivot', 'level': pivots.get('s1', current_price * 0.98)},
                {'name': '21 EMA', 'level': ma_data.get(21, current_price * 0.99)},
                {'name': 'PDL', 'level': pivots.get('pdl', current_price * 0.97)}
            ]
        }
        
        # Get the threshold for this trade type
        trade_config = {
            'scalp': {'rvol_threshold': 150},
            'day': {'rvol_threshold': 130}, 
            'swing': {'rvol_threshold': 120}
        }
        
        config = trade_config.get(trade_type, {'rvol_threshold': 130})
        rvol_threshold = config['rvol_threshold'] / 100  # Convert to decimal
        
        # Alert conditions based on sophisticated logic
        alert_triggered = False
        alert_reason = ""
        
        # Strong bullish confluence check
        if (trend_data.get('9_21') == 'Bullish' and 
            trend_data.get('34_50') == 'Bullish' and 
            rvol > rvol_threshold and 
            current_price > ma_data.get(21, 0)):
            
            alert_triggered = True
            alert_reason = f"Strong bullish confluence - RVOL: {rvol:.1f}x, All EMAs bullish"
        
        # Breakout setup check
        elif (current_price > pivots.get('r1', current_price) and 
              rvol > rvol_threshold * 1.2):  # Higher threshold for breakouts
            
            alert_triggered = True
            alert_reason = f"Breakout above R1 pivot (${pivots.get('r1', 0):.2f}) with high volume"
        
        # Multi-timeframe alignment check
        elif (trend_data.get('mtf_clouds', {}).get('1H') == 'Bullish' and
              trend_data.get('mtf_clouds', {}).get('4H') == 'Bullish' and
              rvol > rvol_threshold):
            
            alert_triggered = True
            alert_reason = f"Multi-timeframe bullish alignment with elevated volume"
        
        if alert_triggered:
            # Estimate option entry cost based on your logic
            estimated_entry = current_price * 0.03  # Rough 3% of stock price for ATM options
            
            # Create trade data for performance tracking
            trade_data = {
                'symbol': symbol,
                'trade_style': trade_type,
                'estimated_entry_cost': estimated_entry,
                'entry_confluences': confluence_data
            }
            
            # Track setup detection
            setup_id = performance_tracker.record_trade_setup(trade_data)
            
            # Send sophisticated setup alert
            setup_alert = f"""🚨 **{trade_type.upper()} SETUP DETECTED**

*{symbol}* - ${current_price:.2f}
*Reason:* {alert_reason}

*Technical Confluence:*
• 9/21 EMA: {trend_data.get('9_21', 'N/A')}
• 34/50 EMA: {trend_data.get('34_50', 'N/A')}
• RVOL: {rvol:.1f}x (Threshold: {rvol_threshold:.1f}x)
• Price vs 21MA: {'Above' if current_price > ma_data.get(21, 0) else 'Below'}

*Key Levels:*
• R1 Pivot: ${pivots.get('r1', 0):.2f}
• S1 Pivot: ${pivots.get('s1', 0):.2f}
• 50 EMA: ${ma_data.get(50, 0):.2f}

*Estimated Entry:* ~${estimated_entry:.2f}
*Trade Style:* {trade_type.capitalize()}

*Setup ID:* {setup_id}

#{symbol} #SETUP #{trade_type.upper()}"""
            
            # Send the alert using your existing system
            telegram_success = send_telegram_alert(setup_alert)
            
            if telegram_success:
                print(f"✅ {trade_type.upper()} setup alert sent for {symbol}: {alert_reason}")
            else:
                print(f"❌ {trade_type.upper()} setup alert FAILED for {symbol}: {alert_reason}")
                print("📱 Check Telegram bot configuration and try again")
        else:
            print(f"📊 {symbol}: No {trade_type} setup conditions met (RVOL: {rvol:.1f}x, Req: {rvol_threshold:.1f}x)")
            
    except Exception as e:
        print(f"❌ Error in generate_alert_improved for {symbol}: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")

# Performance tracking helper functions
def track_setup_detected(trade_data):
    """Helper function to track setup detection"""
    return performance_tracker.record_trade_setup(trade_data)

def track_trade_entered(setup_id, actual_price):
    """Helper function to track trade entry"""
    return performance_tracker.record_trade_entry(setup_id, actual_price)

def track_trade_exited(setup_id, exit_price, reason):
    """Helper function to track trade exit"""
    return performance_tracker.record_trade_exit(setup_id, exit_price, reason)

def get_daily_performance_report():
    """Get daily performance report for Telegram"""
    return performance_tracker.generate_performance_report()

# Usage example and testing
if __name__ == "__main__":
    print("🧪 Testing Alert Engine...")
    
    # Test alert generation for a few symbols
    test_symbols = ["AAPL", "QQQ", "SPY"]
    test_strategies = ["scalp", "day", "swing"]
    
    for symbol in test_symbols:
        for strategy in test_strategies:
            print(f"\n--- Testing {symbol} {strategy} ---")
            generate_alert_improved(symbol, strategy)