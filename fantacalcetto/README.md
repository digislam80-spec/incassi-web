# FantaCalcetto

Prima versione MVP per gestire partite di calcetto tra amici.

Sponsored by [Digislam Print Lab](https://digislam.shop). App creata da Riccardo Muollo. Tutti i diritti sono riservati.

## Avvio

```bash
python3 app.py
```

Poi apri:

```text
http://127.0.0.1:5001
```

## Cosa fa gia

- Database SQLite locale con giocatori demo.
- Bacheca pubblica con classifica, potenza, score e squadre gia generate.
- Area admin protetta da PIN per rosa arruolabili e gestione partita.
- Registrazione autonoma calciatore con username, password, nome, WhatsApp e mascotte.
- Branding "La lega del Venerdì" con sponsor Digislam Print Lab.
- Approvazione admin prima di diventare arruolabile.
- Creazione partita con numero massimo di giocatori.
- Convocazioni e stato presenza: invitato, confermato, presente, non gioca.
- Link pubblico personale per confermare la partecipazione.
- Generazione automatica delle squadre bilanciando le stelle.
- Nel giorno della partita le squadre vengono generate automaticamente quando ci sono confermati.
- Nomi squadra goliardici e badge giocatore in base alla potenza.
- Mascotte stile fantacalcio abbinate ai giocatori, modificabili dall'admin.
- Dashboard personale calciatore con statistiche, convocazioni, conferma e disdetta.
- Penalita di score/affidabilita per disdette vicine alla partita.
- Inserimento risultato, gol e assist.
- Aggiornamento score, presenze, vittorie e potenza.

## Admin

La bacheca pubblica e su:

```text
http://127.0.0.1:5001
```

L'area admin e su:

```text
http://127.0.0.1:5001/admin
```

PIN demo:

```text
1234
```

Puoi cambiarlo avviando l'app con la variabile `CALCETTO_ADMIN_PIN`.

## Pubblicazione beta online gratuita

Questa app e pronta per una beta privata su hosting esterno, senza usare `digislam.shop`.

Opzione consigliata per ora: GitHub + Render Free + Supabase. Il progetto include gia:

- `requirements.txt`
- `Procfile`
- `render.yaml`
- `supabase_fantacalcetto_schema.sql`

Variabili ambiente da impostare online:

```text
SECRET_KEY=una_stringa_lunga_casuale
CALCETTO_ADMIN_PIN=un_pin_tuo_non_1234
DATABASE_URL=postgresql://...
```

Comando di avvio produzione:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT
```

Supabase:

Nel SQL Editor del progetto Supabase esegui `supabase_fantacalcetto_schema.sql`. Le tabelle sono `players`, `matches` e `match_players`; non toccano la tabella `incassi` dell'altra app.

In locale l'app continua a usare SQLite (`calcetto.db`) se `DATABASE_URL` non e impostato. Online, quando `DATABASE_URL` e presente, usa PostgreSQL/Supabase e i dati restano salvati anche dopo i redeploy.

Checklist prima di condividere il link nel gruppo:

- Cambiare `CALCETTO_ADMIN_PIN`.
- Usare un `SECRET_KEY` sicuro.
- Eseguire lo schema Supabase di FantaCalcetto.
- Impostare `DATABASE_URL` con la connection string Supabase.
- Fare una registrazione test da telefono.
- Copiare nel gruppo WhatsApp il link pubblico dell'app.

## Prossimi innesti goliardici

- Badge e titoli tipo "Bomber da riscaldamento" o "Ha litigato col pallone".
- Messaggi automatici stile spogliatoio.
- Classifica marcatori, MVP, bidone della serata.
- Generazione squadre con nomi casuali.
- Inviti WhatsApp pronti da copiare.
