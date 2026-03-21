# Project Documentation Rules (Non-Obvious Only)

## Ask Mode Specific Guidance

### Documentation Structure
- [`docs/spec_v2_simplified.md`](docs/spec_v2_simplified.md:1) - Main architecture spec with 7-step flow diagram
- [`docs/项目说明文档（1.0）.md`](docs/项目说明文档（1.0）.md:1) - Chinese project overview
- [`docs/建议文档.md`](docs/建议文档.md:1) - Recommendations and suggestions
- Prompt files in [`src/agent/prompt/`](src/agent/prompt/) - Agent behavior definitions

### Dual-Track Data Flow
The core concept is natural language ↔ structured data conversion:
```
Player Input (NL) → DM Agent → Structured Intent → Rule System → Numerical Result
                                                        ↓
Narrative Output ← State Evolution ← State Changes ← IO System
```

Refer to spec_v2_simplified.md Section 2.1 for the complete flow diagram.

### AI Authority Levels
Per the spec, modules have different AI decision authority:
- **High**: DM Agent, State Evolution - Can override rules based on narrative
- **Low**: Rule System, IO System - Deterministic, no AI involvement
- **Medium**: Input System - Basic command parsing only

### Character Attribute Aliases
[`rule_system.py`](src/rule/rule_system.py:87) maps common aliases:
- `luck` → `lucky` (in CharacterStatus)
- All COC attributes: str, con, siz, dex, app, int, pow, edu

When adding new aliases, update `get_attribute_value()` function.

### World Configuration Versions
Two world loading modes exist:
1. **New**: Directory-based (`config/world/<world_name>/`) with split entity files
2. **Old**: Single-table files (`config/world/characters.json`, etc.)

[`WorldLoader`](src/data/init/world_loader.py:30) auto-detects and handles both.
