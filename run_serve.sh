#!/bin/bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
uv run textual serve "python -m cli_textual.app"
