"""Read existing Google OAuth pickles without importing executable pickle globals."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from os import chmod, fdopen, replace, unlink
from pathlib import Path
from pickle import HIGHEST_PROTOCOL, Unpickler, UnpicklingError, dump
from pickletools import genops
from tempfile import mkstemp

from google.oauth2.credentials import Credentials


MAX_TOKEN_SIZE = 1024 * 1024


class _LegacyCredentials:
    pass


class _IgnoredState:
    def __new__(cls, *args, **kwargs):
        return object.__new__(cls)

    def __init__(self, *args, **kwargs):
        pass


def _legacy_bytes(value, encoding):
    if not isinstance(value, str) or encoding != "latin1":
        raise UnpicklingError("Unsupported legacy byte encoding")
    return value.encode("latin1")


class _CredentialReader(Unpickler):
    def find_class(self, module, name):
        # Inert objects receive legacy state; Google's __setstate__ is never run.
        if (module, name) == ("google.oauth2.credentials", "Credentials"):
            return _LegacyCredentials
        if module == "google.auth._regional_access_boundary_utils":
            # Version-dependent cache state is ignored, never instantiated as Google code.
            return _IgnoredState
        if (module, name) == ("_codecs", "encode"):
            return _legacy_bytes
        if module in {"builtins", "__builtin__"} and name in {"set", "frozenset"}:
            return {"set": set, "frozenset": frozenset}[name]
        if module == "datetime" and name in {"datetime", "timedelta", "timezone"}:
            return {"datetime": datetime, "timedelta": timedelta, "timezone": timezone}[name]
        raise UnpicklingError("Unsupported object in Google Drive token")

    def persistent_load(self, pid):
        raise UnpicklingError("Persistent objects are not supported")


def read_drive_credentials(path):
    try:
        with open(path, "rb") as stream:
            payload = stream.read(MAX_TOKEN_SIZE + 1)
        if not payload or len(payload) > MAX_TOKEN_SIZE:
            raise ValueError("Google Drive token is empty or too large")
        # Cached extension objects can otherwise bypass find_class().
        for opcode, argument, _ in genops(payload):
            if opcode.name in {"EXT1", "EXT2", "EXT4", "PERSID", "BINPERSID"}:
                raise ValueError("Unsupported pickle extension in Google Drive token")
            if opcode.name == "FRAME" and argument > MAX_TOKEN_SIZE:
                raise ValueError("Google Drive token frame is too large")
        value = _CredentialReader(BytesIO(payload)).load()
        if type(value) is not _LegacyCredentials:
            raise ValueError("Expected Google OAuth user credentials")
        state = vars(value)
        fields = {
            "token": "token", "refresh_token": "_refresh_token", "token_uri": "_token_uri",
            "client_id": "_client_id", "client_secret": "_client_secret",
            "id_token": "_id_token", "quota_project_id": "_quota_project_id", "rapt_token": "_rapt_token",
        }
        arguments = {}
        for name, key in fields.items():
            field = state.get(key)
            if field is not None and not isinstance(field, str):
                raise ValueError(f"Invalid Google OAuth field: {name}")
            arguments[name] = field
        scopes = state.get("_scopes")
        if scopes is not None and (
            not isinstance(scopes, (list, tuple, set))
            or any(not isinstance(scope, str) for scope in scopes)
        ):
            raise ValueError("Invalid Google OAuth scopes")
        expiry = state.get("expiry")
        if expiry is not None and type(expiry) is not datetime:
            raise ValueError("Invalid Google OAuth expiry")
        credentials = Credentials(**arguments, scopes=scopes)
        credentials.expiry = expiry
        return credentials
    except (OSError, ValueError, TypeError, AttributeError, EOFError, UnpicklingError, OverflowError) as error:
        raise ValueError("Invalid or unsafe Google Drive token; generate a new token.pickle") from error


def write_drive_credentials(credentials, path):
    if type(credentials) is not Credentials:
        raise ValueError("Expected Google OAuth user credentials")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = mkstemp(prefix=".token-", suffix=".pickle", dir=target.parent)
    try:
        with fdopen(descriptor, "wb") as stream:
            dump(credentials, stream, protocol=HIGHEST_PROTOCOL)
        # Also validate what will be persisted before replacing a working token.
        read_drive_credentials(temporary)
        chmod(temporary, 0o600)
        replace(temporary, target)
    finally:
        if Path(temporary).exists():
            unlink(temporary)
