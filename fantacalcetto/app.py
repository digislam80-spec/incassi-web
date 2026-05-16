import itertools
import json
import os
import random
import sqlite3
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from functools import wraps
from threading import Lock

from flask import Flask, Response, g, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # Local SQLite mode does not need psycopg installed.
    psycopg = None
    dict_row = None


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get("FANTACALCETTO_DB_PATH", os.path.join(BASE_DIR, "calcetto.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
SEED_DEMO_DATA = os.environ.get("FANTACALCETTO_SEED_DEMO", "").lower() in ("1", "true", "yes")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "calcetto-local-demo")
ADMIN_PIN = os.environ.get("CALCETTO_ADMIN_PIN", "1234")
DB_INIT_LOCK = Lock()
DATA_TABLES = [
    "leagues",
    "league_memberships",
    "league_requests",
    "players",
    "matches",
    "match_players",
    "award_types",
    "match_awards",
    "password_reset_requests",
    "league_events",
    "league_event_comments",
    "match_comments",
    "transfer_proposals",
]

DEFAULT_LEAGUE_SLUG = "lega-bombonera"
DEFAULT_LEAGUE_NAME = "Lega Bombonera"
DEFAULT_LEAGUE_LOGO = "league-bombonera.svg"
DEFAULT_DEVELOP_USERNAME = os.environ.get("FANTACALCETTO_DEVELOP_USERNAME", "riccardo")
DEFAULT_DEVELOP_PASSWORD = os.environ.get("FANTACALCETTO_DEVELOP_PASSWORD", "Bombonera2026!")
PUBLIC_DEVELOP_FALLBACK_PASSWORD = "Bombonera2026!"

APP_UPDATES = [
    {
        "title": "MVP a tempo",
        "body": "Il Mister assegna l'MVP partita: vale bonus score, finisce su LegaGram e il badge resta solo fino alla partita successiva se il campione conferma davvero.",
        "tag": "Premi",
    },
    {
        "title": "Formazioni più leggibili",
        "body": "Campo tattico e liste squadra danno più spazio a mascotte, nomi veri, overall e dettagli tecnici: più TV, meno elenco della spesa.",
        "tag": "Partita",
    },
    {
        "title": "Richiesta nuova lega",
        "body": "Dal login un supporter può chiedere al Develop di aprire una nuova lega. Se approvato, diventa Mister solo di quella lega.",
        "tag": "Leghe",
    },
    {
        "title": "Ruoli multi-lega",
        "body": "La stessa persona può supportare una lega e amministrarne un'altra: ogni torneo resta separato, sotto supervisione Develop.",
        "tag": "Develop",
    },
    {
        "title": "Fede da curva",
        "body": "Commenti e reazioni su LegaGram aumentano il punteggio Fede. Per i supporter è orgoglio da tribuna, per i calciatori pesa anche un po' sull'overall.",
        "tag": "LegaGram",
    },
    {
        "title": "Digislam Dev Room",
        "body": "Nasce la fonte ufficiale con spunta blu che racconta cosa cambia nell'app, senza verbali noiosi da condominio sportivo.",
        "tag": "Develop",
    },
    {
        "title": "Ticker SkyCalcetto24",
        "body": "La partita ora parla come una diretta TV: news scorrevoli, countdown più chiaro e stato personale senza blocchi confusi.",
        "tag": "Partita",
    },
    {
        "title": "Storico solo analisi",
        "body": "Le partite già fatte aprono una scheda pulita con risultato, formazioni, pagelle e premi. I commenti restano su LegaGram.",
        "tag": "Storico",
    },
    {
        "title": "Formazioni trascinabili",
        "body": "Mister e Develop possono spostare graficamente i calciatori tra Squadra A, Squadra B e panchina prima di salvare.",
        "tag": "Mister",
    },
    {
        "title": "SkySpogliatoio Mercato",
        "body": "Il Mister può proporre prestiti o cessioni definitive tra squadre: il calciatore approva, rifiuta o paga dazio in affidabilità.",
        "tag": "Mercato",
    },
    {
        "title": "Develop arbitro delle leghe",
        "body": "Approvazioni, spostamenti di lega, promozioni e degradazioni a supporter passano dal Develop: il Mister pensa alla partita.",
        "tag": "Develop",
    },
    {
        "title": "Next Match più hype",
        "body": "La home calciatore mette davanti countdown, squadre e formazioni quando sono pronte: meno caos, più serata Champions.",
        "tag": "Partita",
    },
    {
        "title": "Scelta lega in registrazione",
        "body": "Chi si registra sceglie subito la lega: supporter e richieste calciatore finiscono nello spogliatoio corretto.",
        "tag": "Leghe",
    },
    {
        "title": "Identità lega modificabile",
        "body": "Il Develop può ritoccare nome, logo e colori delle leghe esistenti senza toccare giocatori e storico.",
        "tag": "Develop",
    },
    {
        "title": "Lega Bombonera ufficiale",
        "body": "I dati attuali sono stati agganciati alla Lega Bombonera. Il Develop può creare nuove leghe e assegnare Mister dedicati.",
        "tag": "Develop",
    },
    {
        "title": "Logo lega attivo",
        "body": "La Bombonera ha il suo stemma verde e oro. Le prossime leghe potranno avere logo e identità separata.",
        "tag": "Grafica",
    },
    {
        "title": "Dashboard meno caotiche",
        "body": "Admin e calciatore ora separano partita, storico, profilo e approvazioni: meno scroll mentale, più calcetto.",
        "tag": "Esperienza",
    },
    {
        "title": "Profilo in pagina dedicata",
        "body": "Il calciatore modifica dati, piede e mascotte in una schermata separata e torna alla home quando salva.",
        "tag": "Profilo",
    },
    {
        "title": "Storico partite più visibile",
        "body": "Le partite future e quelle già giocate sono divise meglio, così nessuno si perde tra convocazioni e pagelle.",
        "tag": "Partite",
    },
    {
        "title": "App più chiara da telefono",
        "body": "Partite, admin e profilo iniziano a separare meglio azioni rapide, stato partita e storico.",
        "tag": "Mobile",
    },
    {
        "title": "Date in italiano",
        "body": "Le date iniziano a parlare come il gruppo: Venerdì 22 maggio alle 21:15, non codici da gestionale.",
        "tag": "Esperienza",
    },
    {
        "title": "Card scudo pubblicata",
        "body": "La card profilo usa uno scudo dorato più pulito: overall centrato, mascotte leggibile e statistiche rapide ordinate.",
        "tag": "Grafica",
    },
    {
        "title": "Card profilo più professionale",
        "body": "La figurina calciatore diventa uno scudo stile card calcistica: overall più grande, mascotte protagonista e niente box inutile.",
        "tag": "Grafica",
    },
    {
        "title": "Mascotte selezionabili al click",
        "body": "Nel profilo il dropdown mascotte lascia spazio a una griglia di avatar grandi: clicchi la mascotte e la scegli.",
        "tag": "Profilo",
    },
    {
        "title": "Aiuto rapido nel profilo",
        "body": "Nel profilo calciatore c'è un tasto che apre una spiegazione veloce di cosa si può fare con l'app.",
        "tag": "Guida",
    },
    {
        "title": "Cronache scritte dai calciatori",
        "body": "Ogni calciatore può pubblicare una cronaca di spogliatoio: battute, comunicazioni e perle tattiche finiscono in bacheca.",
        "tag": "Spogliatoio",
    },
    {
        "title": "Profilo calciatore modificabile",
        "body": "Ora ogni calciatore può ritoccare nome, soprannome, WhatsApp, piede e mascotte anche dopo la registrazione.",
        "tag": "Profilo",
    },
    {
        "title": "Overall in stile figurina",
        "body": "La carta calciatore mette più in vista rating, stelle, ruolo e mascotte: finalmente il talento sembra quasi ufficiale.",
        "tag": "Grafica",
    },
    {
        "title": "Bacheca spogliatoio attiva",
        "body": "Da oggi FantaCalcetto racconta registrazioni, conferme, disdette e novità dell'app in una cronaca unica.",
        "tag": "Novità app",
    },
    {
        "title": "Stato conferma più chiaro",
        "body": "Il calciatore vede Da confermare in neutro, Confermato in verde e In lista d'attesa in giallo.",
        "tag": "Esperienza calciatore",
    },
    {
        "title": "Recupero password dal mister",
        "body": "Se un calciatore dimentica la password può chiedere soccorso: l'admin imposta una password provvisoria.",
        "tag": "Account",
    },
    {
        "title": "Ruoli Supporter e Calciatore",
        "body": "Chi si registra entra subito come supporter. Il Develop può poi promuoverlo a calciatore arruolabile nella lega giusta.",
        "tag": "Account",
    },
]

TEAM_NAMES = [
    ("Real Madrink", "Atletico Ma Non Troppo"), ("AC Tua", "Dinamo Spritz"),
    ("Boca Senior", "Paris San Gennar"), ("Lokomotiv Arrosto", "Sporting Aperitivo"),
    ("Scapoli FC", "Ammogliati United"), ("Birrareal", "Frittatina City"),
    ("Panchina Hotspur", "Borussia Porchetta"), ("Real Vesuvio", "Atletico Sciorta"),
    ("Dinamo Frittur", "Sporting Sasicc"), ("New Team E Nient", "Longobarda 2.0"),
    ("Real Cornetto", "Celta Vino"), ("Pro Secco FC", "Bayern Miez"),
    ("Ajax Sapone", "Manchester Sinty"), ("Intervallo FC", "Napoli Centrale"),
    ("Lazio di Sole", "Roma Capoccia"), ("Juve Stabirra", "Milanese Imbruttiti"),
    ("Udinese Ma Non Troppo", "Sampdoria di Panza"), ("Torino Sbagliato", "Fiorentina 5+"),
    ("Salernitana Subito", "Genoa Gin Tonic"), ("Real Sciatavinn", "Atletico Ma Chi"),
    ("Dinamo Appanzati", "Boca Lievito"), ("Sporting Panuozzo", "Paris Saint Gennar"),
    ("Lokomotiv Cuzzetiello", "Aston Birra"), ("Crystal Pallon", "Tottenham Hotspurch"),
]

TEAM_LOGOS = [f"crest-{index}" for index in range(1, 21)]


def team_name_ideas():
    names = []
    for pair in TEAM_NAMES:
        names.extend(pair)
    names.extend(MARKET_TEAM_IDEAS)
    return sorted(set(names))

MARKET_TEAM_IDEAS = [
    "Real Madrink",
    "Atletico Ma Non Troppo",
    "Boca Senior",
    "Dinamo Spritz",
    "Sporting Aperitivo",
    "Paris San Gennar",
    "Lokomotiv Arrosto",
    "Scapoli FC",
    "Ammogliati United",
    "Birrareal",
    "Frittatina City",
    "Panchina Hotspur",
]

MARKET_OFFERS = [
    "un cornetto caldo",
    "una birra post partita",
    "una pizza a portafoglio",
    "un pacchetto di patatine",
    "due caffè e una promessa",
    "una borraccia mezza piena",
    "un buono sfotto' illimitato",
    "tre minuti senza essere criticato",
]

TRANSFER_ACCEPT_PHRASES = [
    "{player} firma con {team}: operazione da {offer}. SkySpogliatoio conferma, lo spogliatoio giudica.",
    "{player} saluta {old_team} e vola a {team}. Formula {kind}, pagamento in {offer}.",
    "Ufficiale: {player} passa a {team}. Il direttore sportivo parla di progetto, il gruppo parla di {offer}.",
    "{player} ha detto sì: da oggi è uomo {team}. Trattativa chiusa con {offer} e stretta di mano sudata.",
]

TRANSFER_DECLINE_PHRASES = [
    "{player} blocca il trasferimento a {team}: la società prende atto e l'affidabilità fa stretching verso il basso.",
    "{player} rifiuta {team}. Il mercato piange, il Mister prende appunti sul taccuino delle vendette sportive.",
    "Niente accordo: {player} resta dov'e'. Offerta da {offer} rispedita al mittente, punti disciplina in uscita.",
]

PLAYER_TITLES = {
    5: "Top player dichiarato",
    4: "Pericolo pubblico",
    3: "Onesto mestierante",
    2: "Cuore e tibia",
    1: "Progetto tecnico",
}

FOOT_LABELS = {
    "right": "Destro",
    "left": "Sinistro",
    "both": "Entrambi",
}

WEEKDAYS_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
WEEKDAYS_SHORT_IT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
MONTHS_IT = [
    "",
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]

MASCOTS = {
    "fantasista": {"code": "F10", "label": "O' Poet ca palla", "class": "gold"},
    "saracinesca": {"code": "GK", "label": "A' Serranda e Scampia", "class": "blue"},
    "panzer": {"code": "PZ", "label": "O' Cingolato", "class": "red"},
    "diesel": {"code": "DS", "label": "O' Diesel senza fine", "class": "green"},
    "tackle": {"code": "TK", "label": "O' Scippatore e palloni", "class": "red"},
    "trivela": {"code": "TV", "label": "A' Trivela e Marechiaro", "class": "blue"},
    "tap_in": {"code": "TI", "label": "O' Tap-in sotto porta", "class": "gold"},
    "jolly": {"code": "JY", "label": "O' Jolly ca fa casino", "class": "green"},
    "regista": {"code": "RG", "label": "O' Professore d'o passaggio", "class": "blue"},
    "bomber": {"code": "B9", "label": "O' Bomber ro vicariello", "class": "gold"},
    "muraglia": {"code": "MW", "label": "O' Muro e tufo", "class": "red"},
    "scatto": {"code": "SP", "label": "O' Scatto senza fiato", "class": "green"},
    "rabona": {"code": "RB", "label": "A' Rabona ca nun esce", "class": "blue"},
    "pressing": {"code": "PR", "label": "O' Pressing appiccicato", "class": "green"},
    "caviglia": {"code": "CV", "label": "A' Caviglia ballerina", "class": "red"},
    "professore": {"code": "PF", "label": "O' Mister d'a lavagna", "class": "blue"},
    "meteorite": {"code": "MT", "label": "O' Meteorite ncopp'a fascia", "class": "gold"},
    "sciarpa": {"code": "SC", "label": "A' Sciarpa tattica", "class": "green"},
    "rigorista": {"code": "PK", "label": "O' Rigorista morale", "class": "gold"},
    "varista": {"code": "VAR", "label": "O' Varista d'o gruppo", "class": "blue"},
}


def db():
    if not app.config.get("DB_INITIALIZING"):
        ensure_database_ready()
    if "db" not in g:
        if USE_POSTGRES:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL impostato, ma psycopg non è installato.")
            g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            db_dir = os.path.dirname(DB_PATH)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def sql_for_backend(sql):
    if not USE_POSTGRES:
        return sql
    translated = sql.replace("?", "%s")
    translated = translated.replace("m.match_date >= datetime('now', '-1 day')", "m.match_date::timestamp >= now() - interval '1 day'")
    translated = translated.replace("m.match_date < datetime('now', '-1 day')", "m.match_date::timestamp < now() - interval '1 day'")
    translated = translated.replace("match_date >= datetime('now', '-4 hours')", "match_date::timestamp >= now() - interval '4 hours'")
    translated = translated.replace("match_date < datetime('now', '-4 hours')", "match_date::timestamp < now() - interval '4 hours'")
    translated = translated.replace("max(0, score - %s)", "greatest(0, score - %s)")
    translated = translated.replace("max(0, score + %s)", "greatest(0, score + %s)")
    translated = translated.replace("max(0, reliability - %s)", "greatest(0, reliability - %s)")
    translated = translated.replace("min(100, reliability + %s)", "least(100, reliability + %s)")
    translated = translated.replace("min(5, max(1, power + %s))", "least(5, greatest(1, power + %s))")
    translated = translated.replace(
        "min(5, max(1, power + case when score + %s >= power * 25 then 1 else 0 end))",
        "least(5, greatest(1, power + case when score + %s >= power * 25 then 1 else 0 end))",
    )
    return translated


def query(sql, params=(), one=False):
    cursor = db().execute(sql_for_backend(sql), params)
    rows = cursor.fetchall()
    cursor.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    connection = db()
    statement = sql_for_backend(sql)
    normalized = " ".join(statement.lower().split())
    needs_returning_id = (
        USE_POSTGRES
        and normalized.startswith(("insert into players", "insert into matches"))
        and " returning " not in normalized
        and " on conflict " not in normalized
    )
    if needs_returning_id:
        statement = f"{statement.rstrip()} returning id"
    cursor = connection.execute(statement, params)
    inserted_id = None
    if needs_returning_id:
        row = cursor.fetchone()
        inserted_id = row["id"] if row else None
    connection.commit()
    return inserted_id if USE_POSTGRES else cursor.lastrowid


def is_admin():
    return session.get("is_admin") is True


def current_player():
    if "current_player_value" in g:
        return g.current_player_value
    player_id = session.get("player_id")
    if not player_id:
        g.current_player_value = None
        return None
    player = query("select * from players where id = ?", (player_id,), one=True)
    if player and player["account_status"] in ("rejected", "removed"):
        session.pop("player_id", None)
        g.current_player_value = None
        return None
    g.current_player_value = player
    return player


def current_player_role():
    player = current_player()
    if not player:
        return "member"
    if "app_role" in player.keys() and player["app_role"] == "develop":
        return "develop"
    league_id = session.get("active_league_id") or player["league_id"]
    if league_id:
        membership = query(
            "select role from league_memberships where player_id = ? and league_id = ? and status = 'approved' limit 1",
            (player["id"], league_id),
            one=True,
        )
        if membership and membership["role"] in ("mister", "develop"):
            return membership["role"]
    return (player["app_role"] if "app_role" in player.keys() else "") or "member"


def is_develop():
    return current_player_role() == "develop"


def is_mister():
    return current_player_role() in ("develop", "mister")


def can_manage():
    return is_admin() or is_mister()


def is_player_logged_in():
    return current_player() is not None


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not can_manage():
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def require_player(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_player():
            return redirect(url_for("player_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_user_state():
    return {
        "is_admin": is_admin(),
        "is_mister": is_mister(),
        "is_develop": is_develop(),
        "can_manage": can_manage(),
        "current_player": current_player(),
        "current_league": current_league(),
        "current_memberships": player_league_memberships(current_player()["id"]) if current_player() else [],
    }


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.exception("Errore non gestito su %s", request.path)
    return render_template("error.html", error=error), 500


def safe_schema_execute(connection, statement):
    try:
        connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        app.logger.exception("Migrazione schema ignorata: %s", statement)


def init_db():
    connection = db()
    if USE_POSTGRES:
        connection.execute(
            """
            create table if not exists leagues (
                id integer generated by default as identity primary key,
                name text not null,
                slug text not null unique,
                logo text default '',
                primary_color text default '#0f6b4f',
                secondary_color text default '#f2c94c',
                active integer not null default 1,
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists players (
                id integer generated by default as identity primary key,
                name text not null,
                nickname text default '',
                phone text not null,
                username text default '',
                password_hash text default '',
                account_status text not null default 'approved',
                account_type text not null default 'player',
                app_role text not null default 'member',
                league_id integer,
                supporter_player_name text default '',
                supporter_relation text default '',
                permanent_team_name text default '',
                role text not null default 'Jolly',
                preferred_foot text not null default 'right',
                mascot text not null default 'jolly',
                mascot_name text default '',
                power numeric(2,1) not null default 3 check(power between 1 and 5),
                score integer not null default 0,
                faith_score integer not null default 0,
                goals integer not null default 0,
                assists integer not null default 0,
                wins integer not null default 0,
                matches integer not null default 0,
                reliability integer not null default 80,
                invite_token text not null unique,
                active integer not null default 1,
                is_guest integer not null default 0,
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists transfer_proposals (
                id integer generated by default as identity primary key,
                league_id integer,
                player_id integer not null references players(id) on delete cascade,
                from_team text default '',
                to_team text not null,
                transfer_type text not null default 'loan',
                offer_label text default '',
                status text not null default 'pending',
                created_by_player_id integer references players(id) on delete set null,
                created_at timestamptz not null default now(),
                responded_at timestamptz
            )
            """
        )
        connection.execute(
            """
            create table if not exists matches (
                id integer generated by default as identity primary key,
                league_id integer,
                title text not null,
                match_date text not null,
                location text not null,
                player_limit integer not null default 10,
                status text not null default 'open',
                team_a_name text default 'Squadra A',
                team_b_name text default 'Squadra B',
                team_a_logo text not null default 'crest-1',
                team_b_logo text not null default 'crest-2',
                team_a_score integer,
                team_b_score integer,
                result_processed integer not null default 0,
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists match_players (
                match_id integer not null references matches(id) on delete cascade,
                player_id integer not null references players(id) on delete cascade,
                response text not null default 'invited',
                team text,
                goals integer not null default 0,
                assists integer not null default 0,
                rating numeric(3,1),
                review text default '',
                points_awarded integer not null default 0,
                win_awarded integer not null default 0,
                power_bonus_awarded numeric(2,1) not null default 0,
                cancelled_at timestamptz,
                responded_at timestamptz,
                penalty_points integer not null default 0,
                primary key(match_id, player_id)
            )
            """
        )
        connection.execute(
            """
            create table if not exists award_types (
                id integer generated by default as identity primary key,
                name text not null unique,
                description text default '',
                active integer not null default 1,
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists match_awards (
                id integer generated by default as identity primary key,
                match_id integer not null references matches(id) on delete cascade,
                award_type_id integer not null references award_types(id) on delete cascade,
                player_id integer not null references players(id) on delete cascade,
                note text default '',
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists password_reset_requests (
                id integer generated by default as identity primary key,
                player_id integer references players(id) on delete set null,
                display_name text default '',
                username text default '',
                phone text default '',
                message text default '',
                status text not null default 'pending',
                temp_password_set integer not null default 0,
                created_at timestamptz not null default now(),
                resolved_at timestamptz
            )
            """
        )
        connection.execute(
            """
            create table if not exists league_events (
                id integer generated by default as identity primary key,
                league_id integer,
                actor_player_id integer references players(id) on delete set null,
                event_type text not null default 'news',
                actor_display_role text default '',
                title text not null,
                body text default '',
                visibility text not null default 'all',
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists league_event_comments (
                id integer generated by default as identity primary key,
                event_id integer not null references league_events(id) on delete cascade,
                player_id integer references players(id) on delete set null,
                display_role text default '',
                body text not null,
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            """
            create table if not exists match_comments (
                id integer generated by default as identity primary key,
                match_id integer not null references matches(id) on delete cascade,
                player_id integer references players(id) on delete set null,
                body text not null,
                visibility text not null default 'all',
                created_at timestamptz not null default now()
            )
            """
        )
        connection.execute(
            "update matches set title = 'Calcetto del Venerdì' where title in ('Calcetto del Venerdi', 'Calcetto del Giovedi')"
        )
        connection.execute(
            """
            insert into leagues (name, slug, logo, primary_color, secondary_color)
            values ('Lega Bombonera', 'lega-bombonera', 'league-bombonera.svg', '#0f6b4f', '#f2c94c')
            on conflict(slug) do update set
                name = excluded.name,
                logo = excluded.logo,
                primary_color = excluded.primary_color,
                secondary_color = excluded.secondary_color,
                active = 1
            """
        )
        connection.commit()
        connection.execute(
            """
            create table if not exists league_memberships (
                id integer generated by default as identity primary key,
                player_id integer not null references players(id) on delete cascade,
                league_id integer not null references leagues(id) on delete cascade,
                role text not null default 'supporter',
                status text not null default 'approved',
                created_at timestamptz not null default now(),
                unique(player_id, league_id)
            )
            """
        )
        connection.execute(
            """
            create table if not exists league_requests (
                id integer generated by default as identity primary key,
                requester_player_id integer references players(id) on delete set null,
                username text default '',
                display_name text default '',
                phone text default '',
                league_name text not null,
                note text default '',
                status text not null default 'pending',
                created_league_id integer references leagues(id) on delete set null,
                resolved_at timestamptz,
                created_at timestamptz not null default now()
            )
            """
        )
        connection.commit()
        for statement in (
            "alter table players alter column power type numeric(2,1) using power::numeric",
            "alter table players add column if not exists preferred_foot text not null default 'right'",
            "alter table players add column if not exists is_guest integer not null default 0",
            "alter table players add column if not exists account_type text not null default 'player'",
            "alter table players add column if not exists app_role text not null default 'member'",
            "alter table players add column if not exists league_id integer",
            "alter table players add column if not exists supporter_player_name text default ''",
            "alter table players add column if not exists supporter_relation text default ''",
            "alter table players add column if not exists permanent_team_name text default ''",
            "alter table players add column if not exists faith_score integer not null default 0",
            "alter table matches add column if not exists league_id integer",
            "alter table matches add column if not exists result_processed integer not null default 0",
            "alter table matches add column if not exists team_a_logo text not null default 'crest-1'",
            "alter table matches add column if not exists team_b_logo text not null default 'crest-2'",
            "alter table league_events add column if not exists league_id integer",
            "alter table league_events add column if not exists actor_display_role text default ''",
            "alter table league_event_comments add column if not exists display_role text default ''",
            "alter table match_players add column if not exists responded_at timestamptz",
            "alter table match_players add column if not exists rating numeric(3,1)",
            "alter table match_players add column if not exists review text default ''",
            "alter table match_players add column if not exists points_awarded integer not null default 0",
            "alter table match_players add column if not exists win_awarded integer not null default 0",
            "alter table match_players add column if not exists power_bonus_awarded numeric(2,1) not null default 0",
            "alter table password_reset_requests add column if not exists temp_password_set integer not null default 0",
        ):
            safe_schema_execute(connection, statement)
        safe_schema_execute(
            connection,
            """
            update match_players
            set responded_at = current_timestamp
            where response in ('confirmed', 'present') and responded_at is null
            """,
        )
        ensure_default_league_and_roles()
        ensure_player_memberships()
        seed_award_types()
        seed_develop_feed()
        seed_initial_data()
        return

    connection.executescript(
        """
        create table if not exists leagues (
            id integer primary key autoincrement,
            name text not null,
            slug text not null unique,
            logo text default '',
            primary_color text default '#0f6b4f',
            secondary_color text default '#f2c94c',
            active integer not null default 1,
            created_at text not null default current_timestamp
        );

        create table if not exists league_memberships (
            id integer primary key autoincrement,
            player_id integer not null references players(id) on delete cascade,
            league_id integer not null references leagues(id) on delete cascade,
            role text not null default 'supporter',
            status text not null default 'approved',
            created_at text not null default current_timestamp,
            unique(player_id, league_id)
        );

        create table if not exists league_requests (
            id integer primary key autoincrement,
            requester_player_id integer references players(id) on delete set null,
            username text default '',
            display_name text default '',
            phone text default '',
            league_name text not null,
            note text default '',
            status text not null default 'pending',
            created_league_id integer references leagues(id) on delete set null,
            resolved_at text,
            created_at text not null default current_timestamp
        );

        create table if not exists players (
            id integer primary key autoincrement,
            name text not null,
            nickname text default '',
            phone text not null,
            username text default '',
            password_hash text default '',
            account_status text not null default 'approved',
            account_type text not null default 'player',
            app_role text not null default 'member',
            league_id integer,
            supporter_player_name text default '',
            supporter_relation text default '',
            permanent_team_name text default '',
            role text not null default 'Jolly',
            preferred_foot text not null default 'right',
            mascot text not null default 'jolly',
            mascot_name text default '',
            power numeric not null default 3 check(power between 1 and 5),
            score integer not null default 0,
            faith_score integer not null default 0,
            goals integer not null default 0,
            assists integer not null default 0,
            wins integer not null default 0,
            matches integer not null default 0,
            reliability integer not null default 80,
            invite_token text not null unique,
            active integer not null default 1,
            is_guest integer not null default 0,
            created_at text not null default current_timestamp
        );

        create table if not exists transfer_proposals (
            id integer primary key autoincrement,
            league_id integer,
            player_id integer not null references players(id) on delete cascade,
            from_team text default '',
            to_team text not null,
            transfer_type text not null default 'loan',
            offer_label text default '',
            status text not null default 'pending',
            created_by_player_id integer references players(id) on delete set null,
            created_at text not null default current_timestamp,
            responded_at text
        );

        create table if not exists matches (
            id integer primary key autoincrement,
            league_id integer,
            title text not null,
            match_date text not null,
            location text not null,
            player_limit integer not null default 10,
            status text not null default 'open',
            team_a_name text default 'Squadra A',
            team_b_name text default 'Squadra B',
            team_a_logo text not null default 'crest-1',
            team_b_logo text not null default 'crest-2',
            team_a_score integer,
            team_b_score integer,
            result_processed integer not null default 0,
            created_at text not null default current_timestamp
        );

        create table if not exists match_players (
            match_id integer not null references matches(id) on delete cascade,
            player_id integer not null references players(id) on delete cascade,
            response text not null default 'invited',
            team text,
            goals integer not null default 0,
            assists integer not null default 0,
            rating numeric,
            review text default '',
            points_awarded integer not null default 0,
            win_awarded integer not null default 0,
            power_bonus_awarded numeric not null default 0,
            cancelled_at text,
            responded_at text,
            penalty_points integer not null default 0,
            primary key(match_id, player_id)
        );

        create table if not exists award_types (
            id integer primary key autoincrement,
            name text not null unique,
            description text default '',
            active integer not null default 1,
            created_at text not null default current_timestamp
        );

        create table if not exists match_awards (
            id integer primary key autoincrement,
            match_id integer not null references matches(id) on delete cascade,
            award_type_id integer not null references award_types(id) on delete cascade,
            player_id integer not null references players(id) on delete cascade,
            note text default '',
            created_at text not null default current_timestamp
        );

        create table if not exists password_reset_requests (
            id integer primary key autoincrement,
            player_id integer references players(id) on delete set null,
            display_name text default '',
            username text default '',
            phone text default '',
            message text default '',
            status text not null default 'pending',
            temp_password_set integer not null default 0,
            created_at text not null default current_timestamp,
            resolved_at text
        );

        create table if not exists league_events (
            id integer primary key autoincrement,
            league_id integer,
            actor_player_id integer references players(id) on delete set null,
            event_type text not null default 'news',
            actor_display_role text default '',
            title text not null,
            body text default '',
            visibility text not null default 'all',
            created_at text not null default current_timestamp
        );

        create table if not exists league_event_comments (
            id integer primary key autoincrement,
            event_id integer not null references league_events(id) on delete cascade,
            player_id integer references players(id) on delete set null,
            display_role text default '',
            body text not null,
            created_at text not null default current_timestamp
        );

        create table if not exists match_comments (
            id integer primary key autoincrement,
            match_id integer not null references matches(id) on delete cascade,
            player_id integer references players(id) on delete set null,
            body text not null,
            visibility text not null default 'all',
            created_at text not null default current_timestamp
        );
        """
    )
    connection.commit()
    columns = [row["name"] for row in query("pragma table_info(players)")]
    player_migrations = {
        "mascot": "alter table players add column mascot text not null default 'jolly'",
        "mascot_name": "alter table players add column mascot_name text default ''",
        "username": "alter table players add column username text default ''",
        "password_hash": "alter table players add column password_hash text default ''",
        "account_status": "alter table players add column account_status text not null default 'approved'",
        "account_type": "alter table players add column account_type text not null default 'player'",
        "app_role": "alter table players add column app_role text not null default 'member'",
        "league_id": "alter table players add column league_id integer",
        "supporter_player_name": "alter table players add column supporter_player_name text default ''",
        "supporter_relation": "alter table players add column supporter_relation text default ''",
        "permanent_team_name": "alter table players add column permanent_team_name text default ''",
        "faith_score": "alter table players add column faith_score integer not null default 0",
        "preferred_foot": "alter table players add column preferred_foot text not null default 'right'",
        "is_guest": "alter table players add column is_guest integer not null default 0",
    }
    for column, sql in player_migrations.items():
        if column not in columns:
            connection.execute(sql)
    match_player_columns = [row["name"] for row in query("pragma table_info(match_players)")]
    match_player_migrations = {
        "cancelled_at": "alter table match_players add column cancelled_at text",
        "responded_at": "alter table match_players add column responded_at text",
        "penalty_points": "alter table match_players add column penalty_points integer not null default 0",
        "rating": "alter table match_players add column rating numeric",
        "review": "alter table match_players add column review text default ''",
        "points_awarded": "alter table match_players add column points_awarded integer not null default 0",
        "win_awarded": "alter table match_players add column win_awarded integer not null default 0",
        "power_bonus_awarded": "alter table match_players add column power_bonus_awarded numeric not null default 0",
    }
    for column, sql in match_player_migrations.items():
        if column not in match_player_columns:
            connection.execute(sql)
    match_columns = [row["name"] for row in query("pragma table_info(matches)")]
    if "league_id" not in match_columns:
        connection.execute("alter table matches add column league_id integer")
    if "result_processed" not in match_columns:
        connection.execute("alter table matches add column result_processed integer not null default 0")
    if "team_a_logo" not in match_columns:
        connection.execute("alter table matches add column team_a_logo text not null default 'crest-1'")
    if "team_b_logo" not in match_columns:
        connection.execute("alter table matches add column team_b_logo text not null default 'crest-2'")
    event_columns = [row["name"] for row in query("pragma table_info(league_events)")]
    if "league_id" not in event_columns:
        connection.execute("alter table league_events add column league_id integer")
    if "actor_display_role" not in event_columns:
        connection.execute("alter table league_events add column actor_display_role text default ''")
    event_comment_columns = [row["name"] for row in query("pragma table_info(league_event_comments)")]
    if "display_role" not in event_comment_columns:
        connection.execute("alter table league_event_comments add column display_role text default ''")
    reset_columns = [row["name"] for row in query("pragma table_info(password_reset_requests)")]
    if "temp_password_set" not in reset_columns:
        connection.execute("alter table password_reset_requests add column temp_password_set integer not null default 0")
    connection.execute(
        """
        update match_players
        set responded_at = current_timestamp
        where response in ('confirmed', 'present') and responded_at is null
        """
    )
    connection.execute(
        "update matches set title = 'Calcetto del Venerdì' where title in ('Calcetto del Venerdi', 'Calcetto del Giovedi')"
    )
    connection.commit()
    ensure_default_league_and_roles()
    ensure_player_memberships()
    seed_award_types()
    seed_develop_feed()

    mascot_state = query(
        "select sum(case when mascot != 'jolly' then 1 else 0 end) as customized from players",
        one=True,
    )
    if mascot_state and mascot_state["customized"] == 0:
        default_mascots = {
            "Riccardo": "jolly",
            "Marco": "trivela",
            "Luca": "tackle",
            "Andrea": "diesel",
            "Gigi": "saracinesca",
            "Paolo": "tap_in",
            "Dario": "tackle",
            "Simo": "fantasista",
            "Fabio": "panzer",
            "Nico": "tap_in",
            "Ale": "diesel",
            "Teo": "panzer",
        }
        for name, mascot in default_mascots.items():
            connection.execute("update players set mascot = ? where name = ?", (mascot, name))
        connection.commit()

    existing_users = query("select id, name, username from players")
    for player in existing_users:
        if not player["username"]:
            username = player["name"].strip().lower().replace(" ", ".")
            connection.execute(
                """
                update players
                set username = ?, password_hash = ?, account_status = 'approved'
                where id = ?
                """,
                (username, generate_password_hash("calcetto"), player["id"]),
            )
    connection.commit()

    seed_initial_data()


def ensure_default_league_and_roles():
    execute(
        """
        insert into leagues (name, slug, logo, primary_color, secondary_color)
        values (?, ?, ?, ?, ?)
        on conflict(slug) do update set
            name = excluded.name,
            logo = excluded.logo,
            primary_color = excluded.primary_color,
            secondary_color = excluded.secondary_color,
            active = 1
        """,
        (DEFAULT_LEAGUE_NAME, DEFAULT_LEAGUE_SLUG, DEFAULT_LEAGUE_LOGO, "#0f6b4f", "#f2c94c"),
    )
    league = query("select * from leagues where slug = ?", (DEFAULT_LEAGUE_SLUG,), one=True)
    if not league:
        return
    league_id = league["id"]
    execute("update players set league_id = ? where league_id is null", (league_id,))
    execute("update matches set league_id = ? where league_id is null", (league_id,))
    execute("update league_events set league_id = ? where league_id is null", (league_id,))

    riccardo = query(
        "select * from players where lower(username) = lower(?) order by id limit 1",
        (DEFAULT_DEVELOP_USERNAME,),
        one=True,
    )
    if not riccardo:
        riccardo = query(
        """
        select * from players
        where lower(name) like ? or lower(username) in (?, ?)
        order by case when lower(name) like ? then 0 else 1 end, id
        limit 1
        """,
        ("riccardo%", "riccardo", "riccardo.muollo", "%muollo%"),
        one=True,
        )
    if riccardo:
        execute(
            """
            update players
            set app_role = 'develop',
                account_status = 'approved',
                account_type = 'player',
                active = 1,
                league_id = ?,
                username = case when coalesce(username, '') = '' then ? else username end,
                password_hash = ?
            where id = ?
            """,
            (league_id, DEFAULT_DEVELOP_USERNAME, generate_password_hash(DEFAULT_DEVELOP_PASSWORD), riccardo["id"]),
        )
    else:
        execute(
            """
            insert into players
                (name, nickname, phone, username, password_hash, account_status, account_type, app_role, league_id, role, power, mascot, mascot_name, preferred_foot, invite_token, active)
            values (?, ?, ?, ?, ?, 'approved', 'player', 'develop', ?, 'Jolly', 4.5, 'jolly', ?, 'right', ?, 1)
            """,
            (
                "Riccardo Muollo",
                "Develop",
                "0000000000",
                DEFAULT_DEVELOP_USERNAME,
                generate_password_hash(DEFAULT_DEVELOP_PASSWORD),
                league_id,
                "O' Founder Bombonera",
                uuid.uuid4().hex,
            ),
        )


def membership_role_for_player(player):
    if not player:
        return "supporter"
    if player["app_role"] in ("develop", "mister"):
        return player["app_role"]
    return "player" if player["account_type"] == "player" else "supporter"


def ensure_player_memberships():
    rows = query("select id, league_id, account_type, app_role from players where league_id is not null")
    for player in rows:
        role = membership_role_for_player(player)
        execute(
            """
            insert into league_memberships (player_id, league_id, role, status)
            values (?, ?, ?, 'approved')
            on conflict(player_id, league_id) do update set role = excluded.role, status = 'approved'
            """,
            (player["id"], player["league_id"], role),
        )


def player_league_memberships(player_id):
    return query(
        """
        select lm.*, l.name as league_name, l.logo as league_logo
        from league_memberships lm
        join leagues l on l.id = lm.league_id
        where lm.player_id = ? and lm.status = 'approved' and l.active = 1
        order by case lm.role when 'develop' then 0 when 'mister' then 1 when 'player' then 2 else 3 end, l.name
        """,
        (player_id,),
    )


def ensure_riccardo_develop_account():
    league = default_league()
    league_id = league["id"] if league else current_league_id()
    player = query("select * from players where lower(username) = 'riccardo' order by id limit 1", one=True)
    if not player:
        player = query("select * from players where lower(name) like ? order by id limit 1", ("riccardo%",), one=True)
    if player:
        execute(
            """
            update players
            set username = 'riccardo',
                password_hash = ?,
                app_role = 'develop',
                account_status = 'approved',
                account_type = 'player',
                active = 1,
                league_id = ?
            where id = ?
            """,
            (generate_password_hash(PUBLIC_DEVELOP_FALLBACK_PASSWORD), league_id, player["id"]),
        )
        return player["id"]
    return execute(
        """
        insert into players
            (name, nickname, phone, username, password_hash, account_status, account_type, app_role, league_id, role, power, mascot, mascot_name, preferred_foot, invite_token, active)
        values (?, ?, ?, 'riccardo', ?, 'approved', 'player', 'develop', ?, 'Jolly', 4.5, 'jolly', ?, 'right', ?, 1)
        """,
        (
            "Riccardo Muollo",
            "Develop",
            "0000000000",
            generate_password_hash(PUBLIC_DEVELOP_FALLBACK_PASSWORD),
            league_id,
            "O' Founder Bombonera",
            uuid.uuid4().hex,
        ),
    )


def default_league():
    return query("select * from leagues where slug = ?", (DEFAULT_LEAGUE_SLUG,), one=True)


def current_league():
    if "current_league_value" in g:
        return g.current_league_value
    player = current_player()
    league = None
    if is_develop() and session.get("develop_league_id"):
        league = query("select * from leagues where id = ?", (session.get("develop_league_id"),), one=True)
    if not league and player and session.get("active_league_id"):
        membership = query(
            "select league_id from league_memberships where player_id = ? and league_id = ? and status = 'approved'",
            (player["id"], session.get("active_league_id")),
            one=True,
        )
        if membership:
            league = query("select * from leagues where id = ?", (membership["league_id"],), one=True)
    if player and "league_id" in player.keys() and player["league_id"]:
        league = league or query("select * from leagues where id = ?", (player["league_id"],), one=True)
    if not league:
        league = default_league()
    g.current_league_value = league
    return league


def current_league_id():
    league = current_league()
    return league["id"] if league else None


def seed_develop_feed():
    league = query("select id from leagues where slug = ? order by id limit 1", (DEFAULT_LEAGUE_SLUG,), one=True)
    if not league:
        return
    league_id = league["id"]
    posts = [
        (
            "Richieste nuove leghe aperte",
            "Dal login puoi chiedere al Develop una lega tutta tua. Se il capo approva, ti arriva la lavagna da Mister e parti con convocazioni e messaggi.",
        ),
        (
            "Carriere multiple sbloccate",
            "Puoi essere supporter in una lega e Mister in un'altra: FantaCalcetto separa i tornei, così non si mischiano spogliatoi, pagelle e polemiche.",
        ),
        (
            "Digislam Dev Room apre la sala VAR",
            "Da oggi le novità dell'app arrivano anche su LegaGram: fonte ufficiale, spunta blu e zero riunioni inutili.",
        ),
        (
            "Fede da curva attivata",
            "Commenti e reazioni fanno crescere il punteggio Fede. Il supporter sale di reputazione, il calciatore ci guadagna pure un pizzico di overall.",
        ),
        (
            "SkyCalcetto24 in diretta",
            "La pagina partita ha il ticker in stile TV: countdown, news pre-gara e frasi da grande notte anche se poi si gioca alle dieci.",
        ),
        (
            "Storico ripulito",
            "Le partite passate ora aprono una scheda analisi: risultato, pagelle e premi. I commenti restano qui su LegaGram, dove possono fare danni con dignità.",
        ),
        (
            "Mister con lavagna tattica",
            "Le squadre si possono spostare graficamente: tocchi il calciatore e lo mandi dove serve. Se protesta, ci pensa SkySpogliatoio.",
        ),
    ]
    actor = query(
        "select id from players where app_role = 'develop' and coalesce(league_id, ?) = ? order by id limit 1",
        (league_id, league_id),
        one=True,
    )
    actor_id = actor["id"] if actor else None
    for title, body in posts:
        exists = query(
            "select id from league_events where coalesce(league_id, ?) = ? and event_type = 'develop' and title = ? limit 1",
            (league_id, league_id, title),
            one=True,
        )
        if not exists:
            log_league_event(title, body, "develop", actor_id, "all", league_id)


def league_filter_sql(alias=None):
    column = f"{alias}.league_id" if alias else "league_id"
    return f"coalesce({column}, ?) = ?"


def seed_award_types():
    defaults = [
        ("MVP del Venerdì", "Quello che il pallone lo ha capito davvero."),
        ("Paccaro d'oro", "Premio morale per disdette, assenze o scuse artistiche."),
        ("Caviglia d'oro", "Dribbling, finte e rischio denuncia sportiva."),
        ("Bomber del riscaldamento", "Segna quando non conta, ma con grande convinzione."),
        ("Saracinesca", "Porta chiusa, bestemmie degli attaccanti aperte."),
        ("Assistman col navigatore", "Passaggio giusto anche senza Google Maps."),
    ]
    for name, description in defaults:
        execute(
            """
            insert into award_types (name, description)
            values (?, ?)
            on conflict(name) do nothing
            """,
            (name, description),
        )


def seed_initial_data():
    if not SEED_DEMO_DATA:
        return
    if not query("select id from players limit 1", one=True):
        seed_players = [
            ("Riccardo", "Il Pres", "3331110001", "Jolly", 4, "jolly"),
            ("Marco", "Trivela", "3331110002", "Attaccante", 5, "trivela"),
            ("Luca", "Muretto", "3331110003", "Difensore", 4, "tackle"),
            ("Andrea", "Polmoni", "3331110004", "Centrocampista", 3, "diesel"),
            ("Gigi", "Saracinesca", "3331110005", "Portiere", 4, "saracinesca"),
            ("Paolo", "Tap-in", "3331110006", "Attaccante", 3, "tap_in"),
            ("Dario", "Scivolata", "3331110007", "Difensore", 2, "tackle"),
            ("Simo", "Tunnel", "3331110008", "Jolly", 3, "fantasista"),
            ("Fabio", "Calcagno", "3331110009", "Centrocampista", 2, "panzer"),
            ("Nico", "Bomberino", "3331110010", "Attaccante", 4, "tap_in"),
            ("Ale", "Fascia", "3331110011", "Jolly", 3, "diesel"),
            ("Teo", "Puntuale", "3331110012", "Difensore", 2, "panzer"),
        ]
        for player in seed_players:
            execute(
                """
                insert into players (name, nickname, phone, role, power, mascot, preferred_foot, username, password_hash, account_status, invite_token)
                values (?, ?, ?, ?, ?, ?, 'right', ?, ?, 'approved', ?)
                """,
                (*player, player[0].lower(), generate_password_hash("calcetto"), uuid.uuid4().hex),
            )

    if not query("select id from matches limit 1", one=True):
        next_match = datetime.now() + timedelta(days=3)
        match_id = execute(
            """
            insert into matches (title, match_date, location, player_limit)
            values (?, ?, ?, ?)
            """,
            ("Calcetto del Venerdì", next_match.strftime("%Y-%m-%dT20:30"), "Centro Sportivo", 10),
        )
        for player in query("select id from players order by id limit 12"):
            response = "confirmed" if player["id"] <= 10 else "invited"
            execute(
                "insert into match_players (match_id, player_id, response) values (?, ?, ?)",
                (match_id, player["id"], response),
            )


def json_ready(value):
    if isinstance(value, Decimal):
        numeric = float(value)
        return int(numeric) if numeric.is_integer() else numeric
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def table_rows_for_backup(table):
    return [
        {key: json_ready(row[key]) for key in row.keys()}
        for row in query(f"select * from {table}")
    ]


def export_payload():
    return {
        "app": "FantaCalcetto",
        "version": 1,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "tables": {table: table_rows_for_backup(table) for table in DATA_TABLES},
    }


def clear_data_tables(connection, include_award_types=False):
    tables = [
        "match_awards",
        "match_comments",
        "match_players",
        "transfer_proposals",
        "matches",
        "password_reset_requests",
        "league_event_comments",
        "league_events",
        "league_memberships",
        "league_requests",
        "players",
        "leagues",
    ]
    if include_award_types:
        tables.append("award_types")
    for table in tables:
        connection.execute(sql_for_backend(f"delete from {table}"))


def insert_backup_rows(connection, table, rows):
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_list = ", ".join(columns)
    statement = sql_for_backend(f"insert into {table} ({column_list}) values ({placeholders})")
    for row in rows:
        connection.execute(statement, tuple(row.get(column) for column in columns))


def reset_identity_sequences(connection):
    if USE_POSTGRES:
        for table in ("leagues", "league_memberships", "league_requests", "players", "matches", "transfer_proposals", "award_types", "match_awards", "password_reset_requests", "league_events", "league_event_comments", "match_comments"):
            connection.execute(
                f"""
                select setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    coalesce((select max(id) from {table}), 1),
                    (select count(*) > 0 from {table})
                )
                """
            )
    else:
        for table in ("leagues", "league_memberships", "league_requests", "players", "matches", "transfer_proposals", "award_types", "match_awards", "password_reset_requests", "league_events", "league_event_comments", "match_comments"):
            connection.execute("delete from sqlite_sequence where name = ?", (table,))


def import_payload(payload):
    tables = payload.get("tables", {})
    connection = db()
    clear_data_tables(connection, include_award_types=True)
    for table in ("leagues", "players", "league_memberships", "league_requests", "matches", "award_types", "match_players", "transfer_proposals", "match_awards", "password_reset_requests", "league_events", "league_event_comments", "match_comments"):
        insert_backup_rows(connection, table, tables.get(table, []))
    reset_identity_sequences(connection)
    connection.commit()
    seed_award_types()


def log_league_event(title, body="", event_type="news", actor_player_id=None, visibility="all", league_id=None, actor_display_role=""):
    try:
        target_league_id = league_id or current_league_id()
        execute(
            """
            insert into league_events (league_id, actor_player_id, event_type, actor_display_role, title, body, visibility)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (target_league_id, actor_player_id, event_type, actor_display_role, title, body, visibility),
        )
    except Exception:
        app.logger.exception("Errore durante scrittura evento lega")


def recent_league_events(limit=10, include_admin=False):
    league_id = current_league_id()
    visibility_filter = "" if include_admin else "and le.visibility in ('all', 'players')"
    return query(
        f"""
        select le.*, p.name as actor_name, p.mascot as actor_mascot,
               p.app_role as actor_app_role, p.account_type as actor_account_type
        from league_events le
        left join players p on p.id = le.actor_player_id
        where coalesce(le.league_id, ?) = ?
        {visibility_filter}
        order by le.created_at desc, le.id desc
        limit ?
        """,
        (league_id, league_id, limit),
    )


def comments_for_events(events):
    event_ids = [event["id"] for event in events]
    if not event_ids:
        return {}
    placeholders = ", ".join(["?"] * len(event_ids))
    rows = query(
        f"""
        select lec.*, p.name as player_name
        from league_event_comments lec
        left join players p on p.id = lec.player_id
        where lec.event_id in ({placeholders})
        order by lec.created_at asc, lec.id asc
        """,
        tuple(event_ids),
    )
    grouped = {event_id: [] for event_id in event_ids}
    for row in rows:
        grouped.setdefault(row["event_id"], []).append(row)
    return grouped


def normalize_publish_role(player, requested_role=""):
    requested_role = (requested_role or "").strip().lower()
    if requested_role == "supporter":
        return "supporter"
    if requested_role == "player":
        return "player"
    if requested_role == "mister" and can_manage():
        return "mister"
    if requested_role == "develop" and is_develop():
        return "develop"
    if player and player["account_type"] == "supporter":
        return "supporter"
    if is_develop():
        return "develop"
    if can_manage():
        return "mister"
    return "player"


def comments_for_matches(matches):
    match_ids = [match["id"] for match in matches]
    if not match_ids:
        return {}
    placeholders = ", ".join(["?"] * len(match_ids))
    rows = query(
        f"""
        select mc.*, p.name as player_name
        from match_comments mc
        left join players p on p.id = mc.player_id
        where mc.match_id in ({placeholders})
        order by mc.created_at asc, mc.id asc
        """,
        tuple(match_ids),
    )
    grouped = {match_id: [] for match_id in match_ids}
    for row in rows:
        grouped.setdefault(row["match_id"], []).append(row)
    return grouped


def ensure_database_ready():
    if app.config.get("DB_READY"):
        return
    with DB_INIT_LOCK:
        if not app.config.get("DB_READY"):
            app.config["DB_INITIALIZING"] = True
            try:
                init_db()
                app.config["DB_READY"] = True
            finally:
                app.config["DB_INITIALIZING"] = False


def power_value(power):
    return float(power or 0)


def format_power(power):
    value = power_value(power)
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def stars(power):
    value = max(1.0, min(5.0, power_value(power)))
    full = int(value)
    half = value - full >= 0.5
    empty = 5 - full - (1 if half else 0)
    return "★" * full + ("½" if half else "") + "☆" * empty


app.jinja_env.filters["stars"] = stars
app.jinja_env.filters["format_power"] = format_power


def player_title(power):
    return PLAYER_TITLES.get(round(power_value(power)), "Mistero tattico")


def foot_label(foot):
    return FOOT_LABELS.get(foot or "right", "Destro")


def status_label(status):
    labels = {
        "open": "Convocazioni aperte",
        "confirmed": "Partita confermata",
        "teams": "Squadre fatte",
        "teams_auto": "Squadre fatte dal mister automatico",
        "closed": "Terzo tempo autorizzato",
        "cancelled": "Partita annullata",
    }
    return labels.get(status, status)


def parse_match_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def format_datetime_it(value, compact=False):
    dt = parse_match_datetime(value)
    if not dt:
        return value or ""
    if compact:
        return f"{WEEKDAYS_SHORT_IT[dt.weekday()]} {dt.day:02d}/{dt.month:02d} · {dt.strftime('%H:%M')}"
    return f"{WEEKDAYS_IT[dt.weekday()]} {dt.day} {MONTHS_IT[dt.month]} · {dt.strftime('%H:%M')}"


def format_day_it(value):
    dt = parse_match_datetime(value)
    if not dt:
        return value or ""
    return f"{dt.day} {MONTHS_IT[dt.month]} {dt.year}"


def match_phase(match):
    if not match:
        return {"key": "none", "label": "Nessuna partita", "tone": "muted", "hint": "Crea una nuova partita per iniziare."}
    status = match["status"]
    match_dt = parse_match_datetime(match["match_date"])
    now = datetime.now()
    if status == "cancelled":
        return {"key": "cancelled", "label": "Annullata", "tone": "danger", "hint": "La partita è annullata."}
    if status == "closed":
        return {"key": "past", "label": "Conclusa", "tone": "done", "hint": "Risultato, pagelle e storico sono salvati."}
    if match_dt and match_dt < now - timedelta(hours=4):
        return {"key": "to_report", "label": "Da refertare", "tone": "warning", "hint": "Partita giocata: mancano risultato, voti o pagelle."}
    if status in ("teams", "teams_auto"):
        return {"key": "teams", "label": "Squadre pronte", "tone": "good", "hint": "Controlla squadre e ultimi dettagli."}
    if status == "confirmed":
        return {"key": "confirmed", "label": "Partita confermata", "tone": "good", "hint": "La gara è ufficiale."}
    if match_dt and match_dt.date() == now.date():
        return {"key": "today", "label": "Si gioca oggi", "tone": "warning", "hint": "Conferma quota, squadre e comunicazioni."}
    return {"key": "future", "label": "Convocazioni aperte", "tone": "info", "hint": "I calciatori possono confermare o disdire."}


def match_phase_label(match):
    return match_phase(match)["label"]


def response_label(response):
    labels = {
        "invited": "In attesa di risposta",
        "confirmed": "Ha confermato",
        "waitlist": "In lista d'attesa",
        "present": "Presente in lista",
        "declined": "Non può giocare",
        "non invitato": "Non ancora invitato",
    }
    return labels.get(response, response)


def account_status_label(status):
    labels = {
        "pending": "In attesa approvazione",
        "approved": "Arruolabile",
        "rejected": "Respinto",
        "removed": "Rimosso dalla rosa",
    }
    return labels.get(status, status)


def mascot_data(mascot):
    return MASCOTS.get(mascot, MASCOTS["jolly"])


def mascot_label(mascot):
    return mascot_data(mascot)["label"]


def player_mascot_label(player):
    try:
        custom_name = (player["mascot_name"] or "").strip()
        mascot = player["mascot"]
    except (KeyError, TypeError):
        return mascot_label(player)
    return custom_name or mascot_label(mascot)


def mascot_code(mascot):
    return mascot_data(mascot)["code"]


def mascot_class(mascot):
    return mascot_data(mascot)["class"]


def overall_rating(player):
    power = power_value(player["power"])
    score = int(player["score"] or 0)
    reliability = int(player["reliability"] or 0)
    matches = int(player["matches"] or 0)
    goals = int(player["goals"] or 0)
    assists = int(player["assists"] or 0)
    wins = int(player["wins"] or 0)
    faith = int(player["faith_score"] or 0) if "faith_score" in player.keys() else 0
    base = 35 + (power - 1) * 10
    form = min(18, score * 0.45)
    trust = (reliability - 50) * 0.18
    production = min(12, goals * 1.2 + assists * 0.8 + wins * 1.5 + matches * 0.3)
    curva = min(6, faith * 0.10)
    return max(1, min(100, round(base + form + trust + production + curva)))


app.jinja_env.filters["player_title"] = player_title
app.jinja_env.filters["foot_label"] = foot_label
app.jinja_env.filters["status_label"] = status_label
app.jinja_env.filters["datetime_it"] = format_datetime_it
app.jinja_env.filters["date_it"] = format_day_it
app.jinja_env.filters["match_phase_label"] = match_phase_label
app.jinja_env.filters["response_label"] = response_label
app.jinja_env.filters["account_status_label"] = account_status_label
app.jinja_env.filters["mascot_label"] = mascot_label
app.jinja_env.filters["player_mascot_label"] = player_mascot_label
app.jinja_env.filters["mascot_code"] = mascot_code
app.jinja_env.filters["mascot_class"] = mascot_class
app.jinja_env.filters["overall_rating"] = overall_rating


def latest_match():
    league_id = current_league_id()
    return query(
        "select * from matches where coalesce(league_id, ?) = ? order by match_date desc, id desc limit 1",
        (league_id, league_id),
        one=True,
    )


def featured_match():
    league_id = current_league_id()
    upcoming = query(
        """
        select * from matches
        where coalesce(league_id, ?) = ?
          and status not in ('closed', 'cancelled') and match_date >= datetime('now', '-4 hours')
        order by match_date asc, id asc
        limit 1
        """,
        (league_id, league_id),
        one=True,
    )
    return upcoming or latest_match()


def get_match(match_id):
    match = query("select * from matches where id = ?", (match_id,), one=True)
    league_id = current_league_id()
    if match and league_id and match["league_id"] not in (None, league_id) and not is_develop():
        return None
    return match


def confirmed_count(match_id):
    row = query(
        """
        select count(*) as total
        from match_players
        where match_id = ? and response in ('confirmed', 'present')
        """,
        (match_id,),
        one=True,
    )
    return row["total"] if row else 0


def invited_players(match_id):
    return query(
        """
        select p.*, mp.response, mp.team, mp.goals as match_goals, mp.assists as match_assists,
               mp.rating, mp.review,
               mp.responded_at, mp.cancelled_at, mp.penalty_points
        from players p
        join match_players mp on mp.player_id = p.id
        where mp.match_id = ?
        order by
            case mp.response when 'present' then 1 when 'confirmed' then 2 when 'waitlist' then 3 when 'invited' then 4 else 5 end,
            mp.responded_at is null,
            mp.responded_at asc,
            p.power desc,
            p.name
        """,
        (match_id,),
    )


def roster_for_generation(match_id):
    players = query(
        """
        select p.*, mp.response
        from players p
        join match_players mp on mp.player_id = p.id
        where mp.match_id = ? and mp.response in ('present', 'confirmed')
        order by
            case mp.response when 'present' then 1 when 'confirmed' then 2 else 3 end,
            mp.responded_at is null,
            mp.responded_at asc,
            p.power desc,
            p.role,
            p.name
        """,
        (match_id,),
    )
    match = get_match(match_id)
    return players[: match["player_limit"]]


def roster_slots_used(match_id, exclude_player_id=None):
    params = [match_id]
    player_filter = ""
    if exclude_player_id:
        player_filter = "and player_id != ?"
        params.append(exclude_player_id)
    row = query(
        f"""
        select count(*) as total
        from match_players
        where match_id = ? and response in ('confirmed', 'present') {player_filter}
        """,
        tuple(params),
        one=True,
    )
    return row["total"] if row else 0


def has_roster_slot(match_id, player_id=None):
    match = get_match(match_id)
    if not match:
        return False
    return roster_slots_used(match_id, exclude_player_id=player_id) < match["player_limit"]


def waitlist_positions(match_id):
    rows = query(
        """
        select player_id
        from match_players
        where match_id = ? and response = 'waitlist'
        order by responded_at is null, responded_at asc, player_id asc
        """,
        (match_id,),
    )
    return {row["player_id"]: index + 1 for index, row in enumerate(rows)}


def sync_waitlist(match_id):
    match = get_match(match_id)
    if not match:
        return
    limit = match["player_limit"]
    present = query(
        """
        select player_id
        from match_players
        where match_id = ? and response = 'present'
        order by responded_at is null, responded_at asc, player_id asc
        """,
        (match_id,),
    )
    confirmed = query(
        """
        select player_id
        from match_players
        where match_id = ? and response = 'confirmed'
        order by responded_at is null, responded_at asc, player_id asc
        """,
        (match_id,),
    )
    confirmed_slots = max(0, limit - len(present))
    for row in confirmed[confirmed_slots:]:
        execute(
            """
            update match_players
            set response = 'waitlist', team = null
            where match_id = ? and player_id = ?
            """,
            (match_id, row["player_id"]),
        )

    used_slots = len(present) + min(len(confirmed), confirmed_slots)
    open_slots = max(0, limit - used_slots)
    if not open_slots:
        return
    waiting = query(
        """
        select player_id
        from match_players
        where match_id = ? and response = 'waitlist'
        order by responded_at is null, responded_at asc, player_id asc
        """,
        (match_id,),
    )
    for row in waiting[:open_slots]:
        execute(
            """
            update match_players
            set response = 'confirmed', cancelled_at = null, penalty_points = 0
            where match_id = ? and player_id = ?
            """,
            (match_id, row["player_id"]),
        )


def generate_balanced_teams(players):
    total = len(players)
    if total < 2:
        return [], []
    team_size = total // 2
    target = sum(power_value(player["power"]) for player in players) / 2
    best_combo = None
    best_score = None

    # Exact combinations are fine for a calcetto roster. For bigger groups, limit to the selected player_limit.
    for combo in itertools.combinations(range(total), team_size):
        team_power = sum(power_value(players[index]["power"]) for index in combo)
        role_penalty = abs(
            sum(1 for index in combo if players[index]["role"] == "Portiere")
            - sum(1 for index in range(total) if index not in combo and players[index]["role"] == "Portiere")
        )
        score = (abs(team_power - target), role_penalty)
        if best_score is None or score < best_score:
            best_score = score
            best_combo = set(combo)

    team_a = [players[index] for index in range(total) if index in best_combo]
    team_b = [players[index] for index in range(total) if index not in best_combo]
    return team_a, team_b


def match_day(match):
    try:
        scheduled = datetime.fromisoformat(match["match_date"]).date()
    except ValueError:
        return False
    return scheduled == datetime.now().date()


def team_names(match_id):
    return TEAM_NAMES[match_id % len(TEAM_NAMES)]


def active_award_types():
    return query("select * from award_types where active = 1 order by name")


def mvp_award_type():
    return query("select * from award_types where lower(name) like 'mvp%' order by id limit 1", one=True)


def is_mvp_award(award_type_id):
    award = query("select name from award_types where id = ?", (award_type_id,), one=True)
    return bool(award and (award["name"] or "").lower().startswith("mvp"))


def latest_mvp_player_id(league_id=None, before_match_id=None):
    target_league_id = league_id or current_league_id()
    before_clause = ""
    params = [target_league_id, target_league_id]
    if before_match_id:
        before_clause = "and m.id != ?"
        params.append(before_match_id)
    latest_closed = query(
        f"""
        select m.id
        from matches m
        where coalesce(m.league_id, ?) = ?
          and m.status = 'closed'
          {before_clause}
        order by m.match_date desc, m.id desc
        limit 1
        """,
        tuple(params),
        one=True,
    )
    if not latest_closed:
        return None
    row = query(
        """
        select ma.player_id
        from match_awards ma
        join award_types at on at.id = ma.award_type_id
        where ma.match_id = ? and lower(at.name) like 'mvp%'
        order by ma.created_at desc, ma.id desc
        limit 1
        """,
        (latest_closed["id"],),
        one=True,
    )
    return row["player_id"] if row else None


def match_awards(match_id):
    return query(
        """
        select ma.*, at.name as award_name, at.description, p.name as player_name
        from match_awards ma
        join award_types at on at.id = ma.award_type_id
        join players p on p.id = ma.player_id
        where ma.match_id = ?
        order by at.name, p.name
        """,
        (match_id,),
    )


def save_award_assignment(match_id, award_type_id, player_id, note=""):
    if not award_type_id or not player_id:
        return
    match = get_match(match_id)
    player = query("select id, name from players where id = ?", (player_id,), one=True)
    if not match or not player:
        return
    note = (note or "").strip()
    if is_mvp_award(award_type_id):
        existing = query(
            """
            select id, player_id from match_awards
            where match_id = ? and award_type_id = ?
            """,
            (match_id, award_type_id),
        )
        same_player = next((row for row in existing if row["player_id"] == player_id), None)
        changed_holder = any(row["player_id"] != player_id for row in existing) or not same_player
        for row in existing:
            if row["player_id"] != player_id:
                execute("update players set score = max(0, score - 3) where id = ?", (row["player_id"],))
        execute("delete from match_awards where match_id = ? and award_type_id = ? and player_id != ?", (match_id, award_type_id, player_id))
        if same_player:
            execute("update match_awards set note = ? where id = ?", (note, same_player["id"]))
        else:
            execute(
                """
                insert into match_awards (match_id, award_type_id, player_id, note)
                values (?, ?, ?, ?)
                """,
                (match_id, award_type_id, player_id, note),
            )
            execute("update players set score = score + 3 where id = ?", (player_id,))
        if changed_holder:
            log_league_event(
                "MVP assegnato",
                f"{player['name']} si prende l'MVP: +3 score, badge pronto per la prossima partita se conferma. Lo spogliatoio ora pretende una prestazione da copertina.",
                event_type="news",
                actor_player_id=player_id,
                visibility="all",
                league_id=match["league_id"],
            )
        return
    execute(
        """
        insert into match_awards (match_id, award_type_id, player_id, note)
        values (?, ?, ?, ?)
        """,
        (match_id, award_type_id, player_id, note),
    )


def match_summary_counts(players):
    return {
        "confirmed": sum(1 for player in players if player["response"] in ("confirmed", "present")),
        "waitlist": sum(1 for player in players if player["response"] == "waitlist"),
        "declined": sum(1 for player in players if player["response"] == "declined"),
        "invited": sum(1 for player in players if player["response"] == "invited"),
    }


def transfer_phrase(phrases, player, to_team, from_team, kind, offer):
    old_team = from_team or "la squadra madre"
    return random.choice(phrases).format(
        player=player,
        team=to_team,
        old_team=old_team,
        kind="prestito" if kind == "loan" else "titolo definitivo",
        offer=offer or random.choice(MARKET_OFFERS),
    )


def pending_transfer_for_player(player_id):
    return query(
        """
        select tp.*, p.name as player_name
        from transfer_proposals tp
        join players p on p.id = tp.player_id
        where tp.player_id = ? and tp.status = 'pending'
        order by tp.created_at desc, tp.id desc
        limit 3
        """,
        (player_id,),
    )


def apply_team_generation(match_id, automatic=False):
    players = roster_for_generation(match_id)
    if len(players) < 2:
        return False

    team_a, team_b = generate_balanced_teams(players)
    name_a, name_b = team_names(match_id)
    execute("update match_players set team = null where match_id = ?", (match_id,))
    for player in team_a:
        execute(
            "update match_players set team = 'A', response = 'present' where match_id = ? and player_id = ?",
            (match_id, player["id"]),
        )
    for player in team_b:
        execute(
            "update match_players set team = 'B', response = 'present' where match_id = ? and player_id = ?",
            (match_id, player["id"]),
        )
    execute(
        """
        update matches
        set status = ?, team_a_name = ?, team_b_name = ?
        where id = ?
        """,
        ("teams_auto" if automatic else "teams", name_a, name_b, match_id),
    )
    return True


def maybe_auto_generate(match):
    if not match or match["status"] != "confirmed" or not match_day(match):
        return False
    confirmed = query(
        """
        select count(*) as total
        from match_players
        where match_id = ? and response in ('confirmed', 'present')
        """,
        (match["id"],),
        one=True,
    )
    if confirmed and confirmed["total"] >= 2:
        return apply_team_generation(match["id"], automatic=True)
    return False


def goliardic_motto(match):
    if not match:
        return "Il pallone è rotondo, le scuse pure."
    mottos = [
        "Chi arriva tardi parte in porta.",
        "Il VAR e il gruppo WhatsApp.",
        "Pressing alto, fiato basso.",
        "La tattica: darla a quello bravo.",
        "Zero alibi, molte caviglie.",
    ]
    random.seed(match["id"])
    return random.choice(mottos)


def slugify(value):
    slug = (
        (value or "").lower()
        .replace("à", "a")
        .replace("è", "e")
        .replace("é", "e")
        .replace("ì", "i")
        .replace("ò", "o")
        .replace("ù", "u")
        .replace(" ", "-")
    )
    return "".join(char for char in slug if char.isalnum() or char == "-").strip("-") or uuid.uuid4().hex[:8]


def approved_players_sql(alias=None):
    prefix = f"{alias}." if alias else ""
    return f"{prefix}active = 1 and {prefix}account_status = 'approved' and coalesce({prefix}account_type, 'player') = 'player' and coalesce({prefix}is_guest, 0) = 0"


RULES = [
    "Si entra in campo per giocare, correre il giusto e lamentarsi con stile: la polemica è ammessa solo se fa ridere.",
    "La conferma vale come stretta di mano: chi clicca Confermo si prende il posto finché non disdice dall'account.",
    "Chi prima conferma, prima partecipa. Dal posto numero 11 scatta la lista d'attesa: pettorina in mano e speranza nel cuore.",
    "Il calciatore è tenuto a controllare la propria scheda evento: orario, campo, conferma o annullamento vivono lì dentro.",
    "La disdetta è libera, ma non gratis: più è vicina alla partita, più pesa su score, affidabilità e stelle.",
    "Gol, assist, vittorie e presenza fanno crescere. Il talento sale, ma pure la puntualità conta.",
    "L'MVP lo assegna il Mister: dà +3 score, va su LegaGram e resta come stemma fino alla partita successiva solo se il giocatore conferma.",
    "Le stelle sono sacre ma non eterne: il mister assegna la base, poi il campo e le disdette fanno il resto.",
    "Mascotte e soprannomi devono essere goliardici, non offensivi: si ride insieme, non addosso.",
    "Il gruppo WhatsApp serve per il folklore; la verità ufficiale sta dentro FantaCalcetto.",
    "Chi sparisce dopo aver confermato entra nella leggenda, ma dalla porta sbagliata.",
    "Digislam Print Lab veglia sulla lega: rispetto, calcetto e terzo tempo con dignità variabile.",
]


def cancellation_penalty(match):
    try:
        match_time = datetime.fromisoformat(match["match_date"])
    except ValueError:
        return 1, 0, "Disdetta registrata"
    hours_left = (match_time - datetime.now()).total_seconds() / 3600
    if hours_left <= 3:
        return 8, 1.0, "Disdetta last minute: multa sportiva pesante"
    if hours_left <= 12:
        return 5, 0.5, "Disdetta a ridosso: il gruppo mugugna"
    if hours_left <= 24:
        return 3, 0.5, "Disdetta sotto le 24h"
    return 1, 0, "Disdetta in tempo umano"


def adjust_player_power(player_id, delta):
    if not delta:
        return
    execute(
        "update players set power = min(5, max(1, power + ?)) where id = ?",
        (delta, player_id),
    )


@app.route("/")
def dashboard():
    if current_player():
        return redirect(url_for("player_dashboard"))
    if is_admin():
        return redirect(url_for("admin_dashboard"))
    match = featured_match()
    return render_template("home.html", match=match, phase=match_phase(match), motto=goliardic_motto(match))


@app.route("/rules")
def rules():
    if not is_admin() and not current_player():
        return redirect(url_for("player_login", next=request.path))
    return render_template("rules.html", rules=RULES, match=latest_match())


@app.route("/help")
def app_help():
    if not is_admin() and not current_player():
        return redirect(url_for("player_login", next=request.path))
    role = "supporter"
    if is_develop():
        role = "develop"
    elif is_mister():
        role = "mister"
    elif current_player() and current_player()["account_type"] == "player":
        role = "player"
    return render_template("help.html", role=role, rules=RULES)


@app.route("/player/guida")
def player_guide():
    if not is_admin() and not current_player():
        return redirect(url_for("player_login", next=request.path))
    return render_template("player_guide.html", match=latest_match())


@app.route("/league")
def league_overview():
    if not is_admin() and not current_player():
        return redirect(url_for("player_login", next=request.path))
    match = latest_match()
    maybe_auto_generate(match)
    match = latest_match()
    league_id = current_league_id()
    players = query(
        f"select * from players where {approved_players_sql()} and coalesce(league_id, ?) = ? order by score desc, power desc, name",
        (league_id, league_id),
    )
    matches = query(
        "select * from matches where coalesce(league_id, ?) = ? order by match_date desc, id desc limit 6",
        (league_id, league_id),
    )
    match_players = invited_players(match["id"]) if match else []
    confirmed_count = sum(1 for player in match_players if player["response"] in ("confirmed", "present"))
    return render_template(
        "public.html",
        match=match,
        players=players,
        matches=matches,
        match_players=match_players,
        confirmed_count=confirmed_count,
        motto=goliardic_motto(match),
    )


@app.route("/healthz")
def healthz():
    return {"status": "ok", "app": "FantaCalcetto"}


@app.route("/admin")
@require_admin
def admin_dashboard():
    match = featured_match()
    maybe_auto_generate(match)
    match = featured_match()
    league_id = current_league_id()
    if is_develop():
        players = query(
            """
            select p.*, l.name as league_name
            from players p
            left join leagues l on l.id = p.league_id
            where coalesce(p.account_status, 'approved') != 'pending'
            order by l.name, p.active desc, p.account_status, p.account_type, p.power desc, p.score desc, p.name
            """
        )
        pending_players = query(
            """
            select p.*, l.name as league_name
            from players p
            left join leagues l on l.id = p.league_id
            where p.account_status = 'pending'
            order by p.created_at desc
            """
        )
        rejected_players = query(
            """
            select p.*, l.name as league_name
            from players p
            left join leagues l on l.id = p.league_id
            where p.account_status in ('rejected', 'removed')
            order by p.created_at desc limit 30
            """
        )
    else:
        players = query(
            f"select * from players where {approved_players_sql()} and coalesce(league_id, ?) = ? order by power desc, score desc, name",
            (league_id, league_id),
        )
        pending_players = []
        rejected_players = query(
            "select * from players where account_status in ('rejected', 'removed') and coalesce(league_id, ?) = ? order by created_at desc limit 20",
            (league_id, league_id),
        )
    reset_requests = query(
        """
        select pr.*, p.name as player_name, p.username as player_username
        from password_reset_requests pr
        left join players p on p.id = pr.player_id
        where pr.status = 'pending' and (p.id is null or coalesce(p.league_id, ?) = ?)
        order by pr.created_at desc
        """,
        (league_id, league_id),
    )
    matches = query(
        "select * from matches where coalesce(league_id, ?) = ? order by match_date desc, id desc limit 8",
        (league_id, league_id),
    )
    future_matches = query(
        "select * from matches where coalesce(league_id, ?) = ? and match_date >= datetime('now', '-4 hours') and status not in ('closed', 'cancelled') order by match_date asc, id asc limit 6",
        (league_id, league_id),
    )
    past_matches = query(
        "select * from matches where coalesce(league_id, ?) = ? and (match_date < datetime('now', '-4 hours') or status in ('closed', 'cancelled')) order by match_date desc, id desc limit 6",
        (league_id, league_id),
    )
    match_players = invited_players(match["id"]) if match else []
    news_items = recent_league_events(12, include_admin=True)
    news_comments = comments_for_events(news_items)
    leagues = query("select * from leagues order by active desc, name") if is_develop() else []
    activity_logs = recent_league_events(24, include_admin=True) if is_develop() else []
    develop_stats = {}
    if is_develop():
        develop_stats = {
            "leagues": query("select count(*) as total from leagues where active = 1", one=True)["total"],
            "players": query("select count(*) as total from players where account_status = 'approved' and account_type = 'player'", one=True)["total"],
            "supporters": query("select count(*) as total from players where account_status = 'approved' and account_type = 'supporter'", one=True)["total"],
            "matches": query("select count(*) as total from matches", one=True)["total"],
            "events": query("select count(*) as total from league_events", one=True)["total"],
            "pending_leagues": query("select count(*) as total from league_requests where status = 'pending'", one=True)["total"],
        }
    transfer_requests = query(
        """
        select tp.*, p.name as player_name, p.nickname as player_nickname
        from transfer_proposals tp
        join players p on p.id = tp.player_id
        where coalesce(tp.league_id, ?) = ? and tp.status = 'pending'
        order by tp.created_at desc, tp.id desc
        limit 12
        """,
        (league_id, league_id),
    )
    league_requests = query(
        """
        select lr.*, p.name as player_name, p.username as player_username
        from league_requests lr
        left join players p on p.id = lr.requester_player_id
        where lr.status = 'pending'
        order by lr.created_at desc, lr.id desc
        """
    ) if is_develop() else []
    return render_template(
        "dashboard.html",
        match=match,
        players=players,
        matches=matches,
        future_matches=future_matches,
        past_matches=past_matches,
        match_players=match_players,
        phase=match_phase(match),
        summary_counts=match_summary_counts(match_players),
        confirmed_count=confirmed_count(match["id"]) if match else 0,
        pending_players=pending_players,
        rejected_players=rejected_players,
        reset_requests=reset_requests,
        news_items=news_items,
        news_comments=news_comments,
        app_updates=APP_UPDATES,
        transfer_requests=transfer_requests,
        league_requests=league_requests,
        activity_logs=activity_logs,
        develop_stats=develop_stats,
        market_team_ideas=MARKET_TEAM_IDEAS,
        market_offers=MARKET_OFFERS,
        leagues=leagues,
        develop_username=DEFAULT_DEVELOP_USERNAME,
        match_day=match_day(match) if match else False,
        motto=goliardic_motto(match),
        mascots=MASCOTS,
        foot_labels=FOOT_LABELS,
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("pin") == ADMIN_PIN:
            session.pop("player_id", None)
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        error = "PIN sbagliato. Il mister non ti riconosce."
    return render_template("login.html", error=error)


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("dashboard"))


@app.route("/admin/backup")
@require_admin
def admin_backup():
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    payload = export_payload()
    filename = f"fantacalcetto-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/admin/import", methods=["POST"])
@require_admin
def admin_import():
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    uploaded = request.files.get("backup_file")
    if not uploaded:
        return redirect(url_for("admin_dashboard"))
    payload = json.loads(uploaded.read().decode("utf-8"))
    if payload.get("app") == "FantaCalcetto" and isinstance(payload.get("tables"), dict):
        import_payload(payload)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reset-data", methods=["POST"])
@require_admin
def admin_reset_data():
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    if request.form.get("confirm_text", "").strip().upper() != "RESET":
        return redirect(url_for("admin_dashboard"))
    connection = db()
    clear_data_tables(connection)
    reset_identity_sequences(connection)
    connection.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/develop/leagues", methods=["POST"])
@require_admin
def create_league():
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("admin_dashboard"))
    slug = slugify(name)
    execute(
        """
        insert into leagues (name, slug, logo, primary_color, secondary_color)
        values (?, ?, ?, ?, ?)
        on conflict(slug) do update set
            name = excluded.name,
            logo = excluded.logo,
            primary_color = excluded.primary_color,
            secondary_color = excluded.secondary_color,
            active = 1
        """,
        (
            name,
            slug,
            request.form.get("logo", "").strip() or DEFAULT_LEAGUE_LOGO,
            request.form.get("primary_color", "#0f6b4f").strip() or "#0f6b4f",
            request.form.get("secondary_color", "#f2c94c").strip() or "#f2c94c",
        ),
    )
    log_league_event(
        "Nuova lega creata",
        f"Il Develop ha preparato {name}: un altro campionato, altre scuse ufficiali.",
        "develop",
        visibility="admin",
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/league-requests", methods=["POST"])
def request_new_league():
    username = request.form.get("username", "").strip().lower()
    display_name = request.form.get("display_name", "").strip()
    phone = request.form.get("phone", "").strip()
    league_name = request.form.get("league_name", "").strip()
    note = request.form.get("note", "").strip()
    requester = query("select id, name, phone from players where lower(username) = lower(?)", (username,), one=True) if username else None
    if not league_name:
        return redirect(url_for("player_login", notice="Scrivi almeno il nome della lega che vuoi creare."))
    if requester:
        display_name = display_name or requester["name"]
        phone = phone or requester["phone"]
    exists = query(
        "select id from league_requests where status = 'pending' and lower(league_name) = lower(?) and (lower(username) = lower(?) or phone = ?) limit 1",
        (league_name, username, phone),
        one=True,
    )
    if not exists:
        execute(
            """
            insert into league_requests (requester_player_id, username, display_name, phone, league_name, note)
            values (?, ?, ?, ?, ?, ?)
            """,
            (requester["id"] if requester else None, username, display_name, phone, league_name, note),
        )
        log_league_event(
            "Richiesta nuova lega",
            f"{display_name or username or 'Un aspirante mister'} chiede di aprire {league_name}. Il Develop valuta se consegnargli la lavagna.",
            "develop",
            requester["id"] if requester else None,
            "admin",
        )
    return redirect(url_for("player_login", notice="Richiesta inviata al Develop. Se ti approva, diventi Mister della nuova lega."))


@app.route("/develop/league-requests/<int:request_id>/approve", methods=["POST"])
@require_admin
def approve_league_request(request_id):
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    item = query("select * from league_requests where id = ? and status = 'pending'", (request_id,), one=True)
    if not item:
        return redirect(url_for("admin_dashboard"))
    slug = slugify(item["league_name"])
    suffix = 2
    base_slug = slug
    while query("select id from leagues where slug = ?", (slug,), one=True):
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    execute(
        """
        insert into leagues (name, slug, logo, primary_color, secondary_color)
        values (?, ?, ?, '#0f6b4f', '#f2c94c')
        """,
        (item["league_name"], slug, DEFAULT_LEAGUE_LOGO),
    )
    league = query("select * from leagues where slug = ?", (slug,), one=True)
    requester = None
    if item["requester_player_id"]:
        requester = query("select * from players where id = ?", (item["requester_player_id"],), one=True)
    if not requester and item["username"]:
        requester = query("select * from players where lower(username) = lower(?)", (item["username"],), one=True)
    if requester and league:
        execute(
            """
            insert into league_memberships (player_id, league_id, role, status)
            values (?, ?, 'mister', 'approved')
            on conflict(player_id, league_id) do update set role = 'mister', status = 'approved'
            """,
            (requester["id"], league["id"]),
        )
    execute(
        "update league_requests set status = 'approved', created_league_id = ?, resolved_at = current_timestamp where id = ?",
        (league["id"] if league else None, request_id),
    )
    log_league_event(
        "Nuova lega approvata",
        f"{item['league_name']} entra in FantaCalcetto. Mister nominato: {(requester['name'] if requester else item['display_name']) or 'da agganciare'}.",
        "develop",
        requester["id"] if requester else None,
        "all",
        league["id"] if league else None,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/develop/league-requests/<int:request_id>/reject", methods=["POST"])
@require_admin
def reject_league_request(request_id):
    if is_develop():
        execute(
            "update league_requests set status = 'rejected', resolved_at = current_timestamp where id = ?",
            (request_id,),
        )
    return redirect(url_for("admin_dashboard"))


@app.route("/develop/league-context", methods=["POST"])
@require_admin
def switch_develop_league():
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    try:
        league_id = int(request.form.get("league_id") or 0)
    except (TypeError, ValueError):
        league_id = 0
    league = query("select id from leagues where id = ?", (league_id,), one=True)
    if league:
        session["develop_league_id"] = league["id"]
        g.pop("current_league_value", None)
    return redirect(url_for("admin_dashboard", view="mister", _anchor="admin-partita"))


@app.route("/develop/leagues/<int:league_id>", methods=["POST"])
@require_admin
def update_league(league_id):
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    league = query("select * from leagues where id = ?", (league_id,), one=True)
    if not league:
        return redirect(url_for("admin_dashboard"))
    name = request.form.get("name", "").strip() or league["name"]
    logo = request.form.get("logo", "").strip() or league["logo"] or DEFAULT_LEAGUE_LOGO
    primary_color = request.form.get("primary_color", "").strip() or league["primary_color"] or "#0f6b4f"
    secondary_color = request.form.get("secondary_color", "").strip() or league["secondary_color"] or "#f2c94c"
    active = 1 if request.form.get("active") == "1" else 0
    execute(
        """
        update leagues
        set name = ?, logo = ?, primary_color = ?, secondary_color = ?, active = ?
        where id = ?
        """,
        (name, logo, primary_color, secondary_color, active, league_id),
    )
    log_league_event(
        "Lega aggiornata",
        f"Il Develop ha ritoccato identità e logo di {name}. Stemma pulito, polemiche pronte.",
        "develop",
        visibility="admin",
        league_id=league_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register_player():
    error = None
    leagues = query("select * from leagues where active = 1 order by name")
    if not leagues:
        ensure_default_league_and_roles()
        leagues = query("select * from leagues where active = 1 order by name")
    if request.method == "POST":
        name = request.form["name"].strip()
        surname = request.form.get("surname", "").strip()
        username = request.form["username"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"]
        requested_role = request.form.get("requested_role", "supporter")
        if requested_role not in ("supporter", "player"):
            requested_role = "supporter"
        mascot = request.form.get("mascot", "jolly")
        preferred_foot = request.form.get("preferred_foot", "right")
        if mascot not in MASCOTS:
            mascot = "jolly"
        if preferred_foot not in FOOT_LABELS:
            preferred_foot = "right"
        accepted_rules = request.form.get("accepted_rules") == "yes"
        try:
            selected_league_id = int(request.form.get("league_id") or 0)
        except (TypeError, ValueError):
            selected_league_id = 0
        selected_league = query(
            "select * from leagues where id = ? and active = 1",
            (selected_league_id,),
            one=True,
        )
        if query("select id from players where lower(username) = lower(?)", (username,), one=True):
            error = "Username già preso: serve un nome da spogliatoio originale."
        elif len(password) < 4:
            error = "Password troppo corta: almeno 4 caratteri, senza fare i fenomeni."
        elif not selected_league:
            error = "Scegli la lega giusta: il mister deve sapere in quale spogliatoio buttarti."
        elif not accepted_rules:
            error = "Prima serve il giuramento da spogliatoio: accetta il regolamento."
        else:
            account_status = "pending" if requested_role == "player" else "approved"
            account_type = "supporter"
            event_title = "Richiesta promozione calciatore" if requested_role == "player" else "Nuovo supporter in tribuna"
            event_body = (
                f"{f'{name} {surname}'.strip()} è entrato come supporter e chiede di diventare calciatore arruolabile."
                if requested_role == "player"
                else f"{f'{name} {surname}'.strip()} è entrato in LegaGram come supporter goliardico."
            )
            event_body = f"{event_body} Lega scelta: {selected_league['name']}."
            player_id = execute(
                """
                insert into players
                    (name, nickname, phone, username, password_hash, account_status, account_type, league_id, supporter_player_name, supporter_relation, active, mascot, mascot_name, preferred_foot, invite_token)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    f"{name} {surname}".strip(),
                    request.form.get("nickname", "").strip(),
                    phone,
                    username,
                    generate_password_hash(password),
                    account_status,
                    account_type,
                    selected_league["id"],
                    request.form.get("supporter_player_name", "").strip(),
                    request.form.get("supporter_relation", "").strip(),
                    mascot,
                    request.form.get("mascot_name", "").strip(),
                    preferred_foot,
                    uuid.uuid4().hex,
                ),
            )
            if player_id:
                execute(
                    """
                    insert into league_memberships (player_id, league_id, role, status)
                    values (?, ?, 'supporter', 'approved')
                    on conflict(player_id, league_id) do update set status = 'approved'
                    """,
                    (player_id, selected_league["id"]),
                )
            log_league_event(
                event_title,
                event_body,
                "registration",
                league_id=selected_league["id"],
            )
            return render_template("register_done.html", requested_role=requested_role)
    return render_template(
        "register.html",
        error=error,
        mascots=MASCOTS,
        foot_labels=FOOT_LABELS,
        rules=RULES,
        leagues=leagues,
    )


@app.route("/player/login", methods=["GET", "POST"])
def player_login():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]
        if username == "riccardo" and password == PUBLIC_DEVELOP_FALLBACK_PASSWORD:
            player_id = ensure_riccardo_develop_account()
            player = query("select * from players where id = ?", (player_id,), one=True)
            if player:
                session.pop("is_admin", None)
                session.pop("active_league_id", None)
                session["player_id"] = player["id"]
                log_league_event("Accesso effettuato", f"{player['name']} è entrato nello spogliatoio digitale.", "login", player["id"], "admin")
                return redirect(request.args.get("next") or url_for("player_dashboard"))
        player = query("select * from players where lower(username) = lower(?)", (username,), one=True)
        if player and player["password_hash"] and check_password_hash(player["password_hash"], password):
            if player["account_status"] in ("rejected", "removed"):
                error = "Account non attivo. Parla col mister prima di entrare nello spogliatoio."
                return render_template("player_login.html", error=error, notice=request.args.get("notice", ""))
            session.pop("is_admin", None)
            session.pop("active_league_id", None)
            session["player_id"] = player["id"]
            log_league_event("Accesso effettuato", f"{player['name']} è entrato nello spogliatoio digitale.", "login", player["id"], "admin")
            return redirect(request.args.get("next") or url_for("player_dashboard"))
        error = "Credenziali sbagliate. Riprova senza tunnel."
    return render_template("player_login.html", error=error, notice=request.args.get("notice", ""))


@app.route("/player/password-dimenticata", methods=["GET", "POST"])
def forgot_player_password():
    sent = False
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        display_name = request.form.get("display_name", "").strip()
        message = request.form.get("message", "").strip()
        if not username and not phone and not display_name:
            error = "Scrivi almeno nome, username o numero WhatsApp: il mister deve capire chi sei."
        else:
            player = None
            if username:
                player = query("select * from players where lower(username) = lower(?)", (username,), one=True)
            if not player and phone:
                player = query("select * from players where phone = ?", (phone,), one=True)
            execute(
                """
                insert into password_reset_requests (player_id, display_name, username, phone, message)
                values (?, ?, ?, ?, ?)
                """,
                (player["id"] if player else None, display_name, username, phone, message),
            )
            log_league_event(
                "Richiesta recupero password",
                f"{display_name or username or phone} ha chiesto aiuto al mister per rientrare nello spogliatoio digitale.",
                "account",
                player["id"] if player else None,
                "admin",
            )
            sent = True
    return render_template("forgot_password.html", error=error, sent=sent)


@app.route("/admin/password-requests/<int:request_id>/resolve", methods=["POST"])
@require_admin
def resolve_password_request(request_id):
    reset_request = query("select * from password_reset_requests where id = ?", (request_id,), one=True)
    if not reset_request:
        return redirect(url_for("admin_dashboard"))
    player_id = int(request.form.get("player_id") or reset_request["player_id"] or 0)
    new_password = request.form.get("new_password", "").strip()
    if player_id and new_password:
        execute(
            "update players set password_hash = ? where id = ?",
            (generate_password_hash(new_password), player_id),
        )
        execute(
            """
            update password_reset_requests
            set player_id = ?, status = 'resolved', temp_password_set = 1, resolved_at = current_timestamp
            where id = ?
            """,
            (player_id, request_id),
        )
        player = query("select name from players where id = ?", (player_id,), one=True)
        log_league_event(
            "Password provvisoria impostata",
            f"Il mister ha rimesso le chiavi dello spogliatoio a {player['name'] if player else 'un calciatore'}.",
            "account",
            player_id,
            "admin",
        )
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/password-requests/<int:request_id>/dismiss", methods=["POST"])
@require_admin
def dismiss_password_request(request_id):
    execute(
        "update password_reset_requests set status = 'dismissed', resolved_at = current_timestamp where id = ?",
        (request_id,),
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/player/logout", methods=["POST"])
def player_logout():
    session.pop("player_id", None)
    return redirect(url_for("dashboard"))


@app.route("/player")
@require_player
def player_dashboard():
    player = current_player()
    league_id = current_league_id() or player["league_id"]
    match = featured_match()
    if match:
        maybe_auto_generate(match)
        match = featured_match()
    my_matches = query(
        """
        select m.*, mp.response, mp.team, mp.goals as match_goals, mp.assists as match_assists,
               mp.cancelled_at, mp.responded_at, mp.penalty_points
        from matches m
        left join match_players mp on mp.match_id = m.id and mp.player_id = ?
        where coalesce(m.league_id, ?) = ? and m.match_date >= datetime('now', '-1 day')
        order by m.match_date asc
        limit 6
        """,
        (player["id"], league_id, league_id),
    )
    past_matches = query(
        """
        select m.*, mp.response, mp.team, mp.goals as match_goals, mp.assists as match_assists,
               mp.cancelled_at, mp.responded_at, mp.penalty_points
        from matches m
        left join match_players mp on mp.match_id = m.id and mp.player_id = ?
        where coalesce(m.league_id, ?) = ? and (m.match_date < datetime('now', '-1 day') or m.status in ('closed', 'cancelled'))
        order by m.match_date desc, m.id desc
        limit 8
        """,
        (player["id"], league_id, league_id),
    )
    my_waitlist_positions = {}
    for my_match in my_matches:
        if my_match["response"] == "waitlist":
            my_waitlist_positions[my_match["id"]] = waitlist_positions(my_match["id"]).get(player["id"])
    seed_develop_feed()
    news_items = recent_league_events(14)
    featured_players = invited_players(my_matches[0]["id"]) if my_matches else []
    current_mvp_player_id = latest_mvp_player_id(league_id, my_matches[0]["id"]) if my_matches else None
    pending_transfers = pending_transfer_for_player(player["id"])
    return render_template(
        "player_dashboard.html",
        player=player,
        matches=my_matches,
        past_matches=past_matches,
        featured_players=featured_players,
        match=match,
        phase=match_phase(match),
        waitlist_positions=my_waitlist_positions,
        foot_labels=FOOT_LABELS,
        notice=request.args.get("notice", ""),
        news_items=news_items,
        news_comments=comments_for_events(news_items),
        match_comments=comments_for_matches(my_matches + past_matches),
        app_updates=APP_UPDATES[:3],
        pending_transfers=pending_transfers,
        mascots=MASCOTS,
        memberships=player_league_memberships(player["id"]),
        current_mvp_player_id=current_mvp_player_id,
    )


@app.route("/player/league-context", methods=["POST"])
@require_player
def switch_player_league():
    player = current_player()
    try:
        league_id = int(request.form.get("league_id") or 0)
    except (TypeError, ValueError):
        league_id = 0
    membership = query(
        "select league_id from league_memberships where player_id = ? and league_id = ? and status = 'approved'",
        (player["id"], league_id),
        one=True,
    )
    if membership:
        session["active_league_id"] = membership["league_id"]
        g.pop("current_league_value", None)
    return redirect(url_for("player_dashboard"))


def match_is_locked(match):
    return not match or match["status"] in ("closed", "cancelled")


@app.route("/player/matches/<int:match_id>/confirm", methods=["POST"])
@require_player
def player_confirm(match_id):
    player = current_player()
    if player["account_status"] != "approved" or player["account_type"] != "player":
        return redirect(url_for("player_dashboard"))
    match = get_match(match_id)
    if match_is_locked(match):
        return redirect(url_for("player_dashboard", notice="Questa partita non è più confermabile. Controlla lo stato evento."))
    previous = query(
        "select response from match_players where match_id = ? and player_id = ?",
        (match_id, player["id"]),
        one=True,
    )
    if previous and previous["response"] == "present":
        return redirect(url_for("player_dashboard"))
    response = "confirmed" if has_roster_slot(match_id, player["id"]) else "waitlist"
    try:
        execute(
            """
            insert into match_players (match_id, player_id, response, responded_at)
            values (?, ?, ?, current_timestamp)
            on conflict(match_id, player_id) do update set
                response = excluded.response,
                team = null,
                cancelled_at = null,
                penalty_points = 0,
                responded_at = case
                    when match_players.responded_at is null then current_timestamp
                    else match_players.responded_at
                end
            """,
            (match_id, player["id"], response),
        )
        if response == "confirmed" and (not previous or previous["response"] not in ("confirmed", "present")):
            execute(
                """
                update players
                set score = score + 1,
                    reliability = min(100, reliability + ?)
                where id = ?
                """,
                (2, player["id"]),
            )
        sync_waitlist(match_id)
        maybe_auto_generate(get_match(match_id))
    except Exception:
        app.logger.exception("Errore durante conferma giocatore %s partita %s", player["id"], match_id)
        return redirect(url_for("player_dashboard", notice="Non sono riuscito a registrare la conferma. Riprova o avvisa il mister."))
    log_league_event(
        "Presenza confermata",
        f"{player['name']} ha detto sì alla partita. Il gruppo può iniziare a fare pretattica.",
        "confirmation",
        player["id"],
    )
    notice = "Conferma registrata: sei dentro." if response == "confirmed" else "Posti pieni: sei in lista d'attesa."
    return redirect(url_for("player_dashboard", notice=notice))


@app.route("/player/matches/<int:match_id>/cancel", methods=["POST"])
@require_player
def player_cancel(match_id):
    player = current_player()
    if player["account_status"] != "approved" or player["account_type"] != "player":
        return redirect(url_for("player_dashboard"))
    match = get_match(match_id)
    if match_is_locked(match):
        return redirect(url_for("player_dashboard"))
    penalty, power_penalty, _message = cancellation_penalty(match)
    try:
        execute(
            """
            insert into match_players (match_id, player_id, response, cancelled_at, responded_at, penalty_points)
            values (?, ?, 'declined', current_timestamp, current_timestamp, ?)
            on conflict(match_id, player_id) do update set
                response = 'declined',
                cancelled_at = current_timestamp,
                responded_at = current_timestamp,
                penalty_points = excluded.penalty_points
            """,
            (match_id, player["id"], penalty),
        )
        execute(
            """
            update players
            set score = max(0, score - ?),
                reliability = max(0, reliability - ?)
            where id = ?
            """,
            (penalty, penalty * 2, player["id"]),
        )
        adjust_player_power(player["id"], -power_penalty)
        sync_waitlist(match_id)
        maybe_auto_generate(get_match(match_id))
    except Exception:
        app.logger.exception("Errore durante disdetta giocatore %s partita %s", player["id"], match_id)
        return redirect(url_for("player_dashboard", notice="Non sono riuscito a registrare la disdetta. Riprova o avvisa il mister."))
    log_league_event(
        "Disdetta registrata",
        f"{player['name']} ha disdetto. Penalità: {penalty} punti, il tribunale del calcetto osserva.",
        "cancellation",
        player["id"],
    )
    return redirect(url_for("player_dashboard", notice="Disdetta registrata. Lo spogliatoio prende nota."))


@app.route("/player/matches/<int:match_id>/comments", methods=["POST"])
@require_player
def add_match_comment(match_id):
    player = current_player()
    body = request.form.get("body", "").strip()
    if body and get_match(match_id):
        execute(
            """
            insert into match_comments (match_id, player_id, body)
            values (?, ?, ?)
            """,
            (match_id, player["id"], body[:500]),
        )
        log_league_event(
            "Commento partita",
            f"{player['name']} ha lasciato una nota sulla partita. Lo spogliatoio ha materiale.",
            "comment",
            player["id"],
        )
    return redirect(url_for("player_dashboard", notice="Commento pubblicato nello spogliatoio."))


@app.route("/league-events/<int:event_id>/comments", methods=["POST"])
@require_player
def add_event_comment(event_id):
    player = current_player()
    body = request.form.get("body", "").strip()
    event = query("select id from league_events where id = ?", (event_id,), one=True)
    if body and event:
        display_role = normalize_publish_role(player, request.form.get("as_role", ""))
        execute(
            """
            insert into league_event_comments (event_id, player_id, display_role, body)
            values (?, ?, ?, ?)
            """,
            (event_id, player["id"], display_role, body[:400]),
        )
        execute(
            "update players set faith_score = faith_score + 2, score = score + 1 where id = ?",
            (player["id"],),
        )
    return redirect(url_for("player_dashboard", notice="Commento alla news pubblicato. +2 Fede, la curva prende nota."))


@app.route("/league-events/<int:event_id>/react", methods=["POST"])
@require_player
def react_event(event_id):
    player = current_player()
    reaction = request.form.get("reaction", "cuore").strip()[:24]
    event = query("select id from league_events where id = ?", (event_id,), one=True)
    if event:
        execute(
            """
            insert into league_event_comments (event_id, player_id, body)
            values (?, ?, ?)
            """,
            (event_id, player["id"], f"ha reagito: {reaction}"),
        )
        execute(
            "update players set faith_score = faith_score + 1 where id = ?",
            (player["id"],),
        )
    return redirect(url_for("player_dashboard", notice="Reaction registrata. +1 Fede, la curva applaude."))


@app.route("/player/chronicles", methods=["POST"])
@require_player
def add_player_chronicle():
    player = current_player()
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()
    display_role = normalize_publish_role(player, request.form.get("as_role", ""))
    if not body:
        return redirect(url_for("player_dashboard", notice="Scrivi almeno due righe, pure storte, ma scrivile."))
    if not title:
        title = f"Cronaca di {player['name']}"
    log_league_event(
        title[:90],
        body[:700],
        "cronaca",
        player["id"],
        "all",
        actor_display_role=display_role,
    )
    return redirect(url_for("player_dashboard", notice="Cronaca pubblicata. Lo spogliatoio è stato informato."))


@app.route("/player/profile", methods=["GET", "POST"])
@require_player
def player_update_profile():
    player = current_player()
    if request.method == "GET":
        return render_template(
            "player_profile.html",
            player=player,
            mascots=MASCOTS,
            foot_labels=FOOT_LABELS,
        )
    name = request.form.get("name", "").strip() or player["name"]
    nickname = request.form.get("nickname", "").strip()
    phone = request.form.get("phone", "").strip() or player["phone"]
    mascot = request.form.get("mascot", player["mascot"] or "jolly")
    preferred_foot = request.form.get("preferred_foot", "right")
    if mascot not in MASCOTS:
        mascot = player["mascot"] or "jolly"
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    execute(
        """
        update players
        set name = ?, nickname = ?, phone = ?, mascot = ?, mascot_name = ?, preferred_foot = ?
        where id = ?
        """,
        (
            name,
            nickname,
            phone,
            mascot,
            request.form.get("mascot_name", "").strip(),
            preferred_foot,
            player["id"],
        ),
    )
    log_league_event(
        "Profilo aggiornato",
        f"{name} ha ritoccato profilo, mascotte o piede preferito. Lo scouting prende appunti.",
        "profile",
        player["id"],
    )
    return redirect(url_for("player_dashboard", notice="Profilo aggiornato. La figurina è stata rimessa in posa."))


@app.route("/player/mascot-name", methods=["POST"])
@require_player
def player_update_mascot_name():
    return player_update_profile()


@app.route("/players", methods=["POST"])
@require_admin
def add_player():
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    preferred_foot = request.form.get("preferred_foot", "right")
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    player_id = execute(
        """
        insert into players (league_id, name, nickname, phone, role, power, mascot, preferred_foot, invite_token)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            current_league_id(),
            request.form["name"].strip(),
            request.form.get("nickname", "").strip(),
            request.form["phone"].strip(),
            request.form.get("role", "Jolly"),
            float(request.form.get("power", 3)),
            request.form.get("mascot", "jolly"),
            preferred_foot,
            uuid.uuid4().hex,
        ),
    )
    log_league_event(
        "Giocatore aggiunto dal Develop",
        f"{request.form['name'].strip()} entra nella rosa arruolabili dalla porta Develop.",
        "admin",
        player_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>", methods=["POST"])
@require_admin
def update_player(player_id):
    old_player = query("select * from players where id = ?", (player_id,), one=True)
    if not old_player:
        return redirect(url_for("admin_dashboard"))
    preferred_foot = request.form.get("preferred_foot", "right")
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    requested_app_role = request.form.get("app_role", old_player["app_role"] if old_player and "app_role" in old_player.keys() else "member")
    if requested_app_role not in ("member", "mister", "develop"):
        requested_app_role = "member"
    app_role = requested_app_role if is_develop() else (old_player["app_role"] if old_player and "app_role" in old_player.keys() else "member")
    account_type = old_player["account_type"] if "account_type" in old_player.keys() else "player"
    account_status = old_player["account_status"] if "account_status" in old_player.keys() else "approved"
    target_league_id = old_player["league_id"] if "league_id" in old_player.keys() else current_league_id()
    if is_develop():
        account_type = request.form.get("account_type", account_type)
        if account_type not in ("player", "supporter"):
            account_type = "supporter"
        account_status = request.form.get("account_status", account_status)
        if account_status not in ("approved", "pending", "rejected", "removed"):
            account_status = "approved"
        try:
            requested_league_id = int(request.form.get("league_id") or target_league_id or 0)
        except (TypeError, ValueError):
            requested_league_id = target_league_id
        league = query("select id from leagues where id = ?", (requested_league_id,), one=True)
        if league:
            target_league_id = league["id"]
    execute(
        """
        update players
        set name = ?, nickname = ?, phone = ?, role = ?, power = ?, reliability = ?,
            mascot = ?, mascot_name = ?, preferred_foot = ?, permanent_team_name = ?, app_role = ?,
            account_type = ?, account_status = ?, league_id = ?, active = case when ? in ('removed', 'rejected') then 0 else 1 end
        where id = ?
        """,
        (
            request.form["name"].strip(),
            request.form.get("nickname", "").strip(),
            request.form["phone"].strip(),
            request.form.get("role", "Jolly"),
            float(request.form.get("power", 3)),
            int(request.form.get("reliability", 80)),
            request.form.get("mascot", "jolly"),
            request.form.get("mascot_name", "").strip(),
            preferred_foot,
            request.form.get("permanent_team_name", "").strip(),
            app_role,
            account_type,
            account_status,
            target_league_id,
            account_status,
            player_id,
        ),
    )
    if account_status == "approved" and target_league_id:
        execute(
            """
            insert into league_memberships (player_id, league_id, role, status)
            values (?, ?, ?, 'approved')
            on conflict(player_id, league_id) do update set role = excluded.role, status = 'approved'
            """,
            (player_id, target_league_id, membership_role_for_player({"account_type": account_type, "app_role": app_role})),
        )
    changes = []
    if old_player:
        new_name = request.form["name"].strip()
        new_nickname = request.form.get("nickname", "").strip()
        if old_player["name"] != new_name:
            changes.append(f"nome: {old_player['name']} -> {new_name}")
        if (old_player["nickname"] or "") != new_nickname:
            changes.append("soprannome aggiornato")
        if power_value(old_player["power"]) != float(request.form.get("power", 3)):
            changes.append("stelle ritoccate")
    log_league_event(
        "Scheda calciatore modificata",
        f"{request.form['name'].strip()} aggiornato da {'Develop' if is_develop() else 'Mister'}. {', '.join(changes) if changes else 'Piccoli ritocchi da spogliatoio.'}",
        "admin",
        player_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/transfer", methods=["POST"])
@require_admin
def propose_player_transfer(player_id):
    player = query("select * from players where id = ?", (player_id,), one=True)
    if not player:
        return redirect(url_for("admin_dashboard"))
    league_id = current_league_id()
    if not is_develop() and player["league_id"] not in (None, league_id):
        return redirect(url_for("admin_dashboard"))
    transfer_type = request.form.get("transfer_type", "loan")
    if transfer_type not in ("loan", "permanent"):
        transfer_type = "loan"
    to_team = request.form.get("to_team", "").strip()
    if not to_team:
        return redirect(url_for("admin_dashboard"))
    offer_label = request.form.get("custom_offer", "").strip() or request.form.get("offer_label", "").strip() or random.choice(MARKET_OFFERS)
    from_team = (player["permanent_team_name"] if "permanent_team_name" in player.keys() else "") or "Svincolati di lusso"
    execute(
        """
        insert into transfer_proposals (league_id, player_id, from_team, to_team, transfer_type, offer_label, status, created_by_player_id)
        values (?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            player["league_id"] or league_id,
            player_id,
            from_team,
            to_team,
            transfer_type,
            offer_label,
            current_player()["id"] if current_player() else None,
        ),
    )
    kind_label = "prestito" if transfer_type == "loan" else "titolo definitivo"
    log_league_event(
        "SkySpogliatoio Mercato",
        f"Trattativa aperta: {player['name']} da {from_team} verso {to_team}, formula {kind_label}. Offerta ufficiale: {offer_label}. Ora serve la firma del calciatore.",
        "mercato",
        player_id,
        league_id=player["league_id"] or league_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/player/transfers/<int:transfer_id>/respond", methods=["POST"])
@require_player
def respond_transfer(transfer_id):
    player = current_player()
    transfer = query(
        "select * from transfer_proposals where id = ? and player_id = ? and status = 'pending'",
        (transfer_id, player["id"]),
        one=True,
    )
    if not transfer:
        return redirect(url_for("player_dashboard"))
    decision = request.form.get("decision")
    if decision == "accept":
        execute(
            "update transfer_proposals set status = 'accepted', responded_at = current_timestamp where id = ?",
            (transfer_id,),
        )
        execute("update players set permanent_team_name = ? where id = ?", (transfer["to_team"], player["id"]))
        log_league_event(
            "SkySpogliatoio: firma depositata",
            transfer_phrase(
                TRANSFER_ACCEPT_PHRASES,
                player["name"],
                transfer["to_team"],
                transfer["from_team"],
                transfer["transfer_type"],
                transfer["offer_label"],
            ),
            "mercato",
            player["id"],
            league_id=transfer["league_id"],
        )
        return redirect(url_for("player_dashboard", notice="Trasferimento accettato. La nuova maglia ti aspetta, almeno metaforicamente."))
    execute(
        "update transfer_proposals set status = 'declined', responded_at = current_timestamp where id = ?",
        (transfer_id,),
    )
    execute(
        "update players set score = max(0, score - ?), reliability = max(0, reliability - ?) where id = ?",
        (2, 5, player["id"]),
    )
    log_league_event(
        "SkySpogliatoio: trattativa saltata",
        transfer_phrase(
            TRANSFER_DECLINE_PHRASES,
            player["name"],
            transfer["to_team"],
            transfer["from_team"],
            transfer["transfer_type"],
            transfer["offer_label"],
        ),
        "mercato",
        player["id"],
        league_id=transfer["league_id"],
    )
    g.pop("current_player_value", None)
    return redirect(url_for("player_dashboard", notice="Trasferimento rifiutato: -2 score e -5 affidabilita'. Il mercato non dimentica."))


@app.route("/players/<int:player_id>/mascot", methods=["POST"])
@require_admin
def update_player_mascot(player_id):
    mascot = request.form.get("mascot", "jolly")
    if mascot not in MASCOTS:
        mascot = "jolly"
    execute("update players set mascot = ? where id = ?", (mascot, player_id))
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/mascot-name", methods=["POST"])
@require_admin
def update_player_mascot_name(player_id):
    execute(
        "update players set mascot_name = ? where id = ?",
        (request.form.get("mascot_name", "").strip(), player_id),
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/power", methods=["POST"])
@require_admin
def update_player_power(player_id):
    power = max(1, min(5, float(request.form.get("power", 3))))
    execute("update players set power = ? where id = ?", (power, player_id))
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/approve", methods=["POST"])
@require_admin
def approve_player(player_id):
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    player = query("select * from players where id = ?", (player_id,), one=True)
    target_league_id = player["league_id"] if player and "league_id" in player.keys() else current_league_id()
    try:
        requested_league_id = int(request.form.get("league_id") or target_league_id or 0)
    except (TypeError, ValueError):
        requested_league_id = target_league_id
    league = query("select id from leagues where id = ?", (requested_league_id,), one=True)
    if league:
        target_league_id = league["id"]
    execute(
        "update players set account_status = 'approved', account_type = 'player', active = 1, league_id = ? where id = ?",
        (target_league_id, player_id),
    )
    execute(
        """
        insert into league_memberships (player_id, league_id, role, status)
        values (?, ?, 'player', 'approved')
        on conflict(player_id, league_id) do update set role = 'player', status = 'approved'
        """,
        (player_id, target_league_id),
    )
    log_league_event(
        "Calciatore approvato",
        f"{player['name'] if player else 'Un nuovo calciatore'} è stato promosso calciatore arruolabile dal Develop. Si scaldi la panchina.",
        "approval",
        player_id,
        league_id=target_league_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/reject", methods=["POST"])
@require_admin
def reject_player(player_id):
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    execute("update players set account_status = 'rejected', active = 0 where id = ?", (player_id,))
    player = query("select name from players where id = ?", (player_id,), one=True)
    log_league_event(
        "Richiesta respinta",
        f"{player['name'] if player else 'Una richiesta'} è stata respinta dal Develop.",
        "admin",
        player_id,
        "admin",
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/remove", methods=["POST"])
@require_admin
def remove_player(player_id):
    if not is_develop():
        return redirect(url_for("admin_dashboard"))
    execute(
        "update players set account_status = 'removed', active = 0 where id = ?",
        (player_id,),
    )
    execute(
        """
        delete from match_players
        where player_id = ? and match_id in (
            select id from matches where status != 'closed'
        )
        """,
        (player_id,),
    )
    if session.get("player_id") == player_id:
        session.pop("player_id", None)
    return redirect(url_for("admin_dashboard"))


@app.route("/matches", methods=["POST"])
@require_admin
def create_match():
    league_id = current_league_id()
    match_id = execute(
        """
        insert into matches (league_id, title, match_date, location, player_limit)
        values (?, ?, ?, ?, ?)
        """,
        (
            league_id,
            request.form["title"].strip(),
            request.form["match_date"],
            request.form["location"].strip(),
            int(request.form.get("player_limit", 10)),
        ),
    )
    selected = request.form.getlist("player_ids")
    if not selected:
        selected = [
            str(row["id"])
            for row in query(
                f"select id from players where {approved_players_sql()} and coalesce(league_id, ?) = ?",
                (league_id, league_id),
            )
        ]
    for player_id in selected:
        execute(
            "insert into match_players (match_id, player_id, response) values (?, ?, 'invited')",
            (match_id, int(player_id)),
        )
    log_league_event(
        "Nuova partita creata",
        f"{request.form['title'].strip()} è in calendario: convocazioni aperte, scuse già in preparazione.",
        "match",
    )
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>")
@require_admin
def match_detail(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("admin_dashboard"))
    auto_generated = maybe_auto_generate(match)
    match = get_match(match_id)
    players = invited_players(match_id)
    all_players = query(
        """
        select p.*
        from players p
        where p.active = 1 and p.account_status = 'approved' and coalesce(p.account_type, 'player') = 'player'
          and coalesce(p.is_guest, 0) = 0 and coalesce(p.league_id, ?) = ? and p.id not in (
            select player_id from match_players where match_id = ?
        )
        order by p.name
        """,
        (match["league_id"], match["league_id"], match_id),
    )
    return render_template(
        "match.html",
        match=match,
        players=players,
        all_players=all_players,
        summary_counts=match_summary_counts(players),
        award_types=active_award_types(),
        match_awards=match_awards(match_id),
        match_comments=comments_for_matches([match]).get(match_id, []),
        auto_generated=auto_generated,
        match_day=match_day(match),
        phase=match_phase(match),
        motto=goliardic_motto(match),
        confirmed_count=confirmed_count(match_id),
        mascots=MASCOTS,
        foot_labels=FOOT_LABELS,
        notice=request.args.get("notice", ""),
        team_name_ideas=team_name_ideas(),
        team_logos=TEAM_LOGOS,
        current_mvp_player_id=latest_mvp_player_id(match["league_id"], match_id),
    )


@app.route("/player/matches/<int:match_id>")
@require_player
def player_match_detail(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("player_dashboard"))
    players = invited_players(match_id)
    player = current_player()
    my_row = next((row for row in players if row["id"] == player["id"]), None)
    if not my_row and player["account_type"] != "supporter" and not can_manage():
        return redirect(url_for("player_dashboard"))
    return render_template(
        "player_match_detail.html",
        match=match,
        players=players,
        player=player,
        summary_counts=match_summary_counts(players),
        match_awards=match_awards(match_id),
        phase=match_phase(match),
        my_row=my_row,
        current_mvp_player_id=latest_mvp_player_id(match["league_id"], match_id),
    )


@app.route("/matches/<int:match_id>/settings", methods=["POST"])
@require_admin
def update_match_settings(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("admin_dashboard"))
    title = request.form.get("title", "").strip() or match["title"]
    match_date = request.form.get("match_date", "").strip() or match["match_date"]
    location = request.form.get("location", "").strip() or match["location"]
    try:
        player_limit = max(2, min(30, int(request.form.get("player_limit", match["player_limit"] or 10))))
    except (TypeError, ValueError):
        return redirect(url_for("match_detail", match_id=match_id, notice="Quota partita non valida: inserisci un numero da 2 a 30."))
    try:
        execute(
            """
            update matches
            set title = ?, match_date = ?, location = ?, player_limit = ?
            where id = ?
            """,
            (title, match_date, location, player_limit, match_id),
        )
        sync_waitlist(match_id)
    except Exception:
        app.logger.exception("Errore durante il salvataggio impostazioni partita %s", match_id)
        return redirect(url_for("match_detail", match_id=match_id, notice="Non sono riuscito a salvare la partita. Controlla data, ora e quota."))
    log_league_event(
        "Partita aggiornata",
        f"Il mister ha modificato {title}: orario, campo o quota sono stati ritoccati.",
        "match",
    )
    return redirect(url_for("match_detail", match_id=match_id, notice="Modifiche partita salvate."))


@app.route("/matches/<int:match_id>/confirm-match", methods=["POST"])
@require_admin
def confirm_match(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("admin_dashboard"))
    if match["status"] in ("closed", "cancelled"):
        return redirect(url_for("match_detail", match_id=match_id, notice="Questa partita non può essere confermata perché è chiusa o annullata."))
    quota = int(match["player_limit"] or 0)
    confirmed = confirmed_count(match_id)
    if quota <= 0:
        return redirect(url_for("match_detail", match_id=match_id, notice="Imposta prima una quota partita valida."))
    if confirmed < quota:
        return redirect(url_for("match_detail", match_id=match_id, notice=f"Quota non raggiunta: {confirmed}/{quota}. Aggiungi un esterno o abbassa la quota."))
    try:
        execute("update matches set status = 'confirmed' where id = ?", (match_id,))
    except Exception:
        app.logger.exception("Errore durante la conferma partita %s", match_id)
        return redirect(url_for("match_detail", match_id=match_id, notice="Non sono riuscito a confermare la partita. Riprova dopo aver salvato quota e orario."))
    log_league_event(
        "Partita confermata dal mister",
        f"{match['title']} è confermata: niente più filosofia, si gioca.",
        "match",
    )
    return redirect(url_for("match_detail", match_id=match_id, notice="Partita confermata. Il mister automatico è in panchina."))


@app.route("/matches/<int:match_id>/reopen", methods=["POST"])
@require_admin
def reopen_match(match_id):
    execute("update matches set status = 'open', team_a_score = null, team_b_score = null where id = ?", (match_id,))
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/cancel", methods=["POST"])
@require_admin
def cancel_match(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("admin_dashboard", view="mister", _anchor="history"))
    execute("update matches set status = 'cancelled' where id = ?", (match_id,))
    execute("update match_players set team = null where match_id = ?", (match_id,))
    log_league_event(
        "Partita annullata",
        f"{match['title']} è stata annullata. Resta nello storico: la scusa ufficiale entra agli atti.",
        "match",
        visibility="all",
        league_id=match["league_id"],
    )
    return redirect(url_for("match_detail", match_id=match_id, notice="Partita annullata: resta nello storico."))


@app.route("/matches/<int:match_id>/delete", methods=["POST"])
@require_admin
def delete_match(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("admin_dashboard", view="mister", _anchor="history"))
    execute("delete from match_awards where match_id = ?", (match_id,))
    execute("delete from match_comments where match_id = ?", (match_id,))
    execute("delete from match_players where match_id = ?", (match_id,))
    execute("delete from matches where id = ?", (match_id,))
    return redirect(url_for("admin_dashboard", view="mister", _anchor="history"))


@app.route("/matches/<int:match_id>/external", methods=["POST"])
@require_admin
def add_external_player(match_id):
    match = get_match(match_id)
    if not match:
        return redirect(url_for("admin_dashboard"))
    name = request.form["name"].strip()
    if not name:
        return redirect(url_for("match_detail", match_id=match_id))
    preferred_foot = request.form.get("preferred_foot", "right")
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    player_id = execute(
        """
        insert into players (league_id, name, nickname, phone, role, power, mascot, mascot_name, preferred_foot, invite_token, account_status, account_type, active, is_guest)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', 'player', 1, 1)
        """,
        (
            match["league_id"] or current_league_id(),
            name,
            request.form.get("nickname", "Esterno").strip(),
            request.form.get("phone", "esterno").strip() or "esterno",
            request.form.get("role", "Jolly"),
            float(request.form.get("power", 3)),
            request.form.get("mascot", "jolly"),
            request.form.get("mascot_name", "").strip(),
            preferred_foot,
            uuid.uuid4().hex,
        ),
    )
    execute(
        """
        insert into match_players (match_id, player_id, response, responded_at)
        values (?, ?, 'confirmed', current_timestamp)
        on conflict(match_id, player_id) do update set response = 'confirmed', responded_at = current_timestamp
        """,
        (match_id, player_id),
    )
    sync_waitlist(match_id)
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/player/matches/<int:match_id>/calendar.ics")
@require_player
def player_match_calendar(match_id):
    match = get_match(match_id)
    if not match or match["status"] == "cancelled":
        return redirect(url_for("player_dashboard"))
    try:
        start = datetime.fromisoformat(match["match_date"])
    except ValueError:
        start = datetime.now()
    end = start + timedelta(hours=1, minutes=30)

    def ics_text(value):
        return str(value or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    body = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//FantaCalcetto//Digislam Print Lab//IT",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "BEGIN:VEVENT",
            f"UID:fantacalcetto-{match_id}@digislam.shop",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{ics_text(match['title'])}",
            f"LOCATION:{ics_text(match['location'])}",
            "DESCRIPTION:Controlla sempre la scheda evento FantaCalcetto: orario, campo, conferma o annullamento possono cambiare.",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    filename = f"fantacalcetto-{match_id}.ics"
    return Response(
        body,
        mimetype="text/calendar",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/matches/<int:match_id>/invite", methods=["POST"])
@require_admin
def invite_to_match(match_id):
    for player_id in request.form.getlist("player_ids"):
        execute(
            """
            insert into match_players (match_id, player_id, response)
            values (?, ?, 'invited')
            on conflict(match_id, player_id) do nothing
            """,
            (match_id, int(player_id)),
        )
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/responses", methods=["POST"])
@require_admin
def update_responses(match_id):
    for key, value in request.form.items():
        if key.startswith("response_"):
            player_id = int(key.replace("response_", ""))
            execute(
                """
                update match_players
                set response = ?,
                    responded_at = case
                        when ? in ('confirmed', 'present', 'waitlist') and responded_at is null then current_timestamp
                        when ? = 'declined' then current_timestamp
                        else responded_at
                    end
                where match_id = ? and player_id = ?
                """,
                (value, value, value, match_id, player_id),
            )
    sync_waitlist(match_id)
    maybe_auto_generate(get_match(match_id))
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/generate", methods=["POST"])
@require_admin
def generate_teams(match_id):
    match = get_match(match_id)
    if match and match["status"] != "cancelled":
        apply_team_generation(match_id)
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/teams", methods=["POST"])
@require_admin
def update_match_teams(match_id):
    if get_match(match_id):
        execute(
            """
            update matches
            set team_a_name = ?, team_b_name = ?, team_a_logo = ?, team_b_logo = ?
            where id = ?
            """,
            (
                request.form.get("team_a_name", "Squadra A").strip() or "Squadra A",
                request.form.get("team_b_name", "Squadra B").strip() or "Squadra B",
                request.form.get("team_a_logo", "crest-1") if request.form.get("team_a_logo") in TEAM_LOGOS else "crest-1",
                request.form.get("team_b_logo", "crest-2") if request.form.get("team_b_logo") in TEAM_LOGOS else "crest-2",
                match_id,
            ),
        )
        for key, value in request.form.items():
            if key.startswith("team_") and key.replace("team_", "").isdigit():
                player_id = int(key.replace("team_", ""))
                team = value if value in ("A", "B") else None
                execute(
                    """
                    update match_players
                    set team = ?, response = case when ? is not null then 'present' else response end
                    where match_id = ? and player_id = ?
                    """,
                    (team, team, match_id, player_id),
                )
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/awards", methods=["POST"])
@require_admin
def add_award_type():
    name = request.form.get("name", "").strip()
    if name:
        execute(
            """
            insert into award_types (name, description)
            values (?, ?)
            on conflict(name) do update set description = excluded.description, active = 1
            """,
            (name, request.form.get("description", "").strip()),
        )
    next_url = request.form.get("next") or url_for("admin_dashboard")
    return redirect(next_url)


@app.route("/matches/<int:match_id>/awards", methods=["POST"])
@require_admin
def save_match_awards(match_id):
    award_type_id = int(request.form.get("award_type_id", 0) or 0)
    player_id = int(request.form.get("player_id", 0) or 0)
    if award_type_id and player_id:
        save_award_assignment(match_id, award_type_id, player_id, request.form.get("note", ""))
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/awards/<int:award_id>/delete", methods=["POST"])
@require_admin
def delete_match_award(match_id, award_id):
    award = query(
        """
        select ma.*, at.name as award_name
        from match_awards ma
        join award_types at on at.id = ma.award_type_id
        where ma.id = ? and ma.match_id = ?
        """,
        (award_id, match_id),
        one=True,
    )
    if award and (award["award_name"] or "").lower().startswith("mvp"):
        execute("update players set score = max(0, score - 3) where id = ?", (award["player_id"],))
    execute("delete from match_awards where id = ? and match_id = ?", (award_id, match_id))
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/result", methods=["POST"])
@require_admin
def save_result(match_id):
    match = get_match(match_id)
    if not match or match["status"] == "cancelled":
        return redirect(url_for("match_detail", match_id=match_id))
    first_save = not bool(match["result_processed"])
    team_a_score = int(request.form.get("team_a_score", 0))
    team_b_score = int(request.form.get("team_b_score", 0))
    execute(
        "update matches set team_a_score = ?, team_b_score = ?, status = 'closed', result_processed = 1 where id = ?",
        (team_a_score, team_b_score, match_id),
    )

    rows = query(
        """
        select player_id, team, goals, assists, points_awarded, win_awarded, power_bonus_awarded
        from match_players
        where match_id = ? and (team is not null or response in ('confirmed', 'present'))
        """,
        (match_id,),
    )
    for row in rows:
        goals = int(request.form.get(f"goals_{row['player_id']}", 0) or 0)
        assists = int(request.form.get(f"assists_{row['player_id']}", 0) or 0)
        rating_raw = request.form.get(f"rating_{row['player_id']}", "")
        rating = float(rating_raw) if rating_raw else None
        review = request.form.get(f"review_{row['player_id']}", "").strip()
        won = (row["team"] == "A" and team_a_score > team_b_score) or (row["team"] == "B" and team_b_score > team_a_score)
        win_value = 1 if won else 0
        points = 3 if won else 1 if row["team"] and team_a_score == team_b_score else 0
        points += goals * 2 + assists
        power_bonus = 0.5 if points >= 5 else 0
        execute(
            """
            update match_players
            set goals = ?, assists = ?, rating = ?, review = ?,
                points_awarded = ?, win_awarded = ?, power_bonus_awarded = ?
            where match_id = ? and player_id = ?
            """,
            (goals, assists, rating, review, points, win_value, power_bonus, match_id, row["player_id"]),
        )
        award_type_id = int(request.form.get(f"quick_award_{row['player_id']}", 0) or 0)
        award_note = request.form.get(f"quick_award_note_{row['player_id']}", "").strip()
        if award_type_id:
            existing_award = query(
                """
                select id from match_awards
                where match_id = ? and player_id = ? and award_type_id = ?
                limit 1
                """,
                (match_id, row["player_id"], award_type_id),
                one=True,
            )
            if is_mvp_award(award_type_id):
                save_award_assignment(match_id, award_type_id, row["player_id"], award_note)
            elif existing_award:
                execute("update match_awards set note = ? where id = ?", (award_note, existing_award["id"]))
            else:
                save_award_assignment(match_id, award_type_id, row["player_id"], award_note)
        goals_delta = goals - int(row["goals"] or 0)
        assists_delta = assists - int(row["assists"] or 0)
        score_delta = points - int(row["points_awarded"] or 0)
        win_delta = win_value - int(row["win_awarded"] or 0)
        power_delta = power_bonus - power_value(row["power_bonus_awarded"])
        execute(
            """
            update players
            set matches = matches + ?,
                goals = goals + ?,
                assists = assists + ?,
                wins = wins + ?,
                score = max(0, score + ?)
            where id = ?
            """,
            (1 if first_save else 0, goals_delta, assists_delta, win_delta, score_delta, row["player_id"]),
        )
        adjust_player_power(row["player_id"], power_delta)
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/play/<token>/<int:match_id>", methods=["GET", "POST"])
def public_confirm(token, match_id):
    return redirect(url_for("player_login", next=url_for("player_dashboard")))
    player = query("select * from players where invite_token = ?", (token,), one=True)
    match = get_match(match_id)
    if not player or not match:
        return "Invito non valido", 404
    relation = query(
        "select * from match_players where match_id = ? and player_id = ?",
        (match_id, player["id"]),
        one=True,
    )
    if not relation:
        execute("insert into match_players (match_id, player_id, response) values (?, ?, 'invited')", (match_id, player["id"]))
        relation = query("select * from match_players where match_id = ? and player_id = ?", (match_id, player["id"]), one=True)

    if request.method == "POST":
        response = request.form["response"]
        if response == "confirmed" and not has_roster_slot(match_id, player["id"]):
            response = "waitlist"
        execute(
            """
            update match_players
            set response = ?,
                responded_at = case
                    when ? in ('confirmed', 'waitlist') and responded_at is null then current_timestamp
                    else responded_at
                end
            where match_id = ? and player_id = ?
            """,
            (response, response, match_id, player["id"]),
        )
        sync_waitlist(match_id)
        maybe_auto_generate(get_match(match_id))
        return redirect(url_for("public_confirm", token=token, match_id=match_id))
    return render_template("confirm.html", player=player, match=match, relation=relation)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=port)
