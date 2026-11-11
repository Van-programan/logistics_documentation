from __future__ import annotations

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from src.config import settings

def call_gigachat(system_prompt: str, user_prompt: str) -> str:
    client = GigaChat(
        credentials=settings.gigachat_credentials,
        scope=settings.gigachat_scope,
        model=settings.gigachat_model,
        verify_ssl_certs=False,
        timeout=90.0,
        max_retries=2,
    )

    chat = Chat(
        model=settings.gigachat_model,
        messages=[
            Messages(role=MessagesRole.SYSTEM, content=system_prompt),
            Messages(role=MessagesRole.USER, content=user_prompt),
        ],
        temperature=0.1,
    )

    resp = client.chat(chat)

    content = resp.choices[0].message.content
    return content