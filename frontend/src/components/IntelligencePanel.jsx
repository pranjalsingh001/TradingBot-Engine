import React, { useState, useEffect } from 'react';
import { fetchDashboard } from '../api/dashboard';

const IntelligencePanel = () => {
    const [signal, setSignal] = useState(null);
    const [isExpanded, setIsExpanded] = useState(true);

    useEffect(() => {
        const timer = setInterval(() => {
            fetchDashboard().then(data => {
                if (data?.signals?.length > 0) {
                    setSignal(data.signals[0]);
                }
            });
        }, 3000);
        return () => clearInterval(timer);
    }, []);

    if (!signal) return null;

    return (
        <div className={`glass-panel panel-collapsible ${!isExpanded ? 'panel-collapsed' : ''}`} style={{ marginTop: '0' }}>
            <div className="panel-header" onClick={() => setIsExpanded(!isExpanded)}>
                <h2>🧠 Execution Intelligence</h2>
                <span className="panel-chevron">▼</span>
            </div>
            <div className="panel-content">
                <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginBottom: '12px' }}>
                    Active execution parameters based on real-time market regime mapping:
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Target Regime</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: '700', color: 'var(--accent)' }}>{signal.regime}</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Active Strategy</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: '700', color: 'var(--accent)' }}>{signal.strategy_id}</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Confidence</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: '700', color: 'var(--accent)' }}>{((signal.confidence || 0) * 100).toFixed(0)}%</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Volatility (ATR)</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: '700', color: 'var(--accent)' }}>{signal.indicators?.atr?.toFixed(2) || '—'}</div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default IntelligencePanel;
