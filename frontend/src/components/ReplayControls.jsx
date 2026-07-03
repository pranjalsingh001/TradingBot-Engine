import React, { useState, useEffect } from 'react';
import { fetchReplayStatus, startReplay, pauseReplay, resumeReplay, stopReplay } from '../api/dashboard';

export default function ReplayControls() {
  const [status, setStatus] = useState(null);
  const [speed, setSpeed] = useState(1.0);
  const [startDate, setStartDate] = useState("2024-01-01T00:00:00");
  const [endDate, setEndDate] = useState("2024-02-01T00:00:00");

  useEffect(() => {
    const timer = setInterval(() => {
      fetchReplayStatus().then(setStatus).catch(() => {});
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatISO = (dateStr) => {
    // If it's just YYYY-MM-DDTHH:MM, add :00
    if (dateStr.length === 16) return dateStr + ":00Z";
    if (dateStr.length === 19) return dateStr + "Z";
    return dateStr;
  };

  const handleStart = () => {
    const sDate = formatISO(startDate);
    const eDate = formatISO(endDate);
    startReplay("BTCUSDT", "1m", sDate, eDate, speed);
  };

  return (
    <div className="glass-panel">
      <div className="panel-header" style={{ padding: '12px 20px' }}>
        <h2 style={{ fontSize: '0.85rem' }}>Replay Engine</h2>
        <span className={`badge ${status?.is_running ? 'badge-live' : 'badge-stopped'}`} style={{ fontSize: '0.65rem' }}>
          {status?.is_running ? (status?.is_paused ? 'Paused' : 'Running') : 'Stopped'}
        </span>
      </div>
      <div className="panel-content" style={{ padding: '16px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '12px' }}>
          <input type="datetime-local" value={startDate} onChange={e => setStartDate(e.target.value)} disabled={status?.is_running} style={{ flex: '1 1 auto', padding: '6px 10px', fontSize: '0.8rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px', color: '#fff' }} />
          <input type="datetime-local" value={endDate} onChange={e => setEndDate(e.target.value)} disabled={status?.is_running} style={{ flex: '1 1 auto', padding: '6px 10px', fontSize: '0.8rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px', color: '#fff' }} />
          <select value={speed} onChange={e => setSpeed(Number(e.target.value))} disabled={status?.is_running} style={{ flex: '1 1 auto', padding: '6px 10px', fontSize: '0.8rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '6px', color: '#fff' }}>
            <option value={1.0}>1x Speed</option>
            <option value={10.0}>10x Speed</option>
            <option value={100.0}>100x Speed</option>
            <option value={0.0}>Max Speed</option>
          </select>
        </div>
        <div className="control-grid" style={{ gap: '8px' }}>
          {!status?.is_running ? (
            <button className="btn-premium" onClick={handleStart} style={{ padding: '10px' }}>Start Replay</button>
          ) : (
            <>
              {status?.is_paused ? (
                <button className="btn-premium active" onClick={resumeReplay} style={{ padding: '10px' }}>Resume</button>
              ) : (
                <button className="btn-premium" onClick={pauseReplay} style={{ padding: '10px' }}>Pause</button>
              )}
              <button className="btn-premium text-down" onClick={stopReplay} style={{ padding: '10px' }}>Stop</button>
            </>
          )}
        </div>
        {status?.is_running && status?.current_time && (
          <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center' }}>
            Time: {new Date(status.current_time).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}
