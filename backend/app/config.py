"""
Compatibility shim - the canonical configuration service lives in
app/services/config.py. Both import paths resolve to the same instance so the
YAML configuration (including the `crewai.enabled` flag) is honoured everywhere.
"""
from app.services.config import get_config, get_settings, reset_config

__all__ = ["get_config", "get_settings", "reset_config"]
