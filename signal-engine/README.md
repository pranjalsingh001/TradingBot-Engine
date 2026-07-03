# Signal Engine Microservice

A modular Python FastAPI service designed for deterministic technical analysis, risk management, and market simulation.

## Architecture & Pipeline

The Signal Engine follows a structured pipeline for every request:

1. **Data Ingestion**: Fetches historical candles from MongoDB.
2. **Indicator Computation**: Calculates RSI, SMA (50/200), and ATR.
3. **Regime Detection**: Detects `TRENDING`, `SIDEWAYS`, `BREAKOUT`, or `VOLATILE` conditions.
4. **Adaptive Weighting**: Adjusts indicator weights based on the detected regime.
5. **Signal Scoring**: Generates a composite score and applies dynamic volatility thresholds.
6. **Risk Evaluation**: Calculates position sizes, Stop Loss, and Take Profit.

## Project Layout

- **`app/core`**: The project's foundation. Contains `db.py` (Motor/MongoDB), `config.py` (Pydantic settings), and `schemas.py`.
- **`app/engines`**: The logic layer. Each engine (Signal, Risk, Portfolio) is isolated and testable.
- **`app/trading`**: Orchestration logic. Contains the `TradingLoop` for live monitoring and the `PaperAccount` for simulation.
- **`app/analysis`**: Mathematical tools for backtesting and technical indicators.
- **`app/data`**: Storage for persistent state files like `paper_state.json`.
- **`scripts/`**: Maintenance utilities:
    - `db/`: Migration and health check scripts.
    - `maintenance/`: Data cleanup (purge) scripts.
    - `debug/`: Verification and testing utilities.

## Setup

1. **Initialize Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Create a `.env` file based on `.env.example`:
   ```env
   MONGO_URI=mongodb://localhost:27017
   SIGNAL_ENGINE_PORT=8000
   ```

3. **Run Service**:
   ```bash
   python main.py
   ```

## Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/signal/{symbol}` | Compute current signal and confidence. |
| `GET` | `/backtest/{symbol}` | Run historical performance test. |
| `POST` | `/risk/{symbol}` | Get risk-adjusted trade parameters. |
| `GET` | `/dashboard` | Retrieve paper trading account status. |
| `POST` | `/system/start` | Start the automated trading loop. |
| `GET` | `/api/v1/replay/status` | Check market replay engine state. |

## Development

### Running Tests
```bash
pytest
```

### Maintenance Scripts
Run scripts from the root directory:
```bash
python scripts/db/check_db.py
python scripts/maintenance/purge_nuclear.py
```

## Logging
All logs are stored in the `logs/` directory. `engine_debug.log` provides detailed traces of every signal computation and trade decision.
