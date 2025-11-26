import asyncio
import logging
import os
from dotenv import load_dotenv
from eth_account import Account
from nado_protocol.client import create_nado_client, NadoClientMode
import config

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_price():
    private_key = os.getenv("NADO_PRIVATE_KEY")
    signer = Account.from_key(private_key)
    client = create_nado_client(mode=NadoClientMode.MAINNET, signer=signer)
    
    ticker_id = config.TICKER_ID
    logger.info(f"Checking price for {ticker_id}")

    try:
        # Check Orderbook
        orderbook = client.context.engine_client.get_orderbook(ticker_id, 5)
        logger.info(f"Orderbook Bids: {orderbook.bids}")
        logger.info(f"Orderbook Asks: {orderbook.asks}")
        
        if orderbook.bids:
            best_bid = int(orderbook.bids[0][0]) / 1e18
            logger.info(f"Best Bid: {best_bid}")
        else:
            logger.info("No bids found.")

    except Exception as e:
        logger.error(f"Error fetching orderbook: {e}")

if __name__ == "__main__":
    asyncio.run(check_price())
