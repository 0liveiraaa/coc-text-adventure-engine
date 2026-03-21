# Project Coding Rules (Non-Obvious Only)

## Code Mode Specific Guidance

### LLM Agent Output Schemas
Each agent defines its own JSON Schema for LLM output validation:
- [`DMAgent`](src/agent/dm_agent.py:47) - `DMAGENT_OUTPUT_SCHEMA` with intent parsing fields
- [`StateEvolution`](src/agent/state_evolution.py:50) - `STATE_EVOLUTION_OUTPUT_SCHEMA` with changes array structure

Modify schemas when adding new LLM output fields.

### World Loader Patterns
When adding new entity types to [`WorldLoader`](src/data/init/world_loader.py:30):
1. Create `_load_<entity>()` method following existing `_load_characters()` pattern
2. Add to `_save_to_io_system()` to persist loaded data
3. Update [`WorldBundle`](src/data/init/world_loader.py:21) dataclass if new metadata needed

### StateChange Dot Notation
Field paths in [`StateChange`](src/data/models.py:1) support nested access via dots:
- `attributes.hp` → accesses `character.attributes.hp`
- `status.san` → accesses `character.status.san`
- `inventory` → direct field access

[`IOSystem.apply_state_change()`](src/data/io_system.py:1) handles the resolution automatically.

### Prompt File Loading
Prompts are loaded via [`src/agent/prompt/__init__.py`](src/agent/prompt/__init__.py:1) using relative paths:
```python
from src.agent.prompt import load_system_prompt
prompt = load_system_prompt()  # Loads system_prompt.md from same directory
```

Add new prompt loader functions here when creating new agents.

### Testing with FakeIO
Tests should use [`FakeIO`](tests/test_regression_flow.py:10) stub to avoid database dependencies:
```python
class FakeIO:
    def save_character(self, _): return ERROR_SUCCESS
    def apply_state_change(self, _): return ERROR_SUCCESS
```

Always return `ERROR_SUCCESS` (0) for success cases.
