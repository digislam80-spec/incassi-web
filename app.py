from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os
import uuid
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))
DATA_FILE = DATA_DIR / "incassi.json"
SHARED_PASSWORD = os.environ.get("SHARED_PASSWORD", "incassi2026")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
FIELDS = ["os", "contanti", "bonifici", "paypal", "altri"]
FIELD_ALIASES = {
    "os": ["os", "pos"],
    "contanti": ["contanti", "cash", "contante"],
    "bonifici": ["bonifici", "bonifico", "bankTransfer", "bank_transfer", "transfer"],
    "paypal": ["paypal", "payPal", "pay_pal"],
    "altri": ["altri", "altro", "other", "others", "altriMetodi", "altri_metodi"],
}
DATE_ALIASES = ["data", "date", "giorno", "day"]
TRANSFER_ALIASES = ["bonifici_dettagli", "bonificiDettagli", "transfers", "bonifici_lista"]
TRANSFER_NOTE_MARKER = "\n\n[bonifici_dettagli:"
ITALIAN_MONTHS = {
    "gen": 1,
    "gennaio": 1,
    "feb": 2,
    "febbraio": 2,
    "mar": 3,
    "marzo": 3,
    "apr": 4,
    "aprile": 4,
    "mag": 5,
    "maggio": 5,
    "giu": 6,
    "giugno": 6,
    "lug": 7,
    "luglio": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "sett": 9,
    "settembre": 9,
    "ott": 10,
    "ottobre": 10,
    "nov": 11,
    "novembre": 11,
    "dic": 12,
    "dicembre": 12,
}


class StorageError(Exception):
    pass


def use_supabase():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def supabase_request(path, method="GET", payload=None, prefer=None):
    body = None
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }

    if prefer:
        headers["Prefer"] = prefer

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = Request(f"{SUPABASE_URL}/rest/v1/{path}", data=body, headers=headers, method=method)

    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as error:
        detail = error.read().decode("utf-8")
        raise StorageError(f"Supabase HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise StorageError(f"Supabase non raggiungibile: {error.reason}") from error


def load_supabase_entries():
    rows = supabase_request("incassi?select=*&order=data.desc")
    return [normalize_loaded_entry(row) for row in rows or []]


def save_supabase_entry(entry):
    try:
        rows = supabase_request(
            "incassi?on_conflict=data",
            method="POST",
            payload=entry,
            prefer="resolution=merge-duplicates,return=representation",
        )
    except StorageError as error:
        if "bonifici_dettagli" not in str(error):
            raise
        fallback = dict(entry)
        details = fallback.pop("bonifici_dettagli", [])
        fallback["note"] = encode_transfer_details_in_note(fallback.get("note", ""), details)
        rows = supabase_request(
            "incassi?on_conflict=data",
            method="POST",
            payload=fallback,
            prefer="resolution=merge-duplicates,return=representation",
        )
    return normalize_loaded_entry(rows[0]) if rows else entry


def delete_supabase_entry(entry_id):
    supabase_request(f"incassi?id=eq.{entry_id}", method="DELETE")


def load_entries():
    if use_supabase():
        return load_supabase_entries()

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


def save_entry(entry):
    if use_supabase():
        return save_supabase_entry(entry)

    entries = [item for item in load_entries() if item.get("id") != entry["id"]]

    same_date = next((item for item in entries if item.get("data") == entry["data"]), None)
    if same_date:
        entry["id"] = same_date["id"]
        entries = [item for item in entries if item.get("id") != entry["id"]]

    entries.append(entry)
    save_entries(entries)
    return entry


def import_entries(payload):
    if isinstance(payload, dict):
        rows = payload.get("incassi") or payload.get("entries") or payload.get("data") or [payload]
    else:
        rows = payload

    if not isinstance(rows, list):
        raise ValueError("Il JSON deve contenere un elenco di incassi.")

    if looks_like_finance_export(rows):
        rows = adapt_finance_export(rows)

    imported = []
    errors = []

    for index, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("riga non valida")
            entry = normalize_entry(row)
            if not entry.get("data"):
                raise ValueError("data mancante")
            imported.append(save_entry(entry))
        except (ValueError, StorageError) as error:
            errors.append({"row": index, "message": str(error)})

    return {"imported": len(imported), "errors": errors}


def delete_entry(entry_id):
    if use_supabase():
        delete_supabase_entry(entry_id)
        return

    entries = [item for item in load_entries() if item.get("id") != entry_id]
    save_entries(entries)


def normalize_entry(payload):
    transfer_details = normalize_transfer_details(payload)
    entry = {
        "id": payload.get("id") or str(uuid.uuid4()),
        "data": normalize_date(first_value(payload, DATE_ALIASES)),
        "note": str(first_value(payload, ["note", "notes", "nota"], "")).strip(),
        "bonifici_dettagli": transfer_details,
    }

    for field in FIELDS:
        try:
            entry[field] = round(parse_amount(first_value(payload, FIELD_ALIASES[field], 0)), 2)
        except (TypeError, ValueError):
            entry[field] = 0

    if transfer_details:
        entry["bonifici"] = round(sum(item["importo"] for item in transfer_details), 2)

    entry["totale"] = round(sum(entry[field] for field in FIELDS), 2)
    return entry


def normalize_loaded_entry(row):
    row = dict(row)
    note, details = decode_transfer_details_from_note(row.get("note", ""))
    row["note"] = note
    if details and not row.get("bonifici_dettagli"):
        row["bonifici_dettagli"] = details
    entry = normalize_entry(row)
    entry["id"] = row.get("id") or entry["id"]
    return entry


def first_value(payload, names, default=None):
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for name in names:
        if name in payload:
            return payload[name]
        value = lowered.get(str(name).lower())
        if value is not None:
            return value
    return default


def normalize_date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""

    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return raw[:10]

    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw[:10], date_format).date().isoformat()
        except ValueError:
            continue

    parts = raw.lower().replace(".", "").split()
    if len(parts) == 3 and parts[1] in ITALIAN_MONTHS:
        try:
            day = int(parts[0])
            month = ITALIAN_MONTHS[parts[1]]
            year = int(parts[2])
            return datetime(year, month, day).date().isoformat()
        except ValueError:
            pass

    return raw[:10]


def parse_amount(value):
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value or "0").strip().replace("€", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif "." in raw:
        whole, fraction = raw.split(".", 1)
        if len(fraction) == 3 and whole.isdigit() and fraction.isdigit():
            raw = whole + fraction
    else:
        raw = raw
    return float(raw or 0)


def normalize_transfer_details(payload):
    raw = first_value(payload, TRANSFER_ALIASES, [])
    details = []

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []

    if isinstance(raw, dict):
        raw = [raw]

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(first_value(item, ["nome", "name", "cliente", "da", "from"], "")).strip()
            amount = parse_amount(first_value(item, ["importo", "amount", "valore", "totale"], 0))
            if name or amount:
                details.append({"nome": name, "importo": round(amount, 2)})

    if details:
        return details

    name = str(first_value(payload, ["bonifico_nome", "nome_bonifico", "nomeBonifico"], "")).strip()
    amount = parse_amount(first_value(payload, FIELD_ALIASES["bonifici"], 0))
    if name or amount:
        return [{"nome": name, "importo": round(amount, 2)}]

    return []


def encode_transfer_details_in_note(note, details):
    clean_note, _ = decode_transfer_details_from_note(note)
    if not details:
        return clean_note
    return f"{clean_note}{TRANSFER_NOTE_MARKER}{json.dumps(details, ensure_ascii=False)}]"


def decode_transfer_details_from_note(note):
    raw = str(note or "")
    if TRANSFER_NOTE_MARKER not in raw:
        return raw, []
    clean_note, encoded = raw.split(TRANSFER_NOTE_MARKER, 1)
    encoded = encoded.rsplit("]", 1)[0]
    try:
        details = json.loads(encoded)
    except json.JSONDecodeError:
        details = []
    return clean_note.strip(), details if isinstance(details, list) else []


def looks_like_finance_export(rows):
    sample = [row for row in rows[:10] if isinstance(row, dict)]
    return bool(sample) and all({"category", "amount", "date"}.issubset(row.keys()) for row in sample)


def adapt_finance_export(rows):
    grouped = {}
    unknown_categories = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type", "Entrate")).lower() != "entrate":
            continue

        date = normalize_date(row.get("date"))
        if not date:
            continue

        entry = grouped.setdefault(date, {
            "data": date,
            "os": 0,
            "contanti": 0,
            "bonifici": 0,
            "paypal": 0,
            "altri": 0,
            "note": "",
            "bonifici_dettagli": [],
        })

        category = str(row.get("category", "")).strip().lower()
        amount = parse_amount(row.get("amount", 0))
        remark = str(row.get("remark", "")).strip()

        if category == "pos":
            entry["os"] += amount
        elif category == "contanti":
            entry["contanti"] += amount
        elif category == "bonifici":
            entry["bonifici"] += amount
            entry["bonifici_dettagli"].append({"nome": remark, "importo": round(amount, 2)})
        elif category in {"paypal", "pay pal"}:
            entry["paypal"] += amount
        else:
            entry["altri"] += amount
            unknown_categories.setdefault(date, set()).add(row.get("category", "Altro"))

    adapted = []
    for date, entry in grouped.items():
        if unknown_categories.get(date):
            names = ", ".join(sorted(str(name) for name in unknown_categories[date]))
            entry["note"] = f"Categorie importate in Altri: {names}"
        adapted.append(entry)

    return sorted(adapted, key=lambda item: item["data"])


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
            try:
                entries = sorted(load_entries(), key=lambda item: item.get("data", ""), reverse=True)
                self.send_json(entries)
            except StorageError as error:
                self.send_json({"message": str(error)}, status=502)
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

        if parsed.path == "/api/import":
            if not self.require_auth():
                return

            try:
                result = import_entries(self.read_json())
                self.send_json(result, status=201)
            except (ValueError, json.JSONDecodeError) as error:
                self.send_json({"message": str(error)}, status=400)
            except StorageError as error:
                self.send_json({"message": str(error)}, status=502)
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

        try:
            entry = save_entry(normalize_entry(payload))
            self.send_json(entry, status=201)
        except StorageError as error:
            self.send_json({"message": str(error)}, status=502)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        prefix = "/api/incassi/"
        if not parsed.path.startswith(prefix):
            self.send_error(404)
            return

        if not self.require_auth():
            return

        try:
            entry_id = parsed.path[len(prefix):]
            delete_entry(entry_id)
            self.send_json({"ok": True})
        except StorageError as error:
            self.send_json({"message": str(error)}, status=502)

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
