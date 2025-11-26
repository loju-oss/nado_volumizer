# Nado Volumiser Bot

A trading bot for Nado Protocol that maximizes volume using POST_ONLY limit orders with position risk management.

## Features

- **Volume Optimization**: Rapid order cycling for maximum trading volume
- **Fee Minimization**: POST_ONLY limit orders earn maker rebates
- **Position Risk Management**: Automatic directional bias based on position exposure
- **Smart Order Placement**: Orders at inside market for high fill rate

## Quick Start

### Local Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   Create `.env` with your credentials:
   ```env
   NADO_PRIVATE_KEY=your_private_key_here
   NADO_SUBACCOUNT_NAME=default
   ```

3. **Run the bot**:
   ```bash
   python bot.py
   ```

### Docker

```bash
docker-compose up -d
```

See [README_DOCKER.md](README_DOCKER.md) for details.

## Configuration

Edit `config.py` to customize:

```python
SYMBOL = "BTC-PERP"           # Trading pair
ORDER_SIZE = 0.0015           # Order size in BTC
SPREAD_PERCENTAGE = 0.0003    # 0.03% spread
REFRESH_INTERVAL = 5          # Order cycle (seconds)
ORDER_TIMEOUT = 25            # Min order lifetime (seconds)

# Position Risk Management (USDC)
MAX_SHORT_POSITION = -400     # Only buy if position < -400
MAX_LONG_POSITION = 400       # Only sell if position > +400
```

## How It Works

1. Fetches best bid/ask prices
2. Checks current position exposure
3. Applies risk management (directional bias if position exceeds limits)
4. Places POST_ONLY limit orders at inside market
5. Cancels orders older than `ORDER_TIMEOUT`
6. Repeats every `REFRESH_INTERVAL` seconds

## Utility Scripts

```bash
python check_balance.py      # View account balance
python check_positions.py    # View current positions
python check_price.py        # Get market prices
python single.py             # Test single order placement
```

## Project Structure

```
├── bot.py                   # Main trading bot
├── single.py               # Single order test script
├── config.py               # Configuration
├── requirements.txt        # Dependencies
├── .env.example           # Environment template
├── Dockerfile             # Docker setup
└── check_*.py             # Utility scripts
```



Built with [Nado Protocol](https://nado.xyz) Python SDK
