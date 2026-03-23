# AGENTS.md — plugins/commands/

Each `.py` file defines one `SlashCommand` subclass. Auto-discovered by `CommandManager.auto_discover()` — no registration needed.

## Pattern

```python
class MyCommand(SlashCommand):
    @property
    def name(self) -> str: return "/mycommand"
    @property
    def description(self) -> str: return "Short description"
    async def execute(self, app, args: List[str]): ...
```

## Notes

- Self-contained widgets (e.g., `tools.py` → `ToolsWidget`) should handle their own `@on()` events internally.
- Commands that need permission set `requires_permission = True`.
- Access the app's `add_to_history()`, `query_one()`, interaction container, etc. via the `app` parameter.
