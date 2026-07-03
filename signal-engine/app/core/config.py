"""
config.py — Centralised settings loaded from environment variables.
All other modules import from here; nothing reads os.environ directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # MongoDB
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "tradingbot"
    mongo_collection: str = "prices"

    # Engine tuning
    min_candles: int = 200        # minimum records needed to compute signals (MA200 requires 200)
    default_candle_limit: int = 250  # how many records to fetch per symbol

    # RSI thresholds
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    rsi_period: int = 14

    # Moving average
    ma_period: int = 50
    ma_long_period: int = 200

    # Caching
    cache_ttl_seconds: int = 10

    # ── Risk Engine ──────────────────────────────────────────────────────────
    max_risk_per_trade: float = 0.01        # 1% of account per trade
    max_position_pct: float = 0.10          # 10% of account max position
    atr_stop_multiplier: float = 2.0        # stop loss = ATR * multiplier
    risk_reward_ratio: float = 2.0          # take profit = stop * ratio
    min_confidence: float = 0.3             # skip trade if confidence < this
    max_volatility_ratio: float = 0.05      # skip trade if ATR/price > this
    max_active_trades: int = 3              # portfolio-level cap
    max_drawdown_pct: float = 0.10          # circuit breaker: 10% drawdown
    max_portfolio_exposure: float = 0.30    # total exposure ≤ 30% of balance

    # ── Portfolio Engine ─────────────────────────────────────────────────────
    max_portfolio_risk: float = 0.03        # total risk ≤ 3% of balance
    max_positions: int = 3                  # max simultaneous positions

    # ── Paper Trading ────────────────────────────────────────────────────────
    paper_starting_balance: float = 10_000.0
    paper_loop_interval: int = 60           # seconds between loops
    paper_state_file: str = "app/data/paper_state.json"
    paper_trailing_stops: bool = True       # enable trailing stop logic

    # Server
    signal_engine_port: int = 8000


# Single shared instance — import this everywhere
settings = Settings()
