"""Concrete TheoProvider implementations.

Each file in this directory is one plugin. To add a new market type:
  1. Create a new file (e.g. `sports_lines.py`)
  2. Define a class implementing the TheoProvider protocol
  3. Register it in the bot's startup config

The bot's core (lipmm/theo/base.py, registry.py, integration glue in
deploy/lip_mode.py) does NOT need to change.
"""
