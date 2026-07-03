"""
main.py — FastAPI application entry point for the Phase 2 Signal Engine.

Routes:
    GET /signal/{symbol}   → compute and return trading signal
    GET /health            → liveness check
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OPENBLAS_MAIN_FREE"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"

import logging
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import fetch_prices, fetch_prices_bulk, close_connection, get_client
from app.engines.signal_engine import generate_signal
from app.analysis.backtester import run_backtest
from app.engines.risk_engine import evaluate_risk
from app.engines.portfolio_engine import allocate_portfolio
from app.engines.evaluation_engine import evaluate_backtest
from app.trading.paper_trading_engine import PaperAccount
from app.trading.trading_loop import TradingLoop
from app.engines.analytics_engine import get_performance_metrics
from app.core.schemas import (
    SignalResponse, ErrorResponse, AccountState, RiskDecision, PortfolioDecision,
    BacktestInput, EvaluationResult, PaperStatus,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("logs/engine_debug.log"),
        logging.StreamHandler()
    ]
)
# Silence noisy libraries
logging.getLogger("app.core.db").setLevel(logging.WARNING)
logging.getLogger("app.trading.trading_loop").setLevel(logging.WARNING)
logging.getLogger("app.engines.signal_engine").setLevel(logging.WARNING)
logging.getLogger("app.engines.risk_engine").setLevel(logging.WARNING)
logging.getLogger("app.engines.portfolio_engine").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ── App lifecycle ─────────────────────────────────────────────────────────────
# ── System Orchestration Endpoints ──────────────────────────────────────────────

from app.trading.system_runner import TradingSystem
trading_system = TradingSystem()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[Server] Signal Engine starting on port %d", settings.signal_engine_port)
    get_client()  # Initialise DB connection
    # trading_system is already initialized at module level
    await trading_system.start()
    yield
    await trading_system.stop()
    await close_connection()
    logger.info("[Server] Signal Engine shut down cleanly")

# ── Caching ───────────────────────────────────────────────────────────────────
signal_cache = {}



from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="TradingBot — Phase 2 Signal Engine",
    description="Deterministic technical analysis microservice. No AI. No ML. Pure rules.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "signal-engine", "version": "2.0.0"}


@app.get(
    "/signal/{symbol}",
    response_model=SignalResponse,
    responses={
        200: {"model": SignalResponse, "description": "Signal computed successfully"},
        404: {"model": ErrorResponse,  "description": "Insufficient data for symbol"},
        422: {"description": "Invalid symbol format"},
    },
    summary="Get trading signal for a symbol",
    description=(
        "Fetches recent price history from MongoDB, computes RSI-14 and SMA-50, "
        "and returns a deterministic BUY / SELL / HOLD signal with a confidence score."
    ),
)
async def get_signal(
    symbol: str = Path(
        ...,
        description="Trading pair symbol e.g. BTCUSDT",
        min_length=3,
        max_length=20,
        pattern=r"^[A-Za-z]{3,20}$",
    ),
    interval: str = Query(
        ...,
        description="Timeframe interval e.g., 1m, 5m, 1h, 1d",
        min_length=2,
        max_length=5,
    )
):
    start_time = time.perf_counter()
    symbol = symbol.upper()
    cache_key = f"{symbol}_{interval}"

    # Check cache
    now = time.time()
    if cache_key in signal_cache:
        cached_result, timestamp = signal_cache[cache_key]
        if now - timestamp < settings.cache_ttl_seconds:
            logger.info(f"[Cache] HIT for {cache_key}")
            return cached_result
    
    logger.info(f"[Cache] MISS for {cache_key}")

    # Fetch data from MongoDB
    df = await fetch_prices(symbol, interval=interval, limit=settings.default_candle_limit)

    # Generate signal (handles all error cases internally)
    result = generate_signal(df, symbol, interval)

    # If the engine returned an error response, surface it as 404
    if isinstance(result, ErrorResponse):
        raise HTTPException(status_code=404, detail=result.model_dump())

    # Update Cache
    signal_cache[cache_key] = (result, now)

    # Metrics
    process_time_ms = (time.perf_counter() - start_time) * 1000
    logger.info(f"[Metrics] GET /signal/{symbol}?interval={interval} completed in {process_time_ms:.2f}ms")

    return result


# ── Backtest Endpoint ─────────────────────────────────────────────────────────
@app.get(
    "/backtest/{symbol}",
    summary="Run backtest on historical data for a symbol",
    description=(
        "Fetches historical price data from MongoDB, runs a rolling-window "
        "backtest using the existing signal engine, and returns trade-level "
        "performance metrics. Fully deterministic."
    ),
)
async def get_backtest(
    symbol: str = Path(
        ...,
        description="Trading pair symbol e.g. BTCUSDT",
        min_length=3,
        max_length=20,
        pattern=r"^[A-Za-z]{3,20}$",
    ),
    interval: str = Query(
        ...,
        description="Timeframe interval e.g., 1m, 5m, 1h, 1d",
        min_length=2,
        max_length=5,
    ),
    limit: int = Query(
        1000,
        ge=300,
        le=5000,
        description="Number of historical candles to fetch (min 300)",
    ),
    window: int = Query(
        200,
        ge=200,
        le=500,
        description="Rolling window size for signal computation",
    ),
):
    start_time = time.perf_counter()
    symbol = symbol.upper()

    # Fetch bulk historical data
    df = await fetch_prices_bulk(symbol, interval=interval, limit=limit)

    if df.empty or len(df) < window + 1:
        raise HTTPException(
            status_code=404,
            detail={
                "symbol": symbol,
                "interval": interval,
                "error": f"Insufficient data: need >{window} candles, got {len(df) if not df.empty else 0}",
            },
        )

    # Run backtest
    result = run_backtest(df, symbol, interval, window_size=window)

    # Metrics
    process_time_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        f"[Metrics] GET /backtest/{symbol}?interval={interval} "
        f"completed in {process_time_ms:.2f}ms ({result['total_trades']} trades)"
    )

    return result


# ── Risk Engine Endpoint ─────────────────────────────────────────────────────
@app.post(
    "/risk/{symbol}",
    response_model=RiskDecision,
    summary="Evaluate trade risk for a signal",
    description=(
        "Fetches a live signal, then runs it through the risk engine "
        "to produce an execute/skip decision with position sizing, "
        "stop loss, and take profit levels."
    ),
)
async def evaluate_trade_risk(
    account: AccountState,
    symbol: str = Path(
        ...,
        description="Trading pair symbol e.g. BTCUSDT",
        min_length=3,
        max_length=20,
        pattern=r"^[A-Za-z]{3,20}$",
    ),
    interval: str = Query(
        ...,
        description="Timeframe interval e.g., 1m, 5m, 1h, 1d",
        min_length=2,
        max_length=5,
    ),
):
    start_time = time.perf_counter()
    symbol = symbol.upper()

    # Step 1: Get signal
    df = await fetch_prices(symbol, interval=interval, limit=settings.default_candle_limit)
    signal_result = generate_signal(df, symbol, interval)

    if isinstance(signal_result, ErrorResponse):
        raise HTTPException(status_code=404, detail=signal_result.model_dump())

    # Step 2: Evaluate risk
    decision = evaluate_risk(signal_result, account)

    # Metrics
    process_time_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        f"[Metrics] POST /risk/{symbol}?interval={interval} "
        f"completed in {process_time_ms:.2f}ms (execute={decision.execute})"
    )

    return decision


# ── Portfolio Endpoint ────────────────────────────────────────────────────────
@app.post(
    "/portfolio",
    response_model=PortfolioDecision,
    summary="Allocate portfolio across multiple trade candidates",
    description=(
        "Accepts a list of risk-engine outputs and returns a coordinated "
        "portfolio allocation with correlation control and risk scaling."
    ),
)
async def allocate(
    candidates: List[RiskDecision],
    balance: float = Query(..., gt=0, description="Current account balance"),
):
    start_time = time.perf_counter()

    result = allocate_portfolio(candidates, balance)

    process_time_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        f"[Metrics] POST /portfolio completed in {process_time_ms:.2f}ms "
        f"({result.portfolio.total_positions} trades selected)"
    )

    return result


# ── Evaluation Endpoint ──────────────────────────────────────────────────────
@app.post(
    "/evaluate",
    response_model=EvaluationResult,
    summary="Evaluate backtest performance",
    description=(
        "Accepts backtester output (trades + equity curve) and returns "
        "comprehensive performance metrics, distribution analysis, "
        "consistency checks, and a strategy grade."
    ),
)
async def evaluate(data: BacktestInput):
    start_time = time.perf_counter()

    result = evaluate_backtest(data.trades, data.equity_curve)

    process_time_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        f"[Metrics] POST /evaluate completed in {process_time_ms:.2f}ms "
        f"(grade={result.interpretation.grade})"
    )

    return result


# ── System Orchestration Endpoints ──────────────────────────────────────────────
# trading_system is initialized in the lifespan context above

@app.get(
    "/dashboard",
    summary="Get Trading Dashboard",
    description="Returns full account state, active positions, recent trades, and current signals."
)
async def get_dashboard():
    return trading_system.get_dashboard()

@app.post(
    "/system/start",
    summary="Start System",
    description="Starts the background execution loop."
)
async def system_start():
    # Attempt to load state if available
    trading_system.paper_account.load_state()
    await trading_system.start()
    return {"status": "started", "balance": trading_system.paper_account.balance}

@app.post(
    "/system/stop",
    summary="Stop System",
    description="Stops the background loop safely."
)
async def system_stop():
    await trading_system.stop()
    return {"status": "stopped", "balance": trading_system.paper_account.balance}

@app.post(
    "/system/reset",
    summary="Reset System",
    description="Stops the system, resets the account balance, and clears history."
)
async def system_reset():
    await trading_system.stop()
    trading_system.reset()
    return {"status": "reset", "balance": trading_system.paper_account.balance}

from app.trading.replay_engine import start_replay, pause_replay, resume_replay, stop_replay, state as replay_state
import asyncio

@app.post(
    "/api/v1/replay/start",
    summary="Start Replay Engine",
    description="Starts the market replay engine using historical data. Clears previous replay state."
)
async def api_start_replay(symbol: str = "BTCUSDT", interval: str = "1m", start_time: str = "2024-01-01T00:00:00+00:00", end_time: str = "2024-02-01T00:00:00+00:00", speed: float = 1.0):
    if replay_state.is_running:
        return {"status": "error", "message": "Replay is already running"}
    
    # 1. Fetch current performance before resetting
    from app.engines.analytics_engine import get_performance_metrics
    from app.core.db import get_db
    import datetime
    
    db = get_db()
    metrics = await get_performance_metrics()
    
    # Only save if there were actual trades
    if "error" not in metrics:
        session_doc = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pnl": trading_system.paper_account.balance - 10000.0,
            "win_rate": metrics.get("win_rate", 0),
            "total_trades": metrics.get("total_trades", 0),
            "profit_factor": metrics.get("profit_factor", 0)
        }
        await db.replay_sessions.insert_one(session_doc)
    
    # 2. Reset bot state (Balance to 10k, open positions cleared)
    trading_system.reset()
    
    # 3. Wipe Intelligence Layer for a fresh A/B comparison
    await db.trade_insights.delete_many({})
    await db.adaptation_results.delete_many({})
    await db.recommendations.delete_many({})
    
    # 4. Run replay as a background task
    asyncio.create_task(start_replay(trading_system.loop, symbol, interval, start_time, end_time, speed))
    return {"status": "started", "symbol": symbol, "start_time": start_time, "end_time": end_time, "speed": speed}

@app.post("/api/v1/replay/pause", summary="Pause Replay")
async def api_pause_replay():
    pause_replay()
    return {"status": "paused"}

@app.post("/api/v1/replay/resume", summary="Resume Replay")
async def api_resume_replay():
    resume_replay()
    return {"status": "resumed"}

@app.post("/api/v1/replay/stop", summary="Stop Replay")
async def api_stop_replay():
    stop_replay()
    return {"status": "stopped"}

@app.get("/api/v1/replay/status", summary="Get Replay Status")
async def api_replay_status():
    return {
        "is_running": replay_state.is_running,
        "is_paused": replay_state.is_paused,
        "current_time": replay_state.current_time.isoformat() if replay_state.current_time else None,
        "end_time": replay_state.end_time.isoformat() if replay_state.end_time else None,
        "speed": replay_state.speed,
        "symbol": replay_state.symbol,
        "interval": replay_state.interval
    }

@app.get("/api/v1/replay/sessions", summary="Get Past Replay Sessions")
async def api_replay_sessions():
    try:
        from app.core.db import get_db
        db = get_db()
        cursor = db.replay_sessions.find({}, {"_id": 0}).sort("timestamp", -1)
        sessions = await cursor.to_list(length=100)
        return {"sessions": sessions}
    except Exception as e:
        logger.error(f"[API] Failed to fetch replay sessions: {e}")
        return {"sessions": [], "error": "Database unavailable"}

@app.get("/api/v1/replay/reports", summary="Get Walk Forward Reports")
async def api_replay_reports():
    from app.core.db import get_db
    collection = get_db()["adaptation_results"]
    cursor = collection.find({}, {"_id": 0}).sort("timestamp", -1).limit(20)
    reports = await cursor.to_list(length=20)
    return reports
@app.get(
    "/api/v1/analytics",
    summary="Get Trading Analytics",
    description="Returns performance statistics based on historical trade insights."
)
async def get_analytics():
    return await get_performance_metrics()
