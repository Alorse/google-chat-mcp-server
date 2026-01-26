import os
import pytest
import yaml
from unittest.mock import MagicMock, patch
from src.providers.google_chat.utils.search_manager import SearchManager
from src.mcp_core.engine.provider_loader import get_provider_config_value, initialize_provider_config

# Initialize the provider configuration
initialize_provider_config("google_chat")

# Get search config path from provider config
SEARCH_CONFIG_YAML_PATH = get_provider_config_value("google_chat", "search_config_path")

# Convert to absolute path if it's a relative path
if not os.path.isabs(SEARCH_CONFIG_YAML_PATH):
    # Get the project root directory (parent of src)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../../'))
    SEARCH_CONFIG_YAML_PATH = os.path.join(project_root, SEARCH_CONFIG_YAML_PATH)

# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def regex_manager():
    manager = SearchManager()
    manager.search_modes["regex"] = {
        "enabled": True,
        "weight": 1.0,
        "options": {
            "ignore_case": True,
            "dot_all": True,
            "unicode": True,
            "max_pattern_length": 1000
        }
    }
    return manager

@pytest.fixture(scope="module")
def search_config():
    with open(SEARCH_CONFIG_YAML_PATH, "r") as f:
        return yaml.safe_load(f)

MESSAGES = [
    {"name": "m1", "text": "Please review PR #456 before EOD"},
    {"name": "m2", "text": "Resolved issue in function `calculate_total(amount)`"},
    {"name": "m3", "text": "/deploy staging triggered by @ops-bot"},
    {"name": "m4", "text": "Release v1.2.3-alpha is now live"},
    {"name": "m5", "text": "Refer to JIRA ticket ABC-123 or DEF-4567"},
    {"name": "m6", "text": "2025-05-21 10:34AM: Rebooted service node"},
    {"name": "m7", "text": "[ERROR] Failed to connect to db"},
    {"name": "m8", "text": "Email sent to john.doe@example.com at 3PM"},
    {"name": "m9", "text": "kubectl get pods --namespace=dev"},
    {"name": "m10", "text": "Traceback (most recent call last):\n  File \"app.py\"..."},
    {"name": "m11", "text": "System uptime: 13d 4h 23m"},
    {"name": "m12", "text": "Client IP: 192.168.0.5"},
    {"name": "m13", "text": "CRON job failed @ 0 4 * * *"},
    {"name": "m14", "text": "Disk usage: /dev/sda1  89% full"},
    {"name": "m15", "text": "Log file written to /var/log/app.log"},
    {"name": "m16", "text": "[WARN] Memory usage high"},
]

# ------------------------------------------------------------------------------
# Test Suites
# ------------------------------------------------------------------------------

class TestRegexSearchSuite:

    @pytest.mark.parametrize("pattern,text", [
        (r"\b[A-Z]{2,}-\d+\b", "ABC-123"),
        (r"#\d+", "#456"),
        (r"calculate_total\([^\)]*\)", "calculate_total"),
        (r"/deploy \w+", "/deploy staging"),
        (r"v\d+\.\d+\.\d+(-\w+)?", "v1.2.3-alpha"),
        (r"\b\d{4}-\d{2}-\d{2}\b", "2025-05-21"),
        (r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "john.doe@example.com"),
        (r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "192.168.0.5"),
        (r"\d+ \d+ \* \* \*", "0 4 * * *"),
        (r"/[\w/\.]+\.log", "/var/log/app.log"),
        (r"\[ERROR\]", "[ERROR]"),
        (r"\[WARN\]", "[WARN]"),
        (r"Traceback \(most recent call last\):", "Traceback"),
        (r"\d{1,3}% full", "89%"),
        (r"\d+d \d+h \d+m", "13d 4h 23m"),
        (r"kubectl get pods", "kubectl get pods"),
    ])
    def test_patterns(self, regex_manager, pattern, text):
        results = regex_manager._regex_search(pattern, MESSAGES)
        assert any(text in msg["text"] for _, msg in results)

    def test_invalid_regex_fails_gracefully(self, regex_manager):
        results = regex_manager._regex_search(r"bad(pattern", MESSAGES)
        assert isinstance(results, list) and len(results) == 0


class TestSearchSortingLogic:

    def test_exact_search_sorting(self):
        manager = SearchManager()
        messages = [
            {"name": "msg1", "text": "first"},
            {"name": "msg2", "text": "second"},
            {"name": "msg3", "text": "message"},
        ]
        scores = [score for score, _ in manager._exact_search("message", messages)]
        assert all(scores[i] >= scores[i+1] for i in range(len(scores)-1))

    def test_hybrid_search(self):
        with patch('src.providers.google_chat.utils.search_manager.SearchManager._exact_search') as exact, \
             patch('src.providers.google_chat.utils.search_manager.SearchManager._regex_search') as regex:

            manager = SearchManager()
            manager.search_modes = {
                "exact": {"enabled": True},
                "regex": {"enabled": True},
            }
            manager.config = {
                "search": {
                    "hybrid_weights": {
                        "exact": 1.0,
                        "regex": 1.2,
                    }
                }
            }

            exact.return_value = [(0.8, {"name": "msg1"}), (0.6, {"name": "msg2"})]
            regex.return_value = [(0.9, {"name": "msg2"}), (0.7, {"name": "msg3"})]

            results = manager._hybrid_search("query", [])
            names = [msg["name"] for _, msg in results]
            assert "msg2" in names  # Should be found by both modes


class TestFallbackAndErrorHandling:

    def test_fallback_to_default_mode(self):
        manager = SearchManager()
        manager._exact_search = MagicMock(return_value=[(1.0, {"name": "msg"})])
        manager.get_default_mode = MagicMock(return_value="exact")
        result = manager.search("query", [{"name": "msg", "text": "hi"}], mode=None)
        assert result[0][1]["name"] == "msg"

    def test_invalid_mode_falls_back_to_exact(self):
        manager = SearchManager()
        manager._exact_search = MagicMock(return_value=[(1.0, {"name": "msg"})])
        result = manager.search("query", [{"name": "msg", "text": "hi"}], mode="unsupported")
        assert result[0][1]["name"] == "msg"

    def test_semantic_mode_falls_back_to_exact(self):
        """Semantic mode should gracefully fall back to exact search in lightweight version."""
        manager = SearchManager()
        manager._exact_search = MagicMock(return_value=[(1.0, {"name": "fallback"})])
        result = manager.search("query", [{"name": "fallback", "text": "text"}], mode="semantic")
        assert result[0][1]["name"] == "fallback"

    def test_missing_config_file_raises(self):
        with pytest.raises(FileNotFoundError):
            SearchManager(config_path="does_not_exist.yaml")
