
import base64
import os
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CONFIG_PATH = Path.home() / ".notion_to_intervals_v3.json"
NOTION_VERSION = "2022-06-28"

SPORT_MAP = {
    "Course": "Run",
    "Course à pied": "Run",
    "Running": "Run",
    "Run": "Run",
    "CAP": "Run",
    "Vélo": "Ride",
    "Velo": "Ride",
    "Bike": "Ride",
    "Cyclisme": "Ride",
    "Home trainer": "Ride",
    "HT": "Ride",
    "Natation": "Swim",
    "Swim": "Swim",
    "Piscine": "Swim",
}

DEFAULT_DATABASE_ID = "3879cd904ec380a6bb8dd05772b2a25f"

PROPERTY_DATE = "Date planifiée/réalisée"
PROPERTY_SPORT = "Sport"
PROPERTY_NAME = "Séance"
PROPERTY_DETAILS = "Détails séance"
PROPERTY_SYNC = "Sync Intervals"
PROPERTY_STATUS = "Status"
PROPERTY_ID = "ID Séance"

STATUS_SYNC = "Sync"

SECTION_ALIASES = {
    "échauffement": "Warmup",
    "echauffement": "Warmup",
    "warmup": "Warmup",
    "corps de séance": "Main Set",
    "corps de seance": "Main Set",
    "main set": "Main Set",
    "séance": "Main Set",
    "seance": "Main Set",
    "retour au calme": "Cooldown",
    "cooldown": "Cooldown",
    "option vélo": "Main Set",
    "option velo": "Main Set",
    "vélo": "Main Set",
    "velo": "Main Set",
    "séance simple": "Main Set",
    "seance simple": "Main Set",
    "récupération active vélo": "Main Set",
    "recuperation active velo": "Main Set",
    "retour au calme vélo": "Cooldown",
    "retour au calme velo": "Cooldown",
    "échauffement avant course": "Warmup",
    "echauffement avant course": "Warmup",
    "course": "Main Set",
    "récupération": "Recovery",
    "recuperation": "Recovery",
}

def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_config(database_id):
    CONFIG_PATH.write_text(json.dumps({"database_id": database_id}, indent=2), encoding="utf-8")

def http_json(method, url, headers=None, payload=None, timeout=45):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body:
                return resp.status, None
            return resp.status, json.loads(body)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}\n{body}") from e
    except URLError as e:
        raise RuntimeError(f"Erreur réseau : {e}") from e

def notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

def intervals_headers(api_key):
    auth = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 NotionToIntervalsV3.1/1.0",
    }

def get_plain_text(prop):
    if not prop:
        return ""
    t = prop.get("type")
    if t == "title":
        return "".join(x.get("plain_text", "") for x in prop.get("title", []))
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in prop.get("rich_text", []))
    if t == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    if t == "status":
        st = prop.get("status")
        return st.get("name", "") if st else ""
    if t == "date":
        d = prop.get("date")
        return d.get("start", "") if d else ""
    if t == "checkbox":
        return "true" if prop.get("checkbox") else "false"
    if t == "number":
        v = prop.get("number")
        return "" if v is None else str(v)
    if t == "unique_id":
        uid = prop.get("unique_id") or {}
        prefix = uid.get("prefix") or ""
        number = uid.get("number")
        return f"{prefix}-{number}" if prefix and number is not None else (str(number) if number is not None else "")
    if t == "formula":
        formula = prop.get("formula", {})
        ft = formula.get("type")
        value = formula.get(ft, "")
        if ft == "string":
            return value or ""
        if ft == "number":
            return "" if value is None else str(value)
        if ft == "date":
            return (value or {}).get("start", "") if value else ""
        if ft == "boolean":
            return "true" if value else "false"
        return str(value or "")
    return ""

def get_date(prop):
    if not prop or prop.get("type") != "date" or not prop.get("date"):
        return ""
    return prop["date"].get("start", "")[:10]

def get_prop(props, *names):
    for name in names:
        if name in props:
            return props.get(name)
    return None

def query_notion_pages(token, database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    payload = {
        "filter": {
            "and": [
                {"property": PROPERTY_SYNC, "checkbox": {"equals": True}},
                {"property": PROPERTY_STATUS, "status": {"equals": "To do"}},
            ]
        },
        "page_size": 50
    }
    pages = []
    while True:
        _, res = http_json("POST", url, headers=notion_headers(token), payload=payload)
        pages.extend(res.get("results", []))
        if not res.get("has_more"):
            break
        payload["start_cursor"] = res.get("next_cursor")
    return pages

def update_notion_status(token, page_id, status_name):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": {PROPERTY_STATUS: {"status": {"name": status_name}}}}
    return http_json("PATCH", url, headers=notion_headers(token), payload=payload)

def normalize_text(s):
    s = s.replace("’", "'").replace("′", "'").replace("“", '"').replace("”", '"')
    s = s.replace("×", "x").replace("–", "-").replace("—", "-")
    return s

def normalize_pace(pace):
    pace = pace.strip().replace("/km", "")

    # Format court : 5' signifie 5:00/km.
    m = re.fullmatch(r"(\d+)['’]", pace)
    if m:
        return f"{int(m.group(1))}:00"

    pace = pace.replace("'", ":").replace("’", ":")
    m = re.fullmatch(r"(\d+):(\d{1,2})", pace)
    if not m:
        return pace
    return f"{int(m.group(1))}:{int(m.group(2)):02d}"

def normalize_duration(value, unit):
    value = value.strip()
    unit = unit.lower()
    if unit in ["'", "min", "m"]:
        return f"{value}m"
    if unit in ['"', "s"]:
        return f"{value}s"
    if unit == "h":
        return f"{value}h"
    return f"{value}{unit}"


def normalize_duration_expression(raw):
    """
    Convertit les durées humaines simples en syntaxe Intervals.
    Exemples :
    - 1h -> 1h
    - 1h05 -> 65m
    - 1h05min -> 65m
    - 45min -> 45m
    - 50' -> 50m
    """
    value = normalize_text(raw).strip().lower().replace(" ", "")

    m = re.fullmatch(r"(?P<h>\d+)h(?P<m>\d{1,2})?(?:min|m)?", value)
    if m:
        hours = int(m.group("h"))
        minutes = int(m.group("m") or 0)
        if minutes:
            return f"{hours * 60 + minutes}m"
        return f"{hours}h"

    m = re.fullmatch(r"(?P<n>\d+)(?P<u>'|min|m|s|\")", value)
    if m:
        return normalize_duration(m.group("n"), m.group("u"))

    raise ValueError(f"Durée non reconnue : {raw}")

def detect_section(line):
    raw = line.strip().lstrip("#").strip().lower()
    return SECTION_ALIASES.get(raw)


def split_sections(details):
    """Découpe les vraies sections d'entraînement et exclut les métadonnées de tête."""
    details = normalize_text(details)
    sections = []
    current_name = None
    current_lines = []
    started_training = False
    skip = False

    excluded_headings = {
        "volume", "main set", "mainset", "résumé", "resume",
        "synthèse", "synthese", "objectif"
    }

    def flush():
        nonlocal current_lines
        if current_name and current_lines and not skip:
            sections.append((current_name, current_lines))
        current_lines = []

    for raw in details.splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            section = detect_section(line)

            if section:
                flush()
                current_name = section
                current_lines = []
                skip = False
                started_training = True
                continue

            if not started_training and heading in excluded_headings:
                flush()
                current_name = None
                skip = True
                continue

            if not started_training:
                flush()
                current_name = None
                skip = True
            continue

        if skip and not started_training:
            continue

        line = re.sub(r"^[•\-]\s*", "", line).strip()
        if not line:
            continue

        # Exclut les synthèses de volume placées en tête.
        if re.match(r"^\d+\s*(?:'|min|h)\s*/", line, flags=re.I):
            continue
        if re.search(r"\b\d+\s*(?:à|-)\s*\d+\s*km\b", line, flags=re.I) and "/" in line:
            continue

        if current_name is None:
            current_name = "Main Set"
            started_training = True
            skip = False

        current_lines.append(line)

    flush()
    return sections

def compile_running_line(line):
    line = normalize_text(line).strip()

    duration_expr = r"(?:\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"

    # 0) Séance simple : durée + zone d'allure, ex. 1h Z2 ou 45min Z1-Z2
    m = re.fullmatch(
        rf"(?P<dur>{duration_expr})\s+(?P<zone>Z[1-7](?:\s*-\s*Z[1-7])?)\s*(?:Pace|allure)?",
        line,
        flags=re.I,
    )
    if m:
        zone = re.sub(r"\s+", "", m.group("zone").upper())
        return {"steps": [f"- {normalize_duration_expression(m.group('dur'))} {zone} Pace"]}

    # 1) Répétition temps + plage d'allure + récupération
    m = re.search(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?(?:à|a|@)\s*(?P<p1>\d[':]\d{1,2})\s*-\s*(?P<p2>\d[':]\d{1,2})"
        r".*?(?:récupération|recuperation|r=|r)\s*(?P<rec>\d+)\s*(?P<recunit>'|min|m|s|\")",
        line, flags=re.I
    )
    if m:
        return {
            "repeat": int(m.group("count")),
            "steps": [
                f"- {normalize_duration(m.group('dur'), m.group('unit'))} {normalize_pace(m.group('p1'))}-{normalize_pace(m.group('p2'))} Pace",
                f"- {normalize_duration(m.group('rec'), m.group('recunit'))}"
            ]
        }

    # 2) Durée (y compris 1h / 1h05) + plage d'allure
    m = re.search(
        rf"(?P<dur>{duration_expr})"
        r".*?(?:à|a|@)\s*(?P<p1>\d[':]\d{1,2})\s*-\s*(?P<p2>\d[':]\d{1,2})(?:\s*/?\s*km)?",
        line, flags=re.I
    )
    if m:
        return {"steps": [
            f"- {normalize_duration_expression(m.group('dur'))} "
            f"{normalize_pace(m.group('p1'))}-{normalize_pace(m.group('p2'))} Pace"
        ]}

    # 3) Distance + plage d'allure
    m = re.search(
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>km|m)"
        r".*?(?:à|a|@)\s*(?P<p1>\d[':]\d{1,2})\s*-\s*(?P<p2>\d[':]\d{1,2})",
        line, flags=re.I
    )
    if m:
        dist = m.group("dist").replace(",", ".")
        return {"steps": [
            f"- {dist}{m.group('unit').lower()} "
            f"{normalize_pace(m.group('p1'))}-{normalize_pace(m.group('p2'))} Pace"
        ]}

    # 4) Durée + allure unique
    m = re.search(
        rf"(?P<dur>{duration_expr})"
        r".*?(?:à|a|@)\s*(?P<pace>\d+(?:[':]\d{1,2}|['’]))(?:\s*/?\s*km)?",
        line, flags=re.I
    )
    if m:
        return {"steps": [
            f"- {normalize_duration_expression(m.group('dur'))} {normalize_pace(m.group('pace'))} Pace"
        ]}

    # 5) Distance + allure unique
    m = re.search(
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>km|m)"
        r".*?(?:à|a|@)\s*(?P<pace>\d+(?:[':]\d{1,2}|['’]))",
        line, flags=re.I
    )
    if m:
        dist = format_distance_for_intervals(m.group("dist"), m.group("unit"))
        return {"steps": [f"- {dist} {normalize_pace(m.group('pace'))} Pace"]}

    # 6) Distance + zone d'allure, ex. 10km Z2
    m = re.fullmatch(
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>km|m)\s+(?P<zone>Z[1-7](?:\s*-\s*Z[1-7])?)",
        line,
        flags=re.I,
    )
    if m:
        dist = m.group("dist").replace(",", ".")
        zone = re.sub(r"\s+", "", m.group("zone").upper())
        return {"steps": [f"- {dist}{m.group('unit').lower()} {zone} Pace"]}

    # 7) Répétition simple + récupération
    m = re.search(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?(?:récupération|recuperation|r=|r)\s*(?P<rec>\d+)\s*(?P<recunit>'|min|m|s|\")",
        line, flags=re.I
    )
    if m:
        return {
            "repeat": int(m.group("count")),
            "steps": [
                f"- {normalize_duration(m.group('dur'), m.group('unit'))}",
                f"- {normalize_duration(m.group('rec'), m.group('recunit'))}"
            ]
        }

    # 8) Durée variable réelle
    m = re.search(
        r"(?P<d1>\d+)\s+(?:à|a|-)\s+(?P<d2>\d+)\s*(?P<unit>'|min|m)\b",
        line, flags=re.I
    )
    if m:
        return {
            "steps": [f"- {normalize_duration(m.group('d2'), m.group('unit'))}"],
            "warning": f"Durée variable détectée « {m.group('d1')} à {m.group('d2')} » : borne haute utilisée."
        }

    # 9) Durée simple : 1h, 1h05, 45min, 50'
    m = re.fullmatch(rf"(?P<dur>{duration_expr})(?:\s+(?:facile|libre|souple|endurance fondamentale|EF))?", line, flags=re.I)
    if m:
        return {"steps": [f"- {normalize_duration_expression(m.group('dur'))}"]}

    # 10) Distance simple
    m = re.fullmatch(r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>km|m)(?:\s+(?:facile|libre|souple))?", line, flags=re.I)
    if m:
        dist = format_distance_for_intervals(m.group("dist"), m.group("unit"))
        return {"steps": [f"- {dist}"]}

    return {"error": f"Ligne running non comprise : {line}"}


def compile_ride_line(line):
    line = normalize_text(line).strip()

    m = re.search(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?@?\s*(?P<power>\d+)\s*w"
        r".*?(?:récupération|recuperation|r=|r)\s*(?P<rec>\d+)\s*(?P<recunit>'|min|m|s|\")",
        line,
        flags=re.I,
    )
    if m:
        return {
            "repeat": int(m.group("count")),
            "steps": [
                f"- {normalize_duration(m.group('dur'), m.group('unit'))} {m.group('power')}w",
                f"- {normalize_duration(m.group('rec'), m.group('recunit'))}"
            ]
        }

    m = re.search(
        r"(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?(?P<p1>\d+)\s*-\s*(?P<p2>\d+)\s*w",
        line,
        flags=re.I,
    )
    if m:
        return {
            "steps": [
                f"- {normalize_duration(m.group('dur'), m.group('unit'))} {m.group('p1')}-{m.group('p2')}w"
            ]
        }

    m = re.search(
        r"(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?(?P<pct>\d+)\s*%",
        line,
        flags=re.I,
    )
    if m:
        return {
            "steps": [
                f"- {normalize_duration(m.group('dur'), m.group('unit'))} {m.group('pct')}%"
            ]
        }

    m = re.fullmatch(r"(?P<dur>(?:\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\")))(?:\s+(?:Z[1-7]|facile|libre|souple))?", line, flags=re.I)
    if m:
        return {"steps": [f"- {normalize_duration_expression(m.group('dur'))}"]}

    return {"error": f"Ligne vélo non comprise : {line}"}

def compile_swim_line(line):
    line = normalize_text(line).strip()

    m = re.search(
        r"(?P<count>\d+)\s*x\s*(?P<dist>\d+)\s*m"
        r".*?(?:récupération|recuperation|r=|r)\s*(?P<rec>\d+)\s*(?:s|\")",
        line,
        flags=re.I,
    )
    if m:
        return {
            "repeat": int(m.group("count")),
            "steps": [
                f"- {m.group('dist')}m",
                f"- {m.group('rec')}s"
            ]
        }

    m = re.search(r"(?P<dist>\d+)\s*m\b", line, flags=re.I)
    if m:
        return {"steps": [f"- {m.group('dist')}m"]}

    return {"error": f"Ligne natation non comprise : {line}"}

def compile_details(details, intervals_type):
    forced = re.search(r"INTERVALS\s*:\s*(.*)", details, flags=re.I | re.S)
    if forced:
        return forced.group(1).strip(), []

    sections = split_sections(details)
    output = []
    warnings = []

    compiler = compile_running_line
    if intervals_type == "Ride":
        compiler = compile_ride_line
    elif intervals_type == "Swim":
        compiler = compile_swim_line

    for section_name, lines in sections:
        compiled_lines = []

        for line in lines:
            result = compiler(line)

            if result.get("error"):
                warnings.append(result["error"])
                continue

            if result.get("warning"):
                warnings.append(result["warning"])

            if "repeat" in result:
                if compiled_lines:
                    output.append(section_name)
                    output.extend(compiled_lines)
                    compiled_lines = []

                output.append("")
                output.append(f"{result['repeat']}x")
                output.extend(result["steps"])
            else:
                compiled_lines.extend(result.get("steps", []))

        if compiled_lines:
            output.append(section_name)
            output.extend(compiled_lines)

        output.append("")

    while output and not output[-1].strip():
        output.pop()

    if not output:
        raise ValueError("Aucune étape n'a pu être compilée depuis Détails séance.")

    return "\n".join(output), warnings

def estimate_duration_seconds(workout_text):
    total = 0
    repeat = 1

    for line in workout_text.splitlines():
        l = line.strip()
        if not l:
            continue

        m_rep = re.fullmatch(r"(\d+)x", l, flags=re.I)
        if m_rep:
            repeat = int(m_rep.group(1))
            continue

        if not l.startswith("-"):
            repeat = 1
            continue

        m = re.match(r"-\s*(\d+)h", l)
        if m:
            total += int(m.group(1)) * 3600 * repeat
            continue

        m = re.match(r"-\s*(\d+)m(\d+)s", l)
        if m:
            total += (int(m.group(1)) * 60 + int(m.group(2))) * repeat
            continue

        m = re.match(r"-\s*(\d+)m\b", l)
        if m:
            total += int(m.group(1)) * 60 * repeat
            continue

        m = re.match(r"-\s*(\d+)s\b", l)
        if m:
            total += int(m.group(1)) * repeat
            continue

    return total or None

def page_to_event(page):
    props = page.get("properties", {})

    workout_date = get_date(get_prop(props, PROPERTY_DATE, "Date", "Date planifiée"))
    sport_raw = get_plain_text(get_prop(props, PROPERTY_SPORT, "Sport")).strip()
    name = get_plain_text(get_prop(props, PROPERTY_NAME, "Séance", "Seance", "Nom")).strip()
    details = get_plain_text(get_prop(props, PROPERTY_DETAILS, "Détails séance", "Details séance", "Détails", "Details")).strip()
    session_id = get_plain_text(get_prop(props, PROPERTY_ID, "ID séance", "ID Séance", "ID seance", "ID Seance")).strip()

    if not workout_date:
        raise ValueError("Date manquante")
    if not sport_raw:
        raise ValueError("Sport manquant")
    if not name:
        raise ValueError("Séance/Nom manquant")
    if not details:
        raise ValueError("Détails séance manquant")
    if not session_id:
        raise ValueError("ID séance manquant")

    intervals_type = SPORT_MAP.get(sport_raw, SPORT_MAP.get(sport_raw.capitalize()))
    if not intervals_type:
        raise ValueError(f"Sport non reconnu : {sport_raw}")

    description, warnings = compile_details(details, intervals_type)
    moving_time = estimate_duration_seconds(description)

    event = {
        "category": "WORKOUT",
        "start_date_local": f"{workout_date}T00:00:00",
        "name": name,
        "type": intervals_type,
        "description": description,
        "external_id": session_id,
    }
    if moving_time:
        event["moving_time"] = moving_time

    return event, warnings

def post_events_to_intervals(api_key, events):
    url = "https://intervals.icu/api/v1/athlete/0/events/bulk?upsert=true"
    return http_json("POST", url, headers=intervals_headers(api_key), payload=events)





# =========================
# V7 settings and compiler
# =========================

V6_CONFIG_PATH = Path.home() / ".notion_to_intervals_v7.json"

APPDATA_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "WorkoutSync"
CREDENTIALS_FILE = APPDATA_DIR / "credentials.json"

def load_credentials():
    if not CREDENTIALS_FILE.exists():
        return {}
    try:
        return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_credentials(notion_token, intervals_api_key, database_id):
    APPDATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "notion_token": notion_token.strip(),
        "intervals_api_key": intervals_api_key.strip(),
        "database_id": database_id.strip(),
    }
    CREDENTIALS_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

def clear_credentials():
    try:
        CREDENTIALS_FILE.unlink(missing_ok=True)
    except Exception:
        pass

APP_VERSION = "7.4"

DEFAULT_PROFILE = {
    "ftp": 260,
    "ftp_pct_enabled": True,
    "ftp_pct": 3.0,
    "im_power": 190,
    "im_power_pct_enabled": True,
    "im_power_pct": 3.0,
    "ef_pace": "5:20",
    "ef_pace_pct_enabled": True,
    "ef_pace_pct": 5.0,
    "marathon_pace": "4:15",
    "marathon_pace_pct_enabled": True,
    "marathon_pace_pct": 2.0,
    "threshold_pace": "3:55",
    "threshold_pace_pct_enabled": True,
    "threshold_pace_pct": 2.0,
}

def load_v6_config():
    data = {"database_id": DEFAULT_DATABASE_ID, "profile": DEFAULT_PROFILE.copy()}
    if V6_CONFIG_PATH.exists():
        try:
            saved = json.loads(V6_CONFIG_PATH.read_text(encoding="utf-8"))
            data.update({k: v for k, v in saved.items() if k != "profile"})
            profile = DEFAULT_PROFILE.copy()
            profile.update(saved.get("profile", {}))
            data["profile"] = profile
        except Exception:
            pass
    return data

def save_v6_config(database_id, profile):
    V6_CONFIG_PATH.write_text(
        json.dumps(
            {"database_id": database_id, "profile": profile},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

def clean_training_line(line):
    line = normalize_text(line).strip()
    replacements = [
        (r"\bkilom[eè]tres?\b", "km"),
        (r"\bm[eè]tres?\b", "m"),
        (r"\bheures?\b", "h"),
        (r"\bminutes?\b", "min"),
        (r"\bsecondes?\b", "s"),
        (r"\bsecs?\b", "s"),
    ]
    for pattern, replacement in replacements:
        line = re.sub(pattern, replacement, line, flags=re.I)
    line = re.sub(r"\s+", " ", line)
    return re.sub(r"[\s\.,;:]+$", "", line).strip()

def pace_seconds(pace):
    p = normalize_pace(str(pace))
    minutes, seconds = p.split(":")
    return int(minutes) * 60 + int(seconds)

def pace_from_seconds(seconds):
    seconds = max(1, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"

def target_bounds(value, pct, kind):
    if kind == "power":
        v = float(value)
        return int(round(v * (1 - pct / 100))), int(round(v * (1 + pct / 100)))
    seconds = pace_seconds(value)
    return (
        pace_from_seconds(seconds * (1 - pct / 100)),
        pace_from_seconds(seconds * (1 + pct / 100)),
    )

def profile_target(profile, key, kind):
    value = profile[key]
    enabled = profile.get(f"{key}_pct_enabled", False)
    pct = float(profile.get(f"{key}_pct", 0) or 0)
    if not enabled or pct <= 0:
        return f"{value}w" if kind == "power" else f"{normalize_pace(str(value))} Pace"
    low, high = target_bounds(value, pct, kind)
    return f"{low}-{high}w" if kind == "power" else f"{low}-{high} Pace"

def format_distance_for_intervals(value, unit):
    numeric = float(str(value).replace(",", "."))
    if unit.lower() == "m":
        numeric /= 1000.0
    if numeric.is_integer():
        return f"{int(numeric)}km"
    return f"{numeric:.3f}".rstrip("0").rstrip(".") + "km"

def duration_expression_to_seconds(raw):
    value = clean_training_line(raw).lower().replace(" ", "")
    m = re.fullmatch(r"(?P<h>\d+)h(?P<m>\d{1,2})?", value)
    if m:
        return int(m.group("h")) * 3600 + int(m.group("m") or 0) * 60
    m = re.fullmatch(r"(?P<m>\d+)(?:min|m|')", value)
    if m:
        return int(m.group("m")) * 60
    m = re.fullmatch(r'(?P<s>\d+)(?:s|")', value)
    if m:
        return int(m.group("s"))
    raise ValueError(f"Durée non reconnue : {raw}")

def seconds_to_intervals_duration(seconds):
    seconds = int(seconds)
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes}m{remainder}s" if remainder else f"{minutes}m"
    return f"{seconds}s"

def duration_token(raw):
    return seconds_to_intervals_duration(duration_expression_to_seconds(raw))

def upper_duration(d1, d2, unit=None):
    raw1 = f"{d1}{unit or ''}"
    raw2 = f"{d2}{unit or ''}"
    return seconds_to_intervals_duration(
        max(duration_expression_to_seconds(raw1), duration_expression_to_seconds(raw2))
    )

def split_plus_segments(line):
    return [part.strip() for part in re.split(r"\s+\+\s+", line) if part.strip()]

def is_instruction_note(line):
    low = clean_training_line(line).lower()
    measurable = [
        r"\b\d+\s*(?:h|min|m|km|s|['\"])\b",
        r"\b\d+\s+(?:à|a|-)\s+\d+\s*(?:h|min|m|s|['\"])\b",
        r"\b\d+\s*x\s*\d+",
        r"\b\d+\s*w\b",
        r"\b\d+\s*%\b",
        r"\b\d+\s*rpm\b",
        r"\bz[1-7]\b",
        r"\b\d+[':]\d{1,2}\b",
        r"\b(?:récupération|recuperation|récup|recup|r=)\s*\d+",
    ]
    return not any(re.search(pattern, low, flags=re.I) for pattern in measurable)

def result_steps(*steps, warning=None, repeat=None):
    result = {"steps": list(steps)}
    if warning:
        result["warning"] = warning
    if repeat is not None:
        result["repeat"] = int(repeat)
    return result

# -------------------------
# Running parser rules
# -------------------------

def run_rule_compound(line, profile):
    parts = split_plus_segments(line)
    if len(parts) <= 1:
        return None
    steps, warnings = [], []
    for part in parts:
        result = compile_running_line_v7(part, profile)
        if result.get("error") or result.get("repeat"):
            return {"error": f"Ligne composée non prise en charge : {line}"}
        steps.extend(result.get("steps", []))
        if result.get("warning"):
            warnings.append(result["warning"])
    return result_steps(*steps, warning=" / ".join(warnings) if warnings else None)

def _recovery_to_interval(value, unit, seconds_part=None):
    unit = "'" if unit == "’" else unit
    if unit in ("'", "min", "m"):
        total = int(value) * 60
    else:
        total = int(value)
    if seconds_part:
        total += int(seconds_part)
    return seconds_to_intervals_duration(total)


def run_rule_repeat_distance_pace_inline_recovery(line, profile):
    """5 x 1000 m à 3'50/km, récupération 2'."""
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*"
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)"
        r".*?(?:à|a|@)\s*"
        r"(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?"
        r"(?:\s*/?\s*km)?"
        r".*?(?:récupération|recuperation|récup|recup|repos|r=)\s*"
        r"(?P<rec>\d+)\s*(?P<recunit>'|’|min|m|s|\")"
        r"(?:(?P<recsec>\d+)\s*(?:s|\"))?"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None

    target = normalize_pace(m.group("p1"))
    if m.group("p2"):
        target += f"-{normalize_pace(m.group('p2'))}"

    return result_steps(
        f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))} {target} Pace",
        f"- {_recovery_to_interval(m.group('rec'), m.group('recunit'), m.group('recsec'))}",
        repeat=m.group("count"),
    )


def run_rule_repeat_time_pace_inline_recovery(line, profile):
    """3 x 10' à 4'05-4'10/km récupération 3'."""
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*"
        r"(?P<dur>\d+)\s*(?P<unit>'|’|min|s|\")"
        r".*?(?:à|a|@)\s*"
        r"(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?"
        r"(?:\s*/?\s*km)?"
        r".*?(?:récupération|recuperation|récup|recup|repos|r=)\s*"
        r"(?P<rec>\d+)\s*(?P<recunit>'|’|min|m|s|\")"
        r"(?:(?P<recsec>\d+)\s*(?:s|\"))?"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None

    target = normalize_pace(m.group("p1"))
    if m.group("p2"):
        target += f"-{normalize_pace(m.group('p2'))}"

    effort_unit = "'" if m.group("unit") == "’" else m.group("unit")
    return result_steps(
        f"- {normalize_duration(m.group('dur'), effort_unit)} {target} Pace",
        f"- {_recovery_to_interval(m.group('rec'), m.group('recunit'), m.group('recsec'))}",
        repeat=m.group("count"),
    )


def run_rule_repeat_distance_inline_recovery(line, profile):
    """5 x 1000 m, récupération 400 m ou 2'."""
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*"
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)"
        r".*?(?:récupération|recuperation|récup|recup|repos|r=)\s*"
        r"(?P<rec>\d+)\s*(?P<recunit>'|’|min|m|s|\")"
        r"(?:(?P<recsec>\d+)\s*(?:s|\"))?"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None

    return result_steps(
        f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))}",
        f"- {_recovery_to_interval(m.group('rec'), m.group('recunit'), m.group('recsec'))}",
        repeat=m.group("count"),
    )


def run_rule_repeat_time_inline_recovery(line, profile):
    """4 x 20" relâchées, récupération 1'."""
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*"
        r"(?P<dur>\d+)\s*(?P<unit>'|’|min|s|\")"
        r".*?(?:récupération|recuperation|récup|recup|repos|r=)\s*"
        r"(?P<rec>\d+)\s*(?P<recunit>'|’|min|m|s|\")"
        r"(?:(?P<recsec>\d+)\s*(?:s|\"))?"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None

    effort_unit = "'" if m.group("unit") == "’" else m.group("unit")
    return result_steps(
        f"- {normalize_duration(m.group('dur'), effort_unit)}",
        f"- {_recovery_to_interval(m.group('rec'), m.group('recunit'), m.group('recsec'))}",
        repeat=m.group("count"),
    )


def run_rule_repeat_time_pace(line, profile):
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?(?:à|a|@)\s*(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    target = normalize_pace(m.group("p1"))
    if m.group("p2"):
        target += f"-{normalize_pace(m.group('p2'))}"
    return result_steps(
        f"- {normalize_duration(m.group('dur'), m.group('unit'))} {target} Pace",
        repeat=m.group("count"),
    )

def run_rule_repeat_distance_pace(line, profile):
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)"
        r".*?(?:à|a|@)\s*(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    target = normalize_pace(m.group("p1"))
    if m.group("p2"):
        target += f"-{normalize_pace(m.group('p2'))}"
    return result_steps(
        f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))} {target} Pace",
        repeat=m.group("count"),
    )

def run_rule_repeat_distance_simple(line, profile):
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))}",
        repeat=m.group("count"),
        warning="Récupération non précisée : aucune récupération ajoutée.",
    )

def run_rule_repeat_simple(line, profile):
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>s|\"|'|min|m)(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None

    effort = normalize_duration(m.group("dur"), m.group("unit"))
    effort_seconds = duration_expression_to_seconds(
        f"{m.group('dur')}{m.group('unit')}"
    )

    # Efforts courts : récupération automatique égale à l'effort.
    if effort_seconds < 60:
        return result_steps(
            f"- {effort}",
            f"- {effort}",
            repeat=m.group("count"),
        )

    # À partir d'une minute, aucune récupération n'est inventée.
    return result_steps(
        f"- {effort}",
        repeat=m.group("count"),
        warning="Récupération non précisée : aucune récupération ajoutée.",
    )

def run_rule_variable_with_pace(line, profile):
    m = re.fullmatch(
        r"(?P<d1>\d+h\d{0,2}|\d+)\s+(?:à|a|-)\s+"
        r"(?P<d2>\d+h\d{0,2}|\d+)\s*(?P<unit>'|min|m)?"
        r".*?(?:à|a|@)\s*(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?"
        r"(?:\s*/?\s*km)?(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    target = normalize_pace(m.group("p1"))
    if m.group("p2"):
        target += f"-{normalize_pace(m.group('p2'))}"
    return result_steps(
        f"- {upper_duration(m.group('d1'), m.group('d2'), m.group('unit'))} {target} Pace",
        warning="Durée variable : borne haute utilisée, allure conservée.",
    )

def run_rule_variable_simple(line, profile):
    m = re.fullmatch(
        r"(?P<d1>\d+h\d{0,2}|\d+)\s+(?:à|a|-)\s+"
        r"(?P<d2>\d+h\d{0,2}|\d+)\s*(?P<unit>'|min|m)?(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {upper_duration(m.group('d1'), m.group('d2'), m.group('unit'))}",
        warning="Durée variable : borne haute utilisée, sans cible.",
    )

def run_rule_profile_target(line, profile):
    m = re.search(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?\b(?P<label>EF|endurance fondamentale|AS42|AM|allure marathon|marathon|seuil)\b",
        line,
        flags=re.I,
    )
    if not m:
        return None
    label = m.group("label").lower()
    if label in ["ef", "endurance fondamentale"]:
        key = "ef_pace"
    elif label in ["as42", "am", "allure marathon", "marathon"]:
        key = "marathon_pace"
    else:
        key = "threshold_pace"
    return result_steps(
        f"- {duration_token(m.group('dur'))} {profile_target(profile, key, 'pace')}"
    )

def run_rule_zone(line, profile):
    m = re.fullmatch(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?\b(?P<zone>Z[1-7]|Sweet Spot|Tempo)\b(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if m:
        return result_steps(f"- {duration_token(m.group('dur'))} {m.group('zone')}")
    m = re.fullmatch(
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)"
        r".*?\b(?P<zone>Z[1-7]|Sweet Spot|Tempo)\b(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if m:
        return result_steps(
            f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))} {m.group('zone')}"
        )
    return None

def run_rule_inequality_pace(line, profile):
    m = re.fullmatch(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?(?P<op><|>|plus vite que|moins vite que)\s*"
        r"(?P<pace>\d+(?:[':]\d{1,2}|['’']))(?:\s*/?\s*km)?(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {duration_token(m.group('dur'))} {normalize_pace(m.group('pace'))} Pace",
        warning=f"Borne d’allure « {m.group('op')} » approximée avec la valeur frontière.",
    )

def run_rule_explicit_pace(line, profile):
    # Distance first, otherwise "1000 m" could be misread as 1000 minutes.
    m = re.search(
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)"
        r".*?(?:à|a|@)\s*(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?",
        line,
        flags=re.I,
    )
    if m:
        target = normalize_pace(m.group("p1"))
        if m.group("p2"):
            target += f"-{normalize_pace(m.group('p2'))}"
        return result_steps(
            f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))} {target} Pace"
        )

    m = re.search(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|s|\"))"
        r".*?(?:à|a|@)\s*(?P<p1>\d+(?:[':]\d{1,2}|['’]))"
        r"(?:\s*-\s*(?P<p2>\d+(?:[':]\d{1,2}|['’])))?(?:\s*/?\s*km)?",
        line,
        flags=re.I,
    )
    if m:
        target = normalize_pace(m.group("p1"))
        if m.group("p2"):
            target += f"-{normalize_pace(m.group('p2'))}"
        return result_steps(f"- {duration_token(m.group('dur'))} {target} Pace")

    return None

def run_rule_simple(line, profile):
    m = re.fullmatch(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if m:
        return result_steps(f"- {duration_token(m.group('dur'))}")
    m = re.fullmatch(
        r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if m:
        return result_steps(
            f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))}"
        )
    return None

RUN_RULES = [
    run_rule_compound,
    run_rule_repeat_distance_pace_inline_recovery,
    run_rule_repeat_time_pace_inline_recovery,
    run_rule_repeat_distance_inline_recovery,
    run_rule_repeat_time_inline_recovery,
    run_rule_repeat_time_pace,
    run_rule_repeat_distance_pace,
    run_rule_repeat_distance_simple,
    run_rule_repeat_simple,
    run_rule_variable_with_pace,
    run_rule_variable_simple,
    run_rule_profile_target,
    run_rule_zone,
    run_rule_inequality_pace,
    run_rule_explicit_pace,
    run_rule_simple,
]

def compile_running_line_v7(line, profile):
    cleaned = clean_training_line(line)
    for rule in RUN_RULES:
        result = rule(cleaned, profile)
        if result is not None:
            return result
    return {"error": f"Ligne running non comprise : {cleaned}"}

# -------------------------
# Cycling parser rules
# -------------------------

def ride_rule_compound(line, profile):
    parts = split_plus_segments(line)
    if len(parts) <= 1:
        return None
    steps, warnings = [], []
    for part in parts:
        result = compile_ride_line_v7(part, profile)
        if result.get("error") or result.get("repeat"):
            return {"error": f"Ligne composée non prise en charge : {line}"}
        steps.extend(result.get("steps", []))
        if result.get("warning"):
            warnings.append(result["warning"])
    return result_steps(*steps, warning=" / ".join(warnings) if warnings else None)

def ride_rule_repeat_simple(line, profile):
    m = re.fullmatch(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>s|\"|'|min|m)"
        r"(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None

    effort = normalize_duration(m.group("dur"), m.group("unit"))
    effort_seconds = duration_expression_to_seconds(
        f"{m.group('dur')}{m.group('unit')}"
    )

    # Efforts courts de vélocité, activation ou relâchement :
    # récupération automatique égale à l'effort.
    if effort_seconds < 60:
        return result_steps(
            f"- {effort}",
            f"- {effort}",
            repeat=m.group("count"),
        )

    return result_steps(
        f"- {effort}",
        repeat=m.group("count"),
        warning="Récupération non précisée : aucune récupération ajoutée.",
    )

def ride_rule_repeat_power(line, profile):
    m = re.search(
        r"(?P<count>\d+)\s*x\s*(?P<dur>\d+)\s*(?P<unit>'|min|m|s|\")"
        r".*?(?P<p1>\d+)(?:\s*-\s*(?P<p2>\d+))?\s*w",
        line,
        flags=re.I,
    )
    if not m:
        return None
    power = m.group("p1")
    if m.group("p2"):
        power += f"-{m.group('p2')}"
    return result_steps(
        f"- {normalize_duration(m.group('dur'), m.group('unit'))} {power}w",
        repeat=m.group("count"),
    )

def ride_rule_variable_power(line, profile):
    m = re.fullmatch(
        r"(?P<d1>\d+h\d{0,2}|\d+)\s+(?:à|a|-)\s+"
        r"(?P<d2>\d+h\d{0,2}|\d+)\s*(?P<unit>'|min|m)?"
        r".*?(?P<p1>\d+)\s*-\s*(?P<p2>\d+)\s*w(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {upper_duration(m.group('d1'), m.group('d2'), m.group('unit'))} "
        f"{m.group('p1')}-{m.group('p2')}w",
        warning="Durée variable : borne haute utilisée, puissance conservée.",
    )

def ride_rule_variable_simple(line, profile):
    m = re.fullmatch(
        r"(?P<d1>\d+h\d{0,2}|\d+)\s+(?:à|a|-)\s+"
        r"(?P<d2>\d+h\d{0,2}|\d+)\s*(?P<unit>'|min|m)?(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {upper_duration(m.group('d1'), m.group('d2'), m.group('unit'))}",
        warning="Durée variable : borne haute utilisée, sans cible.",
    )

def ride_rule_im_power(line, profile):
    m = re.search(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?\b(?:puissance IM|allure IM|ironman)\b",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {duration_token(m.group('dur'))} {profile_target(profile, 'im_power', 'power')}"
    )

def ride_rule_zone(line, profile):
    m = re.fullmatch(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?\b(?P<zone>Z[1-7]|Sweet Spot|Tempo)\b(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(f"- {duration_token(m.group('dur'))} {m.group('zone')}")

def ride_rule_power(line, profile):
    m = re.search(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?(?P<p1>\d+)(?:\s*-\s*(?P<p2>\d+))?\s*w",
        line,
        flags=re.I,
    )
    if not m:
        return None
    power = m.group("p1")
    if m.group("p2"):
        power += f"-{m.group('p2')}"
    return result_steps(f"- {duration_token(m.group('dur'))} {power}w")

def ride_rule_cadence(line, profile):
    m = re.search(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?(?P<c1>\d+)(?:\s*-\s*(?P<c2>\d+))?\s*rpm",
        line,
        flags=re.I,
    )
    if not m:
        return None
    cadence = f"{m.group('c1')}-{m.group('c2')}rpm" if m.group("c2") else f"{m.group('c1')}rpm"
    return result_steps(f"- {duration_token(m.group('dur'))} {cadence}")

def ride_rule_inequality_power(line, profile):
    m = re.fullmatch(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))"
        r".*?(?P<op><|>|inf[eé]rieur[e]?\s+à|sup[eé]rieur[e]?\s+à|moins de|plus de)"
        r"\s*(?P<power>\d+)\s*w(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(
        f"- {duration_token(m.group('dur'))} {m.group('power')}w",
        warning=f"Borne de puissance « {m.group('op')} » approximée avec la valeur frontière.",
    )

def ride_rule_simple(line, profile):
    m = re.fullmatch(
        r"(?P<dur>\d+h\d{0,2}(?:min|m)?|\d+\s*(?:'|min|m|s|\"))(?:\s+.*)?",
        line,
        flags=re.I,
    )
    if not m:
        return None
    return result_steps(f"- {duration_token(m.group('dur'))}")

RIDE_RULES = [
    ride_rule_compound,
    ride_rule_repeat_power,
    ride_rule_repeat_simple,
    ride_rule_variable_power,
    ride_rule_variable_simple,
    ride_rule_im_power,
    ride_rule_zone,
    ride_rule_inequality_power,
    ride_rule_power,
    ride_rule_cadence,
    ride_rule_simple,
]

def compile_ride_line_v7(line, profile):
    cleaned = clean_training_line(line)
    for rule in RIDE_RULES:
        result = rule(cleaned, profile)
        if result is not None:
            return result
    return {"error": f"Ligne vélo non comprise : {cleaned}"}

def compile_details_v7(details, intervals_type, profile):
    forced = re.search(r"INTERVALS\s*:\s*(.*)", details, flags=re.I | re.S)
    if forced:
        script = forced.group(1).strip()
        return script, [], [{"status": "ok", "source": "Bloc INTERVALS manuel", "output": script}]

    sections = split_sections(details)
    output, warnings, records = [], [], []
    compiler = (
        (lambda line: compile_running_line_v7(line, profile))
        if intervals_type == "Run"
        else (lambda line: compile_ride_line_v7(line, profile))
    )

    for section_name, lines in sections:
        section_output = []
        last_repeat = None

        for raw_line in lines:
            line = clean_training_line(raw_line)

            # Recovery by distance.
            m = re.fullmatch(
                r"(?:récupération|recuperation|récup|recup|repos)"
                r"(?:\s+entre.*?|\s*:|\s*)"
                r"(?P<dist>\d+(?:[.,]\d+)?)\s*(?P<unit>m|km)(?:\s+.*)?",
                line,
                flags=re.I,
            )
            if m and last_repeat is not None:
                step = f"- {format_distance_for_intervals(m.group('dist'), m.group('unit'))}"
                output.append(step)
                last_repeat["record"]["output"] += f"\n{step}"
                records.append({
                    "status": "ok",
                    "source": raw_line,
                    "output": "Récupération en distance rattachée à la répétition précédente.",
                })
                continue

            # Recovery by time.
            m = re.fullmatch(
                r"(?:récupération|recuperation|récup|recup|repos)"
                r"(?:\s+entre.*?|\s*:|\s*)"
                r"(?P<rec>\d+)\s*(?P<unit>'|min|m|s|\")?(?:\s+.*)?",
                line,
                flags=re.I,
            )
            if m and last_repeat is not None:
                unit = m.group("unit") or "'"
                step = f"- {normalize_duration(m.group('rec'), unit)}"
                output.append(step)
                last_repeat["record"]["output"] += f"\n{step}"
                records.append({
                    "status": "ok",
                    "source": raw_line,
                    "output": "Récupération rattachée à la répétition précédente.",
                })
                continue

            # Complete recovery = same time as effort.
            if re.search(
                r"(?:récupération|recuperation|récup|recup|repos)\s+compl[eè]te",
                line,
                flags=re.I,
            ) and last_repeat is not None:
                effort = last_repeat["steps"][0]
                duration_match = re.match(r"-\s*(\d+h|\d+m(?:\d+s)?|\d+s)", effort)
                if duration_match:
                    step = f"- {duration_match.group(1)}"
                    output.append(step)
                    last_repeat["record"]["output"] += f"\n{step}"
                    records.append({
                        "status": "ok",
                        "source": raw_line,
                        "output": "Récupération complète = même durée que l’intervalle.",
                    })
                    continue

            result = compiler(line)

            if result.get("error"):
                if is_instruction_note(line):
                    records.append({
                        "status": "note",
                        "source": raw_line,
                        "output": "Information ignorée : aucune étape Garmin à créer.",
                    })
                else:
                    records.append({
                        "status": "error",
                        "source": raw_line,
                        "output": result["error"],
                    })
                continue

            status = "warning" if result.get("warning") else "ok"
            if result.get("warning"):
                warnings.append(result["warning"])

            if "repeat" in result:
                if section_output:
                    output.append(section_name)
                    output.extend(section_output)
                    section_output = []
                output.append("")
                output.append(f"{result['repeat']}x")
                output.extend(result["steps"])
                record = {
                    "status": status,
                    "source": raw_line,
                    "output": "\n".join([f"{result['repeat']}x"] + result["steps"]),
                }
                records.append(record)
                last_repeat = {"steps": result["steps"], "record": record}
            else:
                section_output.extend(result["steps"])
                records.append({
                    "status": status,
                    "source": raw_line,
                    "output": "\n".join(result["steps"]),
                })
                last_repeat = None

        if section_output:
            output.append(section_name)
            output.extend(section_output)
        output.append("")

    while output and not output[-1].strip():
        output.pop()

    if not output:
        raise ValueError("Aucune étape n'a pu être compilée depuis Détails séance.")

    script = "\n".join(output)

    source_repeats = len(re.findall(r"\b\d+\s*x\s*\d+", normalize_text(details), flags=re.I))
    script_repeats = len(re.findall(r"^\s*\d+x\s*$", script, flags=re.I | re.M))
    if script_repeats < source_repeats:
        records.append({
            "status": "error",
            "source": "Contrôle de cohérence",
            "output": (
                f"{source_repeats} répétition(s) détectée(s) dans la source, "
                f"seulement {script_repeats} dans le script."
            ),
        })

    return script, warnings, records

# Backward-compatible name used by the UI.
compile_details_v6 = compile_details_v7
