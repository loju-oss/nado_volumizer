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

async def check_wallet():
    private_key = os.getenv("NADO_PRIVATE_KEY")
    if not private_key:
        logger.error("NADO_PRIVATE_KEY not found.")
        return

    signer = Account.from_key(private_key)
    client = create_nado_client(mode=NadoClientMode.MAINNET, signer=signer)
    
    logger.info(f"Signer Address: {signer.address}")

    # Clear the report file
    with open("wallet_report.txt", "w") as f:
        f.write("--- Wallet Report ---\n")

    import config
    
    # List of subaccounts to check: (Name, Address or None)
    # If Address is None, it will be derived from Name
    targets = [
        (config.SUBACCOUNT_NAME, None),
        ("Specific Address", "0xf94e2c37097709f3aca86ecd45cd1d7d1828dedc64656661756c745f31000000"),
        ("Api test", None),
        ("default_1", None),
        ("default", None),
        ("Default", None)
    ]
    
    for name, address in targets:
        if address is None:
            subaccount_params = SubaccountParams(
                subaccount_owner=signer.address,
                subaccount_name=name
            )
            subaccount_address = subaccount_to_hex(subaccount_params)
        else:
            subaccount_address = address
            
        logger.info(f"Checking wallet for '{name}' ({subaccount_address})")

        try:
            info = client.context.engine_client.get_subaccount_info(subaccount_address)
            
            with open("wallet_report.txt", "a") as f:
                f.write(f"\n--- Wallet Balances for '{name}' ---\n")
                f.write(f"Address: {subaccount_address}\n")
                
                # Check Health / Assets
                if hasattr(info, 'healths'):
                    for i, health in enumerate(info.healths):
                        assets = int(health.assets)
                        if assets > 0:
                            f.write(f"  Health Group {i}: Assets (Collateral) = {assets / 1e18:.6f}\n")

                # Check Spot Balances
                if hasattr(info, 'spot_balances'):
                    f.write("  Spot Balances:\n")
                    found_spot = False
                    for balance in info.spot_balances:
                        amount = int(balance.balance.amount)
                        if amount != 0:
                            f.write(f"    Product ID {balance.product_id}: {amount / 1e18:.6f}\n")
                            found_spot = True
                    if not found_spot:
                        f.write("    (None)\n")
                
                # Check Perp Balances
                if hasattr(info, 'perp_balances'):
                    f.write("  Perp Balances:\n")
                    found_perp = False
                    for balance in info.perp_balances:
                        amount = int(balance.balance.amount)
                        quote_balance = int(balance.balance.v_quote_balance)
                        if amount != 0 or quote_balance != 0:
                            f.write(f"    Product ID {balance.product_id}: Position {amount / 1e18:.6f}, Quote Balance {quote_balance / 1e18:.6f}\n")
                            found_perp = True
                    if not found_perp:
                        f.write("    (None)\n")

                f.write("-----------------------\n")
            
            print(f"Checked '{name}' - see wallet_report.txt")

        except Exception as e:
            logger.error(f"Error fetching subaccount info for '{name}': {e}")



if __name__ == "__main__":
    asyncio.run(check_wallet())
