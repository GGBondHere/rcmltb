import ast
import asyncio
from configparser import ConfigParser, Error as ConfigError
from html import escape
import logging
import os
from pathlib import Path
from shutil import rmtree
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from source_loader import ROOT, load_source

sys.path.insert(0, str(ROOT))
from local_storage import LocalStorage


OWNER = 100
USER = 111


async def async_rmtree(path):
    rmtree(path)


async def async_makedirs(path, **kwargs):
    os.makedirs(path, **kwargs)


def message(user_id=USER):
    return SimpleNamespace(
        id=777, from_user=SimpleNamespace(id=user_id, username="tester"),
        chat=SimpleNamespace(id=-123), topic_message=False, message_thread_id=None,
        reply_to_message=None,
    )


def filter_create(function):
    async def call(client, update):
        return await function(None, client, update)
    return call


def rclone_fixture(config, data, users):
    filters = load_source("bot/helper/telegram_helper/filters.py", {"CustomFilters"}, {
        "create": filter_create, "OWNER_ID": OWNER, "user_data": users,
        "config_dict": config,
    }).CustomFilters
    return load_source("bot/helper/ext_utils/rclone_utils.py", {
        "is_shared_owner_upload", "can_manage_rclone", "get_rclone_upload_target",
        "is_remote_selected", "is_rclone_config", "get_rclone_path",
    }, {
        "OWNER_ID": OWNER, "config_dict": config, "user_data": users,
        "ospath": os.path, "ConfigParser": ConfigParser, "ConfigError": ConfigError,
        "get_rclone_data": lambda key, uid: data.get(uid, {}).get(key, ""),
        "update_rclone_data": lambda key, value, uid: data.setdefault(uid, {}).update({key: value}),
        "remotes_multi": [], "CustomFilters": filters,
        "sendMessage": AsyncMock(), "send_rclone_config_upload_prompt": AsyncMock(),
        "list_remotes": AsyncMock(), "NotRclonePathFound": ValueError,
        "BotCommands": SimpleNamespace(MirrorSelectCommand=["ms"]),
    })


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_seed_finish_only_deletes_files_after_successful_upload(self):
        for succeeded, local in ((False, False), (True, False), (True, True)):
            with self.subTest(succeeded=succeeded, local=local):
                listener = SimpleNamespace(upload_succeeded=succeeded, onUploadError=AsyncMock())
                remove = AsyncMock()
                module = load_source("bot/helper/listeners/qbit_listener.py", {"__onSeedFinish"}, {
                    "new_task": lambda func: func, "LOGGER": logging.getLogger("test"),
                    "getTaskByGid": AsyncMock(return_value=SimpleNamespace(client=Mock(), listener=lambda: listener)),
                    "get_readable_time": str, "__remove_torrent": remove,
                    "config_dict": {"LOCAL_MIRROR": local},
                })
                await module.__dict__["__onSeedFinish"](SimpleNamespace(hash="hash", name="video", tags="777", ratio=1, seeding_time=1))
                self.assertEqual(remove.call_args.kwargs["delete_files"], succeeded and not local)

    async def test_qbit_removal_and_cancel_keep_task_files(self):
        torrents = SimpleNamespace(delete=AsyncMock(), delete_tags=AsyncMock(), stop=AsyncMock())
        namespace = {
            "TorrentManager": SimpleNamespace(qbittorrent=SimpleNamespace(torrents=torrents)),
            "qb_listener_lock": asyncio.Lock(), "QbTorrents": {},
        }
        module = load_source("bot/helper/listeners/qbit_listener.py", {"_get_tag", "__remove_torrent"}, namespace)
        await module.__dict__["__remove_torrent"]("hash", "777")
        self.assertFalse(torrents.delete.call_args.kwargs["delete_files"])
        status = load_source("bot/helper/mirror_leech_utils/status_utils/qbit_status.py", {"QbitTorrentStatus"}, {
            **namespace, "MirrorStatus": SimpleNamespace(STATUS_SEEDING="seed"),
            "config_dict": {"NO_TASKS_LOGS": True}, "sleep": AsyncMock(),
        })
        task = object.__new__(status.QbitTorrentStatus)
        task.__dict__.update({
            "_QbitTorrentStatus__update": AsyncMock(),
            "_QbitTorrentStatus__info": SimpleNamespace(tags="777", hash="hash"),
            "_QbitTorrentStatus__listener": SimpleNamespace(onDownloadError=AsyncMock()),
            "status": AsyncMock(return_value="download"),
        })
        await task.cancel_task()
        self.assertFalse(torrents.delete.call_args.kwargs["delete_files"])

    async def test_repeated_start_stop_keeps_downloads_and_other_data(self):
        for relative in ("bot/helper/ext_utils/misc_utils.py", "bot/helper/ext_utils/files_utils.py"):
            for local in (False, True):
                with self.subTest(module=relative, local=local), TemporaryDirectory() as tmp:
                    downloads = Path(tmp) / "downloads"
                    residual = downloads / "777" / "video.mp4"
                    residual.parent.mkdir(parents=True)
                    residual.write_bytes(b"not uploaded yet")
                    other = Path(tmp) / "data" / "state.db"
                    other.parent.mkdir()
                    other.write_bytes(b"persistent")

                    async def delete(*args, **kwargs):
                        if kwargs.get("delete_files"):
                            rmtree(residual.parent)

                    torrents = SimpleNamespace(delete=AsyncMock(side_effect=delete))
                    manager = SimpleNamespace(qbittorrent=SimpleNamespace(torrents=torrents), remove_all=AsyncMock())
                    module = load_source(relative, {"start_cleanup", "clean_all"}, {
                        "TorrentManager": manager, "DOWNLOAD_DIR": str(downloads),
                        "config_dict": {"DOWNLOAD_DIR": str(downloads), "LOCAL_MIRROR": local},
                        "aiormtree": async_rmtree, "rmtree": rmtree,
                        "makedirs": async_makedirs, "LOGGER": logging.getLogger("test"),
                    })
                    for _ in range(5):
                        await module.start_cleanup()
                        await module.clean_all()
                    self.assertEqual(residual.read_bytes(), b"not uploaded yet")
                    self.assertEqual(other.read_bytes(), b"persistent")
                    self.assertTrue(downloads.is_dir())
                    self.assertFalse(torrents.delete.call_args.kwargs["delete_files"])

    async def test_failed_or_cancelled_task_keeps_original_and_processed_files(self):
        module = load_source("bot/helper/listeners/task_listener.py", {"TaskListener"}, {
            "TaskConfig": object, "status_dict": {}, "status_dict_lock": asyncio.Lock(),
            "sendMessage": AsyncMock(), "sendMarkup": AsyncMock(),
            "update_all_messages": AsyncMock(), "escape": escape,
            "clean_download": async_rmtree,
        })
        for method in ("onDownloadError", "onUploadError"):
            with self.subTest(method=method), TemporaryDirectory() as tmp:
                original, processed = Path(tmp) / "777", Path(tmp) / "77710000"
                original.mkdir()
                processed.mkdir()
                (original / "video.mp4").write_bytes(b"original")
                (processed / "video.zip").write_bytes(b"processed")
                listener = object.__new__(module.TaskListener)
                listener.__dict__.update(uid=777, dir=str(original), newDir=str(processed), sameDir={},
                                         tag="tester", message=message(), clean=AsyncMock())
                await getattr(listener, method)("Upload cancelled!")
                self.assertTrue((original / "video.mp4").is_file())
                self.assertTrue((processed / "video.zip").is_file())

    async def test_success_cleans_only_completed_task_even_with_multi_remote_setting(self):
        for multi_upload in (False, True):
            with self.subTest(multi_upload=multi_upload), TemporaryDirectory() as tmp:
                done, residual = Path(tmp) / "777", Path(tmp) / "888"
                done.mkdir()
                residual.mkdir()
                (done / "video.mp4").write_bytes(b"done")
                (residual / "video.mp4").write_bytes(b"pending")
                queue_module = SimpleNamespace(start_from_queued=AsyncMock())
                module = load_source("bot/helper/listeners/task_listener.py", {"TaskListener"}, {
                    "TaskConfig": object, "config_dict": {"MULTI_REMOTE_UP": True, "RC_INDEX_URL": ""},
                    "status_dict": {777: Mock()}, "status_dict_lock": asyncio.Lock(),
                    "escape": escape, "ButtonMaker": lambda: SimpleNamespace(url_buildbutton=Mock(), build_menu=Mock()),
                    "cmd_exec": AsyncMock(return_value=("https://example.com/video", "", 0)),
                    "sendMessage": AsyncMock(), "update_all_messages": AsyncMock(),
                    "clean_download": async_rmtree,
                })
                task = object.__new__(module.TaskListener)
                task.__dict__.update(uid=777, dir=str(done), tag="tester", message=message(),
                                     isLeech=False, seed=False, clean=AsyncMock(), multi_remote_upload=multi_upload)
                with patch.dict(sys.modules, {"bot.helper.ext_utils.task_manager": queue_module}):
                    await task.onUploadComplete(None, "4B", 1, 0, "File", "video.mp4",
                                                rclone_config="rclone/100/rclone.conf", rclone_path="drive:Videos")
                self.assertEqual(done.exists(), multi_upload)
                self.assertEqual((residual / "video.mp4").read_bytes(), b"pending")


class SharedRcloneTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.tmp.name)
        self.config = {"MULTI_RCLONE_CONFIG": False, "DEFAULT_GLOBAL_REMOTE": "",
                       "DEFAULT_OWNER_REMOTE": "", "MULTI_REMOTE_UP": False,
                       "UPLOAD_PATH_TEMPLATE": "", "GD_INDEX_URL": "", "RC_INDEX_URL": ""}
        self.data = {OWNER: {"MIRROR_SELECT_REMOTE": "gdrive", "MIRROR_SELECT_BASE_DIR": "Videos/"}}
        self.users = {USER: {"is_auth": True}}
        self.rc = rclone_fixture(self.config, self.data, self.users)
        self.owner_config = Path(f"rclone/{OWNER}/rclone.conf")
        self.owner_config.parent.mkdir(parents=True)
        self.owner_config.write_text("[gdrive]\ntype = drive\n[other]\ntype = drive\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.previous)
        self.tmp.cleanup()

    async def test_shared_preflight_and_path_use_owner_without_global_copy(self):
        self.assertTrue(await self.rc.is_rclone_config(USER, message(), for_upload=True))
        self.assertTrue(await self.rc.is_remote_selected(USER, message()))
        self.assertEqual(await self.rc.get_rclone_path(USER, for_upload=True), self.owner_config.as_posix())
        self.assertFalse(Path("rclone/rclone_global/rclone.conf").exists())

    async def test_missing_owner_config_or_selection_is_rejected(self):
        self.owner_config.unlink()
        self.assertFalse(await self.rc.is_rclone_config(USER, message(), for_upload=True, show_prompt=True))
        self.rc.send_rclone_config_upload_prompt.assert_not_awaited()
        self.assertIn("owner", self.rc.sendMessage.call_args.args[0].lower())
        self.owner_config.write_text("[gdrive]\ntype = drive\n")
        self.data.clear()
        self.config["DEFAULT_OWNER_REMOTE"] = "gdrive"
        self.assertFalse(await self.rc.is_remote_selected(USER, message(), open_selector=True))
        self.rc.list_remotes.assert_not_awaited()

    async def test_removed_remote_is_rejected(self):
        self.data[OWNER]["MIRROR_SELECT_REMOTE"] = "removed"
        self.assertFalse(await self.rc.is_remote_selected(USER, message()))

    async def test_invalid_owner_config_does_not_disclose_contents(self):
        self.owner_config.write_text("secret_oauth_token_without_a_section\n")
        self.assertFalse(await self.rc.is_remote_selected(USER, message()))
        self.assertNotIn("secret_oauth_token", self.rc.sendMessage.call_args.args[0])

    async def test_explicit_global_retains_config_and_remote(self):
        self.config["DEFAULT_GLOBAL_REMOTE"] = "global"
        conf = Path("rclone/rclone_global/rclone.conf")
        conf.parent.mkdir(parents=True)
        conf.write_text("[global]\ntype = drive\n")
        self.assertTrue(await self.rc.is_rclone_config(USER, message(), for_upload=True))
        self.assertEqual(await self.rc.get_rclone_path(USER, for_upload=True), conf.as_posix())
        self.assertEqual(self.rc.get_rclone_upload_target(USER), ("global", ""))

    async def test_independent_mode_and_admins_keep_their_own_config(self):
        for uid, multi in ((USER, True), (OWNER, False), (222, False)):
            with self.subTest(uid=uid, multi=multi):
                self.config["MULTI_RCLONE_CONFIG"] = multi
                self.users[222] = {"is_sudo": True}
                path = Path(f"rclone/{uid}/rclone.conf")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("[personal]\ntype = drive\n")
                self.data[uid] = {"MIRROR_SELECT_REMOTE": "personal", "MIRROR_SELECT_BASE_DIR": "Own/"}
                self.assertEqual(await self.rc.get_rclone_path(uid), path.as_posix())
                self.assertEqual(self.rc.get_rclone_upload_target(uid), ("personal", "Own/"))

    async def test_management_lookup_cannot_return_owner_credentials(self):
        self.assertFalse(await self.rc.is_rclone_config(USER, message()))
        with self.assertRaises(ValueError):
            await self.rc.get_rclone_path(USER, message())
        self.assertTrue(await self.rc.is_rclone_config(USER, message(), isLeech=True))

    def uploader_fixture(self, user_id=USER, return_codes=None):
        template = load_source("bot/helper/ext_utils/template_utils.py", {"apply_upload_template", "join_upload_path"}, {
            "datetime": __import__("datetime").datetime,
        })
        uploads = []
        codes = iter(return_codes or [0] * 10)
        async def spawn(*args, **kwargs):
            self.assertTrue(Path(args[3]).is_file(), "Upload source was deleted before all targets finished")
            uploads.append(args)
            return SimpleNamespace(wait=AsyncMock(return_value=next(codes)),
                                   stderr=SimpleNamespace(read=AsyncMock(return_value=b"failed")))

        uploader = load_source("bot/helper/mirror_leech_utils/upload_utils/rclone_mirror.py", {"RcloneMirror"}, {
            "config_dict": self.config, "user_data": self.users,
            "get_rclone_path": self.rc.get_rclone_path,
            "get_rclone_upload_target": lambda uid: self.rc.get_rclone_upload_target(uid),
            "is_shared_owner_upload": lambda uid: self.rc.is_shared_owner_upload(uid),
            "get_rclone_data": self.rc.get_rclone_data, "remotes_multi": [],
            "CustomFilters": self.rc.CustomFilters, "ospath": os.path,
            "GLOBAL_EXTENSION_FILTER": [], "walk": os.walk,
            "MirrorStatus": SimpleNamespace(STATUS_UPLOADING="upload"),
            "apply_upload_template": template.apply_upload_template,
            "join_upload_path": lambda *args: template.join_upload_path(*args),
            "create_subprocess_exec": spawn, "PIPE": -1,
            "is_gdrive_remote": AsyncMock(return_value=True), "setRcloneFlags": AsyncMock(),
            "status_dict_lock": asyncio.Lock(), "status_dict": {},
            "RcloneStatus": lambda *a: SimpleNamespace(start=AsyncMock()),
            "sendStatusMessage": AsyncMock(), "get_readable_file_size": str,
            "SystemRandom": __import__("random").SystemRandom,
            "ascii_letters": "abc", "digits": "123", "NotRclonePathFound": ValueError,
            "clean_download": AsyncMock(),
        })
        Path("video.mp4").write_bytes(b"video")
        listener = SimpleNamespace(message=message(user_id), uid=777, dir="downloads/777",
                                   onUploadComplete=AsyncMock(), onUploadError=AsyncMock())
        return uploader, uploads, listener

    async def test_upload_reads_current_owner_target_and_preserves_template_priority(self):
        uploader, uploads, listener = self.uploader_fixture()
        async def upload():
            await uploader.RcloneMirror("video.mp4", "video.mp4", 5, USER, listener).mirror()
        await upload()
        self.assertEqual(uploads[-1][4], "gdrive:Videos/")
        self.config["UPLOAD_PATH_TEMPLATE"] = "{user_id}"
        await upload()
        self.assertEqual(uploads[-1][4], "gdrive:Videos/111")
        self.users[USER]["upload_template"] = "{username}/{category}/{task_type}"
        self.users[USER]["category"] = "Clips"
        self.data[OWNER] = {"MIRROR_SELECT_REMOTE": "other", "MIRROR_SELECT_BASE_DIR": "New/"}
        await upload()
        self.assertEqual(uploads[-1][4], "other:New/tester/Clips/mirror")
        self.users[USER]["upload_template"] = "../escape"
        count = len(uploads)
        await upload()
        self.assertEqual(len(uploads), count)
        listener.onUploadError.assert_awaited()

    async def test_explicit_global_upload_ignores_owner_and_user_selections(self):
        self.config["DEFAULT_GLOBAL_REMOTE"] = "global"
        self.data[USER] = {"MIRROR_SELECT_REMOTE": "stale", "MIRROR_SELECT_BASE_DIR": "Wrong/"}
        path = Path("rclone/rclone_global/rclone.conf")
        path.parent.mkdir(parents=True)
        path.write_text("[global]\ntype=drive\n")
        uploader, uploads, listener = self.uploader_fixture()
        await uploader.RcloneMirror("video.mp4", "video.mp4", 5, USER, listener).mirror()
        self.assertEqual(uploads[0][2], "--config=rclone/rclone_global/rclone.conf")
        self.assertEqual(uploads[0][4], "global:/")

    async def test_independent_upload_uses_user_config_and_selected_directory(self):
        self.config["MULTI_RCLONE_CONFIG"] = True
        path = Path(f"rclone/{USER}/rclone.conf")
        path.parent.mkdir(parents=True)
        path.write_text("[personal]\ntype=drive\n")
        self.data[USER] = {"MIRROR_SELECT_REMOTE": "personal", "MIRROR_SELECT_BASE_DIR": "Mine/"}
        uploader, uploads, listener = self.uploader_fixture()
        await uploader.RcloneMirror("video.mp4", "video.mp4", 5, USER, listener).mirror()
        self.assertEqual(uploads[0][2], f"--config={path.as_posix()}")
        self.assertEqual(uploads[0][4], "personal:Mine/")

    async def test_multi_remote_failure_does_not_clean_local_files(self):
        self.config["MULTI_REMOTE_UP"] = True
        uploader, uploads, listener = self.uploader_fixture(OWNER, [0, 1])
        uploader.remotes_multi[:] = ["gdrive", "other"]
        await uploader.RcloneMirror("video.mp4", "video.mp4", 5, OWNER, listener).mirror()
        self.assertEqual(len(uploads), 2)
        listener.onUploadError.assert_awaited_once()
        uploader.clean_download.assert_not_awaited()
        self.assertEqual(Path("video.mp4").read_bytes(), b"video")

    async def test_multi_remote_success_cleans_task_after_all_uploads(self):
        self.config["MULTI_REMOTE_UP"] = True
        uploader, uploads, listener = self.uploader_fixture(OWNER)
        uploader.remotes_multi[:] = ["gdrive", "other"]
        completion_flags = []
        listener.onUploadComplete.side_effect = lambda *args, **kwargs: completion_flags.append(listener.multi_remote_upload)
        await uploader.RcloneMirror("video.mp4", "video.mp4", 5, OWNER, listener).mirror()
        self.assertEqual(len(uploads), 2)
        self.assertEqual(completion_flags, [True, False])

    async def test_real_multi_remote_listener_preserves_seed_sources_and_failed_uploads(self):
        for seed, compress, processed, succeeds in (
            (False, False, False, True), (True, False, False, True),
            (True, True, False, True), (True, True, True, True),
            (True, True, False, False), (True, True, True, False),
        ):
            with self.subTest(seed=seed, compress=compress, processed=processed, succeeds=succeeds):
                self.config["MULTI_REMOTE_UP"] = True
                uploader, uploads, _ = self.uploader_fixture(OWNER, [0, 0 if succeeds else 1])
                uploader.remotes_multi[:] = ["gdrive", "other"]
                task_dir = Path(f"downloads/{seed}-{compress}-{processed}-{succeeds}")
                task_dir.mkdir(parents=True)
                original = task_dir / "video.mp4"
                original.write_bytes(b"original video")
                new_dir = task_dir.with_name(task_dir.name + "-processed") if processed else None
                if new_dir:
                    new_dir.mkdir()
                source = ((new_dir or task_dir) / "video.zip") if compress else original
                if compress:
                    source.write_bytes(b"compressed video")
                module = load_source("bot/helper/listeners/task_listener.py", {"TaskListener"}, {
                    "TaskConfig": object, "config_dict": self.config,
                    "status_dict": {}, "status_dict_lock": asyncio.Lock(), "escape": escape,
                    "ButtonMaker": lambda: SimpleNamespace(url_buildbutton=Mock(), build_menu=Mock()),
                    "get_id": AsyncMock(return_value="file-id"), "sendMessage": AsyncMock(),
                    "update_all_messages": AsyncMock(), "clean_download": async_rmtree,
                    "clean_target": lambda path: asyncio.to_thread(lambda: Path(path).unlink() if Path(path).is_file() else rmtree(path)),
                })
                listener = object.__new__(module.TaskListener)
                listener.__dict__.update(uid=777, dir=task_dir.as_posix(), tag="tester", message=message(OWNER),
                                         isLeech=False, seed=seed, compress=compress, newDir=new_dir.as_posix() if new_dir else "",
                                         clean=AsyncMock())
                queue = SimpleNamespace(start_from_queued=AsyncMock())
                with patch.dict(sys.modules, {"bot.helper.ext_utils.task_manager": queue}):
                    await uploader.RcloneMirror(source.as_posix(), source.name, 5, OWNER, listener).mirror()
                self.assertEqual(len(uploads), 2)
                if succeeds:
                    self.assertEqual(original.exists(), seed)
                    if compress:
                        self.assertFalse(source.exists())
                else:
                    self.assertEqual(original.read_bytes(), b"original video")
                    self.assertTrue(source.exists())

    async def test_cancel_during_multi_remote_completion_cannot_start_next_upload(self):
        self.config["MULTI_REMOTE_UP"] = True
        uploader, uploads, listener = self.uploader_fixture(OWNER)
        uploader.remotes_multi[:] = ["gdrive", "other"]
        task = uploader.RcloneMirror("video.mp4", "video.mp4", 5, OWNER, listener)
        async def cancel_on_complete(*args, **kwargs):
            await task.cancel_task()
        listener.onUploadComplete.side_effect = cancel_on_complete
        await task.mirror()
        self.assertEqual(len(uploads), 1)
        uploader.clean_download.assert_not_awaited()

    async def test_auto_media_and_tg_link_pass_shared_preflight(self):
        downloader = SimpleNamespace(download=AsyncMock())
        module = load_source("bot/modules/mirror_leech.py", {"mirror_leech", "handle_auto_mirror"}, {
            "is_rclone_config": self.rc.is_rclone_config, "is_remote_selected": self.rc.is_remote_selected,
            "TaskListener": lambda *args: SimpleNamespace(uid=777),
            "TelegramDownloader": lambda *args: downloader,
            "conditional_queue_add": AsyncMock(), "DOWNLOAD_DIR": "downloads/",
            "parse_tg_message_link": lambda text: ("channel", 1, False),
            "parser": SimpleNamespace(parse_args=Mock(side_effect=ValueError("stop after preflight"))),
            "sendMessage": AsyncMock(), "MIRROR_HELP_DICT": {"Cmd": "help", "Menu": None},
        })
        media = message()
        media.text = None
        media.document = None
        media.video = SimpleNamespace(mime_type="video/mp4")
        await module.handle_auto_mirror(None, media)
        module.conditional_queue_add.assert_awaited_once_with(media, downloader.download)
        link = message()
        link.text = "https://t.me/channel/123"
        await module.handle_auto_mirror(None, link)
        module.parser.parse_args.assert_called_once_with([link.text])

    async def test_regular_user_can_cancel_only_own_tasks(self):
        cancel = AsyncMock()
        task = SimpleNamespace(message=message(), type=lambda: "Rclone", task=lambda: SimpleNamespace(cancel_task=cancel))
        module = load_source("bot/modules/cancel.py", {"cancel_task"}, {
            "getTaskByGid": AsyncMock(return_value=task), "sendMessage": AsyncMock(),
            "OWNER_ID": OWNER, "user_data": self.users,
        })
        other = message(222)
        other.text = "/cancel gid"
        await module.cancel_task(None, other)
        cancel.assert_not_awaited()
        own = message()
        own.text = "/cancel gid"
        await module.cancel_task(None, own)
        cancel.assert_awaited_once()

    async def test_sqlite_restores_owner_config_and_target_for_shared_uploads(self):
        storage = LocalStorage("test", "data/state.db")
        holder = load_source("bot/helper/ext_utils/rclone_data_holder.py", {"get_rclone_data", "update_rclone_data"}, {
            "local_storage": storage, "rclone_dict": self.data,
            "PERSISTENT_KEYS": {"MIRROR_SELECT_REMOTE", "MIRROR_SELECT_BASE_DIR"},
        })
        holder.update_rclone_data("MIRROR_SELECT_REMOTE", "other", OWNER)
        holder.update_rclone_data("MIRROR_SELECT_BASE_DIR", "Restored/Videos/", OWNER)
        storage.store_file(self.owner_config)
        storage.close()
        self.owner_config.unlink()
        self.data.clear()
        storage = LocalStorage("test", "data/state.db")
        try:
            manager = load_source("bot/helper/ext_utils/sqlite_handler.py", {"SQLiteManager"}, {
                "config_dict": {"ALLOWED_CHATS": "", "SUDO_USERS": ""},
                "local_storage": storage, "user_data": {}, "aria2_options": {},
                "qbit_options": {}, "remotes_multi": [], "to_thread": asyncio.to_thread,
                "LOGGER": logging.getLogger("test"),
            })
            with patch.dict(sys.modules, {"bot.helper.ext_utils.rclone_data_holder": holder}):
                await manager.SQLiteManager().load_settings()
            self.assertTrue(await self.rc.is_rclone_config(USER, message(), for_upload=True))
            self.assertEqual(self.rc.get_rclone_upload_target(USER), ("other", "Restored/Videos/"))
            self.assertIn("[other]", self.owner_config.read_text())
        finally:
            storage.close()

    async def test_shared_management_callbacks_denied_and_independent_menus_bound_to_requester(self):
        filters = self.rc.CustomFilters
        query = SimpleNamespace(from_user=message().from_user,
                                message=SimpleNamespace(reply_to_message=message()))
        self.assertFalse(await filters.rclone_callback_filter(None, query))
        self.assertTrue(await filters.user_callback_filter(None, query))
        self.config["MULTI_RCLONE_CONFIG"] = True
        self.assertTrue(await filters.rclone_callback_filter(None, query))
        query.message.reply_to_message = message(OWNER)
        self.assertFalse(await filters.rclone_callback_filter(None, query))
        query.from_user = message(OWNER).from_user
        self.assertTrue(await filters.rclone_callback_filter(None, query))
        query.from_user = message().from_user
        query.message.reply_to_message = message()
        self.users.clear()
        self.assertFalse(await filters.rclone_callback_filter(None, query))

    async def test_files_view_sends_secrets_only_in_requesters_private_chat(self):
        module = load_source("bot/modules/botfiles.py", {"_view_section_file"}, {
            "_section_path": lambda *args: str(self.owner_config), "ospath": os.path,
            "sendMessage": AsyncMock(),
        })
        client = SimpleNamespace(send_document=AsyncMock())
        for section in ("rclone", "token", "config", "rclone_global"):
            await module._view_section_file(client, message(OWNER), OWNER, section)
            self.assertEqual(client.send_document.call_args.kwargs["chat_id"], OWNER)
        client.send_document.reset_mock()
        client.send_document.side_effect = RuntimeError("secret_token_in_transport_error")
        await module._view_section_file(client, message(OWNER), OWNER, "rclone")
        client.send_document.assert_awaited_once()
        self.assertNotIn("secret_token", module.sendMessage.call_args.args[0])
        self.assertIn("private", module.sendMessage.call_args.args[0])

    def test_cloud_callbacks_register_the_management_guard(self):
        expected = {
            "copy": {"next_page_copy", "copy_menu_callback"},
            "rcfm": {"myfiles_callback", "next_page_myfiles"},
            "mirror_select": {"next_page_mirrorselect", "mirrorselect_callback"},
            "sync": {"sync_callback"}, "bisync": {"bysync_cb"},
            "cleanup": {"cleanup_callback"}, "storage": {"storage_menu_cb"},
            "botfiles": {"botfiles_callback"}, "leech": {"next_page_leech", "leech_menu_cb"},
            "serve": {"serve_callback"}, "mirror_leech": {"mirror_select"},
        }
        for module, callbacks in expected.items():
            tree = ast.parse((ROOT / f"bot/modules/{module}.py").read_text(encoding="utf-8"))
            for call in ast.walk(tree):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "CallbackQueryHandler":
                    name = call.args[0].id
                    if name in callbacks:
                        expression = next(kw.value for kw in call.keywords if kw.arg == "filters")
                        self.assertIn("CustomFilters.rclone_callback_filter", ast.unparse(expression), name)
                        callbacks.remove(name)
            self.assertFalse(callbacks, module)

    def test_runtime_defaults_stay_shared_and_compose_does_not_override_them(self):
        config = load_source("bot/core/config_manager.py", {"Config"})
        self.assertFalse(config.Config.MULTI_RCLONE_CONFIG)
        self.assertEqual(config.Config.DEFAULT_GLOBAL_REMOTE, "")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("MULTI_RCLONE_CONFIG:", compose)
        self.assertNotIn("DEFAULT_GLOBAL_REMOTE:", compose)


if __name__ == "__main__":
    unittest.main()
