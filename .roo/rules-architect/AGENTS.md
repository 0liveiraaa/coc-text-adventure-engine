# Project Architecture Rules (Non-Obvious Only)

## Architect Mode Specific Guidance

### 7-Step Turn Flow
From [`game_engine.py`](src/engine/game_engine.py:35) and spec:
```
1. Input → 2. IO Read → 3. DM Agent Parse → 4. Rule Check → 
5. State Evolution → 6. IO Write → 7. Output
```

Each step is implemented in [`_process_turn()`](src/engine/game_engine.py:1) method.

### Module Coupling
- **GameEngine** orchestrates all modules via dependency injection
- **StateEvolution** has hard dependency on [`LLMService`](src/agent/llm_service.py:1)
- **DMAgent** requires [`load_system_prompt()`](src/agent/prompt/__init__.py:23) at init
- **IOSystem** is the only module accessing database/files directly

### Configuration Priority Chain
[`LLMConfig.from_sources()`](src/agent/llm_service.py:89) implements:
1. Environment variables (deployment override)
2. `config/llm.json` (project defaults)
3. Hardcoded defaults (fallback)

Environment variables: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`

### Database Schema (SQLite Mode)
Three main tables via SQLAlchemy ORM in [`io_system.py`](src/data/io_system.py:28):
- `characters` - id (PK), data (JSON)
- `items` - id (PK), data (JSON)
- `maps` - id (PK), data (JSON)
- `game_meta` - key (PK), value

All entity data is JSON-serialized Pydantic models.

### StateChange Transaction Model
[`StateChange`](src/data/models.py:1) uses dot-notation paths:
```python
StateChange(
    id="char-01",
    field="attributes.hp",  # Nested path
    operation=ChangeOperation.UPDATE,
    value=5
)
```

Operations: UPDATE (replace), ADD (append to list), DEL (remove)

### NPC Integration
NPC behavior is handled by [`StateEvolution`](src/agent/state_evolution.py:1), not a separate agent. The `evolve_player_action()` method returns:
- `narrative` - What happened
- `changes` - State mutations
- `resolved` - Whether turn is complete
- `next_action_hint` - Suggested next action

This eliminates separate NPC Agent complexity per spec V2 simplification.
