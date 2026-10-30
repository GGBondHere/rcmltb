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

if __name__ == "__main__":
    unittest.main()
