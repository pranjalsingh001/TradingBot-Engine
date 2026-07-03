"""
walk_forward.py - Phase 3: Walk-Forward Validation
Coordinates ReplayEngine over training and evaluation windows.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.trading.replay_engine import start_replay, state as replay_state
from app.core.db import get_db

logger = logging.getLogger(__name__)

class WalkForwardEngine:
    def __init__(self, trading_system):
        self.system = trading_system
        self.is_running = False

    async def run_walk_forward(self, symbol: str, interval: str, train_start: str, eval_end: str, train_days: int = 30, eval_days: int = 7):
        """
        Run a walk-forward optimization.
        - Replay through training window with adaptive learning ON.
        - Replay through evaluation window with adaptive learning OFF.
        """
        if self.is_running:
            logger.warning("[WF] Walk-Forward engine already running.")
            return
            
        self.is_running = True
        logger.info(f"[WF] Starting Walk-Forward: Train={train_days}d, Eval={eval_days}d")
        
        current_train_start = datetime.fromisoformat(train_start)
        final_end = datetime.fromisoformat(eval_end)
        
        # Reset paper trading state
        self.system.reset()
        
        while current_train_start < final_end:
            train_end = current_train_start + timedelta(days=train_days)
            eval_start = train_end
            eval_period_end = eval_start + timedelta(days=eval_days)
            
            if eval_period_end > final_end:
                break
                
            logger.info(f"[WF] --- WINDOW START ---")
            logger.info(f"[WF] Training: {current_train_start.isoformat()} to {train_end.isoformat()}")
            
            # Enable adaptive learning
            self.system.adaptive_learning_enabled = True
            await start_replay(
                self.system.loop, symbol, interval, 
                current_train_start.isoformat(), train_end.isoformat(), 
                speed=0.0 # max speed
            )
            
            # Wait for replay to finish
            while replay_state.is_running:
                await asyncio.sleep(0.5)
                
            logger.info(f"[WF] Evaluation: {eval_start.isoformat()} to {eval_period_end.isoformat()}")
            
            # Freeze adaptive learning
            self.system.adaptive_learning_enabled = False
            await start_replay(
                self.system.loop, symbol, interval, 
                eval_start.isoformat(), eval_period_end.isoformat(), 
                speed=0.0
            )
            
            # Wait for replay to finish
            while replay_state.is_running:
                await asyncio.sleep(0.5)
                
            logger.info(f"[WF] --- WINDOW END ---")
            
            # Slide window
            current_train_start = current_train_start + timedelta(days=eval_days)
            
        self.is_running = False
        logger.info("[WF] Walk-Forward complete.")
