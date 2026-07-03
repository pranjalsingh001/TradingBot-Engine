# TradingBot — Phase 2: Signal Engine & Intelligence Layer

A deterministic technical analysis and automated trading system.

**Architecture**: 
1. **Inners**: Binance WebSocket → Node.js Backend → MongoDB
2. **Brains**: Python Signal Engine (FastAPI) → Adaptive Intelligence Layer
3. **Display**: React Dashboard (Vite)

---

## Project Structure

```
treading bot/
├── backend/               # Node.js Market Data Ingestion
│   └── src/               # Express API and WebSocket services
├── frontend/              # React Dashboard (Vite)
│   └── src/               # Dashboard components and hooks
└── signal-engine/         # Python FastAPI Logic Engine
    ├── app/               # Modular Application Package
    │   ├── core/          # Config, DB, Schemas
    │   ├── engines/       # Logic Engines (Signal, Risk, Portfolio)
    │   ├── trading/       # Execution & Replay Loops
    │   ├── analysis/      # Backtesting & Indicators
    │   └── data/          # State persistence
    ├── scripts/           # Utility Scripts (Maintenance, Debug)
    ├── logs/              # Centralized Log Store
    ├── main.py            # FastAPI Entry Point
    └── run_system.py      # Simulation/Live Runner
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | ≥ 18 |
| Python | ≥ 3.11 |
| MongoDB | Local or Atlas |
| npm | ≥ 9 |

---

## Setup & Run

### 1. Market Ingestion (Node.js)
```bash
cd backend
npm install
npm run dev
```
Backend runs on **http://localhost:5000**

### 2. Signal Engine (Python)
```bash
cd signal-engine
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Signal Engine runs on **http://localhost:8000**

### 3. Dashboard (React)
```bash
cd frontend
npm install
npm run dev
```
Frontend runs on **http://localhost:5173**

---

## API Reference (Signal Engine)

### `GET /signal/{symbol}`
Compute trading signal based on RSI-14 and SMA-50.

### `GET /backtest/{symbol}`
Run a rolling-window backtest on historical MongoDB data.

### `POST /risk/{symbol}`
Evaluate trade risk and calculate dynamic SL/TP levels.

### `GET /dashboard`
Get full state of the paper trading system.

---

## Intelligence Layer
The Signal Engine now includes an **Intelligence Layer** that:
- Detects market regimes (**Trending** vs **Sideways**).
- Applies **Adaptive Weighting** to indicators based on the regime.
- Learns from trade outcomes via the `ai_recommender` (Phase 2).
- Penalizes signal confidence during factor disagreement.

---

## Verification Checklist

- [x] Backend logs `[WS] Connection established`
- [x] Signal Engine logs `[Server] Signal Engine starting on port 8000`
- [x] `GET /signal/BTCUSDT` returns deterministic BUY/SELL/HOLD
- [x] Paper Trading loop correctly updates `paper_state.json` in `app/data/`
- [x] Frontend dashboard shows live updating price and signals
