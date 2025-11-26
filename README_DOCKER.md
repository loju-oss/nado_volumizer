# Nado Volumiser Bot - Docker Instructions

## Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop) installed on your machine.
- A `.env` file with your configuration (see `.env.example`).

## How to Run

### Option 1: Using Docker Compose (Recommended)

1.  Ensure your `.env` file is populated with your credentials.
2.  Run the bot:
    ```bash
    docker-compose up --build -d
    ```
    The `-d` flag runs it in the background. To see logs:
    ```bash
    docker-compose logs -f
    ```
3.  To stop the bot:
    ```bash
    docker-compose down
    ```

### Option 2: Using Docker directly

1.  Build the image:
    ```bash
    docker build -t nado-bot .
    ```
2.  Run the container (passing the env file):
    ```bash
    docker run --env-file .env --name my-nado-bot nado-bot
    ```

## Sharing

To share this with others, send them the entire directory (excluding `venv`, `__pycache__`, and your private `.env` file). They will need to create their own `.env` file based on `.env.example`.
