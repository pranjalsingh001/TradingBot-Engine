import os

# Set testing mode so MongoDB Motor client is mocked during test collection
os.environ["TESTING"] = "1"

# Enforce default settings for tests to prevent custom .env files from failing strict assertions
os.environ["MIN_CONFIDENCE"] = "0.3"
os.environ["MAX_ACTIVE_TRADES"] = "3"
os.environ["MAX_POSITION_PCT"] = "0.1"
os.environ["RSI_OVERSOLD"] = "30.0"
os.environ["RSI_OVERBOUGHT"] = "70.0"
os.environ["BASE_THRESHOLD"] = "0.10"
