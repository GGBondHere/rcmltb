from bot.i18n import tr, raw
from re import (
    ASCII,
    IGNORECASE,
    compile as re_compile,
    fullmatch as re_fullmatch,
    match as re_match,
)
from urllib.parse import parse_qsl

from bot.helper.ext_utils.exceptions import TgLinkException


_TG_MESSAGE_LINK = re_compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog)/"
    r"(?:c/(?P<channel>[1-9][0-9]{0,15})|(?:s/)?(?P<username>[a-z][a-z0-9_]{0,31}))/"
    r"(?:(?P<thread>[1-9][0-9]{0,9})/)?(?P<message>[1-9][0-9]{0,9})/?"
    r"(?:\?(?P<query>[^#\s]*))?",
    ASCII | IGNORECASE,
)
_TG_RESERVED_PATHS = {
    "a", "addemoji", "addlist", "addstickers", "addstyle", "addtheme",
    "auction", "auth", "bg", "boost", "c", "call", "confirmphone",
    "contact", "giftcode", "invoice", "iv", "joinchat", "k", "login",
    "m", "msg", "nft", "proxy", "s", "setlanguage", "share", "socks",
    "web", "z",
}


def parse_tg_message_link(text):
    """Return (chat_id, message_id, user_only) for a complete message link."""
    if not isinstance(text, str):
        return None
    link = text.strip()
    if not link or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in link
    ):
        return None

    open_message = link.lower().startswith("tg://openmessage?")
    match = None if open_message else _TG_MESSAGE_LINK.fullmatch(link)
    if not open_message and match is None:
        return None
    query = link.partition("?")[2] if open_message else match["query"] or ""
    try:
        pairs = parse_qsl(query, keep_blank_values=True, max_num_fields=3)
    except ValueError:
        return None
    params = dict(pairs)
    if len(params) != len(pairs):
        return None

    if open_message:
        if set(params) != {"user_id", "message_id"}:
            return None
        if not re_fullmatch(r"[1-9][0-9]{0,18}", params["user_id"]):
            return None
        if not re_fullmatch(r"[1-9][0-9]{0,9}", params["message_id"]):
            return None
        chat_id = int(params["user_id"])
        if chat_id > 2**63 - 1:
            return None
        message_id = int(params["message_id"])
    else:
        # Comments name a different chat/message; do not save the parent post instead.
        if set(params) - {"single", "thread", "t"}:
            return None
        if "single" in params and params["single"] not in {"", "1"}:
            return None
        if "thread" in params and (
            not re_fullmatch(r"[1-9][0-9]{0,9}", params["thread"])
            or int(params["thread"]) > 2**31 - 1
            or (match["thread"] and match["thread"] != params["thread"])
        ):
            return None
        if "t" in params and (
            not params["t"]
            or not re_fullmatch(
                r"[0-9]+(?::[0-9]{1,2}){0,2}|(?:[0-9]+h)?(?:[0-9]+m)?(?:[0-9]+s)?",
                params["t"],
            )
        ):
            return None
        if match["thread"] and int(match["thread"]) > 2**31 - 1:
            return None
        if match["channel"] is not None:
            channel_id = int(match["channel"])
            if channel_id >= 2**52:
                return None
            chat_id = -1_000_000_000_000 - channel_id
        else:
            chat_id = match["username"]
            if chat_id.lower() in _TG_RESERVED_PATHS:
                return None
        message_id = int(match["message"])
    if message_id > 2**31 - 1:
        return None
    return chat_id, message_id, open_message


def is_magnet(url: str):
    return bool(
        re_match(
            r"^magnet:\?.*xt=urn:(btih|btmh):([a-zA-Z0-9]{32,40}|[a-z2-7]{32}).*", url
        )
    )


def is_url(url: str):
    return bool(
        re_match(
            r"^(?!\/)(rtmps?:\/\/|mms:\/\/|rtsp:\/\/|https?:\/\/|ftp:\/\/)?([^\/:]+:[^\/@]+@)?(www\.)?(?=[^\/:\s]+\.[^\/:\s]+)([^\/:\s]+\.[^\/:\s]+)(:\d+)?(\/[^#\s]*[\s\S]*)?(\?[^#\s]*)?(#.*)?$",
            url,
        )
    )


def is_gdrive_link(url: str):
    return "drive.google.com" in url or "drive.usercontent.google.com" in url


def is_telegram_link(url: str):
    return parse_tg_message_link(url) is not None or url.startswith(
        ("https://t.me/", "tg://openmessage?user_id=")
    )


def is_share_link(url: str):
    return bool(
        re_match(
            r"https?:\/\/.+\.gdtot\.\S+|https?:\/\/(filepress|filebee|appdrive|gdflix)\.\S+",
            url,
        )
    )


def is_rclone_path(path: str):
    return bool(
        re_match(
            r"^(mrcc:)?(?!(magnet:|mtp:|sa:|tp:))(?![- ])[a-zA-Z0-9_\. -]+(?<! ):(?!.*\/\/).*$|^rcl$",
            path,
        )
    )


def is_gdrive_id(id_: str):
    return bool(
        re_match(
            r"^(tp:|sa:|mtp:)?(?:[a-zA-Z0-9-_]{33}|[a-zA-Z0-9_-]{19})$|^gdl$|^(tp:|mtp:)?root$",
            id_,
        )
    )


def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url


async def get_tg_link_message(link):
    target = parse_tg_message_link(link)
    if target is None:
        raise TgLinkException(
            tr('helpers.text.invalid_or_unsupported_telegram_message_link_send_a_direct_link_to_a', _html=False)
        )
    chat_id, msg_id, user_only = target

    from bot import bot, app

    if not user_only:
        try:
            msg = await bot.get_messages(chat_id, msg_id)
            if msg and not msg.empty:
                return msg, bot
        except Exception:
            pass
        if not app:
            raise TgLinkException(
                tr('helpers.text.bot_can_t_access_this_message_or_it_has_been_deleted_make', _html=False)
            )
    elif not app:
        raise TgLinkException(tr('helpers.text.this_private_message_link_requires_user_session_string', _html=False))

    try:
        msg = await app.get_messages(chat_id, msg_id)
    except Exception as e:
        raise TgLinkException(tr('helpers.text.can_t_access_this_chat_with_the_user_session', value1=e, _html=False)) from e
    if msg and not msg.empty:
        return msg, app
    raise TgLinkException(tr('helpers.text.message_not_found_deleted_or_inaccessible_to_the_user_session', _html=False))
