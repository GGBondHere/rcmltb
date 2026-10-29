from asyncio import to_thread
from pathlib import Path

from bot import (
    LOGGER,
    aria2_options,
    config_dict,
    local_storage,
    qbit_options,
    remotes_multi,
    user_data,
)


class SQLiteManager:
    enabled = True
    is_local = True

    def __init__(self):
        self.static_auth = {
            flag: {int(uid) for uid in config_dict[key].split()}
            for flag, key in (("is_auth", "ALLOWED_CHATS"), ("is_sudo", "SUDO_USERS"))
        }

    async def connect(self):
        LOGGER.info("[DB] Using SQLite local storage: data/state.db")
        return True

    async def disconnect(self):
        await to_thread(local_storage.close)

    async def load_settings(self):
        await to_thread(local_storage.restore_files)
        users = await to_thread(local_storage.read_all, "users")
        for user_id, data in users.items():
            user_data[int(user_id)] = data
        aria2_options.update(local_storage.read("settings", "aria2c", {}))
        qbit_options.update(local_storage.read("settings", "qbittorrent", {}))
        remotes_multi[:] = local_storage.read("settings", "multi_remotes", [])
        from bot.helper.ext_utils.rclone_data_holder import rclone_dict

        for user_id, selections in local_storage.read_all("rclone").items():
            rclone_dict[int(user_id)] = selections
        LOGGER.info("[DB] Local settings and private files restored")

    def _user_settings(self, user_id, data):
        data = dict(data)
        # Static permissions are rebuilt from config, rather than saved as grants.
        for flag, ids in self.static_auth.items():
            if int(user_id) in ids:
                data.pop(flag, None)
        return data

    async def save_settings(self):
        records = [
            ("settings", "config", dict(config_dict)),
            ("settings", "aria2c", dict(aria2_options)),
            ("settings", "qbittorrent", dict(qbit_options)),
        ]
        records.extend(
            ("users", uid, self._user_settings(uid, data))
            for uid, data in user_data.items()
        )
        local_storage.write_many(records)
        await self._import_files()

    async def _import_files(self):
        paths = [Path(name) for name in (
            "config.env", "config.py", ".netrc", "cookies.txt", "credentials.json",
            "token.pickle", "token_sa.pickle", "accounts.zip",
        )]
        for directory in ("rclone", "tokens", "Thumbnails", "accounts"):
            root = Path(directory)
            if root.is_dir():
                paths.extend(path for path in root.rglob("*") if path.is_file())
        for path in paths:
            if path.is_file():
                await to_thread(local_storage.store_file, path)

    async def db_load(self):
        await self.load_settings()

    async def update_deploy_config(self):
        from bot.core.config_manager import Config

        await to_thread(local_storage.prepare_config, Config.get_all())

    async def update_config(self, values):
        auth_updates = {}
        for flag, key in (("is_auth", "ALLOWED_CHATS"), ("is_sudo", "SUDO_USERS")):
            if key in values:
                auth_updates[flag] = {int(uid) for uid in str(values[key] or "").split()}
        local_storage.patch("settings", "config", values)
        for flag, ids in auth_updates.items():
            for user_id in self.static_auth[flag] - ids:
                user_data.get(user_id, {}).pop(flag, None)
            for user_id in ids:
                user_data.setdefault(user_id, {})[flag] = True
            self.static_auth[flag] = ids

    async def update_aria2(self, key, value):
        local_storage.patch("settings", "aria2c", {key: value})

    async def update_qbittorrent(self, key, value):
        local_storage.patch("settings", "qbittorrent", {key: value})

    async def update_private_file(self, path):
        await to_thread(local_storage.store_file, path)
        if Path(path).as_posix() == "accounts.zip":
            await to_thread(local_storage.store_directory, "accounts")

    async def update_user_doc(self, user_id, key, path=""):
        if not path:
            path = {
                "rclone": f"rclone/{user_id}/rclone.conf",
                "rclone_global": "rclone/rclone_global/rclone.conf",
                "token_pickle": f"tokens/{user_id}.pickle",
            }[key]
        await self.update_private_file(path)

    async def update_user_data(self, user_id):
        local_storage.write("users", user_id, self._user_settings(user_id, user_data[user_id]))

    async def update_thumb(self, user_id, path=None):
        await self.update_private_file(path or f"Thumbnails/{user_id}.jpg")
        await self.update_user_data(user_id)
