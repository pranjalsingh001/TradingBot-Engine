import React, { useEffect, useState } from "react";
import { fetchDashboard, startTrading, stopTrading, resetSystem, fetchAnalytics } from "../api/dashboard";
import { useLivePrice } from "../hooks/useLivePrice";
import ReplayControls from "../components/ReplayControls";
import WalkForwardReport from "../components/WalkForwardReport";
import SessionComparison from "../components/SessionComparison";
import IntelligencePanel from "../components/IntelligencePanel";
import "../index.css";

const fmt = {
  price: (n) => {
    if (n == null) return "—";
    const num = Number(n);
    if (num < 1) return num.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 6 });
    if (num < 100) return num.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 4 });
    return num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },
  pct: (n) => (n == null ? "—" : `${(Number(n)).toFixed(2)}%`),
  time: (iso) => (iso ? new Date(iso).toLocaleTimeString("en-US", { hour12: false }) : "—"),
  compact: (n) => Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n || 0)
};

// ── Components ───────────────────────────────────────────────────────────────

const StatsOverview = ({ account }) => {
  const stats = [
    { label: "Portfolio Equity", value: `$${fmt.price(account?.equity)}`, sub: `Peak: $${fmt.price(account?.peak_balance)}` },
    { label: "Total Return", value: fmt.pct(account?.total_return_pct), sub: "All time", color: account?.total_return_pct >= 0 ? "text-up" : "text-down" },
    { label: "Win Rate", value: fmt.pct((account?.win_rate || 0) * 100), sub: `${account?.total_trades || 0} trades` },
    { label: "Max Drawdown", value: fmt.pct(account?.drawdown), sub: "Risk buffer", color: "text-down" },
  ];

  return (
    <div className="stats-overview">
      {stats.map((s, i) => (
        <div key={i} className="overview-card">
          <span className="overview-label">{s.label}</span>
          <span className={`overview-value ${s.color || ""}`}>{s.value || "—"}</span>
          <span className="overview-change">{s.sub}</span>
        </div>
      ))}
    </div>
  );
};


const LivePriceWidget = ({ data, error }) => {
  return (
    <div className="glass-panel" style={{ padding: '40px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '200px' }}>
      {(!data && !error) && (
        <>
          <div className="price-symbol" style={{ opacity: 0.5 }}>Waiting for live data...</div>
          <div className="price-main" style={{ fontSize: '2rem' }}>Connecting...</div>
        </>
      )}
      {data && (
        <>
          <div className="price-symbol" style={{ fontSize: '1.2rem', marginBottom: '16px', color: 'var(--accent)', letterSpacing: '0.1em' }}>
            BTC / USDT (Live)
          </div>
          <div className={`price-main ${data.direction || ""}`} style={{ fontSize: '3rem', marginBottom: 0 }}>
            ${fmt.price(data.price)}
          </div>
        </>
      )}
      {error && <div className="text-down" style={{fontSize: '0.8rem', marginTop: '16px'}}>⚠ Connection Interrupted</div>}
    </div>
  );
};

const ControlCenter = ({ running, onUpdate }) => {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action) => {
    setLoading(true);
    try {
      if (action === "start") await startTrading();
      if (action === "stop") await stopTrading();
      if (action === "reset") await resetSystem();
      onUpdate();
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel">
      <div className="panel-header">
        <h2>Control Center</h2>
        <span className={`badge ${running ? "badge-live" : "badge-stopped"}`}>
          {running ? "Active" : "Stopped"}
        </span>
      </div>
      <div className="panel-content">
        <div className="control-grid">
          <button className={`btn-premium ${running ? "active" : ""}`} disabled={running || loading} onClick={() => handleAction("start")}>
            <span>Start</span>
          </button>
          <button className="btn-premium" disabled={!running || loading} onClick={() => handleAction("stop")}>
            <span>Stop</span>
          </button>
          <button className="btn-premium" disabled={loading} onClick={() => handleAction("reset")}>
            <span>Reset</span>
          </button>
        </div>
      </div>
    </div>
  );
};

const PositionsList = ({ positions, liveData }) => (
  <div className="glass-panel">
    <div className="panel-header">
      <h2>Active Positions</h2>
      <span className="badge badge-regime">{positions?.length || 0} Open</span>
    </div>
    <div className="table-container">
      <table className="custom-table">
        <thead>
          <tr>
            <th>Asset</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Stop Loss</th>
            <th>Take Profit</th>
            <th>PnL (Live)</th>
          </tr>
        </thead>
        <tbody>
          {(!positions || positions.length === 0) ? (
            <tr><td colSpan="6" style={{ textAlign: "center", color: "var(--text-muted)", padding: "40px" }}>No active risk exposure</td></tr>
          ) : (
            positions.map((p, i) => {
              const livePrice = liveData ? liveData.price : p.entry_price;
              const isBuy = p.side === "BUY";
              const returnPct = isBuy ? (livePrice - p.entry_price) / p.entry_price : (p.entry_price - livePrice) / p.entry_price;
              const livePnl = p.position_size * returnPct;
              
              return (
                <tr key={i}>
                  <td className="symbol-cell">{p.symbol}</td>
                  <td className={p.side === "BUY" ? "text-up" : "text-down"}>{p.side}</td>
                  <td className="text-mono">${fmt.price(p.entry_price)}</td>
                  <td className="text-mono text-down">${fmt.price(p.stop_loss)}</td>
                  <td className="text-mono text-up">${fmt.price(p.take_profit)}</td>
                  <td className={`pnl-cell ${livePnl >= 0 ? "text-up" : "text-down"}`}>
                    {livePnl >= 0 ? "+" : ""}{fmt.price(livePnl)} ({fmt.pct(returnPct * 100)})
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  </div>
);

const SignalStream = ({ signals }) => (
  <div className="glass-panel">
    <div className="panel-header">
      <h2>Alpha Stream</h2>
    </div>
    <div className="table-container">
      <table className="custom-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Decision</th>
            <th>Strategy</th>
            <th>Confidence</th>
            <th>Risk Status</th>
          </tr>
        </thead>
        <tbody>
          {(!signals || signals.length === 0) ? (
            <tr><td colSpan="5" style={{ textAlign: "center", color: "var(--text-muted)", padding: "40px" }}>Awaiting signals...</td></tr>
          ) : (
            signals.map((s, i) => (
              <tr key={i}>
                <td className="symbol-cell">{s.symbol}</td>
                <td>
                  <span className={`badge ${s.signal === "BUY" || s.signal === "LONG" ? "badge-live" : s.signal === "SELL" || s.signal === "SHORT" ? "badge-stopped" : "badge-neutral"}`}>
                    {s.signal}
                  </span>
                </td>
                <td>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                       <span style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>{s.strategy_id || 'UNKNOWN'}</span>
                    </div>
                </td>
                <td className="text-mono">{(s.confidence * 100).toFixed(0)}%</td>
                <td>
                   <div style={{ display: 'flex', flexDirection: 'column' }}>
                     <span className={`badge ${s.risk_status === 'ACCEPTED' ? 'badge-live' : (s.signal === 'NONE' ? 'badge-neutral' : 'badge-stopped')}`} style={{ fontSize: '10px' }}>
                       {s.signal === 'NONE' ? 'NO SIGNAL' : (s.risk_status || 'PENDING')}
                     </span>
                     {s.quantity && s.risk_status === 'ACCEPTED' && (
                       <span style={{ fontSize: '10px', opacity: 0.7, marginTop: '4px' }}>
                         Size: {Number(s.quantity).toFixed(4)}
                       </span>
                     )}
                     {s.risk_status !== 'ACCEPTED' && s.risk_reason && (
                       <span style={{ fontSize: '10px', opacity: 0.7, marginTop: '4px' }}>
                         {s.risk_reason}
                       </span>
                     )}
                   </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  </div>
);

const AnalyticsCards = ({ analytics }) => {
  const [isExpanded, setIsExpanded] = React.useState(true);
  if (!analytics || analytics.error) {
    return (
      <div className="glass-panel">
        <div className="panel-header">
          <h2>Intelligence Layer</h2>
        </div>
        <div className="panel-content text-dim" style={{textAlign: 'center', padding: '40px'}}>
          Awaiting market data for modeling...
        </div>
      </div>
    );
  }

  const regimeKeys = Object.keys(analytics.regime_performance || {});
  return (
    <div className={`glass-panel panel-collapsible ${!isExpanded ? 'panel-collapsed' : ''}`}>
      <div className="panel-header" onClick={() => setIsExpanded(!isExpanded)}>
        <h2>Intelligence Layer</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className="badge badge-regime">{analytics.total_trades} Modeled</span>
          <span className="panel-chevron">▼</span>
        </div>
      </div>
      <div className="panel-content">
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span className="overview-label">Engine Win Rate</span>
            <span className="text-mono">{(analytics.win_rate * 100).toFixed(1)}%</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span className="overview-label">Profit Factor</span>
            <span className="text-mono">{analytics.profit_factor > 999 ? "∞" : analytics.profit_factor.toFixed(2)}</span>
          </div>
          
          <div style={{marginTop: "4px", borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "8px"}}>
            <span className="overview-label" style={{display: "block", marginBottom: "4px", fontSize: '0.7rem'}}>Regime Edge (Win Rate)</span>
            {regimeKeys.map(r => (
               <div key={r} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", marginBottom: "2px" }}>
                 <span style={{color: "var(--text-muted)"}}>{r}</span>
                 <span className={analytics.regime_performance[r].win_rate > 0.5 ? "text-up" : "text-down"}>
                   {(analytics.regime_performance[r].win_rate * 100).toFixed(0)}% ({analytics.regime_performance[r].total})
                 </span>
               </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Main Dashboard ───────────────────────────────────────────────────────────

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState(null);
  const [replayMode, setReplayMode] = useState(false);
  const { data: liveData, error: liveError } = useLivePrice();

  const loadData = () => {
    fetchDashboard()
      .then(setData)
      .catch(() => setError("Backend unreachable"));
      
    fetchAnalytics()
      .then(setAnalytics)
      .catch(() => {});
  };

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 3000);
    return () => clearInterval(timer);
  }, []);

  const toggleReplayMode = async () => {
    if (replayMode) {
      // Exiting Replay Mode: Stop the engine on backend
      try {
        await fetch(`${settings.signal_engine_url}/api/v1/replay/stop`, { method: 'POST' });
      } catch (err) {
        console.error("Failed to stop replay engine:", err);
      }
    }
    setReplayMode(!replayMode);
  };

  return (
    <div className="dashboard-container">
      <header className="dashboard-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="brand">
          <div className="brand-icon">⚡</div>
          <h1>TradingBot <span style={{opacity: 0.5, fontWeight: 400, fontSize: '0.9rem', marginLeft: '8px', verticalAlign: 'middle'}}>Institutional</span></h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          {error && <div className="badge badge-stopped">⚠ {error}</div>}
          <button 
            className={`btn-premium ${replayMode ? 'active' : ''}`} 
            onClick={toggleReplayMode}
            style={{ padding: '8px 16px', fontSize: '0.9rem' }}
          >
            {replayMode ? 'Exit Replay Mode' : 'Enter Replay Mode'}
          </button>
        </div>
      </header>

      <StatsOverview account={data?.account} />

      <div className="main-grid">
        <div className="grid-stack">
          {replayMode ? (
            <>
              <ReplayControls />
              <IntelligencePanel />
              <SessionComparison />
              <WalkForwardReport />
              <AnalyticsCards analytics={analytics} />
            </>
          ) : (
            <>
              <LivePriceWidget data={liveData} error={liveError} />
              <ControlCenter running={data?.running} onUpdate={loadData} />
              <IntelligencePanel />
              <AnalyticsCards analytics={analytics} />
            </>
          )}
        </div>

        <div className="grid-stack">
          {replayMode && (
            <LivePriceWidget data={liveData} error={liveError} />
          )}
          <PositionsList positions={data?.positions} liveData={liveData} />
          <SignalStream signals={data?.signals} />
        </div>
      </div>
    </div>
  );
}
