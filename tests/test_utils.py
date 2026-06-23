import os
import json
import time
from pathlib import Path
from core.utils import Config, StatsTracker, ActionRecord

def test_config_loads_defaults(tmp_path):
    # Setup mock config
    c = Config()
    c._data = {"default_key": "default_value"}
    assert c.get("default_key") == "default_value"
    assert c.get("non_existent") is None

def test_stats_tracker():
    tracker = StatsTracker()
    tracker.record("test_action", 1.5, success=True)
    tracker.record("test_action", 0.5, success=False)
    
    stats = tracker.summary()
    assert stats["total_calls"] == 2
    assert stats["successes"] == 1
    assert stats["failures"] == 1
    assert stats["success_rate"] == 0.5
    assert stats["avg_duration_ms"] == 1000.0
    assert "test_action" in [a[0] for a in stats["top_actions"]]

def test_config_singleton():
    c1 = Config.instance()
    c2 = Config.instance()
    assert c1 is c2
