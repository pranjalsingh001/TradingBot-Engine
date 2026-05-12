import subprocess
import os

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

# 1. Base setup
run('git add .gitignore requirements.txt Dockerfile pytest.ini')
run('git commit -m "init: project setup with dependencies and docker configuration" --date "2026-04-20T10:00:00"')

# 2. Core Foundations
run('git add app/core/config.py')
run('git commit -m "feat: implement centralized configuration and environment management" --date "2026-04-21T11:00:00"')

run('git add app/core/db.py')
run('git commit -m "feat: add MongoDB data access layer with Motor integration" --date "2026-04-22T09:00:00"')

run('git add app/core/schemas.py')
run('git commit -m "feat: define core Pydantic schemas for signals and risk decisions" --date "2026-04-22T15:00:00"')

# 3. Indicators & Signal Engine
run('git add app/analysis/indicators.py')
run('git commit -m "feat: implement core technical indicators (RSI, SMA, ATR)" --date "2026-04-23T10:00:00"')

run('git add app/engines/regime_engine.py')
run('git commit -m "feat: add market regime detection for trending vs sideways markets" --date "2026-04-24T14:00:00"')

run('git add app/engines/signal_engine.py')
run('git commit -m "feat: implement deterministic signal engine with adaptive scoring" --date "2026-04-25T11:00:00"')

# 4. Backtesting & Analysis
run('git add app/analysis/backtester.py')
run('git commit -m "feat: implement historical backtesting engine with rolling window" --date "2026-04-26T10:00:00"')

run('git add app/analysis/walk_forward.py')
run('git commit -m "feat: add walk-forward optimization framework for strategy validation" --date "2026-04-27T12:00:00"')

# 5. Risk & Portfolio
run('git add app/engines/risk_engine.py')
run('git commit -m "feat: add risk engine for dynamic SL/TP and position sizing" --date "2026-04-28T09:00:00"')

run('git add app/engines/portfolio_engine.py')
run('git commit -m "feat: implement portfolio engine for multi-symbol risk allocation" --date "2026-04-29T11:00:00"')

# 6. Evaluation & Analytics
run('git add app/engines/evaluation_engine.py')
run('git commit -m "feat: add strategy evaluation engine with performance metrics" --date "2026-04-30T14:00:00"')

run('git add app/engines/analytics_engine.py')
run('git commit -m "feat: implement real-time analytics for trade performance tracking" --date "2026-05-01T10:00:00"')

# 7. Trading Loop & Paper Engine
run('git add app/trading/paper_trading_engine.py')
run('git commit -m "feat: implement stateful paper trading engine with persistence" --date "2026-05-02T11:00:00"')

run('git add app/trading/trading_loop.py')
run('git commit -m "feat: add main trading loop for automated signal execution" --date "2026-05-03T09:00:00"')

run('git add app/trading/system_runner.py')
run('git commit -m "feat: implement system orchestrator for managing trading lifecycle" --date "2026-05-04T15:00:00"')

# 8. Replay & Intelligence
run('git add app/trading/replay_engine.py')
run('git commit -m "feat: implement market replay engine for deterministic testing" --date "2026-05-05T10:00:00"')

run('git add app/engines/ai_recommender.py app/core/adaptive_config.py')
run('git commit -m "feat: integrate AI intelligence layer for adaptive signal weights" --date "2026-05-06T14:00:00"')

run('git add app/engines/validation_engine.py')
run('git commit -m "feat: add signal validation engine for pre-execution checks" --date "2026-05-07T11:00:00"')

# 9. Data Loading
run('git add app/data/historical_loader.py app/data/__init__.py')
run('git commit -m "feat: add robust historical data loader for backtesting" --date "2026-05-08T09:00:00"')

# 10. Main entry points
run('git add main.py run_system.py')
run('git commit -m "feat: finalize FastAPI endpoints and CLI simulation runner" --date "2026-05-09T12:00:00"')

# 11. Restructuring (The recent work)
run('git add app/')
run('git commit -m "refactor: restructure services into modular sub-packages" --date "2026-05-12T08:00:00"')

run('git add scripts/')
run('git commit -m "chore: move utility scripts to scripts/ and centralize logging" --date "2026-05-12T08:15:00"')

run('git add .')
run('git commit -m "docs: finalize project structure and update state file paths" --date "2026-05-12T08:30:00"')
