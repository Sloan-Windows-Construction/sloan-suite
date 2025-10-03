import json, os, pathlib
from typing import Any, Dict

APP_DIR = os.path.join(pathlib.Path.home(), ".sloan_suite")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DATE_FMT_DEFAULT = "%Y-%m-%d"
CONFIG_SCHEMA_VERSION = 2

DEFAULT_CONFIG: Dict[str, Any] = {
    "watch_folder": os.path.join(pathlib.Path.home(), "Downloads"),
    "date_format": DATE_FMT_DEFAULT,
    "schema_version": CONFIG_SCHEMA_VERSION,
    "filename_template": "{customer} {keyword} {detail} {extra} {date}",
    "keywords": [
        {"name": "Initial Quote", "acronym": "InitialQ"},
        {"name": "Final Quote",   "acronym": "FinalQ"},
        {"name": "Initial Picture","acronym": "InitialP"},
        {"name": "Final Picture",  "acronym": "FinalP"},
        {"name": "Blueprint",      "acronym": "BP"},
        {"name": "Completion Form","acronym": "CF"},
        {"name": "Measure Sheet",  "acronym": "MS"},
    ],
    "brands": [
        {"name": "Anlin",          "acronym": "A"},
        {"name": "ProVia",         "acronym": "PV"},
        {"name": "Pella",          "acronym": "P"},
        {"name": "Andersen",       "acronym": "AD"},
        {"name": "Hunter Douglas", "acronym": "HD"},
    ],
    "locations": {
        "Interior": [
            {"name": "Living Room", "acronym": "Living"},
            {"name": "Dining Room", "acronym": "Dining"},
            {"name": "Family Room", "acronym": "Family"},
            {"name": "Bedroom",     "acronym": "Bed"},
            {"name": "Master Bed",  "acronym": "MBed"},
            {"name": "Master Bath", "acronym": "MBath"},
        ],
        "Exterior": [
            {"name": "Right Elevation", "acronym": "Right"},
            {"name": "Left Elevation",  "acronym": "Left"},
            {"name": "Rear Elevation",  "acronym": "Rear"},
            {"name": "Front Elevation", "acronym": "Front"},
        ],
    },
    "organizer": {
        "root_library_name": "Documents",
        "downloads_folder_path": "/Downloads",
        "customer_root_path": "/Customers",
        "create_default_tree": [
            "/Initial/Pictures", "/Initial/Quotes",
            "/Final/Pictures", "/Final/Quotes",
            "/Extra/Completion Forms", "/Extra/Measure Sheets",
        ],
        "routing": {
            "InitialP": "/Initial/Pictures",
            "InitialQ": "/Initial/Quotes",
            "FinalP":   "/Final/Pictures",
            "FinalQ":   "/Final/Quotes",
            "CF":       "/Extra/Completion Forms",
            "MS":       "/Extra/Measure Sheets",
            "BP":       "/Extra"
        }
    },
    "graph": {
        "tenant_id": "d52f227f-1a23-4779-bdb3-79ad391a8be1",
        "client_id": "e72c238a-db6f-4b1c-af05-259bfff1af93",
        "client_secret": "-gD8Q~6o~Pc2NUjzIJ.1u.jtjH7CFQsDqx3_jb21",
        "drive_id": "b!JT-uJDMGx0K5t2KwiIVu3Fli9JbnB3NHs44SdLJJWC54rA7DkqFbQo2-z8kQHB3H",
    },
    "jotform": {
        "enabled": True,
        "api_key": "b86480e52e43cc0678f43412a1c472a6",
        "measure_sheet_form_id": "240678032902151",
        "completion_form_id": "240745482639162",
        "poll_seconds": 120,
        "stage_to_sharepoint": True,
        "cursors": {
            "240678032902151": "",
            "240745482639162": ""
         },
    },

    "watch": {
        "process_existing_on_start": False,
        "sweep_enabled": False,
        "sweep_age_seconds": 120,
        "quiet_seconds": 1.5   # how long size must stay unchanged before we process
    },


}


def ensure_app_dirs() -> None:
    os.makedirs(APP_DIR, exist_ok=True)


def _deep_merge_missing(dst, src):
    # fill only missing keys in dst from src; never overwrite explicit user values
    if isinstance(dst, dict) and isinstance(src, dict):
        for k, v in src.items():
            if k not in dst:
                dst[k] = v
            else:
                dst[k] = _deep_merge_missing(dst[k], v)
        return dst
    return dst


def load_config() -> Dict[str, Any]:
    ensure_app_dirs()
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return json.loads(json.dumps(DEFAULT_CONFIG))

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # migrate: fill in any newly added defaults; bump schema_version
    before = json.dumps(cfg, sort_keys=True)
    cfg = _deep_merge_missing(cfg, DEFAULT_CONFIG)
    cfg["schema_version"] = CONFIG_SCHEMA_VERSION
    after = json.dumps(cfg, sort_keys=True)
    if before != after:
        save_config(cfg)  # persist merged/migrated config
    return cfg




def save_config(cfg: Dict[str, Any]) -> None:
    ensure_app_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def reset_config() -> Dict[str, Any]:
    """Forcefully overwrite config.json with DEFAULT_CONFIG."""
    ensure_app_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    return json.loads(json.dumps(DEFAULT_CONFIG))
