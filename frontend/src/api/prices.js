const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

/**
 * Fetches the latest BTCUSDT price from the backend API.
 * @returns {Promise<{symbol: string, price: number, timestamp: string}>}
 */
export const fetchLatestPrice = async () => {
  const res = await fetch(`${API_URL}/api/v1/prices/latest`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
};
