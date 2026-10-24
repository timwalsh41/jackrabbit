#!/usr/bin/env python
"""Entry point for running the Jackrabbit server (``uv run server.py``).

A bare invocation defaults to the ``server`` command (spec: Deployment);
explicit arguments are passed through to the CLI (e.g. ``server.py init-db``).
"""

from jackrabbit.cli import main

if __name__ == "__main__":
    main()
