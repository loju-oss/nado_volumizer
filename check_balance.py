import asyncio
import logging
import os
from dotenv import load_dotenv
from eth_account import Account
from nado_protocol.client import create_nado_client, NadoClientMode
from nado_protocol.utils.subaccount import SubaccountParams
from nado_protocol.utils.bytes32 import subaccount_to_hex

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_balance():
    private_key = os.getenv("NADO_PRIVATE_KEY")
    if not private_key:
        logger.error("NADO_PRIVATE_KEY not found.")
        return

    signer = Account.from_key(private_key)
    client = create_nado_client(mode=NadoClientMode.MAINNET, signer=signer)
    
    logger.info(f"Signer Address: {signer.address}")


    subaccount_params = SubaccountParams(
        subaccount_owner=signer.address,
        subaccount_name="Api test"
    )
    subaccount_address = subaccount_to_hex(subaccount_params)
    logger.info(f"Subaccount Address (default): {subaccount_address}")

    try:

        info = client.context.engine_client.get_subaccount_info(subaccount_address)
        logger.info(f"Subaccount Info: {info}")
        
        
    except Exception as e:
        logger.error(f"Error fetching subaccount info: {e}")

if __name__ == "__main__":
    asyncio.run(check_balance())
