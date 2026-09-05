"""CLI entry for Podium HTTP API."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run(
        "recovery.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
