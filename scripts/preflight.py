import os

import httpx


ODDS_BASE = "https://api.the-odds-api.com/v4"
REQUIRED_SECRETS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
ODDS_KEY_NAMES = ["ODDS_API_KEY", "ODDS_API_KEY_2", "ODDS_API_KEY_3"]
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
    available_keys = [name for name in ODDS_KEY_NAMES if os.getenv(name)]
    if not available_keys:
        missing.append("ODDS_API_KEY (o una clave de respaldo ODDS_API_KEY_2/ODDS_API_KEY_3)")
    if missing:
        raise RuntimeError("Faltan estos secrets en GitHub Actions: " + ", ".join(missing) + ".")

    sports = None
    active_key_name = None
    last_error = None
    for key_name in available_keys:
        try:
            response = httpx.get(f"{ODDS_BASE}/sports", params={"apiKey": os.environ[key_name]}, timeout=20)
            response.raise_for_status()
            sports = response.json()
            active_key_name = key_name
            break
        except httpx.HTTPError as exc:
            last_error = exc

    if sports is None:
        raise RuntimeError(f"Ninguna clave de Odds API pudo validarse: {last_error}")

    available_keys_set = {item.get("key") for item in sports}
    print(f"The Odds API OK usando {active_key_name}: {len(sports)} deportes/competiciones disponibles")
    missing_sports = [key for key in REQUIRED_SPORT_KEYS if key not in available_keys_set]
    if missing_sports:
        print("Aviso: competiciones no activas actualmente: " + ", ".join(missing_sports))
    else:
        print("Todas las ligas principales de NBA y fútbol solicitadas están disponibles.")

    tennis_keys = sorted(key for key in available_keys_set if isinstance(key, str) and key.startswith(("tennis_atp_", "tennis_wta_")))
    print(f"Competiciones de tenis activas detectadas: {len(tennis_keys)}")

    telegram_base = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"
    telegram = httpx.get(f"{telegram_base}/getMe", timeout=15)
    telegram.raise_for_status()
    data = telegram.json()
    if not data.get("ok"):
        raise RuntimeError("Telegram Bot API rechazó el token.")
    print(f"Telegram Bot API OK: @{data['result'].get('username', 'sin_username')}")

    chat = httpx.get(f"{telegram_base}/getChat", params={"chat_id": os.environ["TELEGRAM_CHAT_ID"]}, timeout=15)
    chat.raise_for_status()
    chat_data = chat.json()
    if not chat_data.get("ok"):
        raise RuntimeError("Telegram no pudo resolver TELEGRAM_CHAT_ID. Verifica que el bot esté en el chat y que el ID sea correcto.")
    print(f"Telegram chat OK: {chat_data['result'].get('title') or chat_data['result'].get('username') or chat_data['result'].get('id')}")
    print("Preflight OK")


if __name__ == "__main__":
    main()
