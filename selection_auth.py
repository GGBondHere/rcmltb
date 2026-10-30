"""Task-scoped selection links shared by the bot and the web worker processes."""

from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from os import O_CREAT, O_EXCL, O_WRONLY, fdopen, open as osopen
from pathlib import Path
from re import fullmatch
from secrets import token_bytes
from threading import Lock


KEY_PATH = Path("data/selection.key")
_KEY_LOCK = Lock()


def _selection_key(create=False):
    with _KEY_LOCK:
        if KEY_PATH.is_symlink():
            raise ValueError("Selection key must be a regular file")
        if not KEY_PATH.exists() and create:
            KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = osopen(KEY_PATH, O_CREAT | O_EXCL | O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                with fdopen(descriptor, "wb") as stream:
                    stream.write(token_bytes(32))
        try:
            secret = KEY_PATH.read_bytes()
        except FileNotFoundError:
            return None
        if len(secret) != 32:
            raise ValueError("Invalid selection key")
        return secret


def _valid_gid(gid):
    return isinstance(gid, str) and fullmatch(r"(?:[0-9a-f]{16}|[0-9a-f]{40}|[0-9a-f]{64})", gid.lower()) is not None


def _credentials(secret, gid):
    target = gid.lower().encode("ascii")
    token = hmac_new(secret, b"selection:" + target, sha256).hexdigest()
    pin = f"{int.from_bytes(hmac_new(secret, b'pin:' + target, sha256).digest()[:4], 'big') % 10000:04d}"
    return token, pin


def selection_credentials(gid):
    if not _valid_gid(gid):
        raise ValueError("Invalid torrent task ID")
    return _credentials(_selection_key(create=True), gid)


def verify_selection(gid, token, pin=None):
    if not _valid_gid(gid) or not isinstance(token, str) or not fullmatch(r"[0-9a-f]{64}", token):
        return False
    secret = _selection_key()
    if secret is None:
        return False
    expected_token, expected_pin = _credentials(secret, gid)
    if not compare_digest(token, expected_token):
        return False
    return pin is None or (isinstance(pin, str) and compare_digest(pin, expected_pin))
