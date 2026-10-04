"""Create local tokens once. Never print their values or overwrite an existing .env."""

import secrets
from pathlib import Path


def main() -> None:
    target = Path(".env")
    if target.exists():
        print(".env already exists; kept unchanged.")
        return
    template = Path(".env.example").read_text(encoding="utf-8")
    template = template.replace(
        "WEBHOOK_SECRET=\n", f"WEBHOOK_SECRET={secrets.token_urlsafe(32)}\n"
    )
    template = template.replace("ADMIN_TOKEN=\n", f"ADMIN_TOKEN={secrets.token_urlsafe(32)}\n")
    with target.open("x", encoding="utf-8") as handle:
        handle.write(template)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    print("Created .env with separate local tokens. Mode: PAPER.")


if __name__ == "__main__":
    main()
