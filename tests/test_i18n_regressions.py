"""Cross-module language regressions found during integration review."""

import ast
import asyncio
from collections.abc import Mapping
from functools import partial
from html import escape
import logging
from pathlib import Path
import sys
from time import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from source_loader import ROOT, get_i18n, load_source
from test_i18n_helpers import help_module


i18n = get_i18n()


class Buttons:
    def __init__(self):
        self.rows = []

    def cb_buildbutton(self, text, data, *args):
        self.rows.append(SimpleNamespace(text=text, callback_data=data))

    def build_menu(self, columns=1):
        return SimpleNamespace(inline_keyboard=[self.rows[index:index + columns] for index in range(0, len(self.rows), columns)])


class IntegrationRegressions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {"BOT_UI_LANGUAGE": "zh-CN"}
        self.users = {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}}
        i18n.bind(self.config, self.users)

    def selection_module(self):
        def handler(callback, **kwargs):
            return SimpleNamespace(callback=callback)
        return load_source("bot/modules/ytdlp.py", {"select_format", "YtSelection"}, {
            "tr": i18n.tr, "raw": i18n.raw, "new_task": lambda function: function,
            "localized_handler": i18n.localized_handler, "get_language": i18n.get_language,
            "Event": asyncio.Event, "time": time, "wait_for": asyncio.wait_for, "partial": partial,
            "CallbackQueryHandler": handler, "regex": MagicMock(), "user": MagicMock(),
            "ButtonMaker": Buttons, "sendMessage": AsyncMock(return_value=object()),
            "editMessage": AsyncMock(), "deleteMessage": AsyncMock(),
            "human_readable_timedelta": str, "get_readable_file_size": str,
        })

    async def test_temporary_quality_handler_uses_its_actor(self):
        module = self.selection_module()
        handlers = []
        client = SimpleNamespace(add_handler=lambda handler, **kwargs: (handlers.append(handler) or handler, -1), remove_handler=lambda *args: None)
        selection = module.YtSelection(SimpleNamespace(user_id=1, client=client, is_cancelled=False))
        selection.event.set()
        await selection._event_handler()
        query = SimpleNamespace(data="ytq audio", message=object(), from_user=SimpleNamespace(id=1), answer=AsyncMock())
        with i18n.locale_context():
            await handlers[0].callback(None, query)
        buttons = module.editMessage.call_args.args[2].inline_keyboard
        back = next(button.text for row in buttons for button in row if button.callback_data == "ytq back")
        self.assertEqual(back, i18n.tr("commands.button.back", _language="en", _html=False))

    async def test_quality_back_refreshes_only_display_labels(self):
        module = self.selection_module()
        selection = module.YtSelection(SimpleNamespace(user_id=1, message=object(), is_cancelled=False))
        selection._event_handler = AsyncMock()
        with i18n.locale_context(1):
            await selection.get_quality({"entries": []})
            before = [button.callback_data for row in selection._main_buttons.inline_keyboard for button in row]
            self.users[1]["ui_language"] = "zh-CN"
            await selection.back_to_main()
        after = module.editMessage.call_args.args[2].inline_keyboard
        self.assertEqual(before, [button.callback_data for row in after for button in row])
        cancel = next(button.text for row in after for button in row if button.callback_data == "ytq cancel")
        self.assertEqual(cancel, i18n.tr("commands.button.cancel", _language="zh-CN", _html=False))

    async def test_mongo_restore_updates_live_language_without_rewriting_other_config(self):
        class Cursor:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration
        collections = {
            "deployConfig": SimpleNamespace(find_one=AsyncMock(return_value={"_id": "bot", "BOT_UI_LANGUAGE": "zh-CN"})),
            "config": SimpleNamespace(find_one=AsyncMock(return_value={"_id": "bot", "BOT_UI_LANGUAGE": "en"})),
        }
        for name in ("files", "aria2c", "qbittorrent"):
            collections[name] = SimpleNamespace(find_one=AsyncMock(return_value=None))
        config = SimpleNamespace(DATABASE_URL="mongodb://fixture", BOT_UI_LANGUAGE="zh-CN")
        config.load_dict = lambda values: vars(config).update(values)
        live = {"BOT_UI_LANGUAGE": "zh-CN", "UNRELATED": "original"}
        database = SimpleNamespace(is_local=False, connect=AsyncMock(return_value=True),
                                   _db_ref=SimpleNamespace(settings=SimpleNamespace(**collections), users=SimpleNamespace(find_one=AsyncMock(return_value=None), find=lambda *args: Cursor())))
        module = load_source("bot/core/startup.py", {"load_settings"}, {
            "Config": config, "config_dict": live, "database": database, "environ": {},
            "dotenv_values": lambda *args: {"BOT_UI_LANGUAGE": "zh-CN"}, "LOGGER": logging.getLogger("test"),
        })
        with patch.dict(sys.modules, {"bot": SimpleNamespace(bot_id="bot")}):
            await module.load_settings()
        i18n.bind(live, {})
        self.assertEqual(i18n.get_language(), "en")
        self.assertEqual(live["UNRELATED"], "original")

    async def test_admin_cancel_reason_uses_task_owner_language(self):
        listener = SimpleNamespace(user_id=2, message=SimpleNamespace(from_user=SimpleNamespace(id=2)), onDownloadError=AsyncMock())
        module = load_source("bot/helper/mirror_leech_utils/status_utils/queue_status.py", {"QueueStatus"}, {"tr": i18n.tr})
        task = module.QueueStatus(listener, "gid", "dl")
        with i18n.locale_context(1):
            await task.cancel_task()
        self.assertEqual(listener.onDownloadError.call_args.args[0],
                         i18n.tr("helpers.text.task_cancelled_from_queue", _language="zh-CN", _html=False))

    def test_every_backend_cancel_reason_targets_the_task_owner(self):
        checked = 0
        for path in (ROOT / "bot/helper").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for method in ast.walk(tree):
                if not isinstance(method, ast.AsyncFunctionDef) or method.name != "cancel_task":
                    continue
                for call in ast.walk(method):
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "tr":
                        checked += 1
                        self.assertIn("_user_id", {keyword.arg for keyword in call.keywords}, f"{path}:{call.lineno}")
        self.assertEqual(checked, 18)

    def test_composed_media_html_is_balanced_and_preserves_provider_data(self):
        module = load_source("bot/helper/ext_utils/media_utils.py", {"format_media_info"}, {"tr": i18n.tr})
        info = {"duration": 65, "size": 123, "format": "MP4", "artist": "Artist<&>", "title": "Title<&>",
                "video": {"width": 1920, "height": 1080, "codec": "H264", "fps": 29.97, "bitrate": 1000},
                "audio": [{"channels": 2, "codec": "AAC", "language": "eng", "sample_rate": 48000}],
                "subtitles": [{"language": "chi", "format": "SRT"}]}
        fake = {"bot.helper.ext_utils.human_format": SimpleNamespace(get_readable_file_size=str)}
        with patch.dict(sys.modules, fake):
            for language in i18n.LANGUAGES:
                with i18n.locale_context(language=language):
                    text = module.format_media_info(info, "Original<&>.mp4")
                self.assertIn("Original&lt;&amp;&gt;.mp4", text)
                self.assertIn("H264", text)
                self.assertIn("AAC", text)
                self.assertIn("eng", text)
                self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 1024)
                self.assertNotIn("<value>", text)
                from test_i18n import AuditTests
                if not hasattr(AuditTests, "audit"):
                    AuditTests.setUpClass()
                parser = AuditTests.audit.Markup()
                parser.feed(text)
                self.assertFalse(parser.errors, parser.errors)
                self.assertFalse(parser.stack, parser.stack)

    def test_provider_exception_keeps_original_fallback_classification(self):
        source = ROOT / "bot/helper/mirror_leech_utils/download_utils/direct_link_generator.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        matched = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or len(node.body) != 1 or not isinstance(node.body[0], ast.Raise):
                continue
            call = node.body[0].exc
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "DirectDownloadLinkException" or not call.args:
                continue
            argument = call.args[0]
            original = isinstance(argument, ast.Name) and argument.id == node.name
            wrapped = isinstance(argument, ast.Call) and argument.args and isinstance(argument.args[0], ast.Constant) and argument.args[0].value == "helpers.direct.provider_error"
            if not (original or wrapped):
                continue
            matched += 1
            for diagnostic in ("transport & failed", "ERROR: classified error"):
                namespace = {"DirectDownloadLinkException": RuntimeError, "tr": i18n.tr, node.name: RuntimeError(diagnostic)}
                with self.assertRaises(RuntimeError) as caught:
                    exec(compile(ast.Module(body=node.body, type_ignores=[]), str(source), "exec"), namespace)
                self.assertEqual(str(caught.exception).startswith("ERROR:"), diagnostic.startswith("ERROR:"))
        self.assertGreaterEqual(matched, 4)

    def test_password_help_html_is_trusted_but_user_url_is_escaped(self):
        help_text = help_module().PASSWORD_ERROR_MESSAGE.format("https://example.com/<script>?a=1&b=2")
        error = RuntimeError(help_text)
        detail = i18n.error_detail(error) if hasattr(i18n, "error_detail") else str(error)
        rendered = i18n.tr("commands.link.error", detail=detail)
        self.assertIn("<b>", rendered)
        self.assertNotIn("&lt;b&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        technical = RuntimeError("<script>& diagnostic")
        detail = i18n.error_detail(technical) if hasattr(i18n, "error_detail") else str(technical)
        self.assertIn("&lt;script&gt;&amp;", i18n.tr("commands.link.error", detail=detail))

    def test_trusted_help_format_escapes_future_dynamic_parameters(self):
        with patch.dict(i18n.get_catalog("zh-CN"), {"helpers.help.password_error_message": "<b>密码：</b><code>{{url}}</code>"}):
            help_text = help_module().PASSWORD_ERROR_MESSAGE.format(url="<script>& link")
        self.assertIn("<b>", help_text)
        self.assertNotIn("<script>", help_text)
        self.assertIn("&lt;script&gt;&amp;", help_text)

    async def test_ytdlp_diagnostic_is_escaped_once_by_listener(self):
        tree = ast.parse((ROOT / "bot/modules/ytdlp.py").read_text(encoding="utf-8"))
        handler = next(node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)
                       and any(isinstance(child, ast.Constant) and isinstance(child.value, str) and child.value.startswith("YT-DLP task failed:") for child in ast.walk(node)))
        function = ast.AsyncFunctionDef(name="handle", args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="self"), ast.arg(arg=handler.name)], kwonlyargs=[], kw_defaults=[], defaults=[]), body=handler.body, decorator_list=[])
        namespace = {"LOGGER": logging.getLogger("test"), "tr": i18n.tr, "raw": i18n.raw}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "ytdlp.py", "exec"), namespace)
        task = SimpleNamespace(tag='<a href="tg://user?id=2">user</a>', onDownloadError=AsyncMock())
        await namespace["handle"](task, RuntimeError("a&b"))
        diagnostic = task.onDownloadError.call_args.args[0]
        self.assertEqual(diagnostic, "a&b")
        module = load_source("bot/helper/listeners/task_listener.py", {"TaskListener"}, {
            "TaskConfig": object, "tr": i18n.tr, "raw": i18n.raw, "task_locale": i18n.task_locale,
            "status_dict": {}, "status_dict_lock": asyncio.Lock(), "sendMessage": AsyncMock(),
            "escape": escape, "error_detail": getattr(i18n, "error_detail", str),
        })
        listener = object.__new__(module.TaskListener)
        listener.__dict__.update(uid=7, user_id=2, tag=task.tag, message=object(), sameDir={}, clean=AsyncMock())
        await listener.onDownloadError(diagnostic)
        rendered = module.sendMessage.call_args.args[0]
        self.assertIn("a&amp;b", rendered)
        self.assertNotIn("a&amp;amp;b", rendered)
        self.assertEqual(rendered.count('<a href="tg://user?id=2">'), 1)


if __name__ == "__main__":
    unittest.main()
