const WebSocket = require('ws');
const Price = require('../models/Price');

const SYMBOL = 'btcusdt';
const INTERVALS = ['1m', '5m', '15m'];
const RECONNECT_DELAY_MS = 5000;

let ws = null;
let reconnectTimer = null;

// Throttling: track last save time per interval so we can "upsert" live candles to DB
const lastSaveTimes = {};

/**
 * Stores/Upserts an OHLCV candle to MongoDB.
 */
const saveKlineRecord = async (symbol, kline, isFinal, interval) => {
  try {
    const timestamp = new Date(kline.t); // Start time of the candle
    const open = parseFloat(kline.o);
    const high = parseFloat(kline.h);
    const low = parseFloat(kline.l);
    const close = parseFloat(kline.c);
    const volume = parseFloat(kline.v);

    await Price.updateOne(
      { symbol: symbol.toUpperCase(), timestamp: timestamp, interval: interval },
      {
        $set: {
          price: close, // backward compatibility
          open, high, low, volume,
        }
      },
      { upsert: true }
    );
  } catch (err) {
    console.error(`[WS] Failed to save kline for ${symbol} (${interval}):`, err.message);
  }
};

const scheduleReconnect = () => {
  if (reconnectTimer) return;
  console.log(`[WS] Reconnecting in ${RECONNECT_DELAY_MS / 1000}s…`);
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_DELAY_MS);
};

const connect = () => {
  // Binance Multi-Stream URL for Klines
  const streams = INTERVALS.map(i => `${SYMBOL}@kline_${i}`).join('/');
  const url = `wss://stream.binance.com:9443/stream?streams=${streams}`;

  console.log(`[WS] Connecting to Kline Multi-Stream: ${streams}`);
  ws = new WebSocket(url);

  ws.on('open', () => {
    console.log(`[WS] Connection established for ${SYMBOL} intervals: ${INTERVALS.join(', ')}`);
  });

  ws.on('message', async (data) => {
    try {
      const payload = JSON.parse(data);
      if (!payload.data || !payload.data.k) return;
      const msg = payload.data;
      const symbol = msg.s;
      const kline = msg.k;
      const interval = kline.i;
      const isFinal = kline.x;

      // Upsert immediately if final, otherwise throttle upserts to every 2 seconds
      const now = Date.now();
      const trackKey = `${symbol}_${interval}`;
      if (isFinal || !lastSaveTimes[trackKey] || now - lastSaveTimes[trackKey] > 2000) {
        lastSaveTimes[trackKey] = now;
        await saveKlineRecord(symbol, kline, isFinal, interval);
      }
    } catch (err) {
      console.error('[WS] Error processing message:', err.message);
    }
  });

  ws.on('error', (err) => {
    console.error('[WS] WebSocket error:', err.message);
  });

  ws.on('close', () => {
    console.warn('[WS] Connection closed — will reconnect');
    ws = null;
    scheduleReconnect();
  });
};

const startBinanceStream = () => {
  connect();
};

module.exports = { startBinanceStream };
