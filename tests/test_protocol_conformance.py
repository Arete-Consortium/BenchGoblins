"""Verify concrete classes conform to Protocol interfaces."""

from protocols import IntelligenceBackend
from services.claude import ClaudeService


class TestIntelligenceBackendConformance:
    def test_claude_service(self):
        assert issubclass(ClaudeService, IntelligenceBackend)
