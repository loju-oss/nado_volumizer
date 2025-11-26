import asyncio
import logging
import sys
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import PlaceOrderParams, OrderParams
from nado_protocol.utils.expiration import OrderType, get_expiration_timestamp
from nado_protocol.utils.order import build_appendix
from nado_protocol.utils.subaccount import SubaccountParams
from nado_protocol.utils.bytes32 import subaccount_to_hex
from nado_protocol.utils.math import to_x18, round_x18

from eth_account import Account
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class SingleOrderBot:
    def __init__(self):
        if not config.PRIVATE_KEY:
            raise ValueError("NADO_PRIVATE_KEY not found in environment variables.")
        
        self.signer = Account.from_key(config.PRIVATE_KEY)
        self.client = create_nado_client(mode=NadoClientMode.MAINNET, signer=self.signer)
        self.symbol = config.SYMBOL

    async def get_product_id(self):
        # Check manual mapping first
        if hasattr(config, 'PRODUCT_IDS') and self.symbol in config.PRODUCT_IDS:
            return config.PRODUCT_IDS[self.symbol]

        try:
            import requests
            url = f"{config.GATEWAY_V2_URL}/assets"
            logger.info(f"Fetching products from {url}...")
            
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, requests.get, url)
            resp.raise_for_status()
            
            assets = resp.json()
            
            for asset in assets:
                a_symbol = asset.get('symbol')
                a_ticker = asset.get('ticker_id')
                
                if a_symbol == self.symbol or a_ticker == self.symbol:
                    return asset.get('product_id')
            
            logger.error(f"Product {self.symbol} not found in V2 assets.")
            return None
        except Exception as e:
            logger.error(f"Error fetching product ID: {e}")
            return None

    async def get_best_bid(self, product_id):
        try:
            # Use explicit TICKER_ID as requested
            orderbook = self.client.context.engine_client.get_orderbook(config.TICKER_ID, 1)
            if orderbook.bids:
                return float(orderbook.bids[0][0])
            return None
        except Exception as e:
            logger.error(f"Error fetching market price: {e}")
            return None

    async def place_single_order(self):
        product_id = await self.get_product_id()
        if not product_id:
            logger.error("Product ID not found.")
            return

        best_bid = await self.get_best_bid(product_id)
        if not best_bid:
            logger.error("Could not get market price.")
            return

        # Place a Buy order slightly below best bid (passive)
        # Calculate price and round to nearest dollar (price_increment for BTC-PERP is $1.00)
        price = round(best_bid * (1 - config.SPREAD_PERCENTAGE))
        amount = config.ORDER_SIZE
        
        logger.info(f"Placing SINGLE Buy Order: {amount} {self.symbol} @ {price:.2f}")

        try:
            # Use SDK utilities for proper decimal precision
            amount_x18 = to_x18(amount)
            price_x18 = to_x18(price)
            
            # Round price to the nearest price increment (1e18 = $1.00 for BTC-PERP)
            price_increment_x18 = int(1e18)  # $1.00 increment for BTC-PERP
            price_x18 = round_x18(price_x18, price_increment_x18)
            
            # Derive subaccount address
            subaccount_params = SubaccountParams(
                subaccount_owner=self.signer.address,
                subaccount_name="default"
            )
            sender = subaccount_to_hex(subaccount_params)

            order_params = OrderParams(
                sender=sender, # Use subaccount address
                amount=amount_x18,
                priceX18=price_x18,
                expiration=get_expiration_timestamp(1000),
                appendix=build_appendix(OrderType.POST_ONLY),
                nonce=None
            )
            
            resp = self.client.market.place_order(
                PlaceOrderParams(
                    product_id=product_id,
                    order=order_params,
                    spot_leverage=None
                )
            )
            logger.info(f"Order Placed! Status: {resp.status}")
            if resp.data:
                logger.info(f"Response Data: {resp.data}")
                
        except Exception as e:
            logger.error(f"Error placing order: {e}")

if __name__ == "__main__":
    bot = SingleOrderBot()
    asyncio.run(bot.place_single_order())
