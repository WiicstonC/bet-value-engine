import os

import httpx


ODDS_BASE = "https://api.the-odds-api.com/v4"


def require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta el secret {name} en GitHub Actions.")
    return value


def main() -> None:
    odds_key = require("ODDS_API_KEY")
    telegram_token = require("TELEGRAM_BOT_TOKEN")
    require("TELEGRAM_CHAT_ID")

    response = httpx.get(
        f"{ODDS_BASE}/sports",
        params={"apiKey": odds_key},
        timeout=20,
    )
    response.raise_for_status()
    sports = response.json()
    print(f"The Odds API OK: {len(sports)} deportes disponibles")

    telegram = httpx.get(
        f"https://api.telegram.org/bot{telegram_token}/getMe",
        timeout=15,
    )
    telegram.raise_for_status()
    data = telegram.json()
    if not data.get("ok"):
        raise RuntimeError("Telegram Bot API rechazo el token.")
    print(f"Telegram Bot API OK: @{data['result'].get('username', 'sin_username')}")
    print("Preflight OK")


if __name__ == "__main__":
    main()
