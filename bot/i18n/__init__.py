"""Local Telegram UI translations. Business values never pass through this module."""

from contextlib import contextmanager
from asyncio import Future
from contextvars import ContextVar
from functools import lru_cache, wraps
from html import escape
from inspect import isawaitable
import json
import logging
from pathlib import Path
from string import Formatter


LANGUAGES = ("zh-CN", "en")
DEFAULT_LANGUAGE = "zh-CN"
_actor = ContextVar("telegram_ui_actor", default=None)
_global = ContextVar("telegram_ui_global", default=False)
_language = ContextVar("telegram_ui_language", default=None)
_config = {}
_users = {}
_logger = logging.getLogger(__name__)
_formatter = Formatter()


def bind(config, users):
    """Bind the existing live dictionaries, rather than copying preferences."""
    global _config, _users
    _config, _users = config, users


def normalize_language(value):
    if value not in LANGUAGES:
        raise ValueError("BOT_UI_LANGUAGE must be zh-CN or en")
    return value


def get_language(user_id=None, *, global_default=False):
    if _language.get() and not global_default:
        return _language.get()
    default = _config.get("BOT_UI_LANGUAGE", DEFAULT_LANGUAGE)
    if default not in LANGUAGES:
        _logger.warning("Invalid BOT_UI_LANGUAGE %r; using %s", default, DEFAULT_LANGUAGE)
        default = DEFAULT_LANGUAGE
    if global_default or _global.get():
        return default
    uid = _actor.get() if user_id is None else user_id
    preference = _users.get(uid, {}).get("ui_language")
    return preference if preference in LANGUAGES else default


@contextmanager
def locale_context(user_id=None, *, global_default=False, language=None):
    selected = normalize_language(language) if language else None
    tokens = (
        (_actor, _actor.set(user_id)),
        (_global, _global.set(global_default)),
        (_language, _language.set(selected)),
    )
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def localized_handler(handler):
    """Wrap a Pyrogram handler once, leaving filters and callback data intact."""
    callback = handler.callback
    if getattr(callback, "_ui_localized", False):
        return handler

    @wraps(callback)
    async def invoke(client, update, *args, **kwargs):
        actor = getattr(getattr(update, "from_user", None), "id", None)
        with locale_context(actor):
            result = callback(client, update, *args, **kwargs)
            # new_task callbacks already schedule their work; keep them nonblocking.
            return await result if isawaitable(result) and not isinstance(result, Future) else result

    invoke._ui_localized = True
    handler.callback = invoke
    return handler


def status_locale(function):
    """Shared group/channel status uses the global language, including refreshes."""
    @wraps(function)
    async def invoke(chat_id=None, *args, **kwargs):
        shared = chat_id is None or chat_id < 0
        with locale_context(None if shared else chat_id, global_default=shared):
            return await function(chat_id, *args, **kwargs)
    return invoke


def task_locale(function):
    """Downloader callbacks may arrive on a startup/background event task."""
    @wraps(function)
    async def invoke(task, *args, **kwargs):
        uid = getattr(task, "user_id", None)
        if uid is None:
            uid = getattr(getattr(getattr(task, "message", None), "from_user", None), "id", None)
        with locale_context(uid):
            return await function(task, *args, **kwargs)
    return invoke


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate translation key: {key}")
        result[key] = value
    return result


@lru_cache(maxsize=2)
def get_catalog(language):
    normalize_language(language)
    result = {}
    for path in sorted((Path(__file__).parent / "locales" / language).glob("*.json")):
        entries = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        overlap = result.keys() & entries.keys()
        if overlap:
            raise ValueError(f"Duplicate translation keys in {path}: {sorted(overlap)}")
        result.update(entries)
    return result


class _TrustedHTML(str):
    pass


def raw(value):
    """Mark existing escaped text or composed markup; never use for raw user input."""
    return _TrustedHTML(str(value))


def error_detail(error):
    """Keep only explicitly trusted UI fragments; provider diagnostics stay plain."""
    value = error
    seen = set()
    while isinstance(value, Exception) and len(value.args) == 1 and id(value) not in seen:
        seen.add(id(value))
        value = value.args[0]
    return value if isinstance(value, _TrustedHTML) else str(error)


def tr(_key, *, _language=None, _user_id=None, _html=True, count=None, **params):
    key = _key
    language = normalize_language(_language) if _language else get_language(_user_id)
    template = get_catalog(language).get(key)
    if template is None:
        _logger.warning("Missing %s translation: %s", language, key)
        template = get_catalog("en").get(key)
    if template is None:
        _logger.error("Missing English translation: %s", key)
        return f"[{key}]"
    if isinstance(template, dict):
        template = template.get("one" if count == 1 else "other")
    if not isinstance(template, str):
        raise ValueError(f"Invalid translation entry: {key}")
    if count is not None:
        params["count"] = count
    output = []
    for literal, field, spec, conversion in _formatter.parse(template):
        output.append(literal)
        if field is None:
            continue
        if not field.isidentifier() or field not in params or "{" in spec:
            raise ValueError(f"Invalid or missing placeholder {field!r} in {key}")
        value = params[field]
        if conversion not in (None, "s", "r"):
            raise ValueError(f"Unsupported conversion in {key}")
        formatted = format(repr(value) if conversion == "r" else str(value) if conversion == "s" else value, spec)
        output.append(escape(formatted, quote=True) if _html and not isinstance(value, _TrustedHTML) else formatted)
    return "".join(output)


def display_status(status):
    keys = {
        "⬆️ Uploading": "status.uploading", "📥 Cloning": "status.cloning",
        "⬇️ Downloading": "status.downloading", "📋 Copying": "status.copying",
        "🔄 Syncing": "status.syncing", "📦 Archiving 🔐": "status.archiving",
        "📂 Extracting": "status.extracting", "✂️ Splitting": "status.splitting",
        "⏳ QueueDl": "status.queued_download", "⏳ QueueUp": "status.queued_upload",
        "⏸️ Paused": "status.paused", "🔍 CheckUp": "status.checking",
        "🌱 Seeding": "status.seeding",
    }
    return tr(keys[status]) if status in keys else str(status)


def ui_error(detail):
    return tr("common.technical_error", detail=error_detail(detail))
