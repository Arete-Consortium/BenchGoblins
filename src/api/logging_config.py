import logging
import os


def setup_logging() -> None:
    """Configure structured logging from LOG_LEVEL env var (default INFO)."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
