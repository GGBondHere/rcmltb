"""Offline checks against the actual helper definitions; no Telegram clients."""

import ast
import asyncio
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from functools import partial, wraps
from html import escape
from types import ModuleType, SimpleNamespace
from urllib.parse import urlparse
import unittest

from source_loader import ROOT, get_i18n


i18n = get_i18n()


def definitions(path, names, namespace=None, assignments=False):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if
             isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in names
             or assignments and isinstance(node, ast.Assign)
             and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names]
    module = ModuleType(path)
    module.__dict__.update({name: getattr(i18n, name) for name in
                           ("tr", "raw", "status_locale", "task_locale", "locale_context", "display_status", "error_detail")})
    module.__dict__["escape"] = escape
    module.__dict__.update(namespace or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), module.__dict__)
    return module


class Buttons:
    def __init__(self):
        self.items = []

    def cb_buildbutton(self, text, data, *args):
        self.items.append((text, data))

    def url_buildbutton(self, text, url):
        self.items.append((text, url))

    def build_menu(self, columns=1):
        return self.items


def help_module():
    return definitions("bot/helper/ext_utils/help_messages.py", {
        "_build_help", "LocalizedHelpMap", "LocalizedHelp", "_HELP_LABELS",
        "MIRROR_HELP_DICT", "LEECH_HELP_DICT", "YT_HELP_DICT", "BATCH_HELP_DICT",
        "CLONE_HELP_MESSAGE", "PASSWORD_ERROR_MESSAGE",
    }, {"Mapping": Mapping, "ButtonMaker": Buttons}, assignments=True)


class HelpTests(unittest.TestCase):
    def setUp(self):
        self.config = {"BOT_UI_LANGUAGE": "zh-CN"}
        self.users = {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}}
        i18n.bind(self.config, self.users)
        self.help = help_module()

    def test_help_text_and_menu_recompute_without_changing_callbacks(self):
        with i18n.locale_context(1):
            english = self.help.MIRROR_HELP_DICT["Cmd"]
            en_buttons = self.help.MIRROR_HELP_DICT["Menu"]
        with i18n.locale_context(2):
            chinese = self.help.MIRROR_HELP_DICT["Cmd"]
            zh_buttons = self.help.MIRROR_HELP_DICT["Menu"]
        self.assertIn("MIRROR COMMANDS", english)
        self.assertIn("网盘上传", chinese)
        self.assertEqual([item[1] for item in en_buttons], [item[1] for item in zh_buttons])
        self.assertEqual(en_buttons[0], ("✏️Rename", "help m ✏️Rename"))
        self.assertEqual(zh_buttons[0], ("✏️重命名", "help m ✏️Rename"))
        with i18n.locale_context(1):
            self.users[1]["ui_language"] = "zh-CN"
            self.assertIn("网盘上传", self.help.MIRROR_HELP_DICT["Cmd"])

    def test_constant_help_resolves_when_rendered_and_braces_survive(self):
        with i18n.locale_context(1):
            self.assertIn("Send Gdrive", str(self.help.CLONE_HELP_MESSAGE))
            self.assertIn('{"ffmpeg": ["-threads", "4"]}', self.help.YT_HELP_DICT["Options"])
        with i18n.locale_context(2):
            self.assertIn("批量云端复制", str(self.help.CLONE_HELP_MESSAGE))
            self.assertIn("需要密码", self.help.PASSWORD_ERROR_MESSAGE.format("https://example.com"))
            self.assertIn("<b>", self.help.YT_HELP_DICT["Rename"])
            self.assertNotIn("&lt;b&gt;", self.help.YT_HELP_DICT["Rename"])

    def test_direct_link_error_keeps_machine_prefix_in_both_languages(self):
        module = definitions("bot/helper/mirror_leech_utils/download_utils/direct_link_generator.py",
                             {"direct_link_generator"}, {"urlparse": urlparse, "DirectDownloadLinkException": ValueError})
        for uid, word in ((1, "Invalid URL"), (2, "链接无效")):
            with i18n.locale_context(uid), self.assertRaises(ValueError) as raised:
                module.direct_link_generator("invalid")
            self.assertTrue(str(raised.exception).startswith("ERROR:"))
            self.assertIn(word, str(raised.exception))


class StatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.config = {"BOT_UI_LANGUAGE": "zh-CN", "STATUS_LIMIT": 10, "DOWNLOAD_DIR": "/tmp"}
        self.users = {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}}
        i18n.bind(self.config, self.users)
        raw = definitions("bot/helper/mirror_leech_utils/status_utils/status_utils.py", {"MirrorStatus", "TaskType"})
        self.statuses = raw.MirrorStatus
        self.tasks = {}
        self.pool = ThreadPoolExecutor(max_workers=2)
        self.addCleanup(self.pool.shutdown)
        namespace = {
            "config_dict": self.config, "status_dict": self.tasks, "status_pages": {}, "PAGES": 1,
            "MirrorStatus": raw.MirrorStatus, "TaskType": raw.TaskType, "queue": None, "ButtonMaker": Buttons,
            "iscoroutinefunction": asyncio.iscoroutinefunction, "escape": escape,
            "get_readable_file_size": lambda value: f"{value}B", "get_progress_bar_string": lambda value: "[■]",
            "get_progress_bar_rclone": lambda value: "[■]", "cpu_percent": lambda: 10,
            "disk_usage": lambda path: SimpleNamespace(free=123), "virtual_memory": lambda: SimpleNamespace(percent=20),
            "time": lambda: 65, "botUptime": 0, "BotCommands": SimpleNamespace(CancelCommand="cancel"),
            "LOGGER": SimpleNamespace(error=lambda value: None), "bot_loop": asyncio.get_running_loop(),
            "THREADPOOL": self.pool, "partial": partial, "copy_context": copy_context,
        }
        self.module = definitions("bot/helper/ext_utils/bot_utils.py", {
            "_get_attr", "get_readable_message", "text_size_to_bytes", "get_readable_time", "run_sync_to_async",
        }, namespace)

    def task(self, status):
        return SimpleNamespace(status=lambda: status, type=lambda: "Telegram", name=lambda: "<file&>",
                               size=lambda: "20B", progress=lambda: "50%", processed_bytes=lambda: "10B",
                               speed=lambda: "1B/s", gid=lambda: "gid", message=SimpleNamespace(
                                   chat=SimpleNamespace(type=SimpleNamespace(name="PRIVATE"))))

    async def test_status_uses_private_preference_and_global_group_language(self):
        self.tasks[1] = self.task(self.statuses.STATUS_DOWNLOADING)
        private, en_buttons = await self.module.get_readable_message(1)
        group, zh_buttons = await self.module.get_readable_message(-100)
        self.assertIn("⬇️ Downloading", private)
        self.assertIn("<b>Downloaded:</b>", private)
        self.assertIn("正在下载", group)
        self.assertIn("<b>已下载：</b>", group)
        self.assertIn("磁盘可用空间", group)
        self.assertIn("机器人运行时长", group)
        self.assertIn("&lt;file&amp;&gt;", group)
        self.assertEqual([item[1] for item in en_buttons], [item[1] for item in zh_buttons])
        self.assertEqual(self.statuses.STATUS_DOWNLOADING, "⬇️ Downloading")

    async def test_processed_label_matches_upload_or_other_phase_and_filters_stay_raw(self):
        for status, label in ((self.statuses.STATUS_UPLOADING, "已上传"), (self.statuses.STATUS_CLONING, "已处理")):
            self.tasks[1] = self.task(status)
            text, _ = await self.module.get_readable_message(-100)
            self.assertIn(label, text)
        self.tasks[1] = self.task(self.statuses.STATUS_DOWNLOADING)
        self.assertEqual(await self.module.get_readable_message(-100, "ul"), (None, None))

    async def test_thread_actor_and_nonblocking_future_semantics_are_preserved(self):
        async def read(uid, wait):
            with i18n.locale_context(uid):
                value = await self.module.run_sync_to_async(lambda: i18n.tr("common.enabled"), wait=wait)
                return value if wait else await value
        self.assertEqual(await asyncio.gather(read(1, True), read(2, False)), ["Enabled", "已启用"])

    async def test_download_failure_callback_uses_task_owner_and_escapes_diagnostic(self):
        sent = []
        async def send(text, message, *args):
            sent.append(text)
        async def clean():
            pass
        listener_type = definitions("bot/helper/listeners/task_listener.py", {"TaskListener"}, {
            "TaskConfig": object, "status_dict": {}, "status_dict_lock": asyncio.Lock(),
            "sendMessage": send, "sendMarkup": send, "escape": escape,
        }).TaskListener
        listener = listener_type.__new__(listener_type)
        listener.user_id, listener.uid, listener.sameDir = 1, 1, {}
        listener.message, listener.tag, listener.clean = object(), '<a href="tg://user?id=1">User</a>', clean
        await listener.onDownloadError("<upstream failure>&")
        self.assertIn("Download stopped due to", sent[0])
        self.assertIn("&lt;upstream failure&gt;&amp;", sent[0])
        self.assertIn('<a href="tg://user?id=1">User</a>', sent[0])

    async def test_upload_completion_localizes_fields_and_keeps_cloud_link(self):
        sent = []
        async def send(text, message, buttons=None):
            sent.append((text, buttons))
        listener_type = definitions("bot/helper/listeners/task_listener.py", {"TaskListener"}, {
            "TaskConfig": object, "status_dict": {}, "status_dict_lock": asyncio.Lock(),
            "sendMessage": send, "escape": escape, "ButtonMaker": Buttons,
            "config_dict": {"GD_INDEX_URL": "", "RC_INDEX_URL": ""},
        }).TaskListener
        listener = listener_type.__new__(listener_type)
        listener.user_id, listener.uid, listener.isLeech = 2, 1, False
        listener.message, listener.tag = object(), '<a href="tg://user?id=2">User</a>'
        listener.seed, listener.newDir, listener.user_dict = True, "", {}
        listener.compress = None
        await listener.onUploadComplete("https://example.com/file", "10B", 3, 2, "Folder", "<report&>", is_gdrive=True)
        text, buttons = sent[0]
        self.assertIn("发起者", text)
        self.assertIn("文件夹", text)
        self.assertIn("&lt;report&amp;&gt;", text)
        self.assertEqual(buttons, [("网盘链接", "https://example.com/file")])

    async def test_bottom_status_uses_disk_and_bot_uptime_labels(self):
        module = definitions("bot/helper/mirror_leech_utils/status_utils/status_utils.py", {"get_bottom_status"}, {
            "time": SimpleNamespace(time=lambda: 65), "botUptime": 0,
            "human_readable_timedelta": lambda value: "1m5s", "human_readable_bytes": lambda value: "123B",
            "disk_usage": lambda path: SimpleNamespace(free=123), "cpu_percent": lambda: 10,
            "virtual_memory": lambda: SimpleNamespace(percent=20),
        })
        text = module.get_bottom_status()
        self.assertIn("磁盘可用空间", text)
        self.assertIn("机器人运行时长", text)


if __name__ == "__main__":
    unittest.main()
