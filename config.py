import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Nado Configuration
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Nado Configuration
PRIVATE_KEY = os.getenv("NADO_PRIVATE_KEY")
# Default to Mainnet if not specified
RPC_URL = os.getenv("NADO_RPC_URL", "https://gateway.prod.nado.xyz/v1") 
WS_URL = os.getenv("NADO_WS_URL", "wss://gateway.prod.nado.xyz/v1/ws")
GATEWAY_V2_URL = "https://gateway.prod.nado.xyz/v2"
SUBACCOUNT_NAME = os.getenv("NADO_SUBACCOUNT_NAME", "default")

# Trading Configuration
SYMBOL = "BTC-PERP" 
TICKER_ID = "BTC-PERP_USDT0" # Explicit ticker ID for orderbook lookup
ORDER_SIZE = 0.0015 # Adjust based on minimum order size
SPREAD_PERCENTAGE = 0.0003 # 0.03% spread - tighter for faster fills
REFRESH_INTERVAL = 5 # Seconds - faster cycling for more volume
ORDER_TIMEOUT = 25 # Don't cancel orders younger than this (seconds)
PLACE_AT_INSIDE_MARKET = True # Place orders at best bid/ask for max fill rate

# Position Risk Management (in USDC)
# Note: Position from API is in BTC, but limits are in USDC
# Bot will convert BTC position to USDC using current price before comparing
MAX_SHORT_POSITION = -400  # If position < -1200 USDC, only place buy orders
MAX_LONG_POSITION = 400    # If position > +1200 USDC, only place sell orders
