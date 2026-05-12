from __future__ import annotations

from dataclasses import dataclass

from research_radar.config import Settings, get_settings


@dataclass
class XConnectorStatus:
    status: str
    message: str


class XReadOnlyConnector:
    """Placeholder for future read-only X/Twitter signal ingestion."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.x_bearer_token or self.settings.x_api_key)

    def status(self) -> XConnectorStatus:
        if not self.configured:
            return XConnectorStatus(status="not_configured", message="X/Twitter not configured")
        return XConnectorStatus(
            status="placeholder",
            message=(
                "X/Twitter connector is configured but ingestion is not implemented in the MVP."
            ),
        )
