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
    "players",
    "matches",
    "match_players",
    "award_types",
    "match_awards",
    "password_reset_requests",
    "league_events",
    "league_event_comments",
    "match_comments",
]

APP_UPDATES = [
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
        "title": "Backup, import e squadre manuali",
        "body": "L'admin può salvare i dati, reimportarli e correggere a mano le squadre generate.",
        "tag": "Admin",
    },
]

TEAM_NAMES = [
    ("Real Madrink", "Atletico Ma Non Troppo"),
    ("AC Tua", "Dinamo Spritz"),
    ("Boca Senior", "Paris San Gennar"),
    ("Lokomotiv Arrosto", "Sporting Aperitivo"),
    ("Scapoli FC", "Ammogliati United"),
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


def is_player_logged_in():
    return current_player() is not None


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
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
    return {"is_admin": is_admin(), "current_player": current_player()}


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.exception("Errore non gestito su %s", request.path)
    return render_template("error.html", error=error), 500


def init_db():
    connection = db()
    if USE_POSTGRES:
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
                role text not null default 'Jolly',
                preferred_foot text not null default 'right',
                mascot text not null default 'jolly',
                mascot_name text default '',
                power numeric(2,1) not null default 3 check(power between 1 and 5),
                score integer not null default 0,
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
            create table if not exists matches (
                id integer generated by default as identity primary key,
                title text not null,
                match_date text not null,
                location text not null,
                player_limit integer not null default 10,
                status text not null default 'open',
                team_a_name text default 'Squadra A',
                team_b_name text default 'Squadra B',
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
                actor_player_id integer references players(id) on delete set null,
                event_type text not null default 'news',
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
        connection.execute("alter table players alter column power type numeric(2,1) using power::numeric")
        connection.execute("alter table players add column if not exists preferred_foot text not null default 'right'")
        connection.execute("alter table players add column if not exists is_guest integer not null default 0")
        connection.execute("alter table matches add column if not exists result_processed integer not null default 0")
        connection.execute("alter table match_players add column if not exists responded_at timestamptz")
        connection.execute("alter table match_players add column if not exists rating numeric(3,1)")
        connection.execute("alter table match_players add column if not exists review text default ''")
        connection.execute("alter table match_players add column if not exists points_awarded integer not null default 0")
        connection.execute("alter table match_players add column if not exists win_awarded integer not null default 0")
        connection.execute("alter table match_players add column if not exists power_bonus_awarded numeric(2,1) not null default 0")
        connection.execute("alter table password_reset_requests add column if not exists temp_password_set integer not null default 0")
        connection.execute(
            """
            update match_players
            set responded_at = current_timestamp
            where response in ('confirmed', 'present') and responded_at is null
            """
        )
        connection.commit()
        seed_award_types()
        seed_initial_data()
        return

    connection.executescript(
        """
        create table if not exists players (
            id integer primary key autoincrement,
            name text not null,
            nickname text default '',
            phone text not null,
            username text default '',
            password_hash text default '',
            account_status text not null default 'approved',
            role text not null default 'Jolly',
            preferred_foot text not null default 'right',
            mascot text not null default 'jolly',
            mascot_name text default '',
            power numeric not null default 3 check(power between 1 and 5),
            score integer not null default 0,
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

        create table if not exists matches (
            id integer primary key autoincrement,
            title text not null,
            match_date text not null,
            location text not null,
            player_limit integer not null default 10,
            status text not null default 'open',
            team_a_name text default 'Squadra A',
            team_b_name text default 'Squadra B',
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
            actor_player_id integer references players(id) on delete set null,
            event_type text not null default 'news',
            title text not null,
            body text default '',
            visibility text not null default 'all',
            created_at text not null default current_timestamp
        );

        create table if not exists league_event_comments (
            id integer primary key autoincrement,
            event_id integer not null references league_events(id) on delete cascade,
            player_id integer references players(id) on delete set null,
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
    if "result_processed" not in match_columns:
        connection.execute("alter table matches add column result_processed integer not null default 0")
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
    seed_award_types()

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
        "matches",
        "password_reset_requests",
        "league_event_comments",
        "league_events",
        "players",
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
        for table in ("players", "matches", "award_types", "match_awards", "password_reset_requests", "league_events", "league_event_comments", "match_comments"):
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
        for table in ("players", "matches", "award_types", "match_awards", "password_reset_requests", "league_events", "league_event_comments", "match_comments"):
            connection.execute("delete from sqlite_sequence where name = ?", (table,))


def import_payload(payload):
    tables = payload.get("tables", {})
    connection = db()
    clear_data_tables(connection, include_award_types=True)
    for table in ("players", "matches", "award_types", "match_players", "match_awards", "password_reset_requests", "league_events", "league_event_comments", "match_comments"):
        insert_backup_rows(connection, table, tables.get(table, []))
    reset_identity_sequences(connection)
    connection.commit()
    seed_award_types()


def log_league_event(title, body="", event_type="news", actor_player_id=None, visibility="all"):
    try:
        execute(
            """
            insert into league_events (actor_player_id, event_type, title, body, visibility)
            values (?, ?, ?, ?, ?)
            """,
            (actor_player_id, event_type, title, body, visibility),
        )
    except Exception:
        app.logger.exception("Errore durante scrittura evento lega")


def recent_league_events(limit=10, include_admin=False):
    visibility_filter = "" if include_admin else "where le.visibility in ('all', 'players')"
    return query(
        f"""
        select le.*, p.name as actor_name
        from league_events le
        left join players p on p.id = le.actor_player_id
        {visibility_filter}
        order by le.created_at desc, le.id desc
        limit ?
        """,
        (limit,),
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
    base = 35 + (power - 1) * 10
    form = min(18, score * 0.45)
    trust = (reliability - 50) * 0.18
    production = min(12, goals * 1.2 + assists * 0.8 + wins * 1.5 + matches * 0.3)
    return max(1, min(100, round(base + form + trust + production)))


app.jinja_env.filters["player_title"] = player_title
app.jinja_env.filters["foot_label"] = foot_label
app.jinja_env.filters["status_label"] = status_label
app.jinja_env.filters["response_label"] = response_label
app.jinja_env.filters["account_status_label"] = account_status_label
app.jinja_env.filters["mascot_label"] = mascot_label
app.jinja_env.filters["player_mascot_label"] = player_mascot_label
app.jinja_env.filters["mascot_code"] = mascot_code
app.jinja_env.filters["mascot_class"] = mascot_class
app.jinja_env.filters["overall_rating"] = overall_rating


def latest_match():
    return query("select * from matches order by match_date desc, id desc limit 1", one=True)


def get_match(match_id):
    return query("select * from matches where id = ?", (match_id,), one=True)


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


def match_summary_counts(players):
    return {
        "confirmed": sum(1 for player in players if player["response"] in ("confirmed", "present")),
        "waitlist": sum(1 for player in players if player["response"] == "waitlist"),
        "declined": sum(1 for player in players if player["response"] == "declined"),
        "invited": sum(1 for player in players if player["response"] == "invited"),
    }


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


def approved_players_sql():
    return "active = 1 and account_status = 'approved' and coalesce(is_guest, 0) = 0"


RULES = [
    "Si entra in campo per giocare, correre il giusto e lamentarsi con stile: la polemica è ammessa solo se fa ridere.",
    "La conferma vale come stretta di mano: chi clicca Confermo si prende il posto finché non disdice dall'account.",
    "Chi prima conferma, prima partecipa. Dal posto numero 11 scatta la lista d'attesa: pettorina in mano e speranza nel cuore.",
    "Il calciatore è tenuto a controllare la propria scheda evento: orario, campo, conferma o annullamento vivono lì dentro.",
    "La disdetta è libera, ma non gratis: più è vicina alla partita, più pesa su score, affidabilità e stelle.",
    "Gol, assist, vittorie e presenza fanno crescere. Il talento sale, ma pure la puntualità conta.",
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
    return redirect(url_for("player_login", next=request.path))


@app.route("/rules")
def rules():
    if not is_admin() and not current_player():
        return redirect(url_for("player_login", next=request.path))
    return render_template("rules.html", rules=RULES, match=latest_match())


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
    players = query(f"select * from players where {approved_players_sql()} order by score desc, power desc, name")
    matches = query("select * from matches order by match_date desc, id desc limit 6")
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
    match = latest_match()
    maybe_auto_generate(match)
    match = latest_match()
    players = query(f"select * from players where {approved_players_sql()} order by power desc, score desc, name")
    pending_players = query("select * from players where account_status = 'pending' order by created_at desc")
    rejected_players = query("select * from players where account_status in ('rejected', 'removed') order by created_at desc limit 20")
    reset_requests = query(
        """
        select pr.*, p.name as player_name, p.username as player_username
        from password_reset_requests pr
        left join players p on p.id = pr.player_id
        where pr.status = 'pending'
        order by pr.created_at desc
        """
    )
    matches = query("select * from matches order by match_date desc, id desc limit 8")
    match_players = invited_players(match["id"]) if match else []
    news_items = recent_league_events(12, include_admin=True)
    news_comments = comments_for_events(news_items)
    return render_template(
        "dashboard.html",
        match=match,
        players=players,
        matches=matches,
        match_players=match_players,
        pending_players=pending_players,
        rejected_players=rejected_players,
        reset_requests=reset_requests,
        news_items=news_items,
        news_comments=news_comments,
        app_updates=APP_UPDATES,
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
    if request.form.get("confirm_text", "").strip().upper() != "RESET":
        return redirect(url_for("admin_dashboard"))
    connection = db()
    clear_data_tables(connection)
    reset_identity_sequences(connection)
    connection.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register_player():
    error = None
    if request.method == "POST":
        name = request.form["name"].strip()
        surname = request.form.get("surname", "").strip()
        username = request.form["username"].strip().lower()
        phone = request.form["phone"].strip()
        password = request.form["password"]
        mascot = request.form.get("mascot", "jolly")
        preferred_foot = request.form.get("preferred_foot", "right")
        if mascot not in MASCOTS:
            mascot = "jolly"
        if preferred_foot not in FOOT_LABELS:
            preferred_foot = "right"
        accepted_rules = request.form.get("accepted_rules") == "yes"
        if query("select id from players where lower(username) = lower(?)", (username,), one=True):
            error = "Username già preso: serve un nome da spogliatoio originale."
        elif len(password) < 4:
            error = "Password troppo corta: almeno 4 caratteri, senza fare i fenomeni."
        elif not accepted_rules:
            error = "Prima serve il giuramento da spogliatoio: accetta il regolamento."
        else:
            execute(
                """
                insert into players
                    (name, nickname, phone, username, password_hash, account_status, active, mascot, mascot_name, preferred_foot, invite_token)
                values (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
                """,
                (
                    f"{name} {surname}".strip(),
                    request.form.get("nickname", "").strip(),
                    phone,
                    username,
                    generate_password_hash(password),
                    mascot,
                    request.form.get("mascot_name", "").strip(),
                    preferred_foot,
                    uuid.uuid4().hex,
                ),
            )
            log_league_event(
                "Nuova richiesta di iscrizione",
                f"{f'{name} {surname}'.strip()} ha bussato allo spogliatoio e aspetta l'approvazione del mister.",
                "registration",
            )
            return render_template("register_done.html")
    return render_template(
        "register.html",
        error=error,
        mascots=MASCOTS,
        foot_labels=FOOT_LABELS,
        rules=RULES,
    )


@app.route("/player/login", methods=["GET", "POST"])
def player_login():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        player = query("select * from players where lower(username) = lower(?)", (username,), one=True)
        if player and player["password_hash"] and check_password_hash(player["password_hash"], request.form["password"]):
            if player["account_status"] in ("rejected", "removed"):
                error = "Account non attivo. Parla col mister prima di entrare nello spogliatoio."
                return render_template("player_login.html", error=error)
            session["player_id"] = player["id"]
            return redirect(request.args.get("next") or url_for("player_dashboard"))
        error = "Credenziali sbagliate. Riprova senza tunnel."
    return render_template("player_login.html", error=error)


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
    match = latest_match()
    if match:
        maybe_auto_generate(match)
        match = latest_match()
    my_matches = query(
        """
        select m.*, mp.response, mp.team, mp.goals as match_goals, mp.assists as match_assists,
               mp.cancelled_at, mp.responded_at, mp.penalty_points
        from matches m
        left join match_players mp on mp.match_id = m.id and mp.player_id = ?
        where m.match_date >= datetime('now', '-1 day')
        order by m.match_date asc
        limit 6
        """,
        (player["id"],),
    )
    my_waitlist_positions = {}
    for my_match in my_matches:
        if my_match["response"] == "waitlist":
            my_waitlist_positions[my_match["id"]] = waitlist_positions(my_match["id"]).get(player["id"])
    news_items = recent_league_events(8)
    return render_template(
        "player_dashboard.html",
        player=player,
        matches=my_matches,
        match=match,
        waitlist_positions=my_waitlist_positions,
        foot_labels=FOOT_LABELS,
        notice=request.args.get("notice", ""),
        news_items=news_items,
        news_comments=comments_for_events(news_items),
        match_comments=comments_for_matches(my_matches),
        app_updates=APP_UPDATES[:3],
        mascots=MASCOTS,
    )


def match_is_locked(match):
    return not match or match["status"] in ("closed", "cancelled")


@app.route("/player/matches/<int:match_id>/confirm", methods=["POST"])
@require_player
def player_confirm(match_id):
    player = current_player()
    if player["account_status"] != "approved":
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
    if player["account_status"] != "approved":
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
        execute(
            """
            insert into league_event_comments (event_id, player_id, body)
            values (?, ?, ?)
            """,
            (event_id, player["id"], body[:400]),
        )
    return redirect(url_for("player_dashboard", notice="Commento alla news pubblicato."))


@app.route("/player/profile", methods=["POST"])
@require_player
def player_update_profile():
    player = current_player()
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
    preferred_foot = request.form.get("preferred_foot", "right")
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    player_id = execute(
        """
        insert into players (name, nickname, phone, role, power, mascot, preferred_foot, invite_token)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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
        "Giocatore aggiunto dal mister",
        f"{request.form['name'].strip()} entra nella rosa arruolabili dalla porta admin.",
        "admin",
        player_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>", methods=["POST"])
@require_admin
def update_player(player_id):
    old_player = query("select * from players where id = ?", (player_id,), one=True)
    preferred_foot = request.form.get("preferred_foot", "right")
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    execute(
        """
        update players
        set name = ?, nickname = ?, phone = ?, role = ?, power = ?, reliability = ?, mascot = ?, mascot_name = ?, preferred_foot = ?
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
            player_id,
        ),
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
        f"{request.form['name'].strip()} aggiornato dal mister. {', '.join(changes) if changes else 'Piccoli ritocchi da spogliatoio.'}",
        "admin",
        player_id,
    )
    return redirect(url_for("admin_dashboard"))


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
    execute("update players set account_status = 'approved', active = 1 where id = ?", (player_id,))
    player = query("select name from players where id = ?", (player_id,), one=True)
    log_league_event(
        "Calciatore approvato",
        f"{player['name'] if player else 'Un nuovo calciatore'} è ufficialmente arruolabile. Si scaldi la panchina.",
        "approval",
        player_id,
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/reject", methods=["POST"])
@require_admin
def reject_player(player_id):
    execute("update players set account_status = 'rejected', active = 0 where id = ?", (player_id,))
    player = query("select name from players where id = ?", (player_id,), one=True)
    log_league_event(
        "Richiesta respinta",
        f"{player['name'] if player else 'Una richiesta'} è stata respinta dal mister.",
        "admin",
        player_id,
        "admin",
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/remove", methods=["POST"])
@require_admin
def remove_player(player_id):
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
    match_id = execute(
        """
        insert into matches (title, match_date, location, player_limit)
        values (?, ?, ?, ?)
        """,
        (
            request.form["title"].strip(),
            request.form["match_date"],
            request.form["location"].strip(),
            int(request.form.get("player_limit", 10)),
        ),
    )
    selected = request.form.getlist("player_ids")
    if not selected:
        selected = [str(row["id"]) for row in query(f"select id from players where {approved_players_sql()}")]
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
        where p.active = 1 and p.account_status = 'approved' and coalesce(p.is_guest, 0) = 0 and p.id not in (
            select player_id from match_players where match_id = ?
        )
        order by p.name
        """,
        (match_id,),
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
        motto=goliardic_motto(match),
        confirmed_count=confirmed_count(match_id),
        mascots=MASCOTS,
        foot_labels=FOOT_LABELS,
        notice=request.args.get("notice", ""),
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
    execute("update matches set status = 'cancelled' where id = ?", (match_id,))
    execute("update match_players set team = null where match_id = ?", (match_id,))
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/external", methods=["POST"])
@require_admin
def add_external_player(match_id):
    name = request.form["name"].strip()
    if not name:
        return redirect(url_for("match_detail", match_id=match_id))
    preferred_foot = request.form.get("preferred_foot", "right")
    if preferred_foot not in FOOT_LABELS:
        preferred_foot = "right"
    player_id = execute(
        """
        insert into players (name, nickname, phone, role, power, mascot, mascot_name, preferred_foot, invite_token, account_status, active, is_guest)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'approved', 1, 1)
        """,
        (
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
            set team_a_name = ?, team_b_name = ?
            where id = ?
            """,
            (
                request.form.get("team_a_name", "Squadra A").strip() or "Squadra A",
                request.form.get("team_b_name", "Squadra B").strip() or "Squadra B",
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
        execute(
            """
            insert into match_awards (match_id, award_type_id, player_id, note)
            values (?, ?, ?, ?)
            """,
            (match_id, award_type_id, player_id, request.form.get("note", "").strip()),
        )
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/awards/<int:award_id>/delete", methods=["POST"])
@require_admin
def delete_match_award(match_id, award_id):
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
            if existing_award:
                execute("update match_awards set note = ? where id = ?", (award_note, existing_award["id"]))
            else:
                execute(
                    """
                    insert into match_awards (match_id, award_type_id, player_id, note)
                    values (?, ?, ?, ?)
                    """,
                    (match_id, award_type_id, row["player_id"], award_note),
                )
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
