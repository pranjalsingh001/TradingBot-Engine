const mongoose = require('mongoose');

const connectDB = async () => {
  try {
    const conn = await mongoose.connect(process.env.MONGO_URI, {
      serverSelectionTimeoutMS: 5000, // fail fast if unreachable
    });
    console.log(`[DB] MongoDB connected: ${conn.connection.host}`);
  } catch (err) {
    console.error(`[DB] Connection error: ${err.message}`);
    console.error('[DB] Make sure MongoDB is running or MONGO_URI is set to Atlas.');
    process.exit(1);
  }
};

module.exports = connectDB;
