import os
import sys

# PyInstaller --noconsole stream redirect fix
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import csv
import datetime
import json
import platform
import queue
import random
import re
import shlex
import shutil
import sqlite3
import subprocess
import threading
import time
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import customtkinter as ctk

import i18n
from i18n import num, t, vis

APP_NAME = "AutoScribe"
APP_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG = "#0B0D10"
SIDEBAR = "#101318"
CARD = "#12151A"
INPUT = "#161A20"
DEEP = "#0E1014"
ROW = "#141820"
ROW_ALT = "#15191F"
BORDER = "#1F242C"
BORDER_2 = "#262C35"
HOVER = "#1C222B"
TEXT = "#E8EAED"
TEXT_2 = "#AEB6C1"
MUTED = "#8E97A3"
DIM = "#5B6470"
ACCENT = "#7CC4FF"
ACCENT_HOVER = "#9BD2FF"
ON_ACCENT = "#0B0D10"
ACCENT_SOFT = "#18212C"
ACCENT_LINE = "#2E3B4C"
CHIP = "#1A2330"
CHIP_TEXT = "#A9D8FF"
SELECTED = "#1E2B3B"
GOOD = "#6EE7A8"
GOOD_SOFT = "#12201B"
GOOD_LINE = "#1E3A2E"
GOOD_TEXT = "#B7F0D2"
WARN = "#FBBF24"
WARN_SOFT = "#2A2312"
WARN_TEXT = "#FCD98A"
BAD = "#F87171"
BAD_SOFT = "#2A1517"
BAD_LINE = "#5A2A2E"
BAD_TEXT = "#FFB4B4"
BAD_HOVER = "#3A1C1F"
REC_BG = "#111A22"
REC_LINE = "#23364A"

IS_WINDOWS = platform.system() == "Windows"

# Resolved in init_fonts() once Tk is running; these are the fallbacks.
SANS = "Segoe UI" if IS_WINDOWS else "Helvetica"
MONO = "Consolas" if IS_WINDOWS else "Courier"
ICON_FONT = None

ICONS = {"globe": "\uE774", "list": "\uE8FD", "sliders": "\uE713", "save": "\uE74E", "delete": "\uE74D",
         "up": "\uE70E", "down": "\uE70D", "menu": "\uE700", "collapse": "\uE76B",
         "refresh": "\uE72C"}
ICON_FALLBACK = {"globe": "◎", "list": "≡", "sliders": "⚙", "save": "S", "delete": "✕",
                 "up": "▲", "down": "▼", "menu": "≡", "collapse": "‹", "refresh": "↻"}

PROTO_NAMES = {"wireguard": "WireGuard", "ikev2": "IKEv2", "udp": "UDP", "tcp": "TCP",
               "stealth": "Stealth", "wstunnel": "WStunnel"}

DEFAULT_PROTOCOLS = {
    "wireguard": [443, 80, 53, 123, 1194, 65142],
    "ikev2": [500],
    "udp": [443, 80, 53, 123, 1194, 54783],
    "tcp": [443, 587, 21, 22, 80, 123, 143, 3306, 8080, 54783, 1194],
    "stealth": [443, 587, 21, 22, 80, 123, 143, 3306, 8080, 54783, 8443],
    "wstunnel": [443],
}

if getattr(sys, "frozen", False):
    APP_PATH = os.path.dirname(sys.executable)
else:
    APP_PATH = os.path.dirname(os.path.abspath(__file__))

DB_FILE = os.path.join(APP_PATH, "windscribe_results.db")
CONFIG_FILE = os.path.join(APP_PATH, "config.json")
LOCATIONS_FILE = os.path.join(APP_PATH, "locations.json")
REPORTS_DIR = os.path.join(APP_PATH, "reports")

DEFAULT_CLI = r"C:\Program Files\Windscribe\windscribe-cli.exe" if IS_WINDOWS else "windscribe-cli"
# The public server list that windscribe.com/vpn-servers loads; same format as locations.json.
LOCATIONS_URL = "https://api.windscribe.com/WebsiteStatus"

def init_fonts(root):
    global SANS, MONO, ICON_FONT
    families = set(tkfont.families(root))
    if i18n.LANG == "fa":
        # One font with Persian glyphs everywhere: Tk splits text at font fallbacks, which breaks RTL ordering.
        SANS = next((f for f in ("Segoe UI", "Tahoma", "DejaVu Sans") if f in families), SANS)
        MONO = SANS
    else:
        SANS = next((f for f in ("IBM Plex Sans", "Segoe UI", "Helvetica Neue", "DejaVu Sans") if f in families),
                    SANS)
        MONO = next((f for f in ("IBM Plex Mono", "Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono")
                     if f in families), MONO)
    ICON_FONT = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)


def sans(size, bold=False):
    return (SANS, size, "bold") if bold else (SANS, size)


def mono(size, bold=False):
    return (MONO, size, "bold") if bold else (MONO, size)


def icon(name):
    return ICONS[name] if ICON_FONT else ICON_FALLBACK[name]


def icon_font(size=13):
    return (ICON_FONT or SANS, size)


def hidden_process_kwargs():
    """Keeps console windows from flashing up on Windows."""
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def resolve_cli(path):
    """Returns the argv that runs windscribe-cli, or None.

    A single executable path still works. A command such as
    ``wsl -d Ubuntu -u ubroot -- windscribe-cli`` is accepted when its first token is on PATH.
    """
    path = (path or "").strip().strip('"')
    if not path:
        return None
    parts = [path] if os.path.isfile(path) else shlex.split(path, posix=not IS_WINDOWS)
    # The last word must be the CLI itself, so a bare "wsl" or "wsl -d Ubuntu --" is not "ready".
    if not parts or os.path.basename(parts[-1]).lower() not in ("windscribe-cli", "windscribe-cli.exe"):
        return None
    if os.path.isfile(parts[0]) or shutil.which(parts[0]):
        return parts
    return None


def cli_probe(argv):
    """True when the command really is windscribe-cli: its help banner names itself, with no service needed."""
    try:
        out = subprocess.run(list(argv) + ["help"], capture_output=True, text=True, errors="replace",
                             timeout=30, **hidden_process_kwargs()).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "windscribe-cli" in out.lower()


def wsl_prefix(argv):
    """The ``wsl … --`` prefix in front of windscribe-cli, or None for a native binary."""
    if not argv:
        return None
    base = os.path.basename(argv[0]).lower()
    if base not in ("wsl", "wsl.exe") or "--" not in argv:
        return None
    return argv[:argv.index("--") + 1]


def linux_cli(argv):
    """Only the Linux CLI build has the editable conf file; the Windows exe is a thin client of the GUI."""
    return bool(wsl_prefix(argv)) or platform.system() == "Linux"


# Empty string always means "Windscribe default", so a Windows row equals a Linux default row.
TLS_VALUES = {"off": [""], "on": ["on"], "both": ["", "on"]}
ROUTING_VALUES = {"auto": [""], "regular": ["regular"], "alternate": ["alternate"],
                  "both": ["regular", "alternate"]}


def route_label(r):
    """``wireguard:443 · A · TLS · alt``; default rows read ``wireguard:443`` like upstream."""
    parts = [f"{r['proto']}:{r['port']}"]
    awg = r.get("awg") or ""
    if awg:
        parts.append(awg.split(" - ", 1)[0].strip() or awg)
    if r.get("tls"):
        parts.append("TLS")
    if r.get("routing"):
        parts.append(r["routing"][:3])
    return " · ".join(parts)


def expand_routes(work_plan, presets, tls_mode="off", routing_mode="auto"):
    """(proto, port, awg, tls, routing) routes. Presets multiply WireGuard only; TLS and routing multiply all."""
    routes = []
    for proto, ports in work_plan.items():
        awgs = presets if proto == "wireguard" and presets else [""]
        for port in ports:
            for awg in awgs:
                for tls in TLS_VALUES[tls_mode]:
                    for routing in ROUTING_VALUES[routing_mode]:
                        routes.append((proto, port, awg, tls, routing))
    return routes


def patch_conf(text, awg, tls, routing):
    """Set the anti-censorship keys under [Connection] of windscribe_cli.conf (QSettings INI)."""
    mapping = {
        "ProtocolTweaksMethod": "1" if awg else "2",
        "AmneziawgPreset": awg or "",
        "CircumventCensorship": "true" if tls else "false",
        "ServerRoutingMethod": {"regular": "1", "alternate": "2"}.get(routing, "0"),
    }
    lines = text.splitlines()
    section = re.compile(r"^\[(.+)\]\s*$")
    out = []
    in_section = False
    seen = set()

    def flush():
        for key, value in mapping.items():
            if key not in seen:
                out.append(f"{key}={value}")
                seen.add(key)

    for line in lines:
        match = section.match(line.strip())
        if match:
            if in_section:
                flush()
            in_section = match.group(1) == "Connection"
            out.append(line)
            continue
        if in_section and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in mapping:
                out.append(f"{key}={mapping[key]}")
                seen.add(key)
                continue
        out.append(line)
    if in_section:
        flush()
    elif set(mapping) - seen:
        if out and out[-1] != "":
            out.append("")
        out.append("[Connection]")
        flush()
    body = "\n".join(out)
    return body if body.endswith("\n") else body + "\n"


CLI_CONF = "~/.config/Windscribe/windscribe_cli.conf"
_READ_CONF = ["sh", "-c", f"cat {CLI_CONF} 2>/dev/null"]
_WRITE_CONF = ["sh", "-c", f"mkdir -p {os.path.dirname(CLI_CONF)} && cat > {CLI_CONF}"]


def open_path(path):
    try:
        if IS_WINDOWS:
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"Open Error: {e}")


def ping_color(ping):
    if ping is None:
        return MUTED
    return GOOD if ping < 50 else WARN if ping < 100 else BAD


def ping_quality(ping):
    if ping is None:
        return "slow"
    return "fast" if ping < 50 else "medium" if ping < 100 else "slow"


def rate_color(rate):
    return GOOD if rate >= 0.75 else WARN if rate >= 0.45 else BAD


def loc_key(loc):
    return f"{loc['country']}|{loc['city']}|{loc['location']}"


def loc_name(city, node):
    return f"{city} – {node}" if node else city


def matches_region(loc, region):
    if region == "All":
        return True
    if region == "USA":
        return loc["country"].startswith("US ")
    return loc["continent"] == region


def trunc(text, n):
    return text if len(text) <= n else text[:n - 1] + "…"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class ConfigManager:
    @staticmethod
    def default_settings():
        settings = {
            "timeout": "25",
            "settle": "2",
            "ping_host": "1.1.1.1",
            "ping_count": "5",
            "resume": False,
            "selected": [],
            "random_cities": False,
            "chaos_mode": False,
            "stop_on_success": False,
            "priority_order": list(DEFAULT_PROTOCOLS.keys()),
            "protocols": {},
        }
        for proto, ports in DEFAULT_PROTOCOLS.items():
            settings["protocols"][proto] = {"enabled": True, "ports": {str(p): True for p in ports}}
        return settings

    @staticmethod
    def load_config():
        default_data = {"saved_profiles": {}, "last_settings": ConfigManager.default_settings(),
                        "cli_path": DEFAULT_CLI, "window": "", "sidebar_open": True, "language": ""}
        if not os.path.exists(CONFIG_FILE):
            return default_data
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
            for key, val in default_data.items():
                loaded.setdefault(key, val)
            for key, val in default_data["last_settings"].items():
                loaded["last_settings"].setdefault(key, val)
            return loaded
        except Exception as e:
            print(f"Config Load Error: {e}")
            return default_data

    @staticmethod
    def save_config(data):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Config Save Error: {e}")


# ---------------------------------------------------------------------------
# Locations (Windscribe's locations.json)
# ---------------------------------------------------------------------------
class LocationManager:
    @staticmethod
    def load_locations():
        """Returns a flat list of dicts: city, location, country, continent."""
        locations = []
        if not os.path.exists(LOCATIONS_FILE):
            return locations
        try:
            with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            for _, entry in raw.get("data", {}).get("locations", {}).items():
                country = (entry.get("name") or "Unknown").strip()
                continent = (entry.get("continent") or "Unknown").strip()

                for pop in entry.get("pops", []):
                    if pop.get("status", 1) != 1:
                        continue  # skip offline/disabled nodes
                    pop_name = (pop.get("name") or "").strip()
                    if not pop_name:
                        continue
                    if " - " in pop_name:
                        city, location = pop_name.split(" - ", 1)
                    else:
                        city, location = pop_name, ""

                    locations.append({
                        "city": city.strip(),
                        "location": location.strip(),
                        "country": country,
                        "continent": continent,
                    })
        except Exception as e:
            print(f"Locations Load Error: {e}")
        return locations

    @staticmethod
    def download():
        """Fetches the current server list from windscribe.com and replaces locations.json.
        Raises on any network or format problem, leaving the old file untouched."""
        req = urllib.request.Request(LOCATIONS_URL, headers={
            "User-Agent": f"{APP_NAME}/{APP_VERSION}", "Accept": "application/json",
            # The same placeholder token windscribe.com's own server list page sends.
            "Authorization": "Bearer 1234"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        data = json.loads(raw.decode("utf-8"))
        locations = data.get("data", {}).get("locations")
        if not isinstance(locations, dict) or not locations:
            raise ValueError("the response did not contain a server list")
        if not any(isinstance(v, dict) and v.get("pops") for v in locations.values()):
            raise ValueError("the server list has no servers in it")
        tmp = LOCATIONS_FILE + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, LOCATIONS_FILE)

    @staticmethod
    def last_updated():
        try:
            return datetime.datetime.fromtimestamp(os.path.getmtime(LOCATIONS_FILE))
        except OSError:
            return None


# ---------------------------------------------------------------------------
# Ping - uses the system `ping`, nothing else to install
# ---------------------------------------------------------------------------
class PingRunner:
    TIME_RE = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)

    @staticmethod
    def parse(output):
        """Extracts per-reply latencies. Only lines with a TTL are replies, which also
        keeps the 'Minimum/Maximum/Average' summary line on Windows out of the numbers."""
        times = []
        for line in output.splitlines():
            if "ttl" not in line.lower():
                continue
            m = PingRunner.TIME_RE.search(line)
            if m:
                times.append(float(m.group(1).replace(",", ".")))
        return times

    def run(self, host, count=5, reply_timeout_ms=2000, wsl=None):
        """Returns ({"avg", "min", "max", "loss"}, None) or (None, error).

        ``wsl`` is the ``wsl … --`` prefix. Ping must run in that distro: a Windows ping
        does not enter the WSL tunnel.
        """
        if wsl:
            cmd = list(wsl) + ["ping", "-c", str(count), "-W", str(max(1, reply_timeout_ms // 1000)), host]
        elif IS_WINDOWS:
            cmd = ["ping", "-n", str(count), "-w", str(reply_timeout_ms), host]
        else:
            cmd = ["ping", "-c", str(count), "-W", str(max(1, reply_timeout_ms // 1000)), host]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=count * (reply_timeout_ms / 1000 + 1) + 5, **hidden_process_kwargs())
        except FileNotFoundError:
            return None, "ping command not found"
        except subprocess.TimeoutExpired:
            return None, "ping timed out"
        except Exception as e:
            return None, str(e)

        times = self.parse(result.stdout)
        if not times:
            return None, "no replies"
        return {
            "avg": sum(times) / len(times),
            "min": min(times),
            "max": max(times),
            "loss": (count - len(times)) / count * 100,
        }, None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class DatabaseManager:
    EXPORT_COLUMNS = ["city", "location", "country", "protocol", "port", "awg", "tls", "routing", "status",
                      "duration", "ping", "packet_loss", "profile_name", "timestamp"]
    TWEAK_COLUMNS = ("awg", "tls", "routing")

    def __init__(self, app=None):
        self.app = app
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()

    def _tests_ddl(self):
        return '''
            CREATE TABLE tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location TEXT,
                city TEXT,
                country TEXT,
                protocol TEXT,
                port INTEGER,
                awg TEXT NOT NULL DEFAULT '',
                tls TEXT NOT NULL DEFAULT '',
                routing TEXT NOT NULL DEFAULT '',
                status TEXT,
                duration REAL,
                ping REAL,
                packet_loss REAL,
                profile_name TEXT,
                timestamp TEXT,
                UNIQUE(location, city, country, protocol, port, awg, tls, routing)
            )
        '''

    def create_table(self):
        with self.lock:
            exists = self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tests'").fetchone()
            if not exists:
                self.cursor.execute(self._tests_ddl())
                self.conn.commit()
                return
            cols = [r[1] for r in self.cursor.execute("PRAGMA table_info(tests)").fetchall()]
            if "packet_loss" not in cols:
                self.cursor.execute("ALTER TABLE tests ADD COLUMN packet_loss REAL")
                cols.append("packet_loss")
            if set(self.TWEAK_COLUMNS) - set(cols):
                # Older unique keys did not include the tweak columns, which would collapse every
                # Amnezia/TLS/routing variant into one row. Recreate so each variant is its own row.
                tweaks = ", ".join(c if c in cols else "''" for c in self.TWEAK_COLUMNS)
                self.cursor.execute(self._tests_ddl().replace("CREATE TABLE tests", "CREATE TABLE tests_new", 1))
                self.cursor.execute(f'''
                    INSERT INTO tests_new
                    (location, city, country, protocol, port, awg, tls, routing, status, duration, ping,
                     packet_loss, profile_name, timestamp)
                    SELECT location, city, country, protocol, port, {tweaks}, status, duration, ping,
                           packet_loss, profile_name, timestamp FROM tests
                ''')
                self.cursor.execute("DROP TABLE tests")
                self.cursor.execute("ALTER TABLE tests_new RENAME TO tests")
            self.conn.commit()

    def record_result(self, location, city, country, proto, port, awg, tls, routing, status, duration, ping, loss,
                      profile_name):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            try:
                self.cursor.execute('''
                    INSERT OR REPLACE INTO tests
                    (location, city, country, protocol, port, awg, tls, routing, status, duration, ping,
                     packet_loss, profile_name, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (location, city, country, proto, port, awg or "", tls or "", routing or "", status,
                      round(duration, 2), ping, loss, profile_name, timestamp))
                self.conn.commit()
                return True
            except Exception as e:
                if self.app:
                    self.app.post(self.app.log_message, f"DB ERROR: {e}", "FAILURE")
                return False

    def get_row_count(self):
        with self.lock:
            try:
                self.cursor.execute("SELECT COUNT(*) FROM tests")
                return self.cursor.fetchone()[0]
            except Exception:
                return 0

    def is_tested(self, location, city, country, proto, port, awg="", tls="", routing=""):
        with self.lock:
            self.cursor.execute(
                "SELECT 1 FROM tests WHERE location=? AND city=? AND country=? AND protocol=? AND port=? "
                "AND awg=? AND tls=? AND routing=?",
                (location, city, country, proto, port, awg or "", tls or "", routing or ""))
            return self.cursor.fetchone() is not None

    def fetch_results(self):
        with self.lock:
            self.cursor.execute(
                "SELECT city, location, country, protocol, port, awg, tls, routing, status, duration, ping, "
                "packet_loss FROM tests ORDER BY id")
            return self.cursor.fetchall()

    def export_to_csv(self, current_profile_name="Manual"):
        try:
            os.makedirs(REPORTS_DIR, exist_ok=True)
        except OSError as e:
            return -1, f"Failed to create directory: {e}"

        max_id = 0
        for f in os.listdir(REPORTS_DIR):
            if f.endswith(".csv"):
                head = f.split("_")[0]
                if head.isdigit():
                    max_id = max(max_id, int(head))

        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_profile = "".join(c for c in current_profile_name if c.isalnum() or c in (" ", "-", "_")).strip()
        safe_profile = safe_profile.replace(" ", "_") or "Manual"
        csv_file = os.path.join(REPORTS_DIR, f"{max_id + 1}_{safe_profile}_{ts}.csv")

        with self.lock:
            self.cursor.execute(f"SELECT {', '.join(self.EXPORT_COLUMNS)} FROM tests ORDER BY id")
            rows = self.cursor.fetchall()

        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(self.EXPORT_COLUMNS)
                writer.writerows(rows)
            return len(rows), csv_file
        except PermissionError:
            return -1, "File Open Error - Close the file if open."

    def clear_db(self):
        with self.lock:
            self.cursor.execute("DELETE FROM tests")
            self.conn.commit()


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
class WindscribeWorker:
    # Steps of one test, as shown in the UI.
    DISCONNECT, CONNECT, SETTLE, PING = range(4)

    def __init__(self, app_instance, cli_cmd=None):
        self.app = app_instance
        self.db = DatabaseManager(app=app_instance)
        self.pinger = PingRunner()
        self.stop_event = threading.Event()
        self.running = False
        self.cli_argv = cli_cmd if isinstance(cli_cmd, list) else (resolve_cli(cli_cmd or DEFAULT_CLI) or [DEFAULT_CLI])
        self._tweaks_applied = None
        self._conf_backup = None  # conf text before this job's first write; restored when the job ends

    # -- helpers (all UI access goes through app.post, never touches widgets directly) --
    def log(self, msg, tag="INFO"):
        self.app.post(self.app.log_message, msg, tag)

    def phase(self, idx, state, secs=None):
        self.app.post(self.app.set_phase, idx, state, secs)

    def run_argv(self, argv, timeout=30, stdin=None):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    input=stdin, timeout=timeout, **hidden_process_kwargs())
            return result.returncode, result.stdout
        except subprocess.TimeoutExpired:
            return -1, ""
        except Exception as e:
            self.log(f"CLI Error: {e}", "FAILURE")
            return -1, ""

    def run_cli(self, args, timeout=30):
        return self.run_argv(list(self.cli_argv) + args, timeout=timeout)

    def write_conf(self, text):
        prefix = wsl_prefix(self.cli_argv) or []
        code, _out = self.run_argv(prefix + _WRITE_CONF, timeout=20, stdin=text)
        if code != 0:
            self.log("Could not write windscribe_cli.conf", "FAILURE")
            return False
        # shortcut: the CLI reloads the conf from a file watcher and a routing change refetches the API
        # session; 0.5 s is enough locally. Bump it if alternate-routing tests fail only on the first try.
        self.stop_event.wait(0.5)
        return True

    def apply_tweaks(self, awg, tls, routing):
        """Write the Linux CLI conf so the next connect uses these tweaks (all empty = Windscribe defaults)."""
        tweaks = (awg or "", tls or "", routing or "")
        if self._tweaks_applied == tweaks:
            return True
        if not linux_cli(self.cli_argv):
            if any(tweaks):
                self.log("Censorship tweaks need the Linux windscribe-cli.", "FAILURE")
                return False
            return True
        prefix = wsl_prefix(self.cli_argv) or []
        code, current = self.run_argv(prefix + _READ_CONF, timeout=20)
        if code != 0:
            self.log("Could not read windscribe_cli.conf", "FAILURE")
            return False
        if self._conf_backup is None:
            self._conf_backup = current
        if not self.write_conf(patch_conf(current, *tweaks)):
            return False
        self._tweaks_applied = tweaks
        return True

    def restore_conf(self):
        if self._conf_backup is not None and self.write_conf(self._conf_backup):
            self.log("Restored windscribe_cli.conf", "INFO")
        self._conf_backup = None
        self._tweaks_applied = None

    @staticmethod
    def is_connected_output(out):
        up = out.upper()
        return "CONNECTED" in up and "DISCONNECTED" not in up and "CONNECTING" not in up

    def ensure_disconnected(self):
        for _ in range(5):
            _, out = self.run_cli(["status"])
            if "DISCONNECTED" in out.upper():
                return True
            self.run_cli(["firewall", "off"])
            self.run_cli(["disconnect"])
            if self.stop_event.wait(3):
                break
        _, out = self.run_cli(["status"])
        return "DISCONNECTED" in out.upper()

    def wait_for_connection(self, start_time, timeout):
        while time.time() - start_time < timeout:
            _, out = self.run_cli(["status"])
            if self.is_connected_output(out):
                return True, time.time() - start_time
            if self.stop_event.wait(1):
                return False, 0.0
        return False, 0.0

    # -- job control --
    def start(self, work_plan, opts):
        self.stop_event.clear()
        self.running = True
        threading.Thread(target=self._run, args=(work_plan, opts), daemon=True).start()

    def stop(self):
        self.stop_event.set()
        self.log("Stopping after the current step...", "WARN")

    def connect_to(self, result, timeout):
        """Connects to a single route picked from the results."""
        self.stop_event.clear()
        self.running = True
        threading.Thread(target=self._connect_one, args=(result, timeout), daemon=True).start()

    def disconnect(self):
        self.stop_event.clear()
        self.running = True
        threading.Thread(target=self._disconnect, daemon=True).start()

    def _connect_one(self, r, timeout):
        connected = False
        route = route_label(r)
        try:
            self.log(f"Connecting to {r['city']} via {route}", "HEADER")
            self.phase(self.DISCONNECT, "active")
            t0 = time.time()
            if not self.ensure_disconnected():
                self.phase(self.DISCONNECT, "fail")
                self.log("Could not disconnect the current session first.", "FAILURE")
                return
            self.phase(self.DISCONNECT, "done", time.time() - t0)
            if not self.apply_tweaks(r.get("awg"), r.get("tls"), r.get("routing")):
                self.phase(self.CONNECT, "fail")
                return
            self.phase(self.CONNECT, "active")
            start_ts = time.time()
            self.run_cli(["connect", "-n", r["city"], f"{r['proto']}:{r['port']}"], timeout=timeout + 15)
            connected, duration = self.wait_for_connection(start_ts, timeout)
            if connected:
                self.phase(self.CONNECT, "done", duration)
                self.log(f"Connected to {r['city']} via {route} in {duration:.1f}s", "SUCCESS")
            else:
                self.phase(self.CONNECT, "fail")
                self.log(f"Could not connect to {r['city']} via {route}", "FAILURE")
        except Exception as e:
            self.log(f"Critical Error: {e}", "FAILURE")
        finally:
            if not connected:
                self.restore_conf()
            self.running = False
            self.app.post(self.app.manual_connect_finished, r, connected)

    def _disconnect(self):
        done = False
        try:
            done = self.ensure_disconnected()
            self.log("Disconnected." if done else "Could not disconnect.", "INFO" if done else "FAILURE")
            if done:
                self.restore_conf()
        finally:
            self.running = False
            self.app.post(self.app.disconnect_finished, done)

    def _build_tasks(self, work_plan, opts):
        keys = opts["keys"]
        locations = [l for l in LocationManager.load_locations() if not keys or loc_key(l) in keys]
        if opts["random_cities"]:
            random.shuffle(locations)
        routes = expand_routes(work_plan, opts.get("awg_presets") or [], opts.get("tls_mode", "off"),
                               opts.get("routing_mode", "auto"))
        tasks = [(loc,) + route for loc in locations for route in routes]
        if opts["chaos_mode"]:
            random.shuffle(tasks)
        return locations, tasks

    def _run(self, work_plan, opts):
        kept_connection = None
        ok = fail = executed = 0
        try:
            locations, tasks = self._build_tasks(work_plan, opts)
            if not locations:
                self.log(f"No locations match the selection (or locations.json is missing at {LOCATIONS_FILE})",
                         "FAILURE")
                return

            total = len(tasks)
            self.log(f"Queued {len(locations)} locations, {total} tests", "HEADER")

            for i, (loc, proto, port, awg, tls, routing) in enumerate(tasks, 1):
                if self.stop_event.is_set():
                    break

                city, node, country = loc["city"], loc["location"], loc["country"]
                key = (node, city, country, proto, port, awg, tls, routing)
                route = route_label({"proto": proto, "port": port, "awg": awg, "tls": tls, "routing": routing})

                if opts["resume"] and self.db.is_tested(*key):
                    continue

                executed += 1
                self.app.post(self.app.begin_test, i, total, executed, city, node, country, route)
                self.log(f"[{i}/{total}] {city} ({country}) via {route}", "HEADER")

                self.phase(self.DISCONNECT, "active")
                t0 = time.time()
                if not self.ensure_disconnected():
                    self.phase(self.DISCONNECT, "fail")
                    self.log("Could not disconnect, skipping this test.", "FAILURE")
                    continue
                self.phase(self.DISCONNECT, "done", time.time() - t0)
                if self.stop_event.is_set():
                    break

                if not self.apply_tweaks(awg, tls, routing):
                    # One broken conf write would fail every remaining test the same way; stop instead.
                    self.phase(self.CONNECT, "fail")
                    self.log("Could not apply censorship tweaks, stopping.", "FAILURE")
                    break

                self.phase(self.CONNECT, "active")
                start_ts = time.time()
                self.run_cli(["connect", "-n", city, f"{proto}:{port}"], timeout=opts["timeout"] + 15)
                self.stop_event.wait(1)

                _, status_out = self.run_cli(["status"])
                if "Location does not exist" in status_out or "is disabled" in status_out:
                    self.phase(self.CONNECT, "fail")
                    self.log(f"{city} is unavailable, skipping.", "FAILURE")
                    self.db.record_result(*key, "INVALID_LOC", 0, None, None, opts["profile_name"])
                    self.app.post(self.app.add_result_row, city, node, country, proto, port, awg, tls, routing,
                                  "INVALID_LOC", 0, None, None)
                    fail += 1
                    continue

                connected, duration = self.wait_for_connection(start_ts, opts["timeout"])

                # User pressed Stop while we were still connecting: undo and leave, don't record a bogus failure.
                if self.stop_event.is_set() and not connected:
                    self.run_cli(["disconnect"])
                    self.log("Stopped while connecting; this test was not recorded.", "WARN")
                    break

                ping_avg = loss = None
                status_str = "FAILURE"
                if connected:
                    status_str = "SUCCESS"
                    ok += 1
                    self.phase(self.CONNECT, "done", duration)
                    self.log(f"Connected in {duration:.2f}s", "SUCCESS")

                    if opts["settle"] > 0:
                        self.phase(self.SETTLE, "active")
                        self.stop_event.wait(opts["settle"])
                        self.phase(self.SETTLE, "done", opts["settle"])
                    else:
                        self.phase(self.SETTLE, "skip")

                    self.phase(self.PING, "active")
                    t0 = time.time()
                    result, err = self.pinger.run(opts["ping_host"], opts["ping_count"],
                                                  wsl=wsl_prefix(self.cli_argv))
                    self.phase(self.PING, "done" if result else "fail", time.time() - t0)
                    self.app.post(self.app.set_ping, result)
                    if result:
                        ping_avg, loss = result["avg"], result["loss"]
                        self.log(f"Ping avg {ping_avg:.0f} ms (min {result['min']:.0f} / max {result['max']:.0f}), "
                                 f"loss {loss:.0f}%", "INFO")
                    else:
                        self.log(f"Ping failed: {err}", "WARN")
                else:
                    fail += 1
                    self.phase(self.CONNECT, "fail", opts["timeout"])
                    self.log(f"Timed out on {route}", "FAILURE")

                self.db.record_result(*key, status_str, duration, ping_avg, loss, opts["profile_name"])
                self.app.post(self.app.add_result_row, city, node, country, proto, port, awg, tls, routing,
                              status_str, duration, ping_avg, loss)

                if connected and opts["stop_on_success"]:
                    kept_connection = f"{loc_name(city, node)} · {route}"
                    self.log(f"Stop on success: staying connected to {kept_connection}.", "SUCCESS")
                    break

                self.run_cli(["disconnect"])
                self.stop_event.wait(2)

        except Exception as e:
            self.log(f"Critical Error: {e}", "FAILURE")
        finally:
            if not kept_connection:
                self.restore_conf()
            self.running = False
            self.app.post(self.app.job_finished, kept_connection, ok, fail)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------
SCALE = 1.0  # CustomTkinter's window scaling, set once the window exists
_FONT_CACHE = {}


def measure(font, text):
    """Pixel width of text in a CustomTkinter font tuple (CustomTkinter sizes fonts in scaled pixels)."""
    font = tuple(font or (SANS, 13))
    f = _FONT_CACHE.get(font)
    if f is None:
        f = tkfont.Font(family=font[0], size=-round(font[1] * SCALE),
                        weight="bold" if "bold" in font[2:] else "normal")
        _FONT_CACHE[font] = f
    return f.measure(text)


def display_text(text, wraplength=0, font=None, px_width=None):
    """Text as it should be handed to Tk: Farsi is wrapped in reading order, then put in display order."""
    if not i18n.RTL or not isinstance(text, str) or not text:
        return text
    width = px_width or (wraplength * SCALE if wraplength else 0)
    if width:
        text = i18n.wrap(text, lambda s: measure(font, s), width)
    return vis(text)


def _hook_text(cls, keys=("text",)):
    """Runs every text a widget class displays through display_text(), so call sites pass plain strings."""
    original_init, original_configure = cls.__init__, cls.configure

    def __init__(self, *args, **kw):
        wrap_len = kw.get("wraplength", 0)
        if i18n.RTL:
            for key in keys:
                if key in kw:
                    kw[key] = display_text(kw[key], wrap_len, kw.get("font"))
            if wrap_len:
                kw["wraplength"] = 0  # already wrapped; Tk would re-wrap the display-order text from the wrong end
        original_init(self, *args, **kw)
        self._i18n_wrap, self._i18n_font = wrap_len, kw.get("font")

    def configure(self, require_redraw=False, **kw):
        if i18n.RTL:
            if "font" in kw:
                self._i18n_font = kw["font"]
            for key in keys:
                if key in kw:
                    kw[key] = display_text(kw[key], getattr(self, "_i18n_wrap", 0), getattr(self, "_i18n_font", None))
        return original_configure(self, require_redraw=require_redraw, **kw)

    cls.__init__, cls.configure = __init__, configure


_hook_text(ctk.CTkLabel)
_hook_text(ctk.CTkButton)
_hook_text(ctk.CTkEntry, keys=("placeholder_text",))


# Layout direction. Farsi mirrors the whole window, so every "left"/"right" goes through these.
def start():
    return "right" if i18n.RTL else "left"


def end():
    return "left" if i18n.RTL else "right"


def a_start():
    return "e" if i18n.RTL else "w"


def a_end():
    return "w" if i18n.RTL else "e"


def pads(first, second):
    """(start, end) padding, mirrored for RTL."""
    return (second, first) if i18n.RTL else (first, second)


def gcol(i, n):
    return n - 1 - i if i18n.RTL else i


def justify():
    return "right" if i18n.RTL else "left"


def frame(parent, **kw):
    kw.setdefault("fg_color", "transparent")
    return ctk.CTkFrame(parent, corner_radius=kw.pop("corner_radius", 0), **kw)


def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=kw.pop("fg_color", CARD), corner_radius=kw.pop("corner_radius", 14),
                        border_width=1, border_color=kw.pop("border_color", BORDER), **kw)


def caps(parent, text, color=MUTED):
    return ctk.CTkLabel(parent, text=text.upper(), font=sans(10, True), text_color=color, anchor=a_start())


def label(parent, text="", size=12, color=TEXT, bold=False, font=None, **kw):
    kw.setdefault("justify", justify())
    return ctk.CTkLabel(parent, text=text, font=font or sans(size, bold), text_color=kw.pop("text_color", color),
                        anchor=kw.pop("anchor", a_start()), **kw)


def divider(parent):
    return ctk.CTkFrame(parent, fg_color=BORDER, height=1, corner_radius=0)


def ghost_button(parent, text, command, width=70, height=32, font=None, **kw):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height,
                         corner_radius=kw.pop("corner_radius", 8), fg_color=kw.pop("fg_color", CARD),
                         border_width=1, border_color=kw.pop("border_color", BORDER_2), hover_color=HOVER,
                         text_color=kw.pop("text_color", TEXT), text_color_disabled=DIM,
                         font=font or sans(12), **kw)


def icon_button(parent, name, command, size=32, icon_size=13, **kw):
    return ghost_button(parent, icon(name), command, width=size, height=size, font=icon_font(icon_size), **kw)


def primary_button(parent, text, command, width=140, height=40, **kw):
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height, corner_radius=9,
                         fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                         text_color_disabled="#3B5870", font=sans(13, True), **kw)


def chip(parent, text=""):
    return ctk.CTkLabel(parent, text=f" {text} ", font=mono(11), fg_color=CHIP, text_color=CHIP_TEXT,
                        corner_radius=6, height=22)


def entry(parent, height=34, size=12, rtl_text=True, **kw):
    """Entry box; text the user types in their language is right-aligned in Farsi, paths and numbers are not."""
    return ctk.CTkEntry(parent, height=height, fg_color=kw.pop("fg_color", INPUT), border_color=BORDER_2,
                        font=sans(size), justify="right" if i18n.RTL and rtl_text else "left", **kw)


class Bar(ctk.CTkProgressBar):
    """Progress bar that fills from the right in Farsi (by swapping the fill and track colours)."""

    def __init__(self, parent, track, fill, **kw):
        self._track, self._fill, self._value = track, fill, 0.0
        super().__init__(parent, fg_color=track, progress_color=fill, **kw)
        self.show(0.0, fill)

    def show(self, value, color=None):
        self.stop()
        self.configure(mode="determinate")
        self._fill = color or self._fill
        self._value = value
        if i18n.RTL:
            self.configure(fg_color=self._fill, progress_color=self._track)
            self.set(1.0 - value)
        else:
            self.configure(fg_color=self._track, progress_color=self._fill)
            self.set(value)

    def busy(self, color):
        self.configure(mode="indeterminate", fg_color=self._track, progress_color=color)
        self.start()


def make_dot(color, size=14, radius=4.0):
    img = tk.PhotoImage(width=size, height=size)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            if (x - c) ** 2 + (y - c) ** 2 <= radius ** 2:
                img.put(color, (x, y))
    return img


def bind_click(widgets, command):
    for w in widgets:
        w.bind("<Button-1>", lambda _e: command(), add="+")


def ask_yes_no(parent, title, message):
    message = display_text(message, px_width=380, font=(SANS, 12)) if i18n.RTL else message
    return messagebox.askyesno(vis(title), message, parent=parent)


class Tooltip:
    """Small hover hint. Works with plain Tk and CustomTkinter widgets."""

    def __init__(self, widget, text, delay=450):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self.job = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def _show(self):
        if self.tip or not self.text:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(bg=BORDER_2)
        width = int(280 * SCALE)
        text = display_text(self.text, px_width=width, font=(SANS, 12)) if i18n.RTL else self.text
        tk.Label(self.tip, text=text, bg=INPUT, fg=TEXT, font=sans(9), justify=justify(),
                 wraplength=0 if i18n.RTL else width, padx=9, pady=6).pack(padx=1, pady=1)
        self.tip.update_idletasks()
        x = self.widget.winfo_rootx() + 10
        if i18n.RTL:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() - self.tip.winfo_reqwidth() - 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip.wm_geometry(f"+{max(0, x)}+{y}")

    def _hide(self, _=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None


def place_dialog(dialog, app, w, h, top=80):
    x = app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)
    y = app.winfo_rooty() + top
    dialog.geometry(f"{w}x{h}+{x}+{y}")
    dialog.configure(fg_color=BG)
    dialog.transient(app)

    def grab():
        try:
            dialog.focus()
            dialog.grab_set()
        except tk.TclError:
            pass

    dialog.after(150, grab)


def tree_heading(tree, key, text, anchor):
    tree.heading(key, text=vis(text), anchor=anchor)


# ---------------------------------------------------------------------------
# Location picker - search and pick countries, cities and servers
# ---------------------------------------------------------------------------
class LocationPicker(ctk.CTkToplevel):
    def __init__(self, app, locations, selected, on_done):
        super().__init__(app)
        self.app, self.on_done = app, on_done
        self.selected = set(selected)
        self.region = "All"
        self.item_keys = {}
        self.country_items = set()

        self.title(vis(t("choose_locations")))
        place_dialog(self, app, 560, 700, top=40)
        self.minsize(460, 520)

        head = frame(self)
        head.pack(fill="x", padx=22, pady=(18, 0))
        title_row = frame(head)
        title_row.pack(fill="x")
        label(title_row, t("choose_locations"), 18, bold=True).pack(side=start())
        self.btn_update = ghost_button(title_row, t("update_list"), app.update_locations,
                                       width=app.text_width(t("updating"), sans(12)) + 28, height=30)
        self.btn_update.pack(side=end())
        Tooltip(self.btn_update, t("update_tip"))
        label(head, t("picker_hint"), 11, MUTED, wraplength=500).pack(anchor=a_start(), fill="x", pady=(2, 0))

        self.entry = entry(self, height=40, size=13, placeholder_text=t("search_locations"))
        self.entry.pack(fill="x", padx=22, pady=(14, 0))
        self.entry.bind("<KeyRelease>", self._on_search)
        self.entry.bind("<Down>", lambda _e: self._focus_tree())
        self.entry.bind("<Return>", lambda _e: self.done())

        self.chips = frame(self)
        self.chips.pack(fill="x", padx=22, pady=(10, 0))
        self.region_buttons = {}

        box = card(self, corner_radius=12)
        box.pack(fill="both", expand=True, padx=22, pady=(6, 0))
        box.grid_columnconfigure(gcol(0, 2), weight=1)
        box.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(box, columns=("sel",), show="tree", style="Pick.Treeview", selectmode="browse")
        self.tree.column("#0", width=360, stretch=True, anchor=a_start())
        self.tree.column("sel", width=96, anchor="center", stretch=False)
        self.tree.tag_configure("country", font=sans(10, True))
        self.tree.tag_configure("on", foreground=ACCENT)
        self.tree.tag_configure("empty", foreground=MUTED)
        sb = ctk.CTkScrollbar(box, command=self.tree.yview, button_color=BORDER_2, button_hover_color=HOVER)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=gcol(0, 2), sticky="nsew", padx=pads(8, 0), pady=8)
        sb.grid(row=0, column=gcol(1, 2), sticky="ns", padx=pads(0, 4), pady=8)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", lambda _e: "break")
        self.tree.bind("<space>", lambda _e: self._toggle_focused())
        self.tree.bind("<Return>", lambda _e: self.done())

        self.lbl_count = label(self, "", 12, TEXT_2)
        self.lbl_count.pack(fill="x", padx=24, pady=(10, 0))
        foot = frame(self)
        foot.pack(fill="x", padx=22, pady=(8, 18))
        ghost_button(foot, t("select_shown"), self.select_shown,
                     width=app.text_width(t("select_shown"), sans(12)) + 28, height=36).pack(side=start())
        ghost_button(foot, t("clear"), self.clear, width=70, height=36).pack(side=start(), padx=pads(6, 0))
        primary_button(foot, t("done"), self.done, width=100, height=36).pack(side=end())
        ghost_button(foot, t("cancel"), self.close, width=80, height=36).pack(side=end(), padx=pads(0, 8))

        self.bind("<Escape>", lambda _e: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(200, self.entry.focus_set)
        self.set_locations(locations)

    def set_locations(self, locations):
        """(Re)loads the server list, e.g. after it was downloaded again."""
        self.total = len(locations)
        self.by_country = {}
        for l in sorted(locations, key=lambda l: (l["country"].lower(), l["city"].lower(), l["location"].lower())):
            self.by_country.setdefault(l["country"], []).append(l)
        self.selected &= {loc_key(l) for l in locations}

        for w in self.chips.winfo_children():
            w.destroy()
        self.region_buttons = {}
        regions = ["All"] + sorted({l["continent"] for l in locations})
        if any(l["country"].startswith("US ") for l in locations):
            regions.append("USA")
        line = None
        for i, region in enumerate(regions):
            if i % 5 == 0:
                line = frame(self.chips)
                line.pack(fill="x", pady=(0, 6))
            name = i18n.region_name(region)
            b = ctk.CTkButton(line, text=name, height=28, width=self.app.text_width(name, sans(11)) + 26,
                              corner_radius=14, border_width=1, font=sans(11), hover_color=HOVER,
                              command=lambda r=region: self.set_region(r))
            b.pack(side=start(), padx=pads(0, 6))
            self.region_buttons[region] = b
        self.set_region(self.region if self.region in self.region_buttons else "All")

    # -- data --
    def _matches(self):
        tokens = self.entry.get().lower().split()
        out = []
        for country, locs in self.by_country.items():
            locs = [l for l in locs if matches_region(l, self.region)]
            if not locs:
                continue
            if tokens:
                country_hay = f"{country} {locs[0]['continent']} {i18n.region_name(locs[0]['continent'])}".lower()
                if not all(tok in country_hay for tok in tokens):
                    locs = [l for l in locs if all(
                        tok in f"{country} {l['continent']} {l['city']} {l['location']}".lower() for tok in tokens)]
            if locs:
                out.append((country, locs))
        return out, bool(tokens)

    # -- rendering --
    def render(self):
        self.tree.delete(*self.tree.get_children())
        self.item_keys.clear()
        self.country_items.clear()
        matches, searching = self._matches()
        pad = "" if i18n.RTL else "  "
        for country, locs in matches:
            cid = self.tree.insert("", "end", text=f"{pad}{country}", open=searching or len(matches) == 1,
                                   tags=("country",))
            self.country_items.add(cid)
            self.item_keys[cid] = [loc_key(l) for l in locs]
            for l in locs:
                iid = self.tree.insert(cid, "end", text=f"{pad}{loc_name(l['city'], l['location'])}")
                self.item_keys[iid] = [loc_key(l)]
        if not matches:
            self.tree.insert("", "end", text=f"{pad}{vis(t('no_match_locations'))}", tags=("empty",))
        self.refresh_marks()

    def refresh_marks(self):
        for iid, keys in self.item_keys.items():
            n = sum(k in self.selected for k in keys)
            if iid in self.country_items:
                mark = "☑" if n == len(keys) else "▣" if n else "☐"
                count = f"{n}/{len(keys)}" if n else str(len(keys))
                text = f"{count}   {mark}" if i18n.RTL else f"{mark}   {count}"
                self.tree.item(iid, values=(text,), tags=("country", "on") if n else ("country",))
            else:
                self.tree.item(iid, values=("☑" if n else "☐",), tags=("on",) if n else ())
        n = len(self.selected)
        self.lbl_count.configure(text=t("n_selected", n=num(n), total=num(self.total)) if n
                                 else t("nothing_selected", total=num(self.total)))

    def set_region(self, region):
        self.region = region
        for name, b in self.region_buttons.items():
            active = name == region
            b.configure(fg_color=ACCENT_SOFT if active else "transparent",
                        border_color=ACCENT_LINE if active else BORDER_2,
                        text_color=TEXT if active else TEXT_2)
        self.render()

    # -- interaction --
    def _on_search(self, event):
        if event.keysym in ("Down", "Return", "Escape"):
            return
        self.render()

    def _focus_tree(self):
        children = self.tree.get_children()
        if children:
            self.tree.focus_set()
            self.tree.focus(children[0])
            self.tree.selection_set(children[0])

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self.item_keys:
            return None
        if "indicator" in self.tree.identify_element(event.x, event.y):
            return None  # let the tree expand/collapse
        if iid in self.country_items and self.tree.identify_column(event.x) == "#0":
            self.tree.item(iid, open=not self.tree.item(iid, "open"))
        else:
            self.toggle(iid)
        self.tree.focus(iid)
        self.tree.selection_set(iid)
        return "break"

    def _toggle_focused(self):
        iid = self.tree.focus()
        if iid in self.item_keys:
            self.toggle(iid)
        return "break"

    def toggle(self, iid):
        keys = self.item_keys[iid]
        if all(k in self.selected for k in keys):
            self.selected.difference_update(keys)
        else:
            self.selected.update(keys)
        self.refresh_marks()

    def select_shown(self):
        for iid in self.country_items:
            self.selected.update(self.item_keys[iid])
        self.refresh_marks()

    def clear(self):
        self.selected.clear()
        self.refresh_marks()

    def done(self):
        self.on_done(set(self.selected))
        self.close()

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class App(ctk.CTk):
    # (key, title string, width, numeric)
    RESULT_COLUMNS = [("#0", "col_location", 210, False), ("country", "col_country", 120, False),
                      ("route", "col_route", 118, False), ("status", "col_result", 120, False),
                      ("time", "col_connect", 70, True), ("ping", "col_ping", 70, True),
                      ("loss", "col_loss", 60, True)]
    BEST_COLUMNS = [("#0", "col_location", 260, False), ("country", "col_country", 130, False),
                    ("route", "col_route", 120, False), ("ping", "col_ping", 76, True),
                    ("loss", "col_loss", 64, True), ("time", "col_connect", 80, True)]
    SORT_KEYS = {
        "#0": lambda r: (r["city"].lower(), r["node"].lower()),
        "country": lambda r: r["country"].lower(),
        "route": lambda r: (r["proto"], r["port"], r["awg"], r["tls"], r["routing"]),
        "status": lambda r: r["status"],
        "time": lambda r: r["duration"] if r["status"] == "SUCCESS" else float("inf"),
        "ping": lambda r: r["ping"] if r["ping"] is not None else float("inf"),
        "loss": lambda r: r["loss"] if r["loss"] is not None else float("inf"),
    }
    PHASES = ["phase_disconnect", "phase_connect", "phase_settle", "phase_ping"]
    VIEWS = ["Results", "Best routes", "Log"]
    VIEW_KEYS = {"Results": "tab_results", "Best routes": "tab_best", "Log": "tab_log"}
    FILTER_KEYS = {"All": "filter_all", "Connected": "filter_connected", "Failed": "filter_failed"}

    def __init__(self):
        global SCALE
        self.config_data = ConfigManager.load_config()
        if not self.config_data.get("language"):
            self.config_data["language"] = i18n.detect_language()
        i18n.set_language(self.config_data["language"])
        _FONT_CACHE.clear()

        super().__init__()
        init_fonts(self)
        try:
            self.scale = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            self.scale = 1.0
        SCALE = self.scale
        self.relaunch = False
        self.title(APP_NAME)
        self.geometry("1280x860")
        self.minsize(1100, 720)
        self.configure(fg_color=BG)

        self._ui_queue = queue.Queue()
        self._toast = None
        self._picker = None
        self.protocol_vars = {}
        self.port_vars = {}
        self.port_buttons = {}
        self.results = []
        self.sort_col = None
        self.sort_desc = False
        self.result_filter = "All"
        self.view = "Results"
        self.step = None
        self.run = None
        self.connected_to = None
        self.timing_open = False

        self.last_settings = self.config_data.get("last_settings", {})
        self.saved_profiles = self.config_data.get("saved_profiles", {})
        self.priority_order = self.sanitize_priority(self.last_settings.get("priority_order"))
        self.current_profile_name = "Manual"
        self.locations = LocationManager.load_locations()
        self.all_keys = {loc_key(l) for l in self.locations}
        self.selected_keys = set()
        self.sidebar_open = bool(self.config_data.get("sidebar_open", True))

        size, radius = max(10, int(14 * self.scale)), 4.0 * self.scale
        self.dots = {"SUCCESS": make_dot(GOOD, size, radius), "FAILURE": make_dot(BAD, size, radius),
                     "INVALID_LOC": make_dot(WARN, size, radius), "fast": make_dot(GOOD, size, radius),
                     "medium": make_dot(WARN, size, radius), "slow": make_dot(BAD, size, radius)}

        self.init_vars()
        self.setup_ui()
        self._cli_ok = None  # argv tuple that last passed cli_probe
        self.worker = WindscribeWorker(self, resolve_cli(self.entry_cli.get()) or DEFAULT_CLI)
        self.apply_config_to_ui(self.last_settings)
        self.reload_results_table()
        self.refresh_cli_status()
        self.refresh_locations_info()
        self.restore_window()
        self.bind_shortcuts()
        self.apply_sidebar_state()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(60, self._drain_ui_queue)
        self.after(1000, self._tick)

    # ---------------- thread-safe UI bridge ----------------
    def post(self, fn, *args, **kwargs):
        """Called from the worker thread; the callable runs on the Tk main thread."""
        self._ui_queue.put((fn, args, kwargs))

    def _drain_ui_queue(self):
        try:
            while True:
                fn, args, kwargs = self._ui_queue.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    print(f"UI error: {e}")
        except queue.Empty:
            pass
        self.after(60, self._drain_ui_queue)

    # ---------------- data ----------------
    @staticmethod
    def sanitize_priority(order):
        order = [p for p in (order or []) if p in DEFAULT_PROTOCOLS]
        return order + [p for p in DEFAULT_PROTOCOLS if p not in order]

    def init_vars(self):
        saved_protocols = self.last_settings.get("protocols", {})
        for proto, ports in DEFAULT_PROTOCOLS.items():
            self.protocol_vars[proto] = ctk.BooleanVar(value=saved_protocols.get(proto, {}).get("enabled", True))
            self.protocol_vars[proto].trace_add("write", lambda *_: self.update_scope_preview(user_change=True))
            self.port_vars[proto] = {}
            saved_ports = saved_protocols.get(proto, {}).get("ports", {})
            for port in ports:
                self.port_vars[proto][port] = ctk.BooleanVar(value=saved_ports.get(str(port), True))
        self.load_tweaks(self.last_settings)

    def load_tweaks(self, s):
        saved_awg = list(s.get("awg_presets") or [])
        self.awg_order = saved_awg
        self.awg_enabled = set(saved_awg)
        self.tls_mode = s.get("tls_mode") if s.get("tls_mode") in TLS_VALUES else "off"
        self.routing_mode = s.get("routing_mode") if s.get("routing_mode") in ROUTING_VALUES else "auto"

    def text_width(self, text, font):
        """Width in CustomTkinter's unscaled units."""
        return int(measure(font, text) / self.scale)

    def worker_running(self):
        return hasattr(self, "worker") and self.worker.running

    def scope_locations(self):
        if not self.selected_keys:
            return self.locations
        return [l for l in self.locations if loc_key(l) in self.selected_keys]

    @staticmethod
    def servers_in(n, countries):
        if countries == 1:
            return t("servers_in_one", n=num(n))
        return t("servers_in", n=num(n), c=num(countries))

    def scope_summary(self):
        """(title, subtitle) describing the selected locations."""
        if not self.selected_keys:
            return t("all_servers"), self.servers_in(len(self.locations), len({l["country"] for l in self.locations}))
        chosen = self.scope_locations()
        names, covered = [], set()
        for continent in sorted({l["continent"] for l in self.locations}):
            group = [l for l in self.locations if l["continent"] == continent]
            if all(loc_key(l) in self.selected_keys for l in group):
                names.append(i18n.region_name(continent))
                covered.update(l["country"] for l in group)
        for country in sorted({l["country"] for l in chosen} - covered):
            group = [l for l in self.locations if l["country"] == country]
            if all(loc_key(l) in self.selected_keys for l in group):
                names.append(country)
            else:
                names.extend(sorted({l["city"] for l in chosen if l["country"] == country}))
        sep = "، " if i18n.RTL else ", "
        title = sep.join(names[:2]) + (t("more", n=len(names) - 2) if len(names) > 2 else "")
        return title, self.servers_in(len(chosen), len({l["country"] for l in chosen}))

    # ---------------- layout ----------------
    def setup_ui(self):
        self.grid_columnconfigure(gcol(1, 2), weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.setup_tree_styles()
        self.build_sidebar()
        self.build_rail()
        self.build_main()

    def setup_tree_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        row_h = int(32 * self.scale)
        for name, bg in (("AS", CARD), ("Pick", CARD)):
            style.configure(f"{name}.Treeview", background=bg, fieldbackground=bg, foreground=TEXT, borderwidth=0,
                            rowheight=row_h, font=sans(10), indent=int(18 * self.scale))
            style.map(f"{name}.Treeview", background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
            style.layout(f"{name}.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("AS.Treeview.Heading", background=CARD, foreground=MUTED, relief="flat", borderwidth=0,
                        font=sans(9, True), padding=(8, 8))
        style.map("AS.Treeview.Heading", background=[("active", HOVER)], foreground=[("active", TEXT)])
        style.configure("Treeitem.indicator", foreground=MUTED)

    def draw_logo(self, parent):
        box = ctk.CTkFrame(parent, width=34, height=34, corner_radius=9, fg_color="#16202B", border_width=1,
                           border_color="#27384A")
        box.grid_propagate(False)
        s = self.scale
        size = int(20 * s)
        c = tk.Canvas(box, width=size, height=size, bg="#16202B", highlightthickness=0, bd=0)
        c.place(relx=0.5, rely=0.5, anchor="center")
        cx, cy = size / 2, size * 0.85
        for r in (4.5, 9, 13.5):
            r *= s
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=45, extent=90, style="arc", outline=ACCENT,
                         width=max(2, int(2 * s)))
        d = 1.4 * s
        c.create_oval(cx - d, cy - d, cx + d, cy + d, fill=ACCENT, outline=ACCENT)
        return box

    def edge_line(self, panel):
        """1px border on the side of the sidebar that faces the content."""
        ctk.CTkFrame(panel, fg_color=BORDER, width=1, height=1, corner_radius=0).place(
            relx=0.0 if i18n.RTL else 1.0, rely=0, relheight=1, anchor="nw" if i18n.RTL else "ne")

    # ---- sidebar ----
    def build_sidebar(self):
        side = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, width=320)
        side.grid(row=0, column=gcol(0, 2), sticky="nsew")
        side.grid_propagate(False)
        side.grid_rowconfigure(1, weight=1)
        side.grid_columnconfigure(0, weight=1)
        self.edge_line(side)
        self.sidebar = side

        head = frame(side)
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        head.grid_columnconfigure(gcol(1, 3), weight=1)
        self.draw_logo(head).grid(row=0, column=gcol(0, 3), rowspan=2, padx=pads(0, 10))
        label(head, APP_NAME, 16, bold=True).grid(row=0, column=gcol(1, 3), sticky=a_start())
        label(head, t("tagline", v=APP_VERSION), 10, MUTED).grid(row=1, column=gcol(1, 3), sticky=a_start())
        btn = icon_button(head, "menu" if i18n.RTL else "collapse", self.toggle_sidebar, size=30,
                          fg_color="transparent", border_color=SIDEBAR)
        btn.grid(row=0, column=gcol(2, 3), rowspan=2)
        Tooltip(btn, t("hide_panel_tip"))

        scroll = ctk.CTkScrollableFrame(side, fg_color="transparent", corner_radius=0,
                                        scrollbar_button_color=BORDER_2, scrollbar_button_hover_color=HOVER)
        scroll.grid(row=1, column=0, sticky="nsew", padx=pads(0, 2))
        self.sidebar_scroll = scroll
        px = 16

        # --- Profile ---
        caps(scroll, t("profile")).pack(fill="x", padx=px, pady=(16, 6))
        row = frame(scroll)
        row.pack(fill="x", padx=px)
        self.combo_profiles = ctk.CTkComboBox(
            row, values=list(self.saved_profiles.keys()), command=self.load_profile, height=36, state="readonly",
            fg_color=INPUT, border_color=BORDER_2, button_color=INPUT, button_hover_color=HOVER,
            dropdown_fg_color=INPUT, dropdown_hover_color=HOVER, dropdown_text_color=TEXT, font=sans(12),
            dropdown_font=sans(12), justify=justify())
        self.combo_profiles.pack(side=start(), fill="x", expand=True)
        self.set_profile_placeholder()
        b = icon_button(row, "save", self.ask_profile_name, size=36, fg_color=INPUT)
        b.pack(side=start(), padx=pads(6, 0))
        Tooltip(b, t("save_profile_tip"))
        b = icon_button(row, "delete", self.delete_profile, size=36, fg_color=INPUT)
        b.pack(side=start(), padx=pads(6, 0))
        Tooltip(b, t("delete_profile_tip"))

        # --- Locations ---
        lh = frame(scroll)
        lh.pack(fill="x", padx=px, pady=(20, 6))
        caps(lh, t("locations")).pack(side=start())
        self.btn_update_list = ctk.CTkButton(lh, text=t("update_list"), command=self.update_locations, width=20,
                                             height=20, fg_color="transparent", hover_color=HOVER,
                                             text_color=ACCENT, text_color_disabled=MUTED, font=sans(11))
        self.btn_update_list.pack(side=end())
        self.tip_update_list = Tooltip(self.btn_update_list, "")
        sc = ctk.CTkFrame(scroll, fg_color=INPUT, corner_radius=10, border_width=1, border_color=BORDER_2)
        sc.pack(fill="x", padx=px)
        sc.grid_columnconfigure(gcol(0, 2), weight=1)
        self.lbl_scope_title = label(sc, "", 13, bold=True)
        self.lbl_scope_title.grid(row=0, column=gcol(0, 2), sticky=a_start(), padx=pads(12, 6), pady=(10, 0))
        self.lbl_scope_sub = label(sc, "", 11, MUTED)
        self.lbl_scope_sub.grid(row=1, column=gcol(0, 2), sticky=a_start(), padx=pads(12, 6), pady=(0, 10))
        change = ctk.CTkLabel(sc, text=t("change"), font=sans(12, True), text_color=ACCENT, cursor="hand2")
        change.grid(row=0, column=gcol(1, 2), rowspan=2, padx=pads(0, 12))
        bind_click([sc, self.lbl_scope_title, self.lbl_scope_sub, change], self.open_location_picker)
        Tooltip(change, t("change_tip"))

        tests = ctk.CTkFrame(scroll, fg_color="#141922", corner_radius=8, border_width=1, border_color="#2A3442")
        tests.pack(fill="x", padx=px, pady=(8, 0))
        self.lbl_scope_math = label(tests, "", 12, TEXT_2)
        self.lbl_scope_math.pack(side=start(), padx=11, pady=8)
        self.lbl_scope_tests = label(tests, "", font=mono(12, True))
        self.lbl_scope_tests.pack(side=end(), padx=11, pady=8)
        self.lbl_no_locations = label(scroll, t("no_list_hint"), 11, WARN, wraplength=270)
        self.locations_hint_anchor = tests

        # --- Protocols ---
        ph = frame(scroll)
        ph.pack(fill="x", padx=px, pady=(20, 6))
        caps(ph, t("protocols")).pack(side=start())
        label(ph, t("top_first"), 10, MUTED).pack(side=end())
        self.protocol_container = ctk.CTkFrame(scroll, fg_color=BORDER, corner_radius=10)
        self.protocol_container.pack(fill="x", padx=px)
        self.refresh_protocol_list()

        # --- Censorship tweaks (shown only for the Linux CLI, see refresh_cli_status) ---
        self.censor_card = ctk.CTkFrame(scroll, fg_color=ROW, corner_radius=10)
        self.censor_px = px
        caps(self.censor_card, t("censorship"), TEXT_2).pack(fill="x", padx=12, pady=(8, 0))
        awg_row = frame(self.censor_card)
        awg_row.pack(fill="x", padx=4)
        ctk.CTkLabel(awg_row, text=t("amnezia"), font=sans(12), text_color=TEXT).pack(side=start(), padx=8, pady=6)
        self.btn_awg = ghost_button(awg_row, "", self.open_awg_dialog, width=120, height=24, font=sans(11))
        self.btn_awg.pack(side=end(), padx=4, pady=4)
        self.seg_tls = self.make_mode_picker(t("large_tls"), "tls_mode", TLS_VALUES)
        self.seg_routing = self.make_mode_picker(t("routing"), "routing_mode", ROUTING_VALUES)
        self.update_awg_summary()

        # --- Options ---
        caps(scroll, t("options")).pack(fill="x", padx=px, pady=(20, 4))
        self.sw_resume = self.make_switch(scroll, t("opt_resume"), t("opt_resume_tip"))
        self.sw_random_cities = self.make_switch(scroll, t("opt_shuffle"), t("opt_shuffle_tip"))
        self.sw_chaos = self.make_switch(scroll, t("opt_chaos"), t("opt_chaos_tip"))
        self.sw_stop_success = self.make_switch(scroll, t("opt_stop"), t("opt_stop_tip"))

        self.btn_timing = ctk.CTkButton(scroll, text="", anchor=a_start(), height=30, fg_color="transparent",
                                        hover_color=HOVER, text_color=TEXT_2, font=sans(12),
                                        command=self.toggle_timing)
        self.btn_timing.pack(fill="x", padx=px - 6, pady=(8, 0))
        self.timing_frame = frame(scroll)
        grid = frame(self.timing_frame)
        grid.pack(fill="x", padx=px)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="t")
        self.entry_ping_host = self.make_grid_entry(grid, t("ping_host"), 0, 0, colspan=2,
                                                    tip=t("ping_host_tip"), rtl_text=False)
        self.entry_ping_count = self.make_grid_entry(grid, t("pings_per_test"), 2, 0, tip="1 – 20")
        self.entry_timeout = self.make_grid_entry(grid, t("connect_timeout"), 2, 1, tip=t("connect_timeout_tip"))
        self.entry_settle = self.make_grid_entry(grid, t("settle_delay"), 4, 0, tip=t("settle_delay_tip"))
        label(grid, t("windscribe_cli"), 11, MUTED).grid(row=6, column=0, columnspan=2, sticky=a_start(),
                                                         pady=(10, 3))
        cli_row = frame(grid)
        cli_row.grid(row=7, column=0, columnspan=2, sticky="ew")
        self.entry_cli = entry(cli_row, size=11, rtl_text=False)
        self.entry_cli.pack(side=start(), fill="x", expand=True)
        self.entry_cli.insert(0, self.config_data.get("cli_path") or DEFAULT_CLI)
        self.entry_cli.bind("<FocusOut>", lambda _e: self.refresh_cli_status())
        self.entry_cli.bind("<Return>", lambda _e: self.refresh_cli_status())
        ghost_button(cli_row, t("browse"), self.browse_cli, width=64, height=34, fg_color=INPUT).pack(
            side=start(), padx=pads(6, 0))
        for e in (self.entry_ping_host, self.entry_ping_count, self.entry_timeout):
            e.bind("<KeyRelease>", lambda _e: self.update_timing_summary(), add="+")
        frame(scroll, height=16).pack()

        # --- Language + CLI status ---
        lang_row = frame(side)
        lang_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 0))
        codes = list(i18n.LANGUAGES)
        names = [i18n.LANGUAGES[c] for c in (codes[::-1] if i18n.RTL else codes)]
        self.seg_lang = ctk.CTkSegmentedButton(
            lang_row, values=names, command=self.change_language, height=30, font=sans(12),
            fg_color=DEEP, selected_color="#20262F", selected_hover_color="#262D37", unselected_color=DEEP,
            unselected_hover_color=HOVER, text_color=TEXT, corner_radius=8)
        self.seg_lang.set(i18n.LANGUAGES[i18n.LANG])
        self.seg_lang.pack(fill="x")

        self.cli_pill = ctk.CTkFrame(side, corner_radius=10, border_width=1, height=40)
        self.cli_pill.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        self.cli_dot = ctk.CTkLabel(self.cli_pill, text="●", font=sans(10))
        self.cli_dot.pack(side=start(), padx=pads(12, 6), pady=8)
        self.cli_text = label(self.cli_pill, "", 12)
        self.cli_text.pack(side=start(), pady=8)
        bind_click([self.cli_pill, self.cli_dot, self.cli_text], self.focus_cli_entry)

    def build_rail(self):
        rail = ctk.CTkFrame(self, fg_color=SIDEBAR, corner_radius=0, width=64)
        rail.grid(row=0, column=gcol(0, 2), sticky="nsew")
        rail.grid_propagate(False)
        self.edge_line(rail)
        self.rail = rail
        inner = frame(rail)
        inner.pack(fill="y", expand=True, pady=18)
        self.draw_logo(inner).pack(pady=(0, 18))
        for name, tip, cmd in (("menu", t("show_panel_tip"), self.toggle_sidebar),
                               ("globe", t("locations_tip"), lambda: (self.toggle_sidebar(),
                                                                     self.open_location_picker())),
                               ("list", t("protocols"), self.toggle_sidebar),
                               ("sliders", t("ping_timing"), lambda: (self.toggle_sidebar(),
                                                                     self.toggle_timing(True)))):
            b = icon_button(inner, name, cmd, size=44, icon_size=16, fg_color="transparent", border_color=SIDEBAR,
                            text_color=TEXT_2)
            b.pack(pady=3)
            Tooltip(b, tip)
        self.rail_dot = ctk.CTkLabel(rail, text="●", font=sans(12), cursor="hand2")
        self.rail_dot.pack(side="bottom", pady=18)
        bind_click([self.rail_dot], lambda: (self.toggle_sidebar(), self.focus_cli_entry()))
        rail.grid_remove()

    def make_switch(self, parent, text, tip=None):
        row = frame(parent)
        row.pack(fill="x", padx=16, pady=2)
        lbl = label(row, text, 12, TEXT_2)
        lbl.pack(side=start(), pady=4)
        sw = ctk.CTkSwitch(row, text="", width=40, switch_width=36, switch_height=20, progress_color=ACCENT,
                           button_color=TEXT, button_hover_color="#FFFFFF", fg_color=BORDER_2)
        sw.pack(side=end())
        bind_click([lbl], sw.toggle)
        if tip:
            Tooltip(lbl, tip)
        return sw

    def make_grid_entry(self, parent, text, row, col, colspan=1, tip=None, rtl_text=True):
        c = gcol(col, 2) if colspan == 1 else 0
        label(parent, text, 11, MUTED).grid(row=row, column=c, columnspan=colspan, sticky=a_start(), pady=(8, 3))
        e = entry(parent, rtl_text=rtl_text)
        e.grid(row=row + 1, column=c, columnspan=colspan, sticky="ew",
               padx=(0, 0) if colspan > 1 else pads(0, 6) if col == 0 else (0, 0))
        e.bind("<Key>", lambda _e: e.configure(border_color=BORDER_2), add="+")
        if tip:
            Tooltip(e, tip)
        return e

    # ---- main area ----
    def build_main(self):
        main = frame(self)
        main.grid(row=0, column=gcol(1, 2), sticky="nsew", padx=24, pady=(18, 22))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        self.build_header(main)
        self.live_card = self.build_live_card(main)
        self.live_card.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        self.rec_card = self.build_rec_card(main)
        self.rec_card.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        self.rec_card.grid_remove()
        self.build_stats(main).grid(row=2, column=0, sticky="ew", pady=(16, 0))

        bottom = frame(main)
        bottom.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        bottom.grid_columnconfigure(gcol(0, 2), weight=1)
        bottom.grid_rowconfigure(0, weight=1)
        self.build_results_card(bottom).grid(row=0, column=gcol(0, 2), sticky="nsew")
        side = frame(bottom, width=290)
        side.grid(row=0, column=gcol(1, 2), sticky="ns", padx=pads(16, 0))
        side.pack_propagate(False)
        self.build_insights(side)

    def build_header(self, parent):
        h = frame(parent)
        h.grid(row=0, column=0, sticky="ew")
        n = 5
        h.grid_columnconfigure(gcol(0, n), weight=1)
        left = frame(h)
        left.grid(row=0, column=gcol(0, n), sticky=a_start())
        tr = frame(left)
        tr.pack(anchor=a_start())
        self.lbl_title = label(tr, t("ready"), 20, bold=True)
        self.lbl_title.pack(side=start())
        self.lbl_badge = ctk.CTkLabel(tr, text="", font=sans(11), corner_radius=10, height=22)
        self.lbl_sub = label(left, "", 12, MUTED)
        self.lbl_sub.pack(anchor=a_start())

        self.lbl_conn = ctk.CTkLabel(h, text="", font=sans(11), fg_color=GOOD_SOFT, text_color=GOOD_TEXT,
                                     corner_radius=14, height=30)
        self.lbl_conn.grid(row=0, column=gcol(1, n), padx=pads(8, 0))
        self.lbl_conn.grid_remove()

        def width_for(*keys, minimum=108, font=sans(12)):
            return max([minimum] + [self.text_width(t(k), font) + 36 for k in keys])

        self.btn_export = ghost_button(h, t("export_csv"), self.export_csv, width=width_for("export_csv"),
                                       height=40, corner_radius=9)
        self.btn_export.grid(row=0, column=gcol(2, n), padx=pads(10, 0))
        Tooltip(self.btn_export, t("export_tip"))
        self.btn_disconnect = ghost_button(h, t("disconnect"), self.disconnect_vpn, width=width_for("disconnect"),
                                           height=40, corner_radius=9)
        self.btn_disconnect.grid(row=0, column=gcol(3, n), padx=pads(8, 0))
        Tooltip(self.btn_disconnect, t("disconnect_tip"))
        main_width = max(176, self.text_width(t("start_n", n="0,000"), sans(13, True)) + 40)
        self.btn_start = primary_button(h, t("start"), self.start_job, width=main_width, height=40)
        self.btn_start.grid(row=0, column=gcol(4, n), padx=pads(8, 0))
        Tooltip(self.btn_start, t("start_tip"))
        self.btn_stop = ctk.CTkButton(h, text=t("stop"), command=self.stop_job, width=main_width, height=40,
                                      corner_radius=9, fg_color=BAD_SOFT, hover_color=BAD_HOVER, border_width=1,
                                      border_color=BAD_LINE, text_color=BAD_TEXT, text_color_disabled="#8A5A5A",
                                      font=sans(13, True))
        self.btn_stop.grid(row=0, column=gcol(4, n), padx=pads(8, 0))
        self.btn_stop.grid_remove()

    def build_live_card(self, parent):
        c = card(parent)
        c.grid_columnconfigure(0, weight=1)
        top = frame(c)
        top.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 0))
        top.grid_columnconfigure(gcol(0, 2), weight=1)
        info = frame(top)
        info.grid(row=0, column=gcol(0, 2), sticky=a_start())
        self.lbl_caption = caps(info, "")
        self.lbl_caption.pack(anchor=a_start())
        self.lbl_target = label(info, "", 24, bold=True)
        self.lbl_target.pack(anchor=a_start(), pady=(2, 0))
        sub = frame(info)
        sub.pack(anchor=a_start(), pady=(2, 0))
        self.lbl_target_sub = label(sub, "", 12, TEXT_2)
        self.lbl_target_sub.pack(side=start())
        self.lbl_route = chip(sub)

        ping_box = frame(top)
        ping_box.grid(row=0, column=gcol(1, 2), sticky="n" + a_end())
        pr = frame(ping_box)
        pr.pack(anchor=a_end())
        # Numbers read left to right in every language, so the value/unit pair keeps its order.
        self.lbl_ping = label(pr, "–", font=mono(40, True))
        self.lbl_ping.pack(side="left")
        label(pr, t("ms"), 13, MUTED).pack(side="left", padx=(4, 0), pady=(16, 0))
        self.lbl_ping_detail = label(ping_box, " ", font=mono(11), text_color=MUTED)
        self.lbl_ping_detail.pack(anchor=a_end())

        steps = frame(c)
        steps.grid(row=1, column=0, sticky="ew", padx=22, pady=(16, 0))
        steps.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="steps")
        self.phase_widgets = []
        for i, key in enumerate(self.PHASES):
            f = frame(steps)
            f.grid(row=0, column=gcol(i, 4), sticky="ew", padx=pads(0 if i == 0 else 8, 0))
            bar = Bar(f, BORDER_2, BORDER_2, height=4, corner_radius=2)
            bar.pack(fill="x")
            row = frame(f)
            row.pack(fill="x", pady=(6, 0))
            name_lbl = label(row, t(key), 12, MUTED)
            name_lbl.pack(side=start())
            time_lbl = label(row, "", font=mono(11), text_color=MUTED)
            time_lbl.pack(side=end())
            self.phase_widgets.append((bar, name_lbl, time_lbl))

        divider(c).grid(row=2, column=0, sticky="ew", padx=22, pady=(16, 14))
        self.progress_bar = Bar(c, BORDER, ACCENT, height=8, corner_radius=4)
        self.progress_bar.grid(row=3, column=0, sticky="ew", padx=22)
        pr = frame(c)
        pr.grid(row=4, column=0, sticky="ew", padx=22, pady=(8, 16))
        self.lbl_prog_left = label(pr, "", 12, MUTED)
        self.lbl_prog_left.pack(side=start())
        self.lbl_prog_right = label(pr, "", 12, MUTED)
        self.lbl_prog_right.pack(side=end())
        return c

    def build_rec_card(self, parent):
        c = card(parent, fg_color=REC_BG, border_color=REC_LINE, corner_radius=16)
        c.grid_columnconfigure(gcol(0, 3), weight=1)
        info = frame(c, fg_color=REC_BG)
        info.grid(row=0, column=gcol(0, 3), sticky=a_start(), padx=24, pady=22)
        caps(info, t("best_route_caption"), ACCENT).pack(anchor=a_start())
        self.lbl_rec_name = label(info, "", 26, bold=True)
        self.lbl_rec_name.pack(anchor=a_start(), pady=(4, 0))
        sub = frame(info, fg_color=REC_BG)
        sub.pack(anchor=a_start(), pady=(4, 0))
        self.lbl_rec_country = label(sub, "", 12, TEXT_2)
        self.lbl_rec_country.pack(side=start())
        self.lbl_rec_route = chip(sub)
        self.lbl_rec_route.pack(side=start(), padx=pads(8, 0))
        stats = frame(c, fg_color=REC_BG)
        stats.grid(row=0, column=gcol(1, 3), padx=pads(0, 28))
        self.rec_stats = {}
        for i, (key, text) in enumerate((("ping", "ping"), ("loss", "loss"), ("time", "connect_time"))):
            f = frame(stats, fg_color=REC_BG)
            f.grid(row=0, column=gcol(i, 3), padx=pads(0 if i == 0 else 28, 0))
            label(f, t(text), 11, MUTED).pack(anchor=a_start())
            v = label(f, "", font=mono(22, True))
            v.pack(anchor=a_start())
            self.rec_stats[key] = v
        self.btn_rec_connect = primary_button(c, t("connect_btn"), lambda: self.connect_result(self.best_result()),
                                              width=max(130, self.text_width(t("connect_btn"), sans(13, True)) + 40),
                                              height=46)
        self.btn_rec_connect.grid(row=0, column=gcol(2, 3), padx=pads(0, 24))
        return c

    def build_stats(self, parent):
        c = card(parent)
        self.stat_labels = {}
        items = [("ok", "stat_connected", GOOD), ("fail", "stat_failed", BAD), ("rate", "stat_rate", TEXT),
                 ("best", "stat_best", GOOD), ("avg", "stat_avg", TEXT)]
        n = len(items) * 2 - 1
        for i, (key, text, color) in enumerate(items):
            col = gcol(i * 2, n)
            c.grid_columnconfigure(col, weight=1, uniform="stat")
            f = frame(c, fg_color=CARD)
            f.grid(row=0, column=col, sticky="ew", padx=18, pady=12)
            label(f, t(text), 11, MUTED).pack(anchor=a_start())
            v = label(f, "–", font=mono(20, True), text_color=color)
            v.pack(anchor=a_start())
            self.stat_labels[key] = v
            if i < len(items) - 1:
                ctk.CTkFrame(c, fg_color=BORDER, width=1, height=1, corner_radius=0).grid(
                    row=0, column=gcol(i * 2 + 1, n), sticky="ns", pady=1)
        return c

    def build_results_card(self, parent):
        c = card(parent)
        c.grid_columnconfigure(0, weight=1)
        c.grid_rowconfigure(2, weight=1)

        tb = frame(c, fg_color=CARD)
        tb.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        tabs = [t(self.VIEW_KEYS[v]) for v in self.VIEWS]
        self.seg_view = ctk.CTkSegmentedButton(
            tb, values=tabs[::-1] if i18n.RTL else tabs, command=self.on_view_clicked, height=30, font=sans(12),
            fg_color=DEEP, selected_color="#20262F", selected_hover_color="#262D37", unselected_color=DEEP,
            unselected_hover_color=HOVER, text_color=TEXT, corner_radius=8)
        self.seg_view.pack(side=start())
        self.results_tools = frame(tb, fg_color=CARD)
        self.entry_search = entry(self.results_tools, height=30, width=90, fg_color=DEEP,
                                  placeholder_text=t("search_results"))
        self.entry_search.pack(side=start(), fill="x", expand=True)
        self.entry_search.bind("<KeyRelease>", lambda _e: self.render_results())
        Tooltip(self.entry_search, t("search_tip"))
        self.filter_buttons = {}
        for name, key in self.FILTER_KEYS.items():
            b = ctk.CTkButton(self.results_tools, text=t(key), height=28, corner_radius=14, border_width=1,
                              width=self.text_width(f"{t(key)}  0000", sans(11)) + 22,
                              font=sans(11), hover_color=HOVER, command=lambda n=name: self.set_result_filter(n))
            b.pack(side=start(), padx=pads(6, 0))
            self.filter_buttons[name] = b
        self.log_tools = frame(tb, fg_color=CARD)
        ghost_button(self.log_tools, t("copy"), self.copy_log, width=self.text_width(t("copy"), sans(12)) + 28,
                     height=28).pack(side=end())
        ghost_button(self.log_tools, t("clear"), self.clear_logs, width=self.text_width(t("clear"), sans(12)) + 28,
                     height=28).pack(side=end(), padx=pads(0, 6))

        divider(c).grid(row=1, column=0, sticky="ew")
        body = frame(c, fg_color=CARD)
        body.grid(row=2, column=0, sticky="nsew", padx=pads(6, 4), pady=(2, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.views = {}
        rf = frame(body, fg_color=CARD)
        self.tree = self.make_tree(rf, self.RESULT_COLUMNS)
        for key, *_ in self.RESULT_COLUMNS:
            self.tree.heading(self.tree_key(key), command=lambda k=key: self.on_sort(k))
        self.lbl_empty = ctk.CTkLabel(rf, text="", font=sans(13), text_color=MUTED, fg_color=CARD, justify="center")
        self.views["Results"] = rf

        bf = frame(body, fg_color=CARD)
        self.best_tree = self.make_tree(bf, self.BEST_COLUMNS)
        self.views["Best routes"] = bf

        lf = frame(body, fg_color=CARD)
        self.log_box = tk.Text(lf, bg=CARD, fg=TEXT_2, font=mono(10), relief="flat", borderwidth=0,
                               state="disabled", padx=10, pady=8, selectbackground=SELECTED,
                               insertbackground=TEXT, highlightthickness=0)
        self.log_box.pack(fill="both", expand=True)
        for tag, color in (("SUCCESS", GOOD), ("FAILURE", BAD), ("WARN", WARN), ("INFO", TEXT_2), ("TS", DIM)):
            self.log_box.tag_config(tag, foreground=color)
        self.log_box.tag_config("HEADER", foreground=ACCENT, font=mono(10, True))
        self.views["Log"] = lf

        for tree in (self.tree, self.best_tree):
            tree.bind("<Double-1>", lambda _e, tr=tree: self.connect_selected(tr))
            tree.bind("<Button-3>", lambda e, tr=tree: self.show_row_menu(e, tr))
            if platform.system() == "Darwin":
                tree.bind("<Button-2>", lambda e, tr=tree: self.show_row_menu(e, tr))

        self.row_menu = tk.Menu(self, tearoff=0, bg=INPUT, fg=TEXT, activebackground=SELECTED,
                                activeforeground=TEXT, bd=0, font=sans(10))
        self.row_menu.add_command(label=vis(t("menu_connect")), command=lambda: self.connect_selected(self._menu_tree))
        self.row_menu.add_separator()
        self.row_menu.add_command(label=vis(t("menu_copy_route")), command=lambda: self.copy_selected("route"))
        self.row_menu.add_command(label=vis(t("menu_copy_row")), command=lambda: self.copy_selected("row"))
        self._menu_tree = self.tree

        self.set_view("Results")
        self.set_result_filter("All")
        return c

    @staticmethod
    def tree_key(key):
        # Farsi tables are mirrored; the tree column (#0) is pinned to the left, so the location becomes a data column.
        return "loc" if i18n.RTL and key == "#0" else key

    def make_tree(self, parent, columns):
        parent.grid_columnconfigure(gcol(0, 2), weight=1)
        parent.grid_rowconfigure(0, weight=1)
        keys = [self.tree_key(c[0]) for c in columns]
        data_keys = [k for k in keys if k != "#0"]
        tree = ttk.Treeview(parent, columns=data_keys, show="headings" if i18n.RTL else "tree headings",
                            style="AS.Treeview", selectmode="browse")
        if i18n.RTL:
            tree["displaycolumns"] = data_keys[::-1]
        for (key, text, width, numeric), tkey in zip(columns, keys):
            anchor = ("w" if i18n.RTL else "e") if numeric else a_start()
            tree_heading(tree, tkey, t(text), anchor)
            tree.column(tkey, width=int(width * self.scale), minwidth=40, anchor=anchor, stretch=False)
        specs = [(k, c[2] * self.scale) for k, c in zip(keys, columns)]
        total = sum(w for _, w in specs)

        def fit(event):
            # Every column always fits: the location column takes any spare room, and when space is short
            # all columns shrink together (Tk would otherwise push the last ones out of view).
            available = event.width - 2
            if available >= total:
                for k, w in specs[1:]:
                    tree.column(k, width=int(w))
                tree.column(specs[0][0], width=int(available - (total - specs[0][1])))
            else:
                for k, w in specs:
                    tree.column(k, width=max(30, int(w * available / total)))

        tree.bind("<Configure>", fit, add="+")
        tree.tag_configure("odd", background=ROW_ALT)
        tree.tag_configure("muted", foreground=MUTED)
        sb = ctk.CTkScrollbar(parent, command=tree.yview, button_color=BORDER_2, button_hover_color=HOVER)
        tree.configure(yscrollcommand=sb.set)
        tree.grid(row=0, column=gcol(0, 2), sticky="nsew")
        sb.grid(row=0, column=gcol(1, 2), sticky="ns")
        return tree

    def tree_insert(self, tree, iid, name, image, values, tags):
        if i18n.RTL:
            tree.insert("", "end", iid=iid, values=tuple(vis(v) for v in (name,) + tuple(values)), tags=tags)
        else:
            tree.insert("", "end", iid=iid, text=f"  {name}", image=image, values=values, tags=tags)

    def build_insights(self, parent):
        works = card(parent)
        works.pack(fill="x")
        label(works, t("works_title"), 14, bold=True).pack(anchor=a_start(), fill="x", padx=16, pady=(14, 0))
        label(works, t("works_sub"), 11, MUTED).pack(anchor=a_start(), fill="x", padx=16)
        self.works_rows = frame(works, fg_color=CARD)
        self.works_rows.pack(fill="x", padx=16, pady=(12, 0))
        self.lbl_tip = label(works, "", 11, TEXT_2, wraplength=250)
        self.works_pad = frame(works, height=12, fg_color=CARD)
        self.works_pad.pack()

    # ---------------- views ----------------
    def on_view_clicked(self, shown):
        for v in self.VIEWS:
            if t(self.VIEW_KEYS[v]) == shown:
                self.set_view(v)

    def set_view(self, name):
        self.view = name
        self.seg_view.set(t(self.VIEW_KEYS[name]))
        for key, f in self.views.items():
            if key == name:
                f.grid(row=0, column=0, sticky="nsew")
            else:
                f.grid_remove()
        self.results_tools.pack_forget()
        self.log_tools.pack_forget()
        if name == "Results":
            self.results_tools.pack(side=start(), fill="x", expand=True, padx=pads(10, 0))
        elif name == "Log":
            self.log_tools.pack(side=start(), fill="x", expand=True, padx=pads(10, 0))

    def set_result_filter(self, name):
        self.result_filter = name
        self.render_results()

    def show_hero(self, which):
        if which == "rec":
            self.live_card.grid_remove()
            self.rec_card.grid()
        else:
            self.rec_card.grid_remove()
            self.live_card.grid()

    # ---------------- toasts ----------------
    def toast(self, msg, kind="info", action=None, action_text=None, ms=4000):
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        color = {"info": ACCENT, "success": GOOD, "error": BAD, "warn": WARN}.get(kind, ACCENT)
        toast = ctk.CTkFrame(self, fg_color=INPUT, corner_radius=10, border_width=1, border_color=BORDER_2)
        ctk.CTkFrame(toast, fg_color=color, width=4, height=1, corner_radius=2).pack(
            side=start(), fill="y", padx=pads(10, 0), pady=10)
        label(toast, msg, 12, wraplength=360).pack(side=start(), padx=12, pady=10)

        def close():
            try:
                toast.destroy()
            except tk.TclError:
                pass

        if action:
            ghost_button(toast, action_text, lambda: (action(), close()),
                         width=max(90, self.text_width(action_text, sans(12)) + 28), height=28,
                         fg_color=INPUT).pack(side=start(), padx=pads(0, 10))
        if i18n.RTL:
            toast.place(relx=0.0, rely=1.0, x=24, y=-24, anchor="sw")
        else:
            toast.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        toast.lift()
        toast.bind("<Button-1>", lambda _e: close())
        self._toast = toast
        self.after(ms, close)

    # ---------------- header / hero ----------------
    def render_header(self):
        run = self.run
        badge = None
        if self.worker_running() and run and run["kind"] == "job":
            title = t("testing", scope=run["scope"])
            sub = t("started", t=run["started"].strftime("%H:%M"))
            if run["profile"] != "Manual":
                sub += t("with_profile", p=run["profile"])
        elif run and run.get("finished"):
            took = i18n.duration((run["finished"] - run["started"]).total_seconds())
            sub = t("finished_sub", scope=run["scope"], t=run["finished"].strftime("%H:%M"), d=took)
            if run.get("kept"):
                title, badge = t("found_route"), (t("stopped_first"), GOOD_SOFT, GOOD_TEXT)
            elif run["stopped"]:
                title = t("run_stopped")
                badge = (t("n_of_tests", a=num(run.get("current", 0)), b=num(run.get("total", 0))),
                         WARN_SOFT, WARN_TEXT)
            else:
                title = t("run_complete")
                total = run.get("total", 0)
                badge = (t("n_of_tests", a=num(total), b=num(total)), GOOD_SOFT, GOOD_TEXT) if total else None
        else:
            scope_title, _ = self.scope_summary()
            title, sub = t("ready"), t("ready_sub", scope=scope_title, n=num(self.test_count()))
        self.lbl_title.configure(text=title)
        self.lbl_sub.configure(text=sub)
        if badge:
            self.lbl_badge.configure(text=f"  {badge[0]}  ", fg_color=badge[1], text_color=badge[2])
            self.lbl_badge.pack(side=start(), padx=pads(12, 0))
        else:
            self.lbl_badge.pack_forget()

    def render_hero(self):
        if self.worker_running():
            self.show_hero("live")
            return
        best = self.best_result()
        if best:
            self.lbl_rec_name.configure(text=loc_name(best["city"], best["node"]))
            self.lbl_rec_country.configure(text=best["country"])
            self.lbl_rec_route.configure(text=f" {route_label(best)} ")
            self.rec_stats["ping"].configure(text=f"{best['ping']:.0f} {t('ms')}", text_color=ping_color(best["ping"]))
            self.rec_stats["loss"].configure(text=f"{best['loss']:.0f}%" if best["loss"] is not None else "–")
            self.rec_stats["time"].configure(text=t("secs", v=f"{best['duration']:.1f}"))
            self.show_hero("rec")
        else:
            self.reset_live_idle()
            self.show_hero("live")

    def reset_live_idle(self):
        title, sub = self.scope_summary()
        self.lbl_caption.configure(text=t("cap_ready").upper(), text_color=MUTED)
        self.lbl_target.configure(text=title)
        self.lbl_target_sub.configure(text=sub)
        self.lbl_route.pack_forget()
        self.lbl_ping.configure(text="–", text_color=TEXT)
        self.lbl_ping_detail.configure(text=" ")
        self.reset_phases()
        self.progress_bar.show(0)
        self.lbl_prog_left.configure(text=t("tests_queued", n=num(self.test_count())))
        self.lbl_prog_right.configure(text=t("press_start"))

    def set_target(self, caption_key, city, node, country, route):
        self.lbl_caption.configure(text=t(caption_key).upper(), text_color=ACCENT)
        self.lbl_target.configure(text=loc_name(city, node))
        self.lbl_target_sub.configure(text=country)
        self.lbl_route.configure(text=f" {route} ")
        self.lbl_route.pack(side=start(), padx=pads(8, 0))
        self.lbl_ping.configure(text="–", text_color=TEXT)
        self.lbl_ping_detail.configure(text=" ")
        self.reset_phases()

    def reset_phases(self):
        for bar, name_lbl, time_lbl in self.phase_widgets:
            bar.show(0, BORDER_2)
            name_lbl.configure(text_color=MUTED, font=sans(12))
            time_lbl.configure(text="")

    def set_phase(self, idx, state, secs=None):
        bar, name_lbl, time_lbl = self.phase_widgets[idx]
        if state == "active":
            bar.busy(ACCENT)
            name_lbl.configure(text_color=TEXT, font=sans(12, True))
            time_lbl.configure(text="…", text_color=ACCENT)
            return
        bar.show(1, {"done": GOOD, "fail": BAD}.get(state, BORDER_2))
        name_lbl.configure(text_color=TEXT_2, font=sans(12))
        if state == "skip":
            time_lbl.configure(text=t("skipped"), text_color=MUTED)
        elif state == "fail" and secs is None:
            time_lbl.configure(text=t("failed_lc"), text_color=BAD)
        else:
            time_lbl.configure(text=t("secs", v=f"{secs:.1f}") if secs is not None else "",
                               text_color=BAD if state == "fail" else MUTED)

    def begin_test(self, i, total, executed, city, node, country, route):
        self.step = (i, total, executed, time.time())
        if self.run:
            self.run.update(current=i, total=total)
        self.set_target("cap_testing", city, node, country, route)
        self.progress_bar.show((i - 1) / total)
        self.lbl_prog_left.configure(text=t("test_progress", i=num(i), total=num(total),
                                            pct=int((i - 1) / total * 100)))
        self.title(f"{APP_NAME}  ·  {i}/{total}")

    def set_ping(self, result):
        if result:
            self.lbl_ping.configure(text=f"{result['avg']:.0f}", text_color=ping_color(result["avg"]))
            self.lbl_ping_detail.configure(text=t("ping_detail", a=f"{result['min']:.0f}", b=f"{result['max']:.0f}",
                                                  c=f"{result['loss']:.0f}"))
        else:
            self.lbl_ping.configure(text="–", text_color=BAD)
            self.lbl_ping_detail.configure(text=t("no_reply"))

    def set_connected(self, text):
        self.connected_to = text
        if text:
            self.lbl_conn.configure(text=f"   ●  {t('connected_chip', x=text)}   ")
            self.lbl_conn.grid()
        else:
            self.lbl_conn.grid_remove()

    def _tick(self):
        run = self.run
        if self.worker_running() and run and run["kind"] == "job" and not run.get("finished"):
            now = time.time()
            elapsed = t("elapsed", t=i18n.duration(now - run["started_ts"]))
            text = elapsed
            if self.step:
                i, total, executed, step_ts = self.step
                if executed > 1:
                    avg = (step_ts - run["started_ts"]) / (executed - 1)
                    left = max(avg * (total - i + 1) - (now - step_ts), avg * (total - i))
                    text = t("time_left", left=i18n.duration(left), elapsed=elapsed)
                else:
                    text = t("estimating", elapsed=elapsed)
            self.lbl_prog_right.configure(text=text)
        self.after(1000, self._tick)

    # ---------------- results ----------------
    @staticmethod
    def result_row(idx, city, node, country, proto, port, awg, tls, routing, status, duration, ping, loss):
        return {"id": idx, "city": city, "node": node or "", "country": country, "proto": proto, "port": port,
                "awg": awg or "", "tls": tls or "", "routing": routing or "", "status": status,
                "duration": duration or 0, "ping": ping, "loss": loss}

    def add_result_row(self, *row):
        self.results.append(self.result_row(len(self.results), *row))
        self.render_data()

    def reload_results_table(self):
        self.results = [self.result_row(i, *row) for i, row in enumerate(self.worker.db.fetch_results())]
        self.render_data()

    def render_data(self):
        self.render_results()
        self.render_best()
        self.render_stats()
        self.render_insights()
        if not self.worker_running():
            self.render_hero()

    def best_routes(self):
        rows = [r for r in self.results if r["status"] == "SUCCESS" and r["ping"] is not None]
        rows.sort(key=lambda r: (r["ping"], r["loss"] or 0, r["duration"]))
        return rows

    def best_result(self):
        rows = self.best_routes()
        return rows[0] if rows else None

    @staticmethod
    def status_label(status):
        key = f"status_{status}"
        return t(key) if key in i18n.STRINGS else status

    def result_values(self, r):
        return (r["country"], route_label(r), self.status_label(r["status"]),
                t("secs", v=f"{r['duration']:.1f}") if r["status"] == "SUCCESS" else "–",
                f"{r['ping']:.0f} {t('ms')}" if r["ping"] is not None else "–",
                f"{r['loss']:.0f}%" if r["loss"] is not None else "–")

    def render_results(self):
        if not hasattr(self, "tree"):
            return
        query = self.entry_search.get().strip().lower()
        ok = sum(1 for r in self.results if r["status"] == "SUCCESS")
        counts = {"All": len(self.results), "Connected": ok, "Failed": len(self.results) - ok}
        for name, b in self.filter_buttons.items():
            active = name == self.result_filter
            b.configure(text=f"{t(self.FILTER_KEYS[name])}  {num(counts[name])}",
                        fg_color=ACCENT_SOFT if active else "transparent",
                        border_color=ACCENT_LINE if active else BORDER_2, text_color=TEXT if active else TEXT_2)

        rows = []
        for r in self.results:
            if self.result_filter == "Connected" and r["status"] != "SUCCESS":
                continue
            if self.result_filter == "Failed" and r["status"] == "SUCCESS":
                continue
            if query:
                hay = f"{loc_name(r['city'], r['node'])} {r['country']} {route_label(r)} " \
                      f"{self.status_label(r['status'])}".lower()
                if not all(tok in hay for tok in query.split()):
                    continue
            rows.append(r)
        if self.sort_col:
            rows.sort(key=self.SORT_KEYS[self.sort_col], reverse=self.sort_desc)
        else:
            rows.reverse()  # newest first

        self.tree.delete(*self.tree.get_children())
        for n, r in enumerate(rows):
            tags = ["odd" if n % 2 else "even"]
            if r["status"] != "SUCCESS":
                tags.append("muted")
            self.tree_insert(self.tree, str(r["id"]), loc_name(r["city"], r["node"]), self.dots[r["status"]],
                             self.result_values(r), tags)

        if not self.results:
            self.lbl_empty.configure(text=t("empty_results"))
            self.lbl_empty.place(relx=0.5, rely=0.5, anchor="center")
        elif not rows:
            self.lbl_empty.configure(text=t("empty_filter"))
            self.lbl_empty.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.lbl_empty.place_forget()

    def render_best(self):
        rows = self.best_routes()
        self.best_tree.delete(*self.best_tree.get_children())
        for n, r in enumerate(rows[:100], 1):
            self.tree_insert(self.best_tree, str(r["id"]), f"{n}.  {loc_name(r['city'], r['node'])}",
                             self.dots[ping_quality(r["ping"])],
                             (r["country"], route_label(r), f"{r['ping']:.0f} {t('ms')}",
                              f"{r['loss']:.0f}%" if r["loss"] is not None else "–",
                              t("secs", v=f"{r['duration']:.1f}")),
                             ("odd" if n % 2 == 0 else "even",))

    def render_stats(self):
        total = len(self.results)
        ok_rows = [r for r in self.results if r["status"] == "SUCCESS"]
        s = self.stat_labels
        s["ok"].configure(text=num(len(ok_rows)))
        s["fail"].configure(text=num(total - len(ok_rows)))
        s["rate"].configure(text=f"{len(ok_rows) / total:.0%}" if total else "–")
        best = self.best_result()
        s["best"].configure(text=f"{best['ping']:.0f} {t('ms')}" if best else "–",
                            text_color=ping_color(best["ping"]) if best else TEXT)
        s["avg"].configure(text=t("secs", v=f"{sum(r['duration'] for r in ok_rows) / len(ok_rows):.1f}")
                           if ok_rows else "–")

    def render_insights(self):
        for w in self.works_rows.winfo_children():
            w.destroy()
        stats = {}
        for r in self.results:
            s = stats.setdefault(r["proto"], [0, 0])
            s[1] += 1
            if r["status"] == "SUCCESS":
                s[0] += 1
        if not stats:
            label(self.works_rows, t("works_empty"), 11, MUTED, wraplength=250).pack(anchor=a_start(), fill="x")
        for proto, (ok, total) in sorted(stats.items(), key=lambda kv: -kv[1][0] / kv[1][1]):
            rate = ok / total
            row = frame(self.works_rows, fg_color=CARD)
            row.pack(fill="x", pady=(0, 10))
            top = frame(row, fg_color=CARD)
            top.pack(fill="x")
            label(top, PROTO_NAMES.get(proto, proto), 12).pack(side=start())
            label(top, f"{rate:.0%}", font=mono(11)).pack(side=end())
            label(top, f"{ok}/{total}", font=mono(11), text_color=MUTED).pack(side=end(), padx=pads(0, 10))
            bar = Bar(row, BORDER, rate_color(rate), height=6, corner_radius=3)
            bar.show(rate)
            bar.pack(fill="x", pady=(4, 0))

        weak = [p for p, (ok, total) in stats.items() if total >= 4 and ok / total < 0.4]
        if weak and len(weak) < len(stats) and not self.worker_running():
            names = t("and").join(PROTO_NAMES.get(p, p) for p in weak)
            self.lbl_tip.configure(text=t("tip_one" if len(weak) == 1 else "tip_many", names=names))
            self.lbl_tip.pack(fill="x", padx=16, pady=(2, 0), before=self.works_pad)
        else:
            self.lbl_tip.pack_forget()

    def on_sort(self, col):
        if self.sort_col == col:
            if self.sort_desc:
                self.sort_col, self.sort_desc = None, False  # third click: back to newest first
            else:
                self.sort_desc = True
        else:
            self.sort_col, self.sort_desc = col, False
        for key, text, _, _ in self.RESULT_COLUMNS:
            arrow = ("  ↓" if self.sort_desc else "  ↑") if key == self.sort_col else ""
            title = vis(t(text))
            self.tree.heading(self.tree_key(key), text=(arrow.strip() + "  " + title) if arrow and i18n.RTL
                              else title + arrow)
        self.render_results()

    def selected_result(self, tree):
        sel = tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        return self.results[idx] if 0 <= idx < len(self.results) else None

    def show_row_menu(self, event, tree):
        row = tree.identify_row(event.y)
        if not row:
            return
        tree.selection_set(row)
        self._menu_tree = tree
        self.row_menu.entryconfigure(0, state="disabled" if self.worker.running else "normal")
        try:
            self.row_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.row_menu.grab_release()

    def copy_selected(self, what):
        r = self.selected_result(self._menu_tree)
        if not r:
            return
        if what == "route":
            text = f"{r['city']}  {route_label(r)}"
        else:
            text = "\t".join((loc_name(r["city"], r["node"]),) + self.result_values(r))
        self.clipboard_clear()
        self.clipboard_append(text)
        self.toast(t("copied"), "success", ms=1800)

    # ---------------- log (kept in English: it is technical output, handy for bug reports) ----------------
    def log_message(self, msg, tag="INFO"):
        ts = datetime.datetime.now().strftime("%H:%M:%S  ")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", ts, "TS")
        self.log_box.insert("end", msg + "\n", tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_box.get("1.0", "end-1c"))
        self.toast(t("log_copied"), "success", ms=1800)

    # ---------------- language ----------------
    def change_language(self, shown):
        code = next((c for c, name in i18n.LANGUAGES.items() if name == shown), "en")
        if code == i18n.LANG:
            return
        if self.worker.running:
            self.seg_lang.set(i18n.LANGUAGES[i18n.LANG])
            self.toast(t("lang_busy"), "warn")
            return
        self.config_data["language"] = code
        self.relaunch = True
        self.on_close()

    # ---------------- scope ----------------
    def open_location_picker(self):
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.focus()
            return
        if not self.locations:
            self.toast(t("no_list_toast"), "warn", action=self.update_locations, action_text=t("download"), ms=7000)
            return
        self._picker = LocationPicker(self, self.locations, self.selected_keys, self.on_locations_chosen)

    def refresh_locations_info(self):
        """The missing-list hint and the 'last updated' tooltip in the sidebar."""
        updated = LocationManager.last_updated()
        self.tip_update_list.text = t("update_tip") + "\n" + (
            t("current_list", d=updated.strftime("%Y-%m-%d %H:%M")) if updated else t("no_list_yet"))
        if self.locations:
            self.lbl_no_locations.pack_forget()
        else:
            self.lbl_no_locations.pack(fill="x", padx=16, pady=(6, 0), after=self.locations_hint_anchor)

    def update_locations(self):
        if getattr(self, "_updating_locations", False):
            return
        self._updating_locations = True
        buttons = [self.btn_update_list]
        if self._picker is not None and self._picker.winfo_exists():
            buttons.append(self._picker.btn_update)
        for b in buttons:
            b.configure(state="disabled", text=t("updating"))

        def work():
            try:
                LocationManager.download()
                self.post(self.locations_updated, None)
            except Exception as e:
                self.post(self.locations_updated, str(e) or e.__class__.__name__)

        threading.Thread(target=work, daemon=True).start()

    def locations_updated(self, error):
        self._updating_locations = False
        self.btn_update_list.configure(state="normal", text=t("update_list"))
        picker = self._picker if self._picker is not None and self._picker.winfo_exists() else None
        if picker:
            picker.btn_update.configure(state="normal", text=t("update_list"))
        if error:
            self.log_message(f"Server list update failed: {error}", "FAILURE")
            self.toast(t("update_failed", e=error), "error", ms=7000)
            return

        old_keys = self.all_keys
        self.locations = LocationManager.load_locations()
        self.all_keys = {loc_key(l) for l in self.locations}
        added, removed = len(self.all_keys - old_keys), len(old_keys - self.all_keys)
        had_selection = bool(self.selected_keys)
        self.selected_keys &= self.all_keys
        if picker:
            picker.set_locations(self.locations)
        self.refresh_locations_info()
        self.update_scope_preview(user_change=True)
        self.save_all_config()

        countries = len({l["country"] for l in self.locations})
        msg = t("list_updated", n=num(len(self.locations)), c=num(countries))
        changes = [x for x in (t("changes_new", n=added) if added else "",
                               t("changes_removed", n=removed) if removed else "") if x]
        sep = "، " if i18n.RTL else ", "
        msg += f" ({sep.join(changes)})." if changes and old_keys else "."
        if had_selection and not self.selected_keys:
            msg += t("selection_gone")
        self.log_message(f"Server list updated: {len(self.locations)} servers, {added} new, {removed} removed.",
                         "SUCCESS")
        self.toast(msg, "success", ms=6000)

    def on_locations_chosen(self, keys):
        keys &= self.all_keys
        self.selected_keys = set() if keys == self.all_keys else keys
        self.update_scope_preview(user_change=True)
        self.save_all_config()

    def tweak_opts(self):
        """Matrix inputs for expand_routes; a Windows exe always gets upstream's plain plan."""
        if not linux_cli(resolve_cli(self.entry_cli.get())):
            return [], "off", "auto"
        return self.selected_awg(), self.tls_mode, self.routing_mode

    def route_count(self):
        return len(expand_routes(self.get_plan(), *self.tweak_opts()))

    def test_count(self):
        return len(self.scope_locations()) * self.route_count()

    def update_scope_preview(self, user_change=False):
        if not hasattr(self, "btn_start") or not hasattr(self, "lbl_scope_tests"):
            return
        title, sub = self.scope_summary()
        servers = len(self.scope_locations())
        routes = self.route_count()
        tests = servers * routes
        self.lbl_scope_title.configure(text=trunc(title, 30))
        self.lbl_scope_sub.configure(text=sub)
        self.lbl_scope_math.configure(text=t("scope_math", s=num(servers), r=num(routes)))
        self.lbl_scope_tests.configure(text=t("tests_n", n=num(tests)))
        if self.worker_running():
            return
        if user_change:
            self.run = None
        self.btn_start.configure(text=t("start_n", n=num(tests)) if tests else t("start"))
        self.render_header()
        if self.live_card.winfo_ismapped() or not self.best_result():
            self.render_hero()

    # ---------------- protocols / priority ----------------
    def refresh_protocol_list(self):
        for w in self.protocol_container.winfo_children():
            w.destroy()
        self.port_buttons = {}
        last = len(self.priority_order) - 1
        for i, proto in enumerate(self.priority_order):
            row = ctk.CTkFrame(self.protocol_container, fg_color=ROW, corner_radius=9 if i in (0, last) else 0)
            row.pack(fill="x", padx=1, pady=(1 if i == 0 else 0, 1))
            ctk.CTkCheckBox(row, text=PROTO_NAMES[proto], variable=self.protocol_vars[proto], font=sans(12, True),
                            text_color=TEXT, checkbox_width=17, checkbox_height=17, border_width=2, corner_radius=4,
                            fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=DIM,
                            checkmark_color=ON_ACCENT, width=100).pack(side=start(), padx=pads(10, 4), pady=8)
            down = icon_button(row, "down", lambda p=proto: self.move(p, 1), size=24, icon_size=10,
                               fg_color="transparent", border_color=ROW, text_color=MUTED,
                               state="normal" if i < last else "disabled")
            down.pack(side=end(), padx=pads(0, 6))
            up = icon_button(row, "up", lambda p=proto: self.move(p, -1), size=24, icon_size=10,
                             fg_color="transparent", border_color=ROW, text_color=MUTED,
                             state="normal" if i > 0 else "disabled")
            up.pack(side=end())
            btn = ghost_button(row, "", lambda p=proto: self.open_port_dialog(p), width=60, height=24,
                               font=mono(10), fg_color="transparent", corner_radius=6)
            btn.pack(side=end(), padx=pads(0, 4))
            Tooltip(btn, t("ports_tip"))
            self.port_buttons[proto] = btn
            self.update_summary(proto)
        self.update_scope_preview()

    def move(self, proto, delta):
        idx = self.priority_order.index(proto)
        new = idx + delta
        if 0 <= new < len(self.priority_order):
            self.priority_order[idx], self.priority_order[new] = self.priority_order[new], self.priority_order[idx]
            self.refresh_protocol_list()

    def open_port_dialog(self, proto):
        dialog = ctk.CTkToplevel(self)
        dialog.title(vis(t("ports_title", p=PROTO_NAMES[proto])))
        place_dialog(dialog, self, 320, 480, top=120)
        dialog.resizable(False, True)

        def set_all(value):
            for v in self.port_vars[proto].values():
                v.set(value)

        label(dialog, t("ports_title", p=PROTO_NAMES[proto]), 16, bold=True).pack(fill="x", padx=18, pady=(16, 0))
        label(dialog, t("ports_hint"), 11, MUTED, wraplength=280).pack(fill="x", padx=18)
        top = frame(dialog)
        top.pack(fill="x", padx=18, pady=(10, 0))
        ghost_button(top, t("select_all"), lambda: set_all(True),
                     width=self.text_width(t("select_all"), sans(12)) + 28, height=28).pack(side=start())
        ghost_button(top, t("select_none"), lambda: set_all(False),
                     width=self.text_width(t("select_none"), sans(12)) + 28, height=28).pack(side=start(), padx=6)

        scroll = ctk.CTkScrollableFrame(dialog, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        scroll.pack(fill="both", expand=True, padx=18, pady=10)
        for port, var in self.port_vars[proto].items():
            ctk.CTkCheckBox(scroll, text=str(port), variable=var, font=mono(12), checkbox_width=18,
                            checkbox_height=18, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=DIM,
                            checkmark_color=ON_ACCENT, border_width=2, corner_radius=4).pack(anchor=a_start(),
                                                                                            pady=5, padx=10)

        def done():
            self.update_summary(proto)
            self.update_scope_preview(user_change=True)
            dialog.grab_release()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", done)
        dialog.bind("<Escape>", lambda _e: done())
        dialog.bind("<Return>", lambda _e: done())
        primary_button(dialog, t("done"), done, height=36).pack(fill="x", padx=18, pady=(0, 16))

    def selected_awg(self):
        return [name for name in self.awg_order if name in self.awg_enabled]

    def make_mode_picker(self, title, attr, modes):
        row = frame(self.censor_card)
        row.pack(fill="x", padx=12, pady=(2, 8))
        label(row, title, 12).pack(fill="x")
        names = {t(f"mode_{m}"): m for m in modes}

        def pick(name):
            setattr(self, attr, names[name])
            self.update_scope_preview(user_change=True)
            self.save_all_config()

        seg = ctk.CTkSegmentedButton(
            row, values=list(names), command=pick, height=26, font=sans(11),
            fg_color=DEEP, selected_color="#20262F", selected_hover_color="#262D37", unselected_color=DEEP,
            unselected_hover_color=HOVER, text_color=TEXT, corner_radius=8)
        seg.set(t(f"mode_{getattr(self, attr)}"))
        seg.pack(fill="x", pady=(4, 0))
        return seg

    def list_awg_presets(self):
        argv = resolve_cli(self.entry_cli.get())
        if not argv:
            return None
        try:
            result = subprocess.run(list(argv) + ["amneziawg"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=30, **hidden_process_kwargs())
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return [line.strip() for line in result.stdout.splitlines() if " - " in line]

    def open_awg_dialog(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title(vis(t("amnezia_title")))
        place_dialog(dialog, self, 460, 520, top=100)
        dialog.resizable(False, True)
        label(dialog, t("amnezia_title"), 16, bold=True).pack(fill="x", padx=18, pady=(16, 0))
        label(dialog, t("amnezia_hint"), 11, MUTED, wraplength=420).pack(fill="x", padx=18)
        lbl_status = label(dialog, t("amnezia_loading"), 11, MUTED, wraplength=420)
        lbl_status.pack(fill="x", padx=18, pady=(8, 0))
        checks = {}
        state = {"live": None}

        def set_all(value):
            for var in checks.values():
                var.set(value)

        top = frame(dialog)
        top.pack(fill="x", padx=18, pady=(10, 0))
        ghost_button(top, t("select_all"), lambda: set_all(True),
                     width=self.text_width(t("select_all"), sans(12)) + 28, height=28).pack(side=start())
        ghost_button(top, t("select_none"), lambda: set_all(False),
                     width=self.text_width(t("select_none"), sans(12)) + 28, height=28).pack(side=start(), padx=6)

        scroll = ctk.CTkScrollableFrame(dialog, fg_color=CARD, corner_radius=10, border_width=1, border_color=BORDER)
        scroll.pack(fill="both", expand=True, padx=18, pady=10)

        def fill(names):
            for w in scroll.winfo_children():
                w.destroy()
            checks.clear()
            if not names:
                label(scroll, t("amnezia_empty"), 11, MUTED, wraplength=400).pack(anchor=a_start(), padx=10, pady=8)
            for name in names:
                checks[name] = var = ctk.BooleanVar(value=name in self.awg_enabled)
                ctk.CTkCheckBox(scroll, text=name, variable=var, font=sans(12), checkbox_width=18,
                                checkbox_height=18, fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=DIM,
                                checkmark_color=ON_ACCENT, border_width=2, corner_radius=4).pack(
                    anchor=a_start(), pady=4, padx=10)

        def fetched(live):
            if not dialog.winfo_exists():
                return
            state["live"] = live
            if live is None:
                lbl_status.configure(text=t("amnezia_empty"), text_color=WARN)
            else:
                lbl_status.pack_forget()
                fill(live)

        fill(list(self.awg_order))
        # The CLI call can take seconds on a cold WSL distro; keep the window responsive meanwhile.
        threading.Thread(target=lambda: self.post(fetched, self.list_awg_presets()), daemon=True).start()

        def done():
            if state["live"] is not None:
                self.awg_order = list(checks)
            self.awg_enabled = {name for name, var in checks.items() if var.get()}
            self.update_awg_summary()
            self.update_scope_preview(user_change=True)
            self.save_all_config()
            dialog.grab_release()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", done)
        dialog.bind("<Escape>", lambda _e: done())
        dialog.bind("<Return>", lambda _e: done())
        primary_button(dialog, t("done"), done, height=36).pack(fill="x", padx=18, pady=(0, 16))

    def update_awg_summary(self):
        chosen = self.selected_awg()
        txt = t("amnezia_off") if not chosen else t("amnezia_n", n=len(chosen))
        if hasattr(self, "btn_awg"):
            self.btn_awg.configure(text=txt, text_color=TEXT_2 if chosen else MUTED,
                                   width=max(72, self.text_width(txt, sans(11)) + 28))

    def update_summary(self, proto):
        active = [p for p, v in self.port_vars[proto].items() if v.get()]
        total = len(self.port_vars[proto])
        if not active:
            txt = t("ports_none")
        elif len(active) == total and total > 2:
            txt = t("ports_all", n=total)
        elif len(active) <= 2:
            txt = ", ".join(str(p) for p in active)
        else:
            txt = t("ports_some", a=len(active), b=total)
        btn = self.port_buttons.get(proto)
        if btn is not None:
            btn.configure(text=txt, text_color=TEXT_2 if active else WARN)

    # ---------------- sidebar ----------------
    def toggle_sidebar(self):
        self.sidebar_open = not self.sidebar_open
        self.apply_sidebar_state()

    def apply_sidebar_state(self):
        if self.sidebar_open:
            self.rail.grid_remove()
            self.sidebar.grid()
        else:
            self.sidebar.grid_remove()
            self.rail.grid()

    def toggle_timing(self, force_open=None):
        self.timing_open = (not self.timing_open) if force_open is None else force_open
        if self.timing_open:
            self.timing_frame.pack(fill="x", after=self.btn_timing)
        else:
            self.timing_frame.pack_forget()
        self.update_timing_summary()

    def update_timing_summary(self):
        arrow = "▾" if self.timing_open else ("◂" if i18n.RTL else "▸")
        summary = t("timing_summary", host=self.entry_ping_host.get().strip() or "?",
                    count=self.entry_ping_count.get().strip(), timeout=self.entry_timeout.get().strip())
        self.btn_timing.configure(text=f"{arrow}   {summary}")

    # ---------------- CLI ----------------
    def refresh_cli_status(self, probe=True):
        path = resolve_cli(self.entry_cli.get())
        if linux_cli(path):
            self.censor_card.pack(fill="x", padx=self.censor_px, pady=(8, 0), after=self.protocol_container)
        else:
            self.censor_card.pack_forget()
        self.update_scope_preview()
        if not path:
            self.set_cli_badge("missing")
            return None
        worker = getattr(self, "worker", None)
        running = worker is not None and worker.running
        if worker is not None and not running:
            worker.cli_argv = path
        # shortcut: a passed probe is trusted for the rest of the session; re-probe on job start if users
        # uninstall the CLI mid-session.
        if tuple(path) == self._cli_ok:
            self.set_cli_badge("ready")
        elif probe and not running:
            # "windscribe-cli help" runs off the UI thread: a cold WSL start takes seconds. The CLI allows
            # one instance at a time, so callers about to start a job pass probe=False.
            self.set_cli_badge("checking")
            threading.Thread(target=lambda: self.post(self.cli_probed, path, cli_probe(path)), daemon=True).start()
        return path

    def cli_probed(self, argv, ok):
        if ok:
            self._cli_ok = tuple(argv)
        if resolve_cli(self.entry_cli.get()) == argv:  # the entry may have changed while the probe ran
            self.set_cli_badge("ready" if ok else "missing")

    CLI_BADGE = {"ready": (GOOD_SOFT, GOOD_LINE, GOOD, GOOD_TEXT), "checking": (WARN_SOFT, BORDER_2, WARN, WARN_TEXT),
                 "missing": (BAD_SOFT, BAD_LINE, BAD, BAD_TEXT)}

    def set_cli_badge(self, state):
        bg, line, dot, fg = self.CLI_BADGE[state]
        self.cli_pill.configure(fg_color=bg, border_color=line)
        self.cli_dot.configure(text_color=dot)
        self.cli_text.configure(text=t(f"cli_{state}"), text_color=fg)
        self.rail_dot.configure(text_color=dot)

    def focus_cli_entry(self):
        if resolve_cli(self.entry_cli.get()):
            return
        if not self.sidebar_open:
            self.toggle_sidebar()
        self.toggle_timing(True)
        try:
            self.sidebar_scroll._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass
        self.entry_cli.focus_set()
        self.entry_cli.configure(border_color=BAD)
        self.toast(t("set_cli_path"), "warn")

    def browse_cli(self):
        types = [("windscribe-cli", "windscribe-cli.exe"), (vis(t("all_files")), "*.*")] if IS_WINDOWS \
            else [(vis(t("all_files")), "*")]
        path = filedialog.askopenfilename(title=vis(t("locate_cli")), filetypes=types)
        if path:
            self.set_entry(self.entry_cli, os.path.normpath(path))
            self.entry_cli.configure(border_color=BORDER_2)
            if self.refresh_cli_status():
                self.toast(t("cli_found"), "success", ms=2200)

    # ---------------- config / profiles ----------------
    @staticmethod
    def set_entry(widget, value):
        widget.delete(0, "end")
        widget.insert(0, str(value))

    def set_profile_placeholder(self):
        self.combo_profiles.set(vis(t("choose_profile") if self.saved_profiles else t("no_profiles")))

    def apply_config_to_ui(self, s):
        self.set_entry(self.entry_timeout, s.get("timeout", "25"))
        self.set_entry(self.entry_settle, s.get("settle", "2"))
        self.set_entry(self.entry_ping_host, s.get("ping_host", "1.1.1.1"))
        self.set_entry(self.entry_ping_count, s.get("ping_count", "5"))
        self.update_timing_summary()

        for sw, key in ((self.sw_resume, "resume"), (self.sw_random_cities, "random_cities"),
                        (self.sw_chaos, "chaos_mode"), (self.sw_stop_success, "stop_on_success")):
            sw.select() if s.get(key, False) else sw.deselect()

        keys = set(s.get("selected") or [])
        if not keys:
            # Settings from older versions stored a Region / City / Node filter instead.
            region, city, node = (s.get("filter_continent", "All"), s.get("filter_city", "All"),
                                  s.get("filter_location", "All"))
            if (region, city, node) != ("All", "All", "All"):
                keys = {loc_key(l) for l in self.locations if matches_region(l, region)
                        and city in ("All", l["city"]) and node in ("All", l["location"])}
        keys &= self.all_keys
        self.selected_keys = set() if keys == self.all_keys else keys

        for proto, settings in s.get("protocols", {}).items():
            if proto in self.protocol_vars:
                self.protocol_vars[proto].set(settings.get("enabled", True))
                for port, enabled in settings.get("ports", {}).items():
                    try:
                        port_int = int(port)
                    except ValueError:
                        continue
                    if port_int in self.port_vars[proto]:
                        self.port_vars[proto][port_int].set(enabled)

        self.priority_order = self.sanitize_priority(s.get("priority_order"))
        self.load_tweaks(s)
        self.refresh_protocol_list()
        self.update_awg_summary()
        self.seg_tls.set(t(f"mode_{self.tls_mode}"))
        self.seg_routing.set(t(f"mode_{self.routing_mode}"))

    def gather_config_data(self):
        data = {
            "timeout": self.entry_timeout.get().strip(),
            "settle": self.entry_settle.get().strip(),
            "ping_host": self.entry_ping_host.get().strip(),
            "ping_count": self.entry_ping_count.get().strip(),
            "resume": bool(self.sw_resume.get()),
            "selected": sorted(self.selected_keys),
            "random_cities": bool(self.sw_random_cities.get()),
            "chaos_mode": bool(self.sw_chaos.get()),
            "stop_on_success": bool(self.sw_stop_success.get()),
            "priority_order": list(self.priority_order),
            "protocols": {},
            "awg_presets": self.selected_awg(),
            "tls_mode": self.tls_mode,
            "routing_mode": self.routing_mode,
        }
        for proto, p_var in self.protocol_vars.items():
            data["protocols"][proto] = {
                "enabled": bool(p_var.get()),
                "ports": {str(p): bool(v.get()) for p, v in self.port_vars[proto].items()},
            }
        return data

    def save_all_config(self):
        self.config_data["last_settings"] = self.gather_config_data()
        self.config_data["cli_path"] = self.entry_cli.get().strip()
        self.config_data["sidebar_open"] = self.sidebar_open
        ConfigManager.save_config(self.config_data)

    def ask_profile_name(self):
        d = ctk.CTkToplevel(self)
        d.title(vis(t("save_profile")))
        place_dialog(d, self, 380, 210, top=140)
        d.resizable(False, False)
        label(d, t("save_profile"), 16, bold=True).pack(fill="x", padx=18, pady=(16, 0))
        label(d, t("save_profile_hint"), 11, MUTED, wraplength=340).pack(fill="x", padx=18)
        e = entry(d, height=38, size=13, placeholder_text=t("profile_name"))
        e.pack(fill="x", padx=18, pady=(12, 0))
        if self.current_profile_name != "Manual":
            e.insert(0, self.current_profile_name)

        def ok():
            name = e.get().strip()
            if not name:
                e.configure(border_color=BAD)
                return
            d.grab_release()
            d.destroy()
            self.save_profile(name)

        row = frame(d)
        row.pack(fill="x", padx=18, pady=14)
        primary_button(row, t("save"), ok, width=max(90, self.text_width(t("save"), sans(13, True)) + 32),
                       height=34).pack(side=end())
        ghost_button(row, t("cancel"), d.destroy, width=max(80, self.text_width(t("cancel"), sans(12)) + 28),
                     height=34).pack(side=end(), padx=pads(0, 8))
        e.bind("<Return>", lambda _e: ok())
        d.bind("<Escape>", lambda _e: d.destroy())
        d.after(200, e.focus_set)

    def save_profile(self, name):
        self.saved_profiles[name] = self.gather_config_data()
        self.config_data["saved_profiles"] = self.saved_profiles
        self.save_all_config()
        self.combo_profiles.configure(values=list(self.saved_profiles.keys()))
        self.combo_profiles.set(name)
        self.current_profile_name = name
        self.log_message(f"Saved profile: {name}", "INFO")
        self.toast(t("profile_saved", n=name), "success")

    def load_profile(self, choice=None):
        name = choice or self.combo_profiles.get()
        if name in self.saved_profiles:
            self.apply_config_to_ui(self.saved_profiles[name])
            self.current_profile_name = name
            self.log_message(f"Loaded profile: {name}", "INFO")
            self.toast(t("profile_loaded", n=name), "info", ms=2200)

    def delete_profile(self):
        name = self.combo_profiles.get()
        if name not in self.saved_profiles:
            self.toast(t("choose_to_delete"), "warn")
            return
        if not ask_yes_no(self, t("delete_profile"), t("delete_profile_q", n=name)):
            return
        del self.saved_profiles[name]
        self.config_data["saved_profiles"] = self.saved_profiles
        ConfigManager.save_config(self.config_data)
        self.combo_profiles.configure(values=list(self.saved_profiles.keys()))
        self.set_profile_placeholder()
        self.current_profile_name = "Manual"
        self.log_message(f"Deleted profile: {name}", "WARN")
        self.toast(t("profile_deleted", n=name), "info")

    # ---------------- job control ----------------
    def get_plan(self):
        plan = {}
        for proto in self.priority_order:
            if self.protocol_vars[proto].get():
                ports = [p for p, v in self.port_vars[proto].items() if v.get()]
                if ports:
                    plan[proto] = ports
        return plan

    def read_number(self, widget, name_key, minimum, maximum):
        try:
            value = int(widget.get().strip())
            if not minimum <= value <= maximum:
                raise ValueError
            return value
        except ValueError:
            self.flag_invalid(widget, t("must_be_number", name=t(name_key), a=minimum, b=maximum))
            return None

    def flag_invalid(self, widget, msg):
        if not self.sidebar_open:
            self.toggle_sidebar()
        self.toggle_timing(True)
        widget.configure(border_color=BAD)
        widget.focus_set()
        self.toast(msg, "error")

    def set_running_ui(self, running, stoppable=True):
        if running:
            self.btn_start.grid_remove()
            self.btn_stop.grid()
            self.btn_stop.configure(state="normal" if stoppable else "disabled", text=t("stop"))
        else:
            self.btn_stop.grid_remove()
            self.btn_start.grid()
            self.update_scope_preview()
        self.btn_disconnect.configure(state="disabled" if running else "normal")

    def start_job(self):
        if self.worker.running:
            return
        plan = self.get_plan()
        if not plan:
            self.toast(t("need_protocol"), "warn")
            return
        cli = self.refresh_cli_status(probe=False)
        if not cli:
            self.focus_cli_entry()
            return
        timeout = self.read_number(self.entry_timeout, "name_timeout", 3, 300)
        if timeout is None:
            return
        settle = self.read_number(self.entry_settle, "name_settle", 0, 60)
        if settle is None:
            return
        ping_count = self.read_number(self.entry_ping_count, "name_pings", 1, 20)
        if ping_count is None:
            return
        host = self.entry_ping_host.get().strip()
        if not host or " " in host:
            self.flag_invalid(self.entry_ping_host, t("bad_host"))
            return

        resume = bool(self.sw_resume.get())
        stored = self.worker.db.get_row_count()
        if not resume and stored and not ask_yes_no(self, t("start_fresh"), t("start_fresh_q", n=num(stored))):
            return

        self.save_all_config()
        if not resume:
            self.worker.db.clear_db()
        self.reload_results_table()

        profile_name = self.current_profile_name or "Manual"
        scope_title, _ = self.scope_summary()
        self.run = {"kind": "job", "scope": scope_title, "profile": profile_name,
                    "started": datetime.datetime.now(), "started_ts": time.time(), "stopped": False,
                    "current": 0, "total": self.test_count()}
        self.step = None
        self.set_connected(None)
        presets, tls_mode, routing_mode = self.tweak_opts()
        opts = {
            "keys": set(self.selected_keys), "resume": resume, "timeout": timeout, "settle": settle,
            "ping_count": ping_count, "ping_host": host,
            "random_cities": bool(self.sw_random_cities.get()), "chaos_mode": bool(self.sw_chaos.get()),
            "stop_on_success": bool(self.sw_stop_success.get()), "profile_name": profile_name,
            "awg_presets": presets, "tls_mode": tls_mode, "routing_mode": routing_mode,
        }
        self.worker.cli_argv = cli
        self.worker.start(plan, opts)
        self.set_running_ui(True)
        self.show_hero("live")
        self.lbl_caption.configure(text=t("cap_starting").upper(), text_color=ACCENT)
        self.lbl_prog_left.configure(text=t("preparing"))
        self.lbl_prog_right.configure(text="")
        self.progress_bar.show(0)
        self.render_header()
        self.render_insights()
        self.set_view("Results")

    def stop_job(self):
        if not self.worker.running:
            return
        self.worker.stop()
        self.btn_stop.configure(state="disabled", text=t("stopping"))
        self.lbl_caption.configure(text=t("cap_stopping").upper(), text_color=WARN)

    def job_finished(self, kept_connection, ok, fail):
        stopped = self.worker.stop_event.is_set()
        if self.run:
            self.run.update(finished=datetime.datetime.now(), stopped=stopped, kept=kept_connection)
        self.title(APP_NAME)
        self.set_running_ui(False)
        self.render_header()
        self.render_data()
        if kept_connection:
            self.set_connected(kept_connection)
            self.log_message("Job finished (connection kept).", "HEADER")
            self.toast(t("connected_to", x=kept_connection), "success")
        else:
            self.log_message("Job finished.", "HEADER")
            if not stopped and self.results:
                self.toast(t("finished_toast", ok=num(ok), fail=num(fail)), "success",
                           action=lambda: self.set_view("Best routes"), action_text=t("tab_best"), ms=7000)
        self.bell()

    def connect_selected(self, tree):
        self.connect_result(self.selected_result(tree))

    def connect_result(self, r):
        if not r:
            return
        if self.worker.running:
            self.toast(t("wait_run"), "warn")
            return
        cli = self.refresh_cli_status(probe=False)
        if not cli:
            self.focus_cli_entry()
            return
        try:
            timeout = max(3, min(300, int(self.entry_timeout.get().strip())))
        except ValueError:
            timeout = 25
        self.worker.cli_argv = cli
        self.set_connected(None)
        self.worker.connect_to(r, timeout)
        self.set_running_ui(True)
        self.show_hero("live")
        self.set_target("cap_connecting", r["city"], r["node"], r["country"], route_label(r))
        self.progress_bar.show(0)
        self.lbl_prog_left.configure(text=t("manual_connection"))
        self.lbl_prog_right.configure(text="")

    def manual_connect_finished(self, r, connected):
        self.set_running_ui(False)
        route = route_label(r)
        where = loc_name(r["city"], r["node"])
        if connected:
            self.set_connected(f"{where} · {route}")
            self.toast(t("connected_via", w=where, r=route), "success")
        else:
            self.toast(t("could_not_connect", w=where, r=route), "error")
        self.render_hero()

    def disconnect_vpn(self):
        if self.worker.running:
            return
        cli = self.refresh_cli_status(probe=False)
        if not cli:
            self.focus_cli_entry()
            return
        self.worker.cli_argv = cli
        self.worker.disconnect()
        self.set_running_ui(True, stoppable=False)
        self.btn_stop.configure(text=t("disconnecting"))

    def disconnect_finished(self, done):
        self.set_running_ui(False)
        if done:
            self.set_connected(None)
        self.toast(t("disconnected") if done else t("could_not_disconnect"), "info" if done else "error", ms=2200)

    def export_csv(self):
        count, path = self.worker.db.export_to_csv(self.current_profile_name)
        if count == -1:
            self.toast(t("csv_failed", e=path), "error", ms=6000)
        else:
            self.toast(t("exported", n=num(count), f=os.path.basename(path)), "success",
                       action=lambda: open_path(REPORTS_DIR), action_text=t("open_folder"), ms=7000)

    # ---------------- window ----------------
    def bind_shortcuts(self):
        self.bind("<Control-Return>", lambda _e: self.start_job())
        self.bind("<F5>", lambda _e: self.start_job())
        self.bind("<Escape>", lambda _e: self.stop_job())
        self.bind("<Control-e>", lambda _e: self.export_csv())
        self.bind("<Control-s>", lambda _e: self.ask_profile_name())
        self.bind("<Control-l>", lambda _e: self.open_location_picker())
        self.bind("<Control-b>", lambda _e: self.toggle_sidebar())
        self.bind("<Control-f>", lambda _e: (self.set_view("Results"), self.entry_search.focus_set()))

    def restore_window(self):
        geo = self.config_data.get("window") or ""
        if re.fullmatch(r"\d+x\d+[+-]-?\d+[+-]-?\d+", geo):
            try:
                self.geometry(geo)
            except tk.TclError:
                pass

    def on_close(self):
        if self.worker.running:
            if not ask_yes_no(self, t("quit"), t("quit_q")):
                return
            self.worker.stop_event.set()
        try:
            if self.state() == "normal":
                self.config_data["window"] = self.geometry()
            self.save_all_config()
        except Exception as e:
            print(f"Close Error: {e}")
        self.destroy()


def restart():
    """Starts a fresh copy of the app (used after changing the language)."""
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        cmd = [sys.executable] + sys.argv[1:]
        # A one-file build unpacks itself to a temporary folder that is deleted when this process exits.
        # Without this the new process would reuse that folder (and its Tcl/Tk paths) and fail to start.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for var in ("TCL_LIBRARY", "TK_LIBRARY", "_MEIPASS2", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE",
                    "_PYI_PARENT_PROCESS_LEVEL"):
            env.pop(var, None)
    else:
        cmd = [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]
    subprocess.Popen(cmd, cwd=APP_PATH, env=env)


def _self_check():
    # Plain plan equals upstream: one route per port, every tweak empty.
    assert expand_routes({"wireguard": [443, 80]}, []) == [("wireguard", 443, "", "", ""), ("wireguard", 80, "", "", "")]
    # One preset x TLS both x routing both = 4 WireGuard routes per port; udp gets the same 4 without a preset.
    routes = expand_routes({"wireguard": [443], "udp": [443]}, ["A - one"], "both", "both")
    assert [r for r in routes if r[0] == "wireguard"] == [
        ("wireguard", 443, "A - one", "", "regular"), ("wireguard", 443, "A - one", "", "alternate"),
        ("wireguard", 443, "A - one", "on", "regular"), ("wireguard", 443, "A - one", "on", "alternate")]
    assert [r[2:] for r in routes if r[0] == "udp"] == [("", "", "regular"), ("", "", "alternate"),
                                                         ("", "on", "regular"), ("", "on", "alternate")]
    assert len(expand_routes({"wireguard": [443, 80]}, ["A", "B"], "on", "auto")) == 4
    text = patch_conf("[General]\nLanguage=en\n\n[Connection]\nProtocolTweaksMethod=0\n", "A - one", "on", "alternate")
    assert "ProtocolTweaksMethod=1\n" in text and "AmneziawgPreset=A - one\n" in text
    assert "CircumventCensorship=true\n" in text and "ServerRoutingMethod=2\n" in text
    assert text.count("ProtocolTweaksMethod=") == 1 and text.startswith("[General]\nLanguage=en\n")
    off = patch_conf(text, "", "", "")
    assert "ProtocolTweaksMethod=2\n" in off and "AmneziawgPreset=\n" in off
    assert "CircumventCensorship=false\n" in off and "ServerRoutingMethod=0\n" in off
    assert "[Connection]" in patch_conf("", "", "", "regular")
    assert route_label({"proto": "udp", "port": 443}) == "udp:443"
    assert route_label({"proto": "wireguard", "port": 443, "awg": "A - one", "tls": "on",
                        "routing": "alternate"}) == "wireguard:443 · A · TLS · alt"
    wsl = ["wsl", "-d", "Ubuntu", "-u", "ubroot", "--", "windscribe-cli"]
    assert wsl_prefix(wsl) == wsl[:-1] and linux_cli(wsl)
    assert wsl_prefix([r"C:\Program Files\Windscribe\windscribe-cli.exe"]) is None
    assert linux_cli([r"C:\Program Files\Windscribe\windscribe-cli.exe"]) == (platform.system() == "Linux")
    # The command must end in the CLI itself; an existing but unrelated program is not "ready".
    assert resolve_cli("wsl") is None and resolve_cli("wsl -d Ubuntu --") is None
    assert resolve_cli(sys.executable) is None
    if " " not in sys.executable:
        assert resolve_cli(f"{sys.executable} -- windscribe-cli") == [sys.executable, "--", "windscribe-cli"]
    print("self-check ok")


def main():
    if "--self-check" in sys.argv:
        _self_check()
        return
    app = App()
    app.mainloop()
    if app.relaunch:
        # The new language changes the whole layout direction, so the window is rebuilt from scratch.
        restart()


if __name__ == "__main__":
    main()
