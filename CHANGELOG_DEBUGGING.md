# Trading Bot Debugging & Fixes Summary

This document outlines the key issues encountered and the fixes applied during the debugging session for the Paper Trading Engine and Live Dashboard integration. 

It is intended to provide context for future developers regarding system behavior, specific Windows-related quirks, and architectural adjustments made to stabilize the trading loop.

## 1. Port Conflicts & Connection Issues
*   **Issue**: The Signal Engine frequently failed to start on Windows with a `[Errno 10048] address already in use` socket error. This was caused by zombie Python processes holding onto port `8001`.
*   **Fix**: Permanently migrated the Signal Engine to port `9000` (updated in `.env` and `main.py`). The frontend `Dashboard.jsx` and `dashboard.js` API base URL were updated to point to `http://localhost:9000`.

## 2. Schema Mismatch in Trading Loop
*   **Issue**: The `trading_loop.py` was crashing during the data extraction phase with a `KeyError: 'close'`.
*   **Fix**: Updated the extraction logic to reference the correct column name `price`, aligning with the MongoDB schema format populated by the backend feed.

## 3. Aggressive Trading Configuration & Thresholds
*   **Issue**: The bot was generating `HOLD` signals even when indicators showed positive momentum. The dynamic score calculation was not reaching the required thresholds.
*   **Fix**: 
    *   Lowered `BASE_THRESHOLD` in `signal_engine.py` from `0.5` to `0.1`.
    *   Lowered `MIN_CONFIDENCE` in the `.env` file to `0.05`.
    *   This made the Signal Engine highly sensitive ("hair-trigger"), allowing for active generation of paper trades to test the execution pipeline.

## 4. UI Transparency (Risk Engine Feedback)
*   **Issue**: The dashboard would show `BUY` or `SELL` signals, but no active positions were opened. The user had no visibility into *why* the Risk Engine rejected the trade.
*   **Fix**: 
    *   Modified `trading_loop.py` to capture the Risk Engine's decision (`risk_status` and `risk_reason`) and append it to the signal data.
    *   Updated the frontend `Dashboard.jsx` to restore the `Score` column and add a new `Risk Status` column. The UI now actively displays reasons like "Volatility too high" or "ACCEPTED".

## 5. The "Hidden" Windows Unicode Logging Crash
*   **Issue**: The background trading loop was silently crashing mid-cycle without fully halting the server. This was traced to a `UnicodeEncodeError` occurring on Windows when the `logger.info` function attempted to print the rightwards arrow character (`→`). Because the crash happened in the middle of a cycle, the `recent_signals` array was never updated, causing the dashboard to permanently display "Awaiting signals...".
*   **Fix**: Conducted a global purge of the `→` character across all files in the `services/` directory (`signal_engine.py`, `portfolio_engine.py`, `paper_trading_engine.py`, `indicators.py`, `db.py`), replacing it with the standard ASCII `->`. Deleted one particularly crash-prone log line in `portfolio_engine.py`.

## 6. Graceful Error Handling in the Trading Loop
*   **Issue**: If `generate_signal` returned an `ErrorResponse` (e.g., due to insufficient historical data for a symbol), passing this response to `evaluate_risk` caused an `AttributeError` because `ErrorResponse` lacks the `indicators` object. This crashed the loop cycle for *all* symbols.
*   **Fix**: Added a type check in `trading_loop.py`. If `signal_res` is an `ErrorResponse`, the loop now directly assigns a `risk_status` of "ERROR" and forwards the specific error message to the dashboard, then gracefully `continue`s to the next symbol.

## 7. The Double Initialization Bug (`main.py`)
*   **Issue**: The `TradingSystem` was being instantiated twice in `main.py`—once at the module level (which the dashboard API read from) and once inside the `lifespan` context manager (which actually ran the background loop). This meant the background loop was processing trades, but the dashboard was reading from a dormant instance.
*   **Fix**: 
    *   Consolidated to a single global `trading_system` instance.
    *   Added an explicit `await trading_system.start()` call inside the `lifespan` block so the background loop auto-starts whenever the server boots, ensuring the bot is "Fully Automated" as requested.

## 8. The `AccountState` Type Mismatch
*   **Issue**: The `evaluate_risk` function strictly requires an `AccountState` pydantic model, but `trading_loop.py` was passing the raw `PaperAccount` class instance. This caused an `AttributeError: 'PaperAccount' object has no attribute 'active_trades'` right before saving signals, skipping the dashboard update silently.
*   **Fix**: Modified `trading_loop.py` to construct a proper `AccountState` object on-the-fly using properties extracted from `self.paper_account` before passing it to `evaluate_risk`. This successfully unblocked the pipeline, allowing paper trades to open and populating the dashboard UI.
