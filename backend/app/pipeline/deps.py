"""Quvur bog'liqliklari: ma'lumot manbasi va GEE gateway (testlarda almashtiriladi)."""

from backend.app.gee.gateway import GEEGateway
from backend.app.gee.gateway import gateway as default_gateway
from backend.app.gee.sources import GEESource
from backend.app.gee.types import DataSource

_source: DataSource | None = None
_gateway: GEEGateway | None = default_gateway


def get_data_source() -> DataSource:
    global _source
    if _source is None:
        _source = GEESource(default_gateway)
    return _source


def get_gateway() -> GEEGateway | None:
    return _gateway


def set_data_source(source: DataSource, gateway: GEEGateway | None = None) -> None:
    """Testlar uchun: soxta manbani o'rnatish."""
    global _source, _gateway
    _source, _gateway = source, gateway
