import os

import httpx


ODDS_BASE = "https://api.the-odds-api.com/v4"
REQUIRED_SECRETS = [
    "ODDS_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]
REQUIRED_SPORT_KEYS = [
    "basketball_nba",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_colombia_primera_a",
]


def main() -> None:
    missing = [name for name in REQUIRED_SECRETS if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Faltan estos secrets en GitHub Actions: "
            + ", ".join(missing)
            + ". Crea cada uno exactamente con ese nombre en "
              "Settings > Secrets and variables > Actions > New repository secret."
        )

    odds_key = os.environ["ODDS_API_KEY"]
    telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]

    response = httpx.get(
        f"{ODDS_BASE}/sports",
        params={"apiKey": odds_key},
        timeout=20,
    )
    response.raise_for_status()
    sports = response.json()
    available_keys = {item.get("key") for item in sports}
    print(f"The Odds API OK: {len(sports)} deportes/competiciones disponibles")

    missing_sports = [key for key in REQUIRED_SPORT_KEYS if key not in available_keys]
    if missing_sports:
        print("Aviso: estas competiciones no estan activas actualmente:")
        for key in missing_sports:
            print(f"  - {key}")
        print("Esto no detiene el workflow; The Odds API solo publica ciertos torneos cuando estan en temporada.")
    else:
        print("Todas las ligas principales de NBA y futbol solicitadas estan disponibles.")

    tennis_keys = sorted(
        key for key in available_keys
        if isinstance(key, str) and key.startswith(("tennis_atp_", "tennis_wta_"))
    )
    print(f"Competiciones de tenis activas detectadas: {len(tennis_keys)}")
    for key in tennis_keys:
        print(f"  - {key}")

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
