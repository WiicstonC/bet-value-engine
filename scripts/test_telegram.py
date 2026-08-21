from datetime import datetime
from zoneinfo import ZoneInfo

from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG


def main() -> None:
    sender = TelegramAlertSender()
    if not sender.enabled:
        raise RuntimeError("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no están configurados.")
    now = datetime.now(ZoneInfo(DEFAULT_CONFIG.timezone)).strftime("%d/%m/%Y %H:%M:%S")
    message = (
        "🟢 BET VALUE ENGINE — PRUEBA TELEGRAM\n\n"
        f"Conexión confirmada.\nHora Colombia: {now}\n\n"
        "El siguiente paso será recibir la agenda diaria con preanálisis y usar el ID del evento para solicitar análisis profundo."
    )
    if not sender.send(message):
        raise RuntimeError("Telegram no pudo enviar el mensaje.")
    print("Telegram test enviado correctamente.")


if __name__ == "__main__":
    main()
