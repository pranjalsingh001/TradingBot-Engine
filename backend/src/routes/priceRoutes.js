const express = require('express');
const { getLatestPrice } = require('../controllers/priceController');

const router = express.Router();

// GET /api/v1/prices/latest
router.get('/latest', getLatestPrice);

module.exports = router;
