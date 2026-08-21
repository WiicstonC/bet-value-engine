import os
from typing import Any

import httpx


class TelegramAlertSender:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    @property
    def base_url(self) -> str:
        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado.")
        return f"https://api.telegram.org/bot{self.token}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/{method}",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        if not body.get("ok"):
            raise RuntimeError(body.get("description", f"Telegram API error en {method}"))
        return body

    def send(self, message: str, reply_markup: dict[str, Any] | None = None) -> bool:
        if not self.enabled:
            return False

        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        self._post("sendMessage", payload)
        return True

    def send_many(
        self,
        messages: list[str],
        reply_markups: list[dict[str, Any] | None] | None = None,
    ) -> int:
        sent = 0
        for index, message in enumerate(messages):
            markup = reply_markups[index] if reply_markups and index < len(reply_markups) else None
            if self.send(message, markup):
                sent += 1
        return sent

    def answer_callback(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
        if not self.token:
            return False
        self._post(
            "answerCallbackQuery",
            {
                "callback_query_id": callback_query_id,
                "text": text[:200],
                "show_alert": show_alert,
                "cache_time": 0,
            },
        )
        return True

    def edit_reply_markup(self, chat_id: str | int, message_id: int, reply_markup: dict[str, Any] | None = None) -> bool:
        if not self.token:
            return False
        self._post(
            "editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": reply_markup or {"inline_keyboard": []},
            },
        )
        return True

    def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 0,
    ) -> list[dict[str, Any]]:
        if not self.token:
            return []
        payload: dict[str, Any] = {
            "limit": max(1, min(limit, 100)),
            "timeout": max(0, timeout),
            "allowed_updates": ["callback_query", "message"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self._post("getUpdates", payload).get("result", [])

    def delete_webhook(self, drop_pending_updates: bool = False) -> bool:
        if not self.token:
            return False
        self._post(
            "deleteWebhook",
            {"drop_pending_updates": drop_pending_updates},
        )
        return True
