# Project Debug Rules (Non-Obvious Only)

## Debug Mode Specific Guidance

### Log Configuration
Logging is configured in each module with module-level logger:
```python
logger = logging.getLogger(__name__)
```

Main logging setup is in [`src/main.py`](src/main.py:32) - modify the `basicConfig` there to change global log level.

### LLM Service Error Handling
[`LLMService`](src/agent/llm_service.py:1) has specific exception hierarchy:
- `LLMServiceError` - Base exception
- `LLMAPIError` - API call failures
- `LLMJSONParseError` - JSON parsing failures (critical for agent outputs)
- `LLMRetryExhaustedError` - All retries failed

Enable debug logging to see retry attempts with exponential backoff.

### OpenAI Library Optional Import
[`llm_service.py`](src/agent/llm_service.py:27) handles missing openai library gracefully:
```python
try:
    from openai import OpenAI, APIError, APIConnectionError, RateLimitError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
```

If `OPENAI_AVAILABLE` is False, service will raise `LLMConfigError` on initialization.

### IO System Error Codes
Check return values from [`IOSystem`](src/data/io_system.py:1) methods:
- `0` (`ERROR_SUCCESS`) - Operation successful
- `1` (`ERROR_ID_NOT_FOUND`) - Entity ID doesn't exist
- `2` (`ERROR_FIELD_NOT_FOUND`) - Field path invalid
- `3` (`ERROR_OPERATION_INVALID`) - ChangeOperation not recognized
- `4` (`ERROR_OTHER`) - Unexpected error

### State Evolution Error Field
[`StateEvolutionOutput`](src/agent/state_evolution.py:87) has `erro` field (note typo) for LLM self-correction:
```json
{
  "erro": "Error message for LLM to correct"
}
```

This is intentionally exposed to LLM to enable iterative error correction.
