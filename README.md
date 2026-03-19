---
title: CLI Textual Demo
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: docker
pinned: false
---

# Gemini/Claude CLI TUI Prototype

A Python-based TUI prototype built with [Textual](https://textual.textualize.io/) that mirrors the user experience of modern AI CLI tools.

## Features
- **Scrollable History**: All commands and responses are logged in a top-scrolling container.
- **Dynamic Interaction Area**: A space above the input that appears for background tasks (simulated load with spinner) or interactive selections.
- **Growing Input**: A focused input area at the bottom that highlights when active.
- **Double-Tap Exit**: `Ctrl+D` twice to quit.
- **Mock Commands**:
  - `/help`: Lists commands.
  - `/load`: Simulates a background process with a spinner.
  - `/select`: Shows a model selection menu.
  - `/clear`: Clears the history log.
  - `/ls`: Secure directory listing (demonstrates path jailing).
  - `/head`: View file contents safely.
  - `/survey`: A multi-tab interactive survey.

## Getting Started

### Prerequisites
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended)

### Installation (uv)
```bash
# Clone and install in editable mode
uv sync
uv pip install -e .
```

### Running the TUI
Run the application directly from your terminal:
```bash
uv run demo-cli
```

### Serving via Web Browser
You can serve the application to your browser using `textual-serve`. This runs a terminal emulator in the browser at `http://localhost:8000`.

From the project root, run:
```bash
PYTHONPATH=src uv run textual serve src/cli_textual/app.py
```

## Running Tests
This project uses `pytest` and `textual-pilot` for headless UI testing.
```bash
uv run pytest
```
