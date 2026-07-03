import { useLivePrice } from './hooks/useLivePrice';
import './index.css';

// ── Helpers ──────────────────────────────────────────────────────────────────
const fmt = {
  price: (n) =>
    n == null ? '—' : Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),

  time: (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour12: false });
  },

  datetime: (iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('en-US', { hour12: false });
  },
};

// ── Sub-components ───────────────────────────────────────────────────────────
const StatusPill = ({ error, hasData }) => {
  const cls   = error ? 'error' : hasData ? 'live' : '';
  const label = error ? 'API Error' : hasData ? 'Live' : 'Connecting…';
  return (
    <div className={`status-pill ${cls}`}>
      <span className="status-indicator" />
      {label}
    </div>
  );
};

const PriceCard = ({ data, direction }) => {
  const loading = data == null;
  return (
    <div className="price-card">
      <p className="pair-label">BTC / USDT</p>

      <p className={`price-value ${direction ?? ''} ${loading ? 'skeleton' : ''}`}>
        ${fmt.price(data?.price)}
      </p>
      <p className="price-usd">United States Dollar</p>

      <div className="divider" />

      <div className="meta-row">
        <span>Last update <strong>{fmt.datetime(data?.timestamp)}</strong></span>
        <span>Binance</span>
      </div>
    </div>
  );
};

const StatsStrip = ({ count, direction, data }) => {
  const changeClass = direction === 'up' ? 'green' : direction === 'down' ? 'red' : '';
  const changeIcon  = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '—';

  return (
    <div className="stats-strip">
      <div className="stat-box">
        <p className="stat-label">Updates</p>
        <p className="stat-value">{count}</p>
      </div>
      <div className="stat-box">
        <p className="stat-label">Trend</p>
        <p className={`stat-value ${changeClass}`}>{changeIcon}</p>
      </div>
      <div className="stat-box">
        <p className="stat-label">Symbol</p>
        <p className="stat-value" style={{ fontSize: '1rem' }}>{data?.symbol ?? '—'}</p>
      </div>
    </div>
  );
};

const LogFeed = ({ log }) => (
  <div className="log-card">
    <div className="log-header">
      <span>Price Log</span>
      <span>{log.length} entries</span>
    </div>
    <div className="log-body">
      {log.length === 0 && (
        <div className="log-entry">
          <span className="log-time">Waiting for data…</span>
        </div>
      )}
      {log.map((entry, i) => (
        <div className="log-entry" key={i}>
          <span className="log-time">{fmt.time(entry.timestamp)}</span>
          <span className="log-price">${fmt.price(entry.price)}</span>
        </div>
      ))}
    </div>
  </div>
);

// ── Root App ─────────────────────────────────────────────────────────────────
import React from 'react';
import Dashboard from './pages/Dashboard';
import './index.css';

export default function App() {
  return (
    <div className="app">
      <Dashboard />
    </div>
  );
}
