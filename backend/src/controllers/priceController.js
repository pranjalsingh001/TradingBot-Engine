const Price = require('../models/Price');

/**
 * GET /api/v1/prices/latest
 * Returns the single most recent BTCUSDT price record.
 */
const getLatestPrice = async (req, res) => {
  try {
    const latest = await Price.findOne({ interval: '1m', symbol: 'BTCUSDT' }).sort({ timestamp: -1 }).lean();

    if (!latest) {
      return res.status(404).json({ error: 'No price data available yet' });
    }

    return res.json({
      symbol: latest.symbol,
      price: latest.price,
      timestamp: latest.timestamp,
    });
  } catch (err) {
    console.error('[Controller] getLatestPrice error:', err.message);
    return res.status(500).json({ error: 'Internal server error' });
  }
};

module.exports = { getLatestPrice };
