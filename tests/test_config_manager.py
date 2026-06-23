import json
from pathlib import Path
import pytest
import memory.config_manager as cm

@pytest.fixture
def mock_config_dir(tmp_path, monkeypatch):
    test_dir = tmp_path / "config"
    test_file = test_dir / "api_keys.json"
    
    monkeypatch.setattr(cm, "CONFIG_DIR", test_dir)
    monkeypatch.setattr(cm, "CONFIG_FILE", test_file)
    
    return test_dir, test_file

def test_save_and_load_api_keys(mock_config_dir):
    _, test_file = mock_config_dir
    cm.save_api_keys("test_key_123")
    
    assert test_file.exists()
    keys = cm.load_api_keys()
    assert keys["gemini_api_key"] == "test_key_123"

def test_is_configured(mock_config_dir):
    cm.save_api_keys("this_is_a_valid_long_key_1234567")
    assert cm.is_configured() is True
    
    cm.save_api_keys("short")
    assert cm.is_configured() is False

def test_load_nonexistent_config(mock_config_dir):
    keys = cm.load_api_keys()
    assert keys == {}
