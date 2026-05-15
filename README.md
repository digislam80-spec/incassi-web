# Incassi Web

Versione semplice da usare su iPhone senza App Store, Apple Developer o CloudKit.

L'accesso usa una password unica condivisa. In locale, se non imposti niente, la password predefinita è:

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

Tutti gli iPhone collegati allo stesso indirizzo vedono e modificano lo stesso file `incassi.json` salvato sul Mac.

## Pubblicazione online

Per usarla fuori dalla stessa rete Wi-Fi puoi pubblicarla su Render:

1. Crea un repository GitHub con questa cartella.
2. Vai su Render e crea un nuovo `Blueprint` dal repository.
3. Render leggerà `render.yaml`.
4. Imposta la variabile ambiente `SHARED_PASSWORD` con la password vera.
5. Render creerà un disco persistente in `/var/data`, dove verrà salvato `incassi.json`.
6. Apri il link pubblico da Safari su ogni iPhone e usa `Aggiungi alla schermata Home`.

## Nota

Questa versione è volutamente semplice: una password condivisa e un archivio JSON. Per molti usi interni va benissimo. Se in futuro servono utenti separati, permessi, backup automatici o report mensili avanzati, conviene passare a un database come Supabase/Postgres.
