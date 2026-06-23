import json
import pytest
from pathlib import Path
import memory.memory_manager as mm

@pytest.fixture
def mock_memory_file(tmp_path, monkeypatch):
    test_file = tmp_path / "long_term.json"
    monkeypatch.setattr(mm, "MEMORY_PATH", test_file)
    return test_file

def test_load_empty_memory(mock_memory_file):
    mem = mm.load_memory()
    assert "identity" in mem
    assert "preferences" in mem

def test_save_and_load_memory(mock_memory_file):
    mem = mm._empty_memory()
    mem["identity"]["name"] = {"value": "Tony"}
    
    mm.save_memory(mem)
    assert mock_memory_file.exists()
    
    loaded = mm.load_memory()
    assert loaded["identity"]["name"]["value"] == "Tony"

def test_update_memory(mock_memory_file):
    updates = {"preferences": {"food": {"value": "Pizza"}}}
    mm.update_memory(updates)
    
    mem = mm.load_memory()
    assert mem["preferences"]["food"]["value"] == "Pizza"

def test_format_memory_for_prompt(mock_memory_file):
    mem = mm._empty_memory()
    mem["identity"]["name"] = {"value": "Tony"}
    mem["identity"]["age"] = {"value": "45"}
    mem["preferences"]["food"] = {"value": "Cheeseburger"}
    mem["projects"]["iron_man"] = {"value": "Mark IV"}
    mem["relationships"]["pepper"] = {"value": "Wife"}
    mem["wishes"]["peace"] = {"value": "World Peace"}
    mem["notes"]["suit"] = {"value": "Needs paint"}
    
    prompt = mm.format_memory_for_prompt(mem)
    assert "Name: Tony" in prompt
    assert "Age: 45" in prompt
    assert "Food: Cheeseburger" in prompt
    assert "Iron Man: Mark IV" in prompt
    assert "Pepper: Wife" in prompt
    assert "Peace: World Peace" in prompt
    assert "suit: Needs paint" in prompt

def test_remember_and_forget(mock_memory_file):
    mm.remember("color", "red", "preferences")
    mem = mm.load_memory()
    assert mem["preferences"]["color"]["value"] == "red"
    
    mm.forget("color", "preferences")
    mem = mm.load_memory()
    assert "color" not in mem["preferences"]
