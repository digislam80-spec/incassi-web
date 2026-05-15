import itertools
import os
import random
import sqlite3
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, g, redirect, render_template, request, session, url_for
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

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "calcetto-local-demo")
ADMIN_PIN = os.environ.get("CALCETTO_ADMIN_PIN", "1234")

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
    if "db" not in g:
        if USE_POSTGRES:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL impostato, ma psycopg non e installato.")
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
    player_id = session.get("player_id")
    if not player_id:
        return None
    player = query("select * from players where id = ?", (player_id,), one=True)
    if player and player["account_status"] in ("rejected", "removed"):
        session.pop("player_id", None)
        return None
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
                cancelled_at timestamptz,
                responded_at timestamptz,
                penalty_points integer not null default 0,
                primary key(match_id, player_id)
            )
            """
        )
        connection.execute(
            "update matches set title = 'Calcetto del Venerdi' where title = 'Calcetto del Giovedi'"
        )
        connection.execute("alter table players alter column power type numeric(2,1) using power::numeric")
        connection.execute("alter table match_players add column if not exists responded_at timestamptz")
        connection.execute(
            """
            update match_players
            set responded_at = current_timestamp
            where response in ('confirmed', 'present') and responded_at is null
            """
        )
        connection.commit()
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
            created_at text not null default current_timestamp
        );

        create table if not exists match_players (
            match_id integer not null references matches(id) on delete cascade,
            player_id integer not null references players(id) on delete cascade,
            response text not null default 'invited',
            team text,
            goals integer not null default 0,
            assists integer not null default 0,
            cancelled_at text,
            responded_at text,
            penalty_points integer not null default 0,
            primary key(match_id, player_id)
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
    }
    for column, sql in player_migrations.items():
        if column not in columns:
            connection.execute(sql)
    match_player_columns = [row["name"] for row in query("pragma table_info(match_players)")]
    match_player_migrations = {
        "cancelled_at": "alter table match_players add column cancelled_at text",
        "responded_at": "alter table match_players add column responded_at text",
        "penalty_points": "alter table match_players add column penalty_points integer not null default 0",
    }
    for column, sql in match_player_migrations.items():
        if column not in match_player_columns:
            connection.execute(sql)
    connection.execute(
        """
        update match_players
        set responded_at = current_timestamp
        where response in ('confirmed', 'present') and responded_at is null
        """
    )
    connection.execute(
        "update matches set title = 'Calcetto del Venerdi' where title = 'Calcetto del Giovedi'"
    )
    connection.commit()

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


def seed_initial_data():
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
                insert into players (name, nickname, phone, role, power, mascot, username, password_hash, account_status, invite_token)
                values (?, ?, ?, ?, ?, ?, ?, ?, 'approved', ?)
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
            ("Calcetto del Venerdi", next_match.strftime("%Y-%m-%dT20:30"), "Centro Sportivo", 10),
        )
        for player in query("select id from players order by id limit 12"):
            response = "confirmed" if player["id"] <= 10 else "invited"
            execute(
                "insert into match_players (match_id, player_id, response) values (?, ?, ?)",
                (match_id, player["id"], response),
            )


@app.before_request
def ensure_db():
    init_db()


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


def status_label(status):
    labels = {
        "open": "Convocazioni aperte",
        "teams": "Squadre fatte",
        "teams_auto": "Squadre fatte dal mister automatico",
        "closed": "Terzo tempo autorizzato",
    }
    return labels.get(status, status)


def response_label(response):
    labels = {
        "invited": "In attesa di risposta",
        "confirmed": "Ha confermato",
        "present": "Presente in lista",
        "declined": "Non puo giocare",
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


app.jinja_env.filters["player_title"] = player_title
app.jinja_env.filters["status_label"] = status_label
app.jinja_env.filters["response_label"] = response_label
app.jinja_env.filters["account_status_label"] = account_status_label
app.jinja_env.filters["mascot_label"] = mascot_label
app.jinja_env.filters["player_mascot_label"] = player_mascot_label
app.jinja_env.filters["mascot_code"] = mascot_code
app.jinja_env.filters["mascot_class"] = mascot_class


def latest_match():
    return query("select * from matches order by match_date desc, id desc limit 1", one=True)


def get_match(match_id):
    return query("select * from matches where id = ?", (match_id,), one=True)


def invited_players(match_id):
    return query(
        """
        select p.*, mp.response, mp.team, mp.goals as match_goals, mp.assists as match_assists,
               mp.responded_at, mp.cancelled_at, mp.penalty_points
        from players p
        join match_players mp on mp.player_id = p.id
        where mp.match_id = ?
        order by
            case mp.response when 'present' then 1 when 'confirmed' then 2 when 'invited' then 3 else 4 end,
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
    if not match or match["status"] != "open" or not match_day(match):
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
        return "Il pallone e rotondo, le scuse pure."
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
    return "active = 1 and account_status = 'approved'"


RULES = [
    "Si entra in campo per giocare, correre il giusto e lamentarsi con stile: la polemica e ammessa solo se fa ridere.",
    "La conferma vale come stretta di mano: chi clicca Confermo si prende il posto finche non disdice dall'account.",
    "Chi prima conferma, prima partecipa. Se i posti finiscono, il mister puo ripescare solo per emergenza spogliatoio.",
    "La disdetta e libera, ma non gratis: piu e vicina alla partita, piu pesa su score, affidabilita e stelle.",
    "Gol, assist, vittorie e presenza fanno crescere. Il talento sale, ma pure la puntualita conta.",
    "Le stelle sono sacre ma non eterne: il mister assegna la base, poi il campo e le disdette fanno il resto.",
    "Mascotte e soprannomi devono essere goliardici, non offensivi: si ride insieme, non addosso.",
    "Il gruppo WhatsApp serve per il folklore; la verita ufficiale sta dentro FantaCalcetto.",
    "Chi sparisce dopo aver confermato entra nella leggenda, ma dalla porta sbagliata.",
    "Digislam Print Lab veglia sulla lega: rispetto, calcetto e terzo tempo con dignita variabile.",
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


@app.route("/league")
@require_admin
def league_overview():
    match = latest_match()
    maybe_auto_generate(match)
    match = latest_match()
    players = query("select * from players where active = 1 and account_status = 'approved' order by score desc, power desc, name")
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
    players = query("select * from players where active = 1 and account_status = 'approved' order by power desc, score desc, name")
    pending_players = query("select * from players where account_status = 'pending' order by created_at desc")
    matches = query("select * from matches order by match_date desc, id desc limit 8")
    match_players = invited_players(match["id"]) if match else []
    return render_template(
        "dashboard.html",
        match=match,
        players=players,
        matches=matches,
        match_players=match_players,
        pending_players=pending_players,
        match_day=match_day(match) if match else False,
        motto=goliardic_motto(match),
        mascots=MASCOTS,
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("pin") == ADMIN_PIN:
            session["is_admin"] = True
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        error = "PIN sbagliato. Il mister non ti riconosce."
    return render_template("login.html", error=error, match=latest_match())


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.clear()
    return redirect(url_for("dashboard"))


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
        if mascot not in MASCOTS:
            mascot = "jolly"
        accepted_rules = request.form.get("accepted_rules") == "yes"
        if query("select id from players where lower(username) = lower(?)", (username,), one=True):
            error = "Username gia preso: serve un nome da spogliatoio originale."
        elif len(password) < 4:
            error = "Password troppo corta: almeno 4 caratteri, senza fare i fenomeni."
        elif not accepted_rules:
            error = "Prima serve il giuramento da spogliatoio: accetta il regolamento."
        else:
            execute(
                """
                insert into players
                    (name, nickname, phone, username, password_hash, account_status, active, mascot, mascot_name, invite_token)
                values (?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
                """,
                (
                    f"{name} {surname}".strip(),
                    request.form.get("nickname", "").strip(),
                    phone,
                    username,
                    generate_password_hash(password),
                    mascot,
                    request.form.get("mascot_name", "").strip(),
                    uuid.uuid4().hex,
                ),
            )
            return render_template("register_done.html", match=latest_match())
    return render_template("register.html", error=error, mascots=MASCOTS, rules=RULES, match=latest_match())


@app.route("/player/login", methods=["GET", "POST"])
def player_login():
    error = None
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        player = query("select * from players where lower(username) = lower(?)", (username,), one=True)
        if player and player["password_hash"] and check_password_hash(player["password_hash"], request.form["password"]):
            if player["account_status"] in ("rejected", "removed"):
                error = "Account non attivo. Parla col mister prima di entrare nello spogliatoio."
                return render_template("player_login.html", error=error, match=latest_match())
            session["player_id"] = player["id"]
            return redirect(request.args.get("next") or url_for("player_dashboard"))
        error = "Credenziali sbagliate. Riprova senza tunnel."
    return render_template("player_login.html", error=error, match=latest_match())


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
    return render_template("player_dashboard.html", player=player, matches=my_matches, match=match)


@app.route("/player/matches/<int:match_id>/confirm", methods=["POST"])
@require_player
def player_confirm(match_id):
    player = current_player()
    if player["account_status"] != "approved":
        return redirect(url_for("player_dashboard"))
    previous = query(
        "select response from match_players where match_id = ? and player_id = ?",
        (match_id, player["id"]),
        one=True,
    )
    execute(
        """
        insert into match_players (match_id, player_id, response, responded_at)
        values (?, ?, 'confirmed', current_timestamp)
        on conflict(match_id, player_id) do update set
            response = 'confirmed',
            cancelled_at = null,
            penalty_points = 0,
            responded_at = case
                when responded_at is null then current_timestamp
                else responded_at
            end
        """,
        (match_id, player["id"]),
    )
    if not previous or previous["response"] not in ("confirmed", "present"):
        execute(
            """
            update players
            set score = score + 1,
                reliability = min(100, reliability + ?)
            where id = ?
            """,
            (2, player["id"]),
        )
    maybe_auto_generate(get_match(match_id))
    return redirect(url_for("player_dashboard"))


@app.route("/player/matches/<int:match_id>/cancel", methods=["POST"])
@require_player
def player_cancel(match_id):
    player = current_player()
    if player["account_status"] != "approved":
        return redirect(url_for("player_dashboard"))
    match = get_match(match_id)
    if not match:
        return redirect(url_for("player_dashboard"))
    penalty, power_penalty, _message = cancellation_penalty(match)
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
    return redirect(url_for("player_dashboard"))


@app.route("/player/mascot-name", methods=["POST"])
@require_player
def player_update_mascot_name():
    player = current_player()
    execute(
        "update players set mascot_name = ? where id = ?",
        (request.form.get("mascot_name", "").strip(), player["id"]),
    )
    return redirect(url_for("player_dashboard"))


@app.route("/players", methods=["POST"])
@require_admin
def add_player():
    execute(
        """
        insert into players (name, nickname, phone, role, power, mascot, invite_token)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.form["name"].strip(),
            request.form.get("nickname", "").strip(),
            request.form["phone"].strip(),
            request.form.get("role", "Jolly"),
            float(request.form.get("power", 3)),
            request.form.get("mascot", "jolly"),
            uuid.uuid4().hex,
        ),
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>", methods=["POST"])
@require_admin
def update_player(player_id):
    execute(
        """
        update players
        set name = ?, nickname = ?, phone = ?, role = ?, power = ?, reliability = ?, mascot = ?
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
            player_id,
        ),
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
    return redirect(url_for("admin_dashboard"))


@app.route("/players/<int:player_id>/reject", methods=["POST"])
@require_admin
def reject_player(player_id):
    execute("update players set account_status = 'rejected', active = 0 where id = ?", (player_id,))
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
        selected = [str(row["id"]) for row in query("select id from players where active = 1 and account_status = 'approved'")]
    for player_id in selected:
        execute(
            "insert into match_players (match_id, player_id, response) values (?, ?, 'invited')",
            (match_id, int(player_id)),
        )
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>")
@require_admin
def match_detail(match_id):
    match = get_match(match_id)
    auto_generated = maybe_auto_generate(match)
    match = get_match(match_id)
    players = invited_players(match_id)
    all_players = query(
        """
        select p.*
        from players p
        where p.active = 1 and p.account_status = 'approved' and p.id not in (
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
        auto_generated=auto_generated,
        match_day=match_day(match),
        motto=goliardic_motto(match),
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
                        when ? in ('confirmed', 'present') and responded_at is null then current_timestamp
                        when ? = 'declined' then current_timestamp
                        else responded_at
                    end
                where match_id = ? and player_id = ?
                """,
                (value, value, value, match_id, player_id),
            )
    maybe_auto_generate(get_match(match_id))
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/generate", methods=["POST"])
@require_admin
def generate_teams(match_id):
    apply_team_generation(match_id)
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/matches/<int:match_id>/result", methods=["POST"])
@require_admin
def save_result(match_id):
    team_a_score = int(request.form.get("team_a_score", 0))
    team_b_score = int(request.form.get("team_b_score", 0))
    execute(
        "update matches set team_a_score = ?, team_b_score = ?, status = 'closed' where id = ?",
        (team_a_score, team_b_score, match_id),
    )

    rows = query("select player_id, team from match_players where match_id = ? and team is not null", (match_id,))
    for row in rows:
        goals = int(request.form.get(f"goals_{row['player_id']}", 0) or 0)
        assists = int(request.form.get(f"assists_{row['player_id']}", 0) or 0)
        won = (row["team"] == "A" and team_a_score > team_b_score) or (row["team"] == "B" and team_b_score > team_a_score)
        points = 3 if won else 1 if team_a_score == team_b_score else 0
        points += goals * 2 + assists
        power_bonus = 0.5 if points >= 5 else 0
        execute(
            "update match_players set goals = ?, assists = ? where match_id = ? and player_id = ?",
            (goals, assists, match_id, row["player_id"]),
        )
        execute(
            """
            update players
            set matches = matches + 1,
                goals = goals + ?,
                assists = assists + ?,
                wins = wins + ?,
                score = score + ?
            where id = ?
            """,
            (goals, assists, 1 if won else 0, points, row["player_id"]),
        )
        adjust_player_power(row["player_id"], power_bonus)
    return redirect(url_for("match_detail", match_id=match_id))


@app.route("/play/<token>/<int:match_id>", methods=["GET", "POST"])
def public_confirm(token, match_id):
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
        execute(
            "update match_players set response = ? where match_id = ? and player_id = ?",
            (response, match_id, player["id"]),
        )
        maybe_auto_generate(get_match(match_id))
        return redirect(url_for("public_confirm", token=token, match_id=match_id))
    return render_template("confirm.html", player=player, match=match, relation=relation)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=port)
