import React, { useState, useEffect } from 'react';
import { fetchWalkForwardReports } from '../api/dashboard';

export default function WalkForwardReport() {
    const [reports, setReports] = useState([]);
    const [isExpanded, setIsExpanded] = useState(true);

    useEffect(() => {
        const timer = setInterval(() => {
            fetchWalkForwardReports().then(setReports).catch(() => {});
        }, 5000); // Poll every 5s
        
        fetchWalkForwardReports().then(setReports).catch(() => {});
        
        return () => clearInterval(timer);
    }, []);

    return (
        <div className={`glass-panel panel-collapsible ${!isExpanded ? 'panel-collapsed' : ''}`} style={{ marginTop: '0' }}>
            <div className="panel-header" onClick={() => setIsExpanded(!isExpanded)}>
                <h2>Evaluation Report</h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span className="badge badge-regime">{reports.length} Records</span>
                    <span className="panel-chevron">▼</span>
                </div>
            </div>
            <div className="panel-content" style={{ paddingBottom: '0' }}>
                <p style={{ color: 'var(--text-muted)', marginBottom: '12px', fontSize: '0.8rem' }}>
                    Tracking adaptive configurations over time.
                </p>
                <div className="scrollable-table" style={{ maxHeight: '220px' }}>
                    <table className="custom-table">
                        <thead>
                            <tr>
                                <th>Rec ID</th>
                                <th>Baseline</th>
                                <th>Edge</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {reports.length === 0 ? (
                                <tr>
                                    <td colSpan="4" style={{ textAlign: "center", color: "var(--text-muted)", padding: "30px", fontSize: '0.8rem' }}>
                                        Awaiting adaptation results...
                                    </td>
                                </tr>
                            ) : (
                                reports.map((r, i) => {
                                    const baseWinRate = r.before_metrics?.win_rate || 0;
                                    const afterWinRate = r.after_metrics?.win_rate || 0;
                                    const net = afterWinRate - baseWinRate;
                                    return (
                                        <tr key={i}>
                                            <td className="text-dim" style={{ fontSize: '0.7rem' }}>{r.recommendation_id.substring(0, 8)}</td>
                                            <td className="text-mono" style={{ fontSize: '0.8rem' }}>{(baseWinRate * 100).toFixed(1)}%</td>
                                            <td className={`text-mono ${net > 0 ? 'text-up' : net < 0 ? 'text-down' : ''}`} style={{ fontSize: '0.8rem' }}>
                                                {(afterWinRate * 100).toFixed(1)}%
                                            </td>
                                            <td>
                                                <span className={`badge ${r.status === 'APPROVED' ? 'badge-live' : 'badge-stopped'}`} style={{ padding: '2px 6px', fontSize: '0.6rem' }}>
                                                    {r.status}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
