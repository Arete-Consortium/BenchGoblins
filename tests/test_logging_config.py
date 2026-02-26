"""Tests for logging configuration."""

import logging
from unittest.mock import patch

from logging_config import setup_logging


class TestSetupLogging:
    def test_default_level(self):
        """Default log level is INFO when LOG_LEVEL not set."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("logging.basicConfig") as mock_basic:
                setup_logging()
                mock_basic.assert_called_once()
                assert mock_basic.call_args[1]["level"] == logging.INFO

    def test_custom_level(self):
        """LOG_LEVEL env var sets the logging level."""
        with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
            with patch("logging.basicConfig") as mock_basic:
                setup_logging()
                assert mock_basic.call_args[1]["level"] == logging.DEBUG

    def test_invalid_level_falls_back(self):
        """Invalid LOG_LEVEL falls back to INFO."""
        with patch.dict("os.environ", {"LOG_LEVEL": "NOTREAL"}):
            with patch("logging.basicConfig") as mock_basic:
                setup_logging()
                assert mock_basic.call_args[1]["level"] == logging.INFO
