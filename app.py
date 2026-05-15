from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import json
import os
import uuid


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))
DATA_FILE = DATA_DIR / "incassi.json"
SHARED_PASSWORD = os.environ.get("SHARED_PASSWORD", "incassi2026")


def load_entries():
    if not DATA_FILE.exists():
        return []
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_entries(entries):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_entry(payload):
    fields = ["os", "contanti", "bonifici", "paypal", "altri"]
    entry = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "data": str(payload.get("data", ""))[:10],
        "note": str(payload.get("note", "")).strip(),
    }

    for field in fields:
        try:
            entry[field] = round(float(payload.get(field) or 0), 2)
        except (TypeError, ValueError):
            entry[field] = 0

    entry["totale"] = round(sum(entry[field] for field in fields), 2)
    return entry


class IncassiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR / "static"), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/session":
            self.send_json({"authenticated": self.is_authenticated()})
            return

        if parsed.path == "/api/incassi":
            if not self.require_auth():
                return
            entries = sorted(load_entries(), key=lambda item: item.get("data", ""), reverse=True)
            self.send_json(entries)
            return

        if parsed.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            payload = self.read_json()
            if payload.get("password") == SHARED_PASSWORD:
                self.send_json({"ok": True})
            else:
                self.send_json({"ok": False, "message": "Password non corretta"}, status=401)
            return

        if parsed.path != "/api/incassi":
            self.send_error(404)
            return

        if not self.require_auth():
            return

        payload = self.read_json()
        if not payload.get("data"):
            self.send_error(400, "La data è obbligatoria")
            return

        entry = normalize_entry(payload)
        entries = [item for item in load_entries() if item.get("id") != entry["id"]]

        same_date = next((item for item in entries if item.get("data") == entry["data"]), None)
        if same_date and not payload.get("id"):
            entry["id"] = same_date["id"]
            entries = [item for item in entries if item.get("id") != entry["id"]]

        entries.append(entry)
        save_entries(entries)
        self.send_json(entry, status=201)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        prefix = "/api/incassi/"
        if not parsed.path.startswith(prefix):
            self.send_error(404)
            return

        if not self.require_auth():
            return

        entry_id = parsed.path[len(prefix):]
        entries = [item for item in load_entries() if item.get("id") != entry_id]
        save_entries(entries)
        self.send_json({"ok": True})

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def is_authenticated(self):
        return self.headers.get("X-App-Password") == SHARED_PASSWORD

    def require_auth(self):
        if self.is_authenticated():
            return True
        self.send_json({"message": "Password richiesta"}, status=401)
        return False

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), IncassiHandler)
    print(f"Incassi Web attiva su http://0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
