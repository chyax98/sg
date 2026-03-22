"""Pytest configuration and fixtures."""

import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_search_response():
    """Sample search response for mocking."""
    return {
        "query": "test query",
        "provider": "test",
        "results": [
            {
                "title": "Test Result 1",
                "url": "https://example.com/1",
                "content": "Test content 1",
                "snippet": "Test content 1",
                "score": 0.9,
                "source": "test",
            },
            {
                "title": "Test Result 2",
                "url": "https://example.com/2",
                "content": "Test content 2",
                "snippet": "Test content 2",
                "score": 0.8,
                "source": "test",
            },
        ],
        "total": 2,
        "latency_ms": 100.0,
    }
