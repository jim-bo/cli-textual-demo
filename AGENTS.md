# Textualize Observations for AI Agents

Developing TUI applications with Textualize as an AI agent provides several unique insights into building robust terminal interfaces.

## Instructions
- Use TDD (test driven development). think about how you will test the new feature, write the test that fails.
- If you don't know how to test a new feature ASK for clarification.
- The user may tell you to skip TDD for a specific request, that is OK but you need user permission to do that.

## Key Learning Points

### 1. Robust Testing with Pilot
Textual's built-in testing framework (`app.run_test()`) is essential for AI agents. It allows for headless verification of complex UI states, focus transitions, and message passing without needing a physical terminal or interfering with the user's view.

### 2. Widget Subclassing for Event Isolation
Handling specific key events (like "Enter" for submission) is much more reliable when implemented within a custom widget subclass (e.g., `GrowingTextArea`). This ensures the event is caught and handled before the base widget's internal logic can intercept or swallow it, which is particularly critical for consistent behavior during automated tests.

### 3. Asynchronous DOM Operations
DOM operations like `widget.remove()` are asynchronous in Textual. Attempting to mount a new widget with an identical ID immediately after calling `remove()` on its predecessor will trigger `DuplicateIds` errors. For AI agents, the safest patterns are:
- Using dynamic/unique IDs (e.g., appending a timestamp).
- Explicitly awaiting or pausing between removal and re-mounting in test scripts.

### 4. Focus Management
Focus cannot be successfully applied to a widget until it is fully mounted and the DOM has refreshed. Using `self.call_after_refresh(widget.focus)` is the recommended pattern for ensuring a newly created interactive element (like a selection menu) gains focus the moment it appears.

### 5. Key Event Normalization
Key strings provided by `events.Key` can vary in capitalization (e.g., "enter" vs "Enter") depending on the environment or the input driver. Always normalize key strings using `.lower()` during comparisons to ensure the application remains robust across different terminal emulators.

### 6. Reserved Attribute Collisions
Avoid using common generic names like `COMMANDS` as class variables in the `App` class. Textual uses this specific name for its built-in Command Palette logic; shadowing it with a dictionary or other data structure will cause internal library crashes during mount.

### 7. Dynamic Tab Lifecycle
`TabbedContent` requires its internal sub-widgets (like `ContentTabs`) to be fully settled before panes can be reliably added via `add_pane`. When populating tabs dynamically, prefer a small `self.set_timer(0.1, ...)` over `call_after_refresh` to avoid "No immediate child of type ContentTabs" errors.

### 8. Pilot Latency Guard
In headless tests, the `Pilot` message queue can lag behind the test execution thread. Always `await pilot.pause()` after simulated key presses or text changes before asserting on visibility, class changes, or focus transitions.
