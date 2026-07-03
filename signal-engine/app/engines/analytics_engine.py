"""
analytics_engine.py - Turn raw trades into statistical understanding (Phase 3).
"""
import logging
from app.core.db import get_db

logger = logging.getLogger(__name__)

async def get_performance_metrics() -> dict:
    collection = get_db()["trade_insights"]
    
    total_trades = await collection.count_documents({})
    if total_trades == 0:
        return {"error": "No trades logged yet. Let the system run."}
        
    cursor = collection.find({})
    trades = await cursor.to_list(length=10000)
    
    regime_stats = {}
    rsi_stats = {"<30": {"wins": 0, "total": 0}, "30-70": {"wins": 0, "total": 0}, ">70": {"wins": 0, "total": 0}}
    confidence_stats = {">0.8": {"wins": 0, "total": 0}, "<=0.8": {"wins": 0, "total": 0}}
    
    total_wins = 0
    total_profit = 0.0
    total_loss = 0.0
    
    for t in trades:
        is_win = t.get("result") == "WIN"
        if is_win:
            total_wins += 1
            total_profit += t.get("profit_percent", 0.0)
        else:
            total_loss += abs(t.get("profit_percent", 0.0))
            
        regime = t.get("market_regime", "UNKNOWN")
        if regime not in regime_stats:
            regime_stats[regime] = {"wins": 0, "total": 0}
            
        regime_stats[regime]["total"] += 1
        if is_win:
            regime_stats[regime]["wins"] += 1
            
        rsi = t.get("rsi", 50)
        if rsi < 30:
            rsi_bin = "<30"
        elif rsi > 70:
            rsi_bin = ">70"
        else:
            rsi_bin = "30-70"
            
        rsi_stats[rsi_bin]["total"] += 1
        if is_win:
            rsi_stats[rsi_bin]["wins"] += 1
            
        conf = t.get("confidence", 0.0)
        conf_bin = ">0.8" if conf > 0.8 else "<=0.8"
        confidence_stats[conf_bin]["total"] += 1
        if is_win:
            confidence_stats[conf_bin]["wins"] += 1
            
    win_rate = total_wins / total_trades if total_trades > 0 else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    for r in regime_stats:
        regime_stats[r]["win_rate"] = regime_stats[r]["wins"] / regime_stats[r]["total"] if regime_stats[r]["total"] > 0 else 0
        
    for r in rsi_stats:
        rsi_stats[r]["win_rate"] = rsi_stats[r]["wins"] / rsi_stats[r]["total"] if rsi_stats[r]["total"] > 0 else 0
        
    for c in confidence_stats:
        confidence_stats[c]["win_rate"] = confidence_stats[c]["wins"] / confidence_stats[c]["total"] if confidence_stats[c]["total"] > 0 else 0

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "regime_performance": regime_stats,
        "indicator_performance": {
            "rsi": rsi_stats
        },
        "confidence_accuracy": confidence_stats
    }
