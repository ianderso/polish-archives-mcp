"""Entry point: ``python -m polish_archives_mcp`` / the ``polish-archives-mcp`` script."""

from __future__ import annotations

from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
