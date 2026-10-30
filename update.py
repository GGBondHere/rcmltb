from logging import (
    FileHandler,
    StreamHandler,
    INFO,
    basicConfig,
    error as log_error,
    info as log_info,
)
from os import path as ospath, environ
from source_update import update_source
from pymongo import MongoClient
from dotenv import load_dotenv, dotenv_values
from local_storage import DATABASE_PATH, LocalStorage

if ospath.exists("botlog.txt"):
    with open("botlog.txt", "r+") as f:
        f.truncate(0)

basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[FileHandler("log.txt"), StreamHandler()],
    level=INFO,
)

load_dotenv(
    "config.env",
    override=bool(environ.get("DATABASE_URL") or dotenv_values("config.env").get("DATABASE_URL")),
)

BOT_TOKEN = environ.get("BOT_TOKEN", "")
if len(BOT_TOKEN) == 0:
    log_error("BOT_TOKEN variable is missing! Exiting now")
    exit(1)

bot_id = BOT_TOKEN.split(":", 1)[0]

DATABASE_URL = environ.get("DATABASE_URL", "")
if len(DATABASE_URL) == 0:
    DATABASE_URL = None

if DATABASE_URL is not None:
    try:
        conn = MongoClient(DATABASE_URL)
        db = conn.rcmltb
        old_config = db.settings.deployConfig.find_one({"_id": bot_id})
        config_dict = db.settings.config.find_one({"_id": bot_id})
        if old_config is not None:
            del old_config["_id"]
        if (
            old_config is not None
            and old_config == dict(dotenv_values("config.env"))
            or old_config is None
        ) and config_dict is not None:
            environ["UPSTREAM_REPO"] = config_dict["UPSTREAM_REPO"]
            environ["UPSTREAM_BRANCH"] = config_dict["UPSTREAM_BRANCH"]
        conn.close()
    except Exception as e:
        log_error(f"Database ERROR: {e}")

elif DATABASE_PATH.exists():
    store = LocalStorage(bot_id)
    try:
        current = {
            "UPSTREAM_REPO": environ.get("UPSTREAM_REPO", "").strip(),
            "UPSTREAM_BRANCH": environ.get("UPSTREAM_BRANCH", "").strip() or "master",
        }
        for key, value in store.config_overrides(current).items():
            environ[key] = str(value)
    finally:
        store.close()

UPSTREAM_REPO = environ.get("UPSTREAM_REPO", "")
if len(UPSTREAM_REPO) == 0:
    UPSTREAM_REPO = None

UPSTREAM_BRANCH = environ.get("UPSTREAM_BRANCH", "")
if len(UPSTREAM_BRANCH) == 0:
    UPSTREAM_BRANCH = "master"

if UPSTREAM_REPO is not None:
    try:
        update_source(UPSTREAM_REPO, UPSTREAM_BRANCH)
    except (OSError, ValueError) as error:
        log_error(f"Automatic update skipped: {error}")
    else:
        log_info("Successfully updated from UPSTREAM_REPO")
