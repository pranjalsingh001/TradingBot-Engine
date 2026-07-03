import { useState, useEffect, useRef, useCallback } from 'react';
import { fetchLatestPrice } from '../api/prices';

const POLL_INTERVAL_MS = 1000;

/**
 * Custom hook — polls /api/v1/prices/latest every second.
 * Returns: { prices, error }
 * prices is an object: { BTCUSDT: { price, direction, timestamp }, ETHUSDT: ... }
 */
export const useLivePrice = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const prevPrice = useRef(null);
  const intervalRef = useRef(null);

  const poll = useCallback(async () => {
    try {
      const latest = await fetchLatestPrice();
      setError(null);

      let dir = null;
      if (prevPrice.current !== null) {
        if (latest.price > prevPrice.current) dir = 'up';
        else if (latest.price < prevPrice.current) dir = 'down';
      }
      prevPrice.current = latest.price;

      setData({ ...latest, direction: dir });
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    poll(); // immediate first fetch
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [poll]);

  return { data, error };
};
