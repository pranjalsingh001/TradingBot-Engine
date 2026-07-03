const mongoose = require('mongoose');

const priceSchema = new mongoose.Schema(
  {
    symbol: {
      type: String,
      required: true,
      index: true,
    },
    price: {
      type: Number,
      required: true,
    },
    open: {
      type: Number,
    },
    high: {
      type: Number,
    },
    low: {
      type: Number,
    },
    volume: {
      type: Number,
    },
    interval: {
      type: String,
      required: true,
      default: '5m',
      index: true,
    },
    timestamp: {
      type: Date,
      required: true,
      index: true,
    },
  },
  { versionKey: false }
);

// Compound index: latest record per symbol is fast to query
priceSchema.index({ timestamp: -1 });

module.exports = mongoose.model('Price', priceSchema);
