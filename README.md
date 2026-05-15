# Incassi Web

Versione semplice da usare su iPhone senza App Store, Apple Developer o CloudKit.

L'accesso usa una password unica condivisa. In locale, se non imposti niente, la password predefinita e:

```text
incassi2026
```

## Come avviarla

Da questa cartella:

```bash
SHARED_PASSWORD="scegli-una-password" python3 app.py
```

Poi apri dal Mac:

```text
http://localhost:8000
```

Per aprirla da iPhone, Mac e iPhone devono essere sulla stessa rete Wi-Fi. Trova l'indirizzo IP del Mac e apri:

```text
http://IP-DEL-MAC:8000
```

Esempio:

```text
http://192.168.1.25:8000
```

## Condivisione

In locale tutti gli iPhone collegati allo stesso indirizzo vedono e modificano lo stesso file `incassi.json` salvato sul Mac.

Online l'app usa Supabase, se sono impostate queste variabili ambiente:

```text
SUPABASE_URL
SUPABASE_SERVICE_KEY
SHARED_PASSWORD
```

## Import JSON

L'app accetta un file JSON con un elenco di incassi, oppure un oggetto con chiave `incassi`, `entries` o `data`.
Accetta anche l'export di Gestore delle Finanze con righe separate per categoria: le righe vengono aggregate per data.

Esempio:

```json
[
  {
    "data": "15/05/2026",
    "pos": "120,50",
    "contanti": "80",
    "bonifici_dettagli": [
      { "nome": "Mario Rossi", "importo": "25,00" },
      { "nome": "Studio Bianchi", "importo": "15,00" }
    ],
    "paypal": 0,
    "altri": 10,
    "note": "Import storico"
  }
]
```

Alias accettati:

- `POS`: `pos` oppure `os`
- `Contanti`: `contanti`, `cash`
- `Bonifici`: `bonifici`, `bonifico`, `bankTransfer`
- `Bonifici dettagliati`: `bonifici_dettagli`, `bonificiDettagli`, `transfers`, `bonifici_lista`
- `PayPal`: `paypal`
- `Altri metodi`: `altri`, `altro`, `other`, `altriMetodi`

## Backup

Dalla schermata `Importa` puoi usare `Esporta backup` per scaricare un file JSON con tutti gli incassi attualmente presenti nell'app.

## Tabella Supabase

Nel SQL Editor di Supabase esegui:

```sql
create table if not exists public.incassi (
  id uuid primary key default gen_random_uuid(),
  data date not null unique,
  os numeric(12,2) not null default 0,
  contanti numeric(12,2) not null default 0,
  bonifici numeric(12,2) not null default 0,
  bonifici_dettagli jsonb not null default '[]'::jsonb,
  paypal numeric(12,2) not null default 0,
  altri numeric(12,2) not null default 0,
  totale numeric(12,2) not null default 0,
  note text not null default '',
  created_at timestamptz not null default now()
);
```

Se la tabella esiste gia, prima di pubblicare questa versione esegui anche:

```sql
alter table public.incassi
  add column if not exists bonifici_dettagli jsonb not null default '[]'::jsonb;
```

## Pubblicazione online

Per usarla fuori dalla stessa rete Wi-Fi puoi pubblicarla su Render Free + Supabase Free:

1. Crea un repository GitHub con questa cartella.
2. Crea un progetto Supabase Free e la tabella `incassi`.
3. Vai su Render e crea un nuovo Web Service dal repository.
4. Seleziona il piano `Free`.
5. Imposta le variabili ambiente `SHARED_PASSWORD`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
6. Apri il link pubblico da Safari su ogni iPhone e usa `Aggiungi alla schermata Home`.

## Nota

Questa versione è volutamente semplice: una password condivisa e Supabase come archivio online. Per molti usi interni va benissimo. Se in futuro servono utenti separati, permessi o report mensili avanzati, conviene aggiungere login utenti e viste dedicate.
