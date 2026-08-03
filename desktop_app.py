from __future__ import annotations

def main() -> int:
    from invoice_desktop.main import main as desktop_main

    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())