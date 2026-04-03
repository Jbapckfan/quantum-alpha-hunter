"""ntfy.sh push notification client."""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

import httpx

from .alert_types import BaseAlert

logger = logging.getLogger("qaht.alerts.ntfy")


class NtfyClient:
    """Minimal ntfy.sh publisher using HTTP headers for metadata."""

    def __init__(
        self,
        topic: Optional[str] = None,
        base_url: str = "https://ntfy.sh",
        timeout: float = 10.0,
    ) -> None:
        self.topic = (topic or os.environ.get("NTFY_TOPIC", "james-qah-alerts")).strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def url(self) -> str:
        """Return the fully-qualified publish URL."""
        return f"{self.base_url}/{self.topic}"

    def send(
        self,
        title: str,
        body: str,
        priority: int = 3,
        tags: Optional[Iterable[str]] = None,
        click_url: Optional[str] = None,
    ) -> dict:
        """Publish a message to ntfy.sh and return the response payload."""
        headers = {
            "Title": title,
            "Priority": str(priority),
        }
        tag_list = [tag for tag in (tags or []) if tag]
        if tag_list:
            headers["Tags"] = ",".join(tag_list)
        if click_url:
            headers["Click"] = click_url

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.url, content=body.encode("utf-8"), headers=headers)
            response.raise_for_status()

        try:
            payload = response.json()
        except ValueError:
            payload = {"status_code": response.status_code, "text": response.text}

        logger.info("Published ntfy alert to topic %s", self.topic)
        return payload

    def publish_alert(self, alert: BaseAlert) -> dict:
        """Publish a normalized alert dataclass."""
        return self.send(
            title=alert.title,
            body=alert.body,
            priority=alert.priority,
            tags=alert.tags,
            click_url=alert.click_url,
        )
