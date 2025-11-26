import asyncio
import logging
import time
import os
from dotenv import load_dotenv
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.engine_client.types.execute import PlaceOrderParams, OrderParams
from nado_protocol.utils.expiration import OrderType, get_expiration_timestamp
from nado_protocol.utils.order import build_appendix
from nado_protocol.utils.math import to_x18, round_x18
from nado_protocol.utils.subaccount import SubaccountParams
from nado_protocol.utils.bytes32 import subaccount_to_hex
from eth_account import Account
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class NadoVolumeBot:
    def __init__(self):
        if not config.PRIVATE_KEY:
            raise ValueError("NADO_PRIVATE_KEY not found in environment variables.")
        
        # Create signer
        self.signer = Account.from_key(config.PRIVATE_KEY)
        
        # Initialize client
        # Use MAINNET as requested
        self.client = create_nado_client(mode=NadoClientMode.MAINNET, signer=self.signer)
        
        self.symbol = config.SYMBOL
        self.product_id = None
        self.running = False
        self.active_orders = {}  # Track order IDs: {order_id: {'time': timestamp, 'side': 'buy'|'sell'}}

    async def get_product_id(self):
        """
        Fetches the product ID for the configured symbol using Gateway V2.
        """
        # Check manual mapping first (optional fallback)
        if hasattr(config, 'PRODUCT_IDS') and self.symbol in config.PRODUCT_IDS:
            return config.PRODUCT_IDS[self.symbol]

        try:
            import requests
            url = f"{config.GATEWAY_V2_URL}/assets"
            logger.info(f"Fetching products from {url}...")
            
            # Run in executor to avoid blocking async loop
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, requests.get, url)
            resp.raise_for_status()
            
            assets = resp.json()
            
            for asset in assets:
                # Check symbol or ticker_id
                # Some assets might use 'symbol', others 'ticker_id'
                a_symbol = asset.get('symbol')
                a_ticker = asset.get('ticker_id')
                
                if a_symbol == self.symbol or a_ticker == self.symbol:
                    return asset.get('product_id')
            
            logger.error(f"Product {self.symbol} not found in V2 assets.")
            return None
        except Exception as e:
            logger.error(f"Error fetching product ID: {e}")
            return None

    async def get_market_price(self):
        """
        Fetches the current best bid and ask for the symbol.
        """
        if not self.product_id:
            return None, None

        try:
            # Get orderbook with depth 1
            # Use explicit TICKER_ID as requested
            orderbook = self.client.context.engine_client.get_orderbook(config.TICKER_ID, 1)
            
            best_bid = None
            best_ask = None
            
            if orderbook.bids:
                # bids[0] is [price, size]
                best_bid = float(orderbook.bids[0][0])
                
            if orderbook.asks:
                best_ask = float(orderbook.asks[0][0])
                
            return best_bid, best_ask
        except Exception as e:
            logger.error(f"Error fetching market price: {e}")
            return None, None

    async def get_current_position(self):
        """
        Fetches the current position size for the symbol.
        Returns position size (positive = long, negative = short).
        """
        if not self.product_id:
            return 0

        try:
            # Derive subaccount address
            subaccount_params = SubaccountParams(
                subaccount_owner=self.signer.address,
                subaccount_name=config.SUBACCOUNT_NAME
            )
            sender = subaccount_to_hex(subaccount_params)
            
            # Get subaccount info to check positions
            subaccount_info = self.client.context.engine_client.get_subaccount_info(sender)
            
            # perp_balances is a list of PerpProductBalance objects
            if hasattr(subaccount_info, 'perp_balances') and subaccount_info.perp_balances:
                for perp_balance in subaccount_info.perp_balances:
                    if hasattr(perp_balance, 'product_id') and perp_balance.product_id == self.product_id:
                        # Extract position from balance.amount
                        if hasattr(perp_balance, 'balance') and hasattr(perp_balance.balance, 'amount'):
                            position_str = perp_balance.balance.amount
                            position_size = float(position_str) / 1e18
                            return position_size
            
            return 0  # No position found
        except Exception as e:
            logger.error(f"Error fetching position: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0  # Return 0 on error to be safe


    async def sync_orders_with_exchange(self):
        """
        Syncs tracked orders with actual open orders from the exchange.
        Removes orders from tracking that are no longer on the exchange (filled, cancelled, expired).
        """
        if not self.product_id:
            return

        try:
            # Derive subaccount address
            subaccount_params = SubaccountParams(
                subaccount_owner=self.signer.address,
                subaccount_name=config.SUBACCOUNT_NAME
            )
            sender = subaccount_to_hex(subaccount_params)
            
            # Get actual open orders from exchange
            open_orders_data = self.client.market.get_subaccount_open_orders(
                product_id=self.product_id,
                sender=sender
            )
            
            # Get set of digests from actual open orders
            actual_order_digests = set()
            if hasattr(open_orders_data, 'orders') and open_orders_data.orders:
                for order in open_orders_data.orders:
                    if hasattr(order, 'digest') and order.digest:
                        actual_order_digests.add(order.digest)
            
            # Remove orders from tracking that are no longer on the exchange
            tracked_digests = set(self.active_orders.keys())
            missing_orders = tracked_digests - actual_order_digests
            
            if missing_orders:
                removed_buy = 0
                removed_sell = 0
                for digest in missing_orders:
                    order_info = self.active_orders.get(digest)
                    if isinstance(order_info, dict):
                        side = order_info.get('side')
                        if side == 'buy':
                            removed_buy += 1
                        elif side == 'sell':
                            removed_sell += 1
                    self.active_orders.pop(digest, None)
                
                logger.info(f"Synced orders: Removed {len(missing_orders)} orders from tracking "
                           f"({removed_buy} BUY, {removed_sell} SELL) that are no longer on exchange")
            
        except Exception as e:
            logger.error(f"Error syncing orders with exchange: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def get_open_orders(self):
        """
        Fetches open orders for the symbol and returns statistics.
        Returns: (total_orders, buy_orders, sell_orders)
        """
        if not self.product_id:
            return 0, 0, 0

        try:
            # Count buy and sell orders from our tracking
            # Handle both old format (just timestamp) and new format (dict with 'time' and 'side')
            buy_count = 0
            sell_count = 0
            for order_info in self.active_orders.values():
                if isinstance(order_info, dict):
                    side = order_info.get('side')
                    if side == 'buy':
                        buy_count += 1
                    elif side == 'sell':
                        sell_count += 1
                # Old format orders don't have side info, so we can't count them accurately
                # They'll be counted in total but not in buy/sell breakdown
            
            total_orders = len(self.active_orders)
            
            return total_orders, buy_count, sell_count
            
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return 0, 0, 0

    async def cancel_old_orders(self):
        """
        Cancels orders that are older than ORDER_TIMEOUT seconds.
        This allows orders to stay on the book for the configured time.
        """
        if not self.product_id:
            return

        try:
            current_time = time.time()
            orders_to_cancel = []
            
            # Find orders older than ORDER_TIMEOUT
            for order_id, order_info in list(self.active_orders.items()):
                # Handle both old format (just timestamp) and new format (dict with 'time' and 'side')
                if isinstance(order_info, dict):
                    placement_time = order_info.get('time', current_time)
                else:
                    # Old format: order_info is just a timestamp
                    placement_time = order_info
                age = current_time - placement_time
                if age >= config.ORDER_TIMEOUT:
                    orders_to_cancel.append(order_id)
            
            if not orders_to_cancel:
                # Log current order status even when nothing to cancel
                total_orders, buy_count, sell_count = await self.get_open_orders()
                logger.info(f"No orders older than {config.ORDER_TIMEOUT}s to cancel | "
                           f"Current orders: {buy_count} BUY, {sell_count} SELL (Total: {total_orders})")
                return
            
            # Log order counts before cancellation
            total_before, buy_before, sell_before = await self.get_open_orders()
            logger.info(f"Cancelling {len(orders_to_cancel)} orders older than {config.ORDER_TIMEOUT}s... | "
                       f"Before: {buy_before} BUY, {sell_before} SELL (Total: {total_before})")
            
            from nado_protocol.engine_client.types.execute import CancelProductOrdersParams
            
            # Derive subaccount address (same as when placing orders)
            subaccount_params = SubaccountParams(
                subaccount_owner=self.signer.address,
                subaccount_name=config.SUBACCOUNT_NAME
            )
            sender = subaccount_to_hex(subaccount_params)
            
            params = CancelProductOrdersParams(
                productIds=[self.product_id],
                sender=sender,  # Use subaccount address
                nonce=None  # Auto-generated
            )
            
            self.client.market.cancel_product_orders(params)
            
            # Count buy/sell orders being cancelled for logging
            buy_cancelled = sum(1 for order_id in orders_to_cancel 
                              if isinstance(self.active_orders.get(order_id), dict) 
                              and self.active_orders.get(order_id).get('side') == 'buy')
            sell_cancelled = len(orders_to_cancel) - buy_cancelled
            
            # Remove canceled orders from tracking
            for order_id in orders_to_cancel:
                self.active_orders.pop(order_id, None)
            
            # Log order counts after cancellation
            total_after, buy_after, sell_after = await self.get_open_orders()
            logger.info(f"✓ Cancelled {len(orders_to_cancel)} orders ({buy_cancelled} BUY, {sell_cancelled} SELL) | "
                       f"After: {buy_after} BUY, {sell_after} SELL (Total: {total_after})")
            
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")

    async def place_orders(self, best_bid, best_ask, current_position_btc=0):
        """
        Places 2-3 buy and sell limit orders at the inside market for maximum fill rate.
        Implements position risk management to prevent excessive directional exposure.
        
        Args:
            best_bid: Current best bid price
            best_ask: Current best ask price
            current_position_btc: Current position size in BTC
        """
        if not best_bid or not best_ask or not self.product_id:
            return

        # Get current open orders count
        total_orders, buy_count, sell_count = await self.get_open_orders()
        
        # Calculate mid price for position value conversion
        mid_price = (best_bid + best_ask) / 2
        
        # Convert BTC position to USDC for comparison against limits
        # Position limits are in USDC, but API returns BTC
        current_position_usdc = current_position_btc * mid_price
        
        # Place orders at inside market for maximum fill probability
        if config.PLACE_AT_INSIDE_MARKET:
            # Base prices: 1 tick inside spread to avoid crossing with POST_ONLY
            base_buy_price = round(best_bid - 1)  # 1 tick below bid (won't cross)
            base_sell_price = round(best_ask + 1)  # 1 tick above ask (won't cross)
        else:
            # Fallback: use tight spread from mid
            half_spread = mid_price * config.SPREAD_PERCENTAGE / 2
            base_buy_price = round(mid_price - half_spread)
            base_sell_price = round(mid_price + half_spread)
        
        # Position risk management (using USDC value)
        # Calculate the value of one order in USDC
        order_value_usdc = config.ORDER_SIZE * mid_price
        max_orders_per_side = 3
        
        # Determine if we can place orders on each side
        # Allow orders as long as current position hasn't exceeded the limit
        # This allows placing orders when close to the limit (e.g., -1100 allows sell orders)
        place_buy = True
        place_sell = True
        
        # Check short position limit: only block sell orders if already at or below limit
        if current_position_usdc <= config.MAX_SHORT_POSITION:
            # Already at or below limit, only place buy orders to reduce short
            place_sell = False
            logger.warning(f"Position ({current_position_btc:.6f} BTC / ${current_position_usdc:.2f} USDC) <= ${config.MAX_SHORT_POSITION}, ONLY placing BUY orders")
        
        # Check long position limit: only block buy orders if already at or above limit
        if current_position_usdc >= config.MAX_LONG_POSITION:
            # Already at or above limit, only place sell orders to reduce long
            place_buy = False
            logger.warning(f"Position ({current_position_btc:.6f} BTC / ${current_position_usdc:.2f} USDC) >= ${config.MAX_LONG_POSITION}, ONLY placing SELL orders")
        
        # Place 1 new order per side every cycle (every 5s)
        # Only place if we have fewer than 3 orders on that side
        # With orders lasting 20s and placing every 5s, we'll naturally have 2-3 orders per side
        should_place_buy = place_buy and buy_count < max_orders_per_side
        should_place_sell = place_sell and sell_count < max_orders_per_side
        
        logger.info(f"Position: {current_position_btc:.6f} BTC (${current_position_usdc:.2f} USDC)")
        logger.info(f"Order Status: {buy_count} BUY / {sell_count} SELL open | Max: {max_orders_per_side} per side")
        logger.info(f"Placing: {'1 BUY' if should_place_buy else '0 BUY'}, {'1 SELL' if should_place_sell else '0 SELL'}")

        try:
            # Derive subaccount address
            subaccount_params = SubaccountParams(
                subaccount_owner=self.signer.address,
                subaccount_name=config.SUBACCOUNT_NAME
            )
            sender = subaccount_to_hex(subaccount_params)
            
            # Use SDK utilities for proper decimal precision
            price_increment_x18 = int(1e18)  # $1.00 increment for BTC-PERP
            
            # Place 1 Buy Order (if allowed by position management and under limit)
            if should_place_buy:
                buy_price = base_buy_price
                
                buy_amount_x18 = to_x18(config.ORDER_SIZE)
                buy_price_x18 = to_x18(buy_price)
                buy_price_x18 = round_x18(buy_price_x18, price_increment_x18)
                
                buy_order_params = OrderParams(
                    sender=sender,
                    amount=buy_amount_x18,
                    priceX18=buy_price_x18,
                    expiration=get_expiration_timestamp(config.ORDER_TIMEOUT), 
                    appendix=build_appendix(OrderType.POST_ONLY),
                    nonce=None 
                )
                
                resp_buy = self.client.market.place_order(
                    PlaceOrderParams(
                        product_id=self.product_id,
                        order=buy_order_params,
                        spot_leverage=None 
                    )
                )
                logger.info(f"  ✓ Placed BUY order @ ${buy_price:.2f} | Status: {resp_buy.status}")
                
                # Track order placement time and side for smart cancellation
                if resp_buy.data and hasattr(resp_buy.data, 'digest'):
                    self.active_orders[resp_buy.data.digest] = {
                        'time': time.time(),
                        'side': 'buy'
                    }
            
            # Place 1 Sell Order (if allowed by position management and under limit)
            if should_place_sell:
                sell_price = base_sell_price
                
                sell_amount_x18 = -to_x18(config.ORDER_SIZE)  # Negative for sell
                sell_price_x18 = to_x18(sell_price)
                sell_price_x18 = round_x18(sell_price_x18, price_increment_x18)
                
                sell_order_params = OrderParams(
                    sender=sender,
                    amount=sell_amount_x18,
                    priceX18=sell_price_x18,
                    expiration=get_expiration_timestamp(config.ORDER_TIMEOUT),
                    appendix=build_appendix(OrderType.POST_ONLY),
                    nonce=None
                )
                
                resp_sell = self.client.market.place_order(
                    PlaceOrderParams(
                        product_id=self.product_id,
                        order=sell_order_params,
                        spot_leverage=None
                    )
                )
                logger.info(f"  ✓ Placed SELL order @ ${sell_price:.2f} | Status: {resp_sell.status}")
                
                # Track order placement time and side for smart cancellation
                if resp_sell.data and hasattr(resp_sell.data, 'digest'):
                    self.active_orders[resp_sell.data.digest] = {
                        'time': time.time(),
                        'side': 'sell'
                    }
            
        except Exception as e:
            logger.error(f"Error placing orders: {e}")

    async def run(self):
        self.running = True
        logger.info("Starting Nado Volume Bot...")
        
        # Get Product ID first
        self.product_id = await self.get_product_id()
        if not self.product_id:
            logger.error("Could not find product ID. Exiting.")
            return

        logger.info(f"Found Product ID: {self.product_id}")
        
        while self.running:
            try:
                # 1. Cancel old orders (older than ORDER_TIMEOUT)
                await self.cancel_old_orders()
                
                # 2. Sync tracked orders with actual exchange state (remove filled/cancelled orders)
                await self.sync_orders_with_exchange()
                
                # 3. Get current position for risk management (in BTC)
                current_position_btc = await self.get_current_position()
                
                # 4. Get current price
                best_bid, best_ask = await self.get_market_price()
                
                if best_bid and best_ask:
                    mid_price = (best_bid + best_ask) / 2
                    
                    # Get current order counts before placing new orders
                    total_orders, buy_count, sell_count = await self.get_open_orders()
                    logger.info(f"Market: {best_bid:.2f} / {best_ask:.2f} (Mid: {mid_price:.2f}) | "
                               f"Current Orders: {buy_count} BUY, {sell_count} SELL (Total: {total_orders})")
                    
                    # 5. Place new orders at inside market (with position risk management)
                    await self.place_orders(best_bid, best_ask, current_position_btc)
                    
                    # Log final order counts after placing
                    total_orders_after, buy_count_after, sell_count_after = await self.get_open_orders()
                    logger.info(f"Orders after placement: {buy_count_after} BUY, {sell_count_after} SELL (Total: {total_orders_after})")
                else:
                    logger.warning("Could not get market price.")
                
                logger.info(f"Sleeping for {config.REFRESH_INTERVAL} seconds...")
                await asyncio.sleep(config.REFRESH_INTERVAL)
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user.")
                self.running = False
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    bot = NadoVolumeBot()
    asyncio.run(bot.run())
