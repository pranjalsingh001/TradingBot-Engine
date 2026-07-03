require('dotenv').config();
const express = require('express');
const cors = require('cors');
const connectDB = require('./config/db');
const priceRoutes = require('./routes/priceRoutes');
const { startBinanceStream } = require('./services/binanceWS');

const app = express();
const PORT = process.env.PORT || 5000;

// ── Middleware ─────────────────────────────────────────────────────────────
app.use(cors());
app.use(express.json());

// ── Routes ──────────────────────────────────────────────────────────────────
app.use('/api/v1/prices', priceRoutes);

// ── Health check ────────────────────────────────────────────────────────────
app.get('/health', (_req, res) => res.json({ status: 'ok' }));

// ── Bootstrap ───────────────────────────────────────────────────────────────
const bootstrap = async () => {
  await connectDB();
  startBinanceStream();

  app.listen(PORT, () => {
    console.log(`[Server] Running on http://localhost:${PORT}`);
    console.log(`[Server] Latest price → GET /api/v1/prices/latest`);
  });
};

bootstrap();
