const API_BASE = "http://localhost:9000";

export async function fetchDashboard() {
  const res = await fetch(`${API_BASE}/dashboard`);
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

export async function startTrading() {
  const res = await fetch(`${API_BASE}/system/start`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to start");
  return res.json();
}

export async function stopTrading() {
  const res = await fetch(`${API_BASE}/system/stop`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to stop");
  return res.json();
}

export async function resetSystem() {
  const res = await fetch(`${API_BASE}/system/reset`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reset");
  return res.json();
}

export async function fetchAnalytics() {
  const res = await fetch(`${API_BASE}/api/v1/analytics`);
  if (!res.ok) throw new Error("Failed to fetch analytics");
  return res.json();
}

export async function fetchReplayStatus() {
  const res = await fetch(`${API_BASE}/api/v1/replay/status`);
  if (!res.ok) throw new Error("Failed to fetch replay status");
  return res.json();
}

export async function startReplay(symbol, interval, start_time, end_time, speed) {
  const res = await fetch(`${API_BASE}/api/v1/replay/start?symbol=${symbol}&interval=${interval}&start_time=${start_time}&end_time=${end_time}&speed=${speed}`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to start replay");
  return res.json();
}

export async function pauseReplay() {
  const res = await fetch(`${API_BASE}/api/v1/replay/pause`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to pause replay");
  return res.json();
}

export async function resumeReplay() {
  const res = await fetch(`${API_BASE}/api/v1/replay/resume`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to resume replay");
  return res.json();
}

export async function stopReplay() {
  const res = await fetch(`${API_BASE}/api/v1/replay/stop`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to stop replay");
  return res.json();
}

export async function fetchReplaySessions() {
  const res = await fetch(`${API_BASE}/api/v1/replay/sessions`);
  if (!res.ok) throw new Error("Failed to fetch replay sessions");
  return res.json();
}

export async function fetchWalkForwardReports() {
  const res = await fetch(`${API_BASE}/api/v1/replay/reports`);
  if (!res.ok) throw new Error("Failed to fetch walk forward reports");
  return res.json();
}
