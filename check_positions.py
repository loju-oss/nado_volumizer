import asyncio
import logging
import os
from dotenv import load_dotenv
from eth_account import Account
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.utils.subaccount import SubaccountParams
from nado_protocol.utils.bytes32 import subaccount_to_hex
import config

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def check_positions():
    """
    Checks and displays all open positions for the configured account.
    """
    logger.info("=" * 60)
    logger.info("NADO POSITION CHECKER")
    logger.info("=" * 60)
    
    # Initialize client
    private_key = os.getenv("NADO_PRIVATE_KEY")
    if not private_key:
        logger.error("NADO_PRIVATE_KEY not found in environment variables.")
        return
    
    signer = Account.from_key(private_key)
    client = create_nado_client(mode=NadoClientMode.MAINNET, signer=signer)
    
    logger.info(f"Account Address: {signer.address}")
    
    try:
        # Derive subaccount address
        subaccount_params = SubaccountParams(
            subaccount_owner=signer.address,
            subaccount_name="default"
        )
        sender = subaccount_to_hex(subaccount_params)
        
        logger.info(f"Subaccount Address: {sender}")
        logger.info("=" * 60)
        
        # Get subaccount info
        subaccount_info = client.context.engine_client.get_subaccount_info(sender)
        
        # Parse positions
        if hasattr(subaccount_info, 'perp_balances') and subaccount_info.perp_balances:
            perp_balances = subaccount_info.perp_balances
            
            # Fetch current BTC price for USDC conversion
            btc_price = None
            try:
                orderbook = client.context.engine_client.get_orderbook(config.TICKER_ID, 1)
                if orderbook.bids and orderbook.asks:
                    btc_price = (float(orderbook.bids[0][0]) + float(orderbook.asks[0][0])) / 2
                    logger.info(f"Current BTC Price: ${btc_price:,.2f}")
            except Exception as e:
                logger.warning(f"Could not fetch BTC price: {e}")
            
            # Display positions in clean format
            logger.info("\nPERPETUAL POSITIONS:")
            logger.info("=" * 80)
            logger.info(f"{'Product ID':<12} {'BTC Position':<18} {'USDC Value':<18} {'Direction':<10}")
            logger.info("-" * 80)
            
            has_positions = False
            for perp_balance in perp_balances:
                if hasattr(perp_balance, 'product_id') and hasattr(perp_balance, 'balance'):
                    product_id = perp_balance.product_id
                    
                    # Extract position from balance.amount attribute
                    if hasattr(perp_balance.balance, 'amount'):
                        position_str = perp_balance.balance.amount
                        position_btc = float(position_str) / 1e18
                        
                        # Only show non-zero positions
                        if position_btc != 0:
                            has_positions = True
                            
                            # Determine direction
                            if position_btc > 0:
                                direction = "LONG ↑"
                            else:
                                direction = "SHORT ↓"
                            
                            # Calculate USDC value using real-time price
                            if btc_price and product_id == 2:  # BTC-PERP
                                position_usdc = position_btc * btc_price
                                usdc_str = f"${position_usdc:,.2f}"
                            else:
                                usdc_str = "N/A"
                            
                            logger.info(f"{product_id:<12} {position_btc:<18.8f} {usdc_str:<18} {direction:<10}")
            
            if not has_positions:
                logger.info("No open positions (all positions are zero)")
            
            logger.info("=" * 80)
        else:
            logger.info("\nNo perp_balances found in subaccount")
            
        # Show spot balances summary
        if hasattr(subaccount_info, 'spot_balances') and subaccount_info.spot_balances:
            logger.info("\nSPOT BALANCES:")
            logger.info("=" * 60)
            logger.info(f"{'Product ID':<12} {'Amount':<20}")
            logger.info("-" * 60)
            for spot_balance in subaccount_info.spot_balances:
                if hasattr(spot_balance, 'product_id') and hasattr(spot_balance, 'balance'):
                    product_id = spot_balance.product_id
                    if hasattr(spot_balance.balance, 'amount'):
                        amount_str = spot_balance.balance.amount
                        amount = float(amount_str) / 1e18
                        if amount != 0:
                            logger.info(f"{product_id:<12} {amount:<20.8f}")
            logger.info("=" * 60)
                    
    except Exception as e:
        logger.error(f"Error checking positions: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    logger.info("\n" + "=" * 60)
    logger.info("POSITION CHECK COMPLETE")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(check_positions())
