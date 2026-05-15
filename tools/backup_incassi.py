from pathlib import Path
from urllib.request import Request, urlopen
import json
import os
import subprocess
from datetime import datetime


APP_URL = os.environ.get("INCASSI_APP_URL", "https://incassi-web.onrender.com").rstrip("/")
PASSWORD = os.environ.get("INCASSI_PASSWORD", "incassi2026")
BACKUP_DIR = Path(os.environ.get("INCASSI_BACKUP_DIR", "backups"))


def main():
    entries = fetch_entries()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    target = BACKUP_DIR / f"incassi-backup-{today}.json"
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "source": APP_URL,
        "incassi": entries,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Backup creato: {target} ({len(entries)} incassi)")


def fetch_entries():
    request = Request(
        f"{APP_URL}/api/incassi",
        headers={"X-App-Password": PASSWORD},
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        result = subprocess.run(
            [
                "curl",
                "-fsSL",
                "-H",
                f"X-App-Password: {PASSWORD}",
                f"{APP_URL}/api/incassi",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)


if __name__ == "__main__":
    main()
