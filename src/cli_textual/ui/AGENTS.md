# AGENTS.md — ui/

Custom Textual widgets and modal screens.

## Layout

- `widgets/` — `GrowingTextArea` (multi-line input with submit), `DNASpinner` (animated helix), `LandingPage`
- `screens/` — `PermissionScreen` (modal approval dialog)

## Notes

- Use `@on()` decorators for event handling within widgets.
- Use `self.call_after_refresh(widget.focus)` to focus newly mounted widgets.
- `widget.remove()` is async — await before re-mounting with the same ID.
