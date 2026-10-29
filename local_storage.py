"""SQLite storage shared by the bot and its standalone updater."""

from contextlib import contextmanager
from json import dumps, loads
from os import chmod, fsync, replace, unlink
from pathlib import Path
from sqlite3 import connect
from tempfile import NamedTemporaryFile
from threading import RLock


DATABASE_PATH = Path("data/state.db")


class LocalStorage:
    def __init__(self, bot_id, path=DATABASE_PATH):
        self.bot_id = str(bot_id)
        self.lock = RLock()
        path = Path(path)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.connection = connect(path, timeout=10, check_same_thread=False)
        with self.connection:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS state ("
                "bot_id TEXT NOT NULL, scope TEXT NOT NULL, key TEXT NOT NULL, "
                "value TEXT NOT NULL, PRIMARY KEY (bot_id, scope, key))"
            )
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS files ("
                "bot_id TEXT NOT NULL, path TEXT NOT NULL, content BLOB NOT NULL, "
                "PRIMARY KEY (bot_id, path))"
            )
        chmod(path, 0o600)

    @contextmanager
    def transaction(self):
        with self.lock, self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            yield

    def _read(self, scope, key, default=None):
        row = self.connection.execute(
            "SELECT value FROM state WHERE bot_id = ? AND scope = ? AND key = ?",
            (self.bot_id, scope, str(key)),
        ).fetchone()
        return loads(row[0]) if row else default

    def _write(self, scope, key, value):
        self.connection.execute(
            "INSERT INTO state VALUES (?, ?, ?, ?) "
            "ON CONFLICT(bot_id, scope, key) DO UPDATE SET value = excluded.value "
            "WHERE state.value != excluded.value",
            (self.bot_id, scope, str(key), dumps(value, ensure_ascii=False)),
        )

    def read(self, scope, key, default=None):
        with self.lock:
            return self._read(scope, key, default)

    def read_all(self, scope):
        with self.lock:
            rows = self.connection.execute(
                "SELECT key, value FROM state WHERE bot_id = ? AND scope = ?",
                (self.bot_id, scope),
            ).fetchall()
        return {key: loads(value) for key, value in rows}

    def write(self, scope, key, value):
        with self.transaction():
            self._write(scope, key, value)

    def patch(self, scope, key, values):
        with self.transaction():
            data = self._read(scope, key, {})
            data.update(values)
            self._write(scope, key, data)

    def write_many(self, records):
        with self.transaction():
            for scope, key, value in records:
                self._write(scope, key, value)

    def config_overrides(self, current):
        with self.lock:
            previous = self._read("settings", "deployment", {})
            saved = self._read("settings", "config", {})
        return {
            key: value
            for key, value in saved.items()
            if key in current
            and key != "DATABASE_URL"
            and key in previous
            and current[key] == previous[key]
        }

    def prepare_config(self, current):
        with self.transaction():
            effective = {**current, **self.config_overrides(current)}
            self._write("settings", "deployment", current)
            self._write("settings", "config", effective)
        return effective

    @staticmethod
    def file_path(path):
        root = Path.cwd().resolve()
        target = Path(path).resolve()
        if not target.is_relative_to(root) or target == root:
            raise ValueError("Private file path must stay inside the application directory")
        if target.is_relative_to((root / "data").resolve()):
            raise ValueError("Cannot store the local database as a private file")
        return target, target.relative_to(root).as_posix()

    def store_file(self, path):
        target, key = self.file_path(path)
        try:
            content = target.read_bytes()
        except FileNotFoundError:
            content = None
        with self.transaction():
            if content is None:
                self.connection.execute(
                    "DELETE FROM files WHERE bot_id = ? AND path = ?",
                    (self.bot_id, key),
                )
            else:
                self.connection.execute(
                    "INSERT INTO files VALUES (?, ?, ?) "
                    "ON CONFLICT(bot_id, path) DO UPDATE SET content = excluded.content",
                    (self.bot_id, key, content),
                )

    def restore_files(self):
        with self.lock:
            rows = self.connection.execute(
                "SELECT path, content FROM files WHERE bot_id = ?", (self.bot_id,)
            ).fetchall()
        for path, content in rows:
            target, _ = self.file_path(path)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(dir=target.parent, delete=False) as output:
                    temporary = output.name
                    output.write(content)
                    output.flush()
                    fsync(output.fileno())
                replace(temporary, target)
            finally:
                if temporary and Path(temporary).exists():
                    unlink(temporary)

    def store_directory(self, directory):
        root, key = self.file_path(directory)
        files = []
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file():
                    target, name = self.file_path(path)
                    files.append((self.bot_id, name, target.read_bytes()))
        with self.transaction():
            self.connection.execute(
                "DELETE FROM files WHERE bot_id = ? AND path LIKE ?",
                (self.bot_id, key + "/%"),
            )
            self.connection.executemany("INSERT INTO files VALUES (?, ?, ?)", files)

    def close(self):
        with self.lock:
            self.connection.close()
