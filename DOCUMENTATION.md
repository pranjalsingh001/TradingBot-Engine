# TradingBot Institutional (Chain-Mind) - Complete Technical Documentation

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Folder Structure Explanation](#2-folder-structure-explanation)
3. [File-by-File Breakdown](#3-file-by-file-breakdown)
4. [Function-by-Function Explanation](#4-function-by-function-explanation)
5. [Engine & Strategy Logic](#5-engine--strategy-logic)
6. [System Flow](#6-system-flow)
7. [Dependencies & External Services](#7-dependencies--external-services)
8. [Code Relationships](#8-code-relationships)
9. [Important Notes & Limitations](#9-important-notes)

---

## 1. Project Overview

### What the project does
The project is a fully automated, full-stack Paper Trading Algorithmic Bot. It fetches live cryptocurrency prices from Binance, stores them in a local database, runs technical analysis to generate trading signals, evaluates the risk of those signals, sizes the positions, and executes virtual paper trades. The results are streamed to a modern, real-time React dashboard.

### Main Goal
The primary goal is to provide a robust, risk-controlled, and transparent framework for testing algorithmic trading strategies in real-time without risking actual capital (Paper Trading). It serves as a precursor to live exchange execution.

### Overall Architecture & Workflow
The system is divided into three distinct microservices:
1. **Price Data Backend (Node.js/Express)**: Connects to Binance WebSockets, listens to price ticks for specified assets (e.g., BTC, ETH, SOL, ADA), and logs them to a MongoDB database.
2. **Signal & Trading Engine (Python/FastAPI)**: A background asynchronous loop that constantly polls MongoDB for the latest data, computes technical indicators, generates trading decisions (Alpha Stream), runs them through a strict risk manager, and updates a virtual paper trading account.
3. **Frontend Dashboard (React/Vite)**: A UI that continuously polls the backend for live prices (via Node) and the current trading state (via FastAPI) to display active positions, real-time PnL, and market intelligence.

---

## 2. Folder Structure Explanation

```text
/treading bot
├── backend/                  # Node.js Data Ingestion Service
│   ├── src/
│   │   ├── config/           # Database connection logic
│   │   ├── controllers/      # Express route controllers
│   │   ├── models/           # Mongoose schemas (Price)
│   │   ├── routes/           # Express API endpoints
│   │   └── services/         # Binance WebSocket logic
│   └── server.js             # Node.js entry point
├── frontend/                 # React UI Dashboard
│   ├── src/
│   │   ├── api/              # Axios/Fetch wrappers for API calls
│   │   ├── hooks/            # Custom React hooks (useLivePrice)
│   │   ├── pages/            # Main React components (Dashboard)
│   │   └── index.css         # Styling system
│   └── index.html            # Vite entry HTML
├── signal-engine/            # Python Algorithmic Trading Core
│   ├── services/
│   │   ├── config.py         # Environment variables & constants
│   │   ├── db.py             # MongoDB connection & Motor async driver
│   │   ├── indicators.py     # Pandas TA mathematical calculations
│   │   ├── signal_engine.py  # Generates BUY/SELL/HOLD from indicators
│   │   ├── risk_engine.py    # Filters trades and sizes positions
│   │   ├── portfolio_engine.py # Portfolio allocation logic
│   │   ├── paper_trading_engine.py # Virtual exchange / state tracking
│   │   ├── trading_loop.py   # Async loop orchestrating the pipeline
│   │   ├── system_runner.py  # Lifecycle manager for FastAPI
│   │   └── schemas.py        # Pydantic data validation models
│   ├── tests/                # Pytest unit testing suite
│   └── main.py               # FastAPI entry point & API endpoints
├── docker-compose.yml        # Orchestrates MongoDB container
└── start_all.bat             # Startup script for Windows environments
```

---

## 3. File-by-File Breakdown

### `backend/` (Data Ingestion Layer)

*   **`server.js`**: Core entry point. Initializes Express, mounts routes, starts the Binance WebSocket service.
*   **`src/config/db.js`**: Connects to the local MongoDB instance using Mongoose.
*   **`src/models/Price.js`**: Mongoose Schema defining how tick data (symbol, price, timestamp) is stored.
*   **`src/controllers/priceController.js`**: Handles HTTP requests to fetch the absolute latest price from the DB.
*   **`src/services/binanceWS.js`**: Maintains a continuous WebSocket connection to Binance, formats the incoming ticks, and saves them to MongoDB.

### `frontend/` (Presentation Layer)

*   **`src/pages/Dashboard.jsx`**: The main view. Renders the Control Center, Live Market Prices (2x2 grid), Active Positions table, and Alpha Stream.
*   **`src/hooks/useLivePrice.js`**: A custom hook that polls the Node backend every 1 second, maintaining a dictionary of the latest prices and tracking directional changes (up/down).
*   **`src/api/dashboard.js` & `prices.js`**: Encapsulates all `fetch()` calls to keep the UI components clean.
*   **`src/index.css`**: Vanilla CSS providing the premium "glassmorphism" aesthetic, grid layouts, and color variables.

### `signal-engine/services/` (Trading Logic Layer)

*   **`main.py`**: The FastAPI server. Exposes the `/dashboard` endpoint and manages the `lifespan` context (auto-starting the trading loop on boot).
*   **`config.py`**: Loads parameters like `BASE_THRESHOLD`, `MAX_RISK_PER_TRADE`, and handles environment variables.
*   **`db.py`**: Uses `motor` (Async MongoDB driver) to fetch historical data chunks formatted as Pandas DataFrames.
*   **`indicators.py`**: A pure math module that uses `pandas` to calculate RSI, SMA, and ATR.
*   **`signal_engine.py`**: The "Brain". Analyzes the indicators to score the market from -1.0 to 1.0 and emits BUY/SELL/HOLD signals.
*   **`risk_engine.py`**: The "Shield". Validates signals against strict rules (drawdown limits, max exposure, volatility). Calculates Stop Loss (SL) and Take Profit (TP) via ATR.
*   **`portfolio_engine.py`**: The "Allocator". Decides which signals to prioritize if multiple are generated simultaneously.
*   **`paper_trading_engine.py`**: The "Ledger". Simulates an exchange account. Tracks balance, equity, and logs virtual trades to a local `paper_state.json` file.
*   **`trading_loop.py`**: The "Heartbeat". An infinite `asyncio` loop running every 5 seconds. Connects the DB -> Signal -> Risk -> Portfolio -> Paper engines.
*   **`system_runner.py`**: A wrapper combining the `TradingLoop` and `PaperAccount` so the FastAPI endpoints can easily query the total system state.
*   **`schemas.py`**: Pydantic models ensuring data consistency between all Python modules (e.g., `RiskDecision`, `AccountState`, `SignalResponse`).

---

## 4. Function-by-Function Explanation

### `signal-engine/services/trading_loop.py`

*   **`__init__`**: Sets up state variables, locks, and default symbols.
*   **`start()` / `stop()`**: Safely spins up or tears down the `asyncio` background task.
*   **`run()`**: The infinite `while True` loop that sleeps for `settings.paper_loop_interval` between cycles.
*   **`_execute_cycle()`**: 
    *   *Input*: None (fetches from DB).
    *   *Logic*: Updates open positions -> Generates signals -> Evaluates Risk -> Allocates Portfolio -> Opens new trades.
    *   *Side effects*: Modifies the `PaperAccount` state, saves to JSON.

### `signal-engine/services/signal_engine.py`

*   **`generate_signal(df, symbol)`**:
    *   *Input*: Pandas DataFrame of prices.
    *   *Logic*: Computes RSI, SMA50/200, ATR. Calculates momentum and trend strength. Assigns weights based on market regime (Trending vs. Sideways). Emits a score. If `score > threshold`, returns BUY/SELL.
    *   *Return*: `SignalResponse` or `ErrorResponse`.

### `signal-engine/services/risk_engine.py`
*   **`evaluate_risk(signal_result, account_state)`**:
    *   *Logic*: Runs through 7 hardcoded filters (Signal Type, Confidence, Volatility, Active Trades, Drawdown, Exposure, Correlation).
    *   *Dependencies*: Calls `compute_stop_loss` (entry - ATR * multiplier) and `compute_position_size` (Risk Dollar Amount / Stop Distance).
    *   *Return*: `RiskDecision(execute=True/False)`.

### `frontend/src/pages/Dashboard.jsx`
*   **`LivePriceWidget()`**: Maps over the `prices` object provided by `useLivePrice()` and renders a 2x2 grid. Applies green/red text classes based on tick direction.
*   **`PositionsList()`**: Takes `positions` and `prices`. Calculates real-time PnL directly in the browser using the formula `(LivePrice - EntryPrice) / EntryPrice * Size`.

---

## 5. Engine & Strategy Logic

### How the Trading Engine Works
The strategy is a **Momentum-Trend Hybrid**. 
1. **Indicator Calculation**: It uses RSI (14) for momentum, SMA(50) for short trend, SMA(200) for long trend, and ATR(14) for volatility.
2. **Market Regime Detection**: It compares SMA50 to SMA200. If they are diverging sharply, it labels the market `TRENDING`. If they are flat/converging, it labels it `SIDEWAYS`.
3. **Dynamic Weighting**: If `TRENDING`, trend indicators get higher mathematical weight. If `SIDEWAYS`, mean-reversion (RSI) gets higher weight.
4. **Signal Thresholds**: A final score between -1.0 and 1.0 is generated. If it crosses a baseline threshold (e.g., `0.10`), a BUY/SELL is triggered.

### Risk Management Logic

Risk is heavily controlled using professional standards
:
*   **Stop Loss (SL)**: Dynamic, based on Volatility (ATR). `Stop Loss = Entry Price ± (ATR * Multiplier)`.
*   **Take Profit (TP)**: Fixed ratio based on Stop Loss distance (e.g., 1:2 Risk/Reward).
*   **Position Sizing**: **Crucial mechanic.** The bot risks the *exact same dollar amount* every trade. `Size = Risk Amount / Stop Loss Distance`. Wide stops result in smaller positions; tight stops result in larger positions.
*   **Circuit Breakers**: Will halt trading if total portfolio drawdown exceeds a set percentage.

---

## 6. System Flow

### Startup Flow

1. User runs `docker-compose up -d` to start MongoDB.
2. User starts the Node Backend (`npm start`). It connects to Binance WS and begins filling the database.
3. User starts the Python FastAPI Server. The `@asynccontextmanager lifespan` executes, auto-starting the `TradingLoop`.
4. User starts the React Frontend. It mounts, calls `/dashboard` via HTTP and `/api/v1/prices/latest` via HTTP polling.

### Strategy Execution Flow (The Loop)

1. **Fetch**: `db.py` pulls the last N candles for BTC, ETH, SOL, ADA.
2. **Update**: Engine checks current open positions. If current price crosses SL or TP, the position is closed, PnL is applied to balance, and trade is logged.
3. **Signal**: `signal_engine.py` processes the fresh candles.
4. **Risk**: `risk_engine.py` verifies the portfolio has enough free margin and the signal is safe.
5. **Execute**: Trade is appended to `paper_account.open_positions`.
6. **Sleep**: Loop yields control back to `asyncio` for 5 seconds.

---

## 7. Dependencies & External Services

### External Services

*   **Binance WebSocket API**: Free, public stream used to get live price tickers (`wss://stream.binance.com:9443/ws/!ticker@arr`).
*   **MongoDB**: Local NoSQL storage for high-speed write/read of price ticks.

### Core Libraries

*   **Python**: `fastapi` (API), `motor` (Async Mongo), `pandas` (Math/DataFrames), `pydantic` (Data Validation).
*   **Node.js**: `express` (API), `mongoose` (DB), `ws` (WebSockets).
*   **React**: `vite` (Bundler), `react-dom` (UI).

---

## 8. Code Relationships

*   `main.py` is the absolute root of the Python side. It instantiates the singleton `TradingSystem` (from `system_runner.py`).
*   `system_runner.py` owns both the `TradingLoop` and the `PaperAccount`.
*   `TradingLoop` owns the execution cycle and sequentially imports and calls `generate_signal()`, `evaluate_risk()`, and `allocate_portfolio()`.
*   The **React Frontend** is completely decoupled from the Python Backend. They communicate exclusively through the JSON contract provided by `/dashboard`.

---

## 9. Important Notes & Limitations

### Known Limitations

1. **No Live Execution**: The system currently only writes to `paper_state.json`. Integration with ccxt or Binance REST API is required for real money trading.
2. **Polling over WebSockets (Frontend)**: The React dashboard currently uses `setInterval` polling (every 1s) to get prices from Node, and (every 3s) to get dashboard state from Python. For a true institutional app, both APIs should be refactored to emit WebSocket events to the frontend to reduce HTTP overhead.
3. **Timeframe Simulation Gap**: The paper trading engine triggers exits based on the *latest received tick*. In real life, intra-candle wicks might hit a stop-loss that a close-price-based simulation might miss.

### Technical Debt & Improvements

*   **Database Cleanup**: The Node backend continuously writes ticks to MongoDB. Without a TTL (Time To Live) index or a cron job to prune old data, the database will eventually consume the entire hard drive.
*   **Decimal Handling**: Floating point math is used for currency (`float`). For production crypto systems, standard practice dictates using the `decimal` library to prevent micro-rounding errors.

---

*Documentation auto-generated and maintained by the Chain-Mind Engineering Team.*
