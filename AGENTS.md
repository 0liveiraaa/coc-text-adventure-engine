# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview

COC (Call of Cthulhu) text adventure game framework driven by LLM. Features a dual-track data flow: natural language ↔ structured data via LLM bridging.

## Run Commands

```bash
# Start game
python src/main.py

# Start with custom player name
python src/main.py --name "调查员名称"

# Load save
python src/main.py --load save_name

# Run all tests
python -m unittest discover tests

# Run single test
python -m unittest tests.test_regression_flow
```

## Critical Project-Specific Patterns

### Python Path Requirement
Always add project root to Python path at module start:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### LLM Configuration Priority
1. Environment variables (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`)
2. `config/llm.json`
3. Defaults in `LLMConfig`

### World Configuration Structure
Worlds are directory-based under `config/world/<world_name>/`:
- `world.json` - Manifest with player_id, start_map_id, turn_order
- `characters/*.json` - Character definitions
- `items/*.json` - Item definitions
- `maps/*.json` - Map/room definitions
- `endings/*.json` - Ending conditions

### StateChange Operations
Use `ChangeOperation` enum (UPDATE/ADD/DEL) with dot-notation field paths:
```python
StateChange(id="char-01", field="attributes.hp", operation=ChangeOperation.UPDATE, value=5)
```

### Error Codes (IO System)
```python
ERROR_SUCCESS = 0
ERROR_ID_NOT_FOUND = 1
ERROR_FIELD_NOT_FOUND = 2
ERROR_OPERATION_INVALID = 3
ERROR_OTHER = 4
```

### Prompt Loading
Prompts are Markdown files loaded via `src/agent/prompt/__init__.py`:
```python
from src.agent.prompt import load_system_prompt, load_state_evolution_prompt
```

## Architecture Notes

- **High AI Authority**: DM Agent and State Evolution have highest decision power
- **7-Step Turn Flow**: Input → DM Agent → Rule System → State Evolution → IO
- **Dual Storage**: IOSystem supports `sqlite` (runtime) and `json` (config) modes
- **Pydantic Models**: All data models in `src/data/models.py` use Pydantic BaseModel
