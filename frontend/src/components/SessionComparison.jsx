import React, { useEffect, useState } from "react";
import { fetchReplaySessions } from "../api/dashboard";

const fmt = {
  price: (n) => {
    if (n == null) return "—";
    const num = Number(n);
    const sign = num >= 0 ? "+" : "";
    return `${sign}$${Math.abs(num).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  },
  pct: (n) => (n == null ? "—" : `${(Number(n) * 100).toFixed(2)}%`),
  time: (iso) => (iso ? new Date(iso).toLocaleString("en-US", { 
    month: 'short', 
    day: 'numeric', 
    hour: '2-digit', 
    minute: '2-digit' 
  }) : "—")
};

const SessionComparison = () => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isExpanded, setIsExpanded] = useState(true);

  const loadSessions = async () => {
    try {
      const data = await fetchReplaySessions();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSessions();
    const interval = setInterval(loadSessions, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading && sessions.length === 0) return null;
  if (sessions.length === 0) return null;

  return (
    <div className={`glass-panel panel-collapsible ${!isExpanded ? 'panel-collapsed' : ''}`} style={{ marginTop: '0' }}>
      <div className="panel-header" onClick={() => setIsExpanded(!isExpanded)}>
        <h2>Replay Session History</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span className="badge">{sessions.length} Runs</span>
          <span className="panel-chevron">▼</span>
        </div>
      </div>
      <div className="panel-content" style={{ padding: '0' }}>
        <div className="scrollable-table">
          <table className="custom-table">
            <thead>
              <tr>
                <th>Date</th>
                <th className="text-right">Final PnL</th>
                <th className="text-right">Win Rate</th>
                <th className="text-right">Trades</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s, i) => (
                <tr key={i}>
                  <td className="text-dim" style={{ fontSize: '0.75rem' }}>{fmt.time(s.timestamp)}</td>
                  <td className={`text-right text-mono ${s.pnl >= 0 ? "text-up" : "text-down"}`} style={{ fontSize: '0.8rem' }}>
                    {fmt.price(s.pnl)}
                  </td>
                  <td className="text-right text-mono" style={{ fontSize: '0.8rem' }}>{fmt.pct(s.win_rate)}</td>
                  <td className="text-right text-mono" style={{ fontSize: '0.8rem' }}>{s.total_trades}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default SessionComparison;
