import ast
import asyncio
from collections import Counter
from contextvars import copy_context
from html.parser import HTMLParser
from importlib.util import module_from_spec, spec_from_file_location
import logging
from pathlib import Path
import sys
from string import Formatter
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from source_loader import get_i18n, load_source, ROOT


i18n = get_i18n()


def fields(text):
    return Counter((key, spec, conv) for _, key, spec, conv in Formatter().parse(text) if key is not None)


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.config = {"BOT_UI_LANGUAGE": "zh-CN"}
        self.users = {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}}
        i18n.bind(self.config, self.users)

    def test_default_personal_and_follow_global_are_live(self):
        self.assertEqual(i18n.get_language(), "zh-CN")
        with i18n.locale_context(1):
            self.assertEqual(i18n.tr("common.enabled"), "Enabled")
            self.users[1]["ui_language"] = ""
            self.assertEqual(i18n.tr("common.enabled"), "已启用")
            self.config["BOT_UI_LANGUAGE"] = "en"
            self.assertEqual(i18n.tr("common.enabled"), "Enabled")

    def test_safe_parameters_and_trusted_markup(self):
        self.assertEqual(i18n.tr("common.technical_error", detail="<file>&'"), "操作失败：&lt;file&gt;&amp;&#x27;")
        self.assertEqual(i18n.tr("common.technical_error", detail=i18n.raw("<code>safe</code>")), "操作失败：<code>safe</code>")
        self.assertEqual(i18n.tr("common.technical_error", detail="<file>", _html=False), "操作失败：<file>")

    def test_strict_language_and_missing_key_log(self):
        for value in ("zh", "zh_CN", "fr", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                i18n.normalize_language(value)
        with self.assertLogs(i18n._logger, level="WARNING"):
            self.assertEqual(i18n.tr("missing.test"), "[missing.test]")

    def test_english_fallback_and_quantity_formatting(self):
        catalogs = {"en": {"test.count": {"one": "{count} file", "other": "{count} files"}}, "zh-CN": {}}
        with patch.object(i18n, "get_catalog", side_effect=catalogs.__getitem__):
            with self.assertLogs(i18n._logger, level="WARNING"):
                self.assertEqual(i18n.tr("test.count", count=2), "2 files")
            self.assertEqual(i18n.tr("test.count", count=1, _language="en"), "1 file")

    def test_placeholder_access_is_restricted(self):
        for template in ("{value.__class__}", "{value[secret]}", "{missing}", "{value:{format}}"):
            with self.subTest(template=template), patch.object(i18n, "get_catalog", return_value={"test": template}), self.assertRaises(ValueError):
                i18n.tr("test", value="safe")

    def test_key_can_be_a_named_parameter(self):
        with patch.object(i18n, "get_catalog", return_value={"test": "{key}: {value:.2f}"}):
            self.assertEqual(i18n.tr("test", key="API", value=1.25), "API: 1.25")

    def test_resource_keys_and_placeholders_match(self):
        english, chinese = i18n.get_catalog("en"), i18n.get_catalog("zh-CN")
        self.assertEqual(english.keys(), chinese.keys())
        for key in english:
            with self.subTest(key=key):
                en, zh = english[key], chinese[key]
                self.assertEqual(type(en), type(zh))
                if isinstance(en, dict):
                    self.assertEqual(en.keys(), {"one", "other"})
                    self.assertEqual(zh.keys(), en.keys())
                    for form in en:
                        self.assertEqual(fields(en[form]), fields(zh[form]))
                else:
                    self.assertEqual(fields(en), fields(zh))

    def test_status_display_does_not_mutate_business_states(self):
        status = "⬆️ Uploading"
        self.assertEqual(i18n.display_status(status), "⬆️ 正在上传")
        self.assertEqual(status, "⬆️ Uploading")
        with i18n.locale_context(1):
            self.assertEqual(i18n.display_status(status), status)


class ConcurrentLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        i18n.bind({"BOT_UI_LANGUAGE": "zh-CN"}, {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}})

    async def test_two_simultaneous_users_tasks_and_thread_contexts(self):
        async def render(uid):
            with i18n.locale_context(uid):
                await asyncio.sleep(0)
                thread_text = await asyncio.get_running_loop().run_in_executor(None, copy_context().run, lambda: i18n.tr("common.enabled"))
                return i18n.tr("common.enabled"), thread_text
        self.assertEqual(await asyncio.gather(render(1), render(2)), [("Enabled", "Enabled"), ("已启用", "已启用")])

    async def test_status_uses_global_in_groups_and_personal_in_private(self):
        @i18n.status_locale
        async def status(chat_id):
            return i18n.tr("common.enabled")
        with i18n.locale_context(1):
            self.assertEqual(await status(-100123), "已启用")
            self.assertEqual(await status(1), "Enabled")

    async def test_handler_context_resets_after_callback(self):
        async def callback(client, update):
            await asyncio.sleep(0)
            return i18n.tr("common.enabled")
        handler = i18n.localized_handler(SimpleNamespace(callback=callback))
        self.assertEqual(await handler.callback(None, SimpleNamespace(from_user=SimpleNamespace(id=1))), "Enabled")
        self.assertEqual(i18n.tr("common.enabled"), "已启用")

    async def test_background_task_callback_resolves_task_owner(self):
        @i18n.task_locale
        async def callback(task):
            return i18n.tr("common.enabled")
        self.assertEqual(await callback(SimpleNamespace(user_id=1)), "Enabled")
        self.assertEqual(i18n.tr("common.enabled"), "已启用")

    async def test_handler_preserves_nonblocking_scheduled_task(self):
        completed = asyncio.Event()
        async def work():
            await completed.wait()
            return i18n.tr("common.enabled")
        def callback(client, update):
            return asyncio.create_task(work())
        handler = i18n.localized_handler(SimpleNamespace(callback=callback))
        task = await handler.callback(None, SimpleNamespace(from_user=SimpleNamespace(id=1)))
        self.assertIsInstance(task, asyncio.Task)
        self.assertFalse(task.done())
        completed.set()
        self.assertEqual(await task, "Enabled")

    async def test_sqlite_restart_restores_global_personal_and_follow_global(self):
        sys.path.insert(0, str(ROOT))
        from local_storage import LocalStorage
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.db"
            storage = LocalStorage("i18n-test", path)
            deployment = {"BOT_UI_LANGUAGE": "zh-CN"}
            storage.prepare_config(deployment)
            users = {1: {"ui_language": "en"}, 2: {"ui_language": ""}}
            manager_module = load_source("bot/helper/ext_utils/sqlite_handler.py", {"SQLiteManager"}, {
                "config_dict": {"ALLOWED_CHATS": "", "SUDO_USERS": ""},
                "local_storage": storage, "user_data": users, "to_thread": asyncio.to_thread,
                "LOGGER": logging.getLogger("test"), "aria2_options": {}, "qbit_options": {}, "remotes_multi": [],
            })
            manager = manager_module.SQLiteManager()
            await manager.update_user_data(1)
            await manager.update_user_data(2)
            await manager.update_config({"BOT_UI_LANGUAGE": "en"})
            storage.close()
            storage = LocalStorage("i18n-test", path)
            try:
                manager_module.local_storage = storage
                users.clear()
                with patch.dict(sys.modules, {"bot.helper.ext_utils.rclone_data_holder": SimpleNamespace(rclone_dict={})}):
                    await manager.load_settings()
                config = storage.prepare_config(deployment)
                i18n.bind(config, users)
                self.assertEqual(i18n.get_language(1), "en")
                self.assertEqual(i18n.get_language(2), "en")
                config["BOT_UI_LANGUAGE"] = "zh-CN"
                self.assertEqual(i18n.get_language(1), "en")
                self.assertEqual(i18n.get_language(2), "zh-CN")
            finally:
                storage.close()

    async def test_native_command_menu_follows_personal_and_global_language(self):
        commands = load_source("bot/helper/telegram_helper/bot_commands.py", {"_BotCommands"}, {"CMD_INDEX": ""})._BotCommands()
        namespace = {"get_language": i18n.get_language, "locale_context": i18n.locale_context,
                     "tr": i18n.tr, "logging": logging}
        module = load_source("bot/i18n/commands.py", {"publish_commands"}, namespace)
        tree = ast.parse((ROOT / "bot/i18n/commands.py").read_text(encoding="utf-8"))
        module.COMMANDS = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)))
        users = {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}}
        config = {"BOT_UI_LANGUAGE": "zh-CN"}
        i18n.bind(config, users)
        client = SimpleNamespace(set_bot_commands=AsyncMock(), delete_bot_commands=AsyncMock())
        modules = {
            "pyrogram.types": SimpleNamespace(BotCommand=lambda name, description: (name, description), BotCommandScopeChat=lambda uid: ("chat", uid)),
            "bot": SimpleNamespace(user_data=users),
            "bot.helper.telegram_helper.bot_commands": SimpleNamespace(BotCommands=commands),
        }
        with patch.dict(sys.modules, modules):
            await module.publish_commands(client, user_id=1)
            english = client.set_bot_commands.call_args.args[0]
            self.assertIn(("start", "Start the bot"), english)
            self.assertIn("lang", [row[0] for row in english])
            self.assertTrue(all(len(description) <= 256 for _, description in english))
            self.assertEqual(client.set_bot_commands.call_args.kwargs["scope"], ("chat", 1))
            users[1]["ui_language"] = ""
            await module.publish_commands(client, user_id=1)
            client.delete_bot_commands.assert_awaited_once_with(scope=("chat", 1))
            with i18n.locale_context(2):
                config["BOT_UI_LANGUAGE"] = "en"
                await module.publish_commands(client)
            self.assertEqual(client.set_bot_commands.call_args.args[0], english)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = spec_from_file_location("rcmltb_i18n_audit", ROOT / "scripts/check_i18n.py")
        cls.audit = module_from_spec(spec)
        spec.loader.exec_module(cls.audit)

    def test_complete_resource_and_source_audit(self):
        errors, _ = self.audit.check_resources()
        missing, sources = self.audit.audit_sources()
        self.assertFalse(errors, errors)
        self.assertFalse(missing, missing)
        self.assertFalse(sources["hardcoded"], sources["hardcoded"])

    def test_scanner_detects_indirect_text_and_helper_api_outputs(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper = root / "bot/helper"
            helper.mkdir(parents=True)
            (helper / "example.py").write_text(
                'async def menu(message):\n    text = "Untranslated prompt"\n'
                '    await sendMessage(text, message)\n'
                '    await message.reply_text("Another untranslated prompt")\n'
                '    buttons.cb_buildbutton("Untranslated button", "callback_kept")\n', encoding="utf-8")
            with patch.object(self.audit, "ROOT", root):
                _, report = self.audit.audit_sources()
            self.assertEqual(report["sinks"], 3)
            self.assertEqual(len(report["hardcoded"]), 3)

    def test_rendered_resources_keep_telegram_lengths_and_safe_markup(self):
        for language in i18n.LANGUAGES:
            for key, entry in i18n.get_catalog(language).items():
                forms = entry.values() if isinstance(entry, dict) else [entry]
                for template in forms:
                    params = {field: 1.234 if any(character in spec for character in "fge%") else 1 if spec else "<value>&"
                              for _, field, spec, _ in Formatter().parse(template) if field is not None}
                    if isinstance(entry, dict):
                        params["count"] = 2
                    with self.subTest(language=language, key=key):
                        output = i18n.tr(key, _language=language, **params)
                        self.assertNotIn("<value>", output)
                        self.assertLessEqual(len(output.encode("utf-16-le")) // 2, 4096)
                        parser = self.audit.Markup()
                        parser.feed(output)
                        if key not in self.audit.HTML_FRAGMENTS:
                            self.assertFalse(parser.errors, parser.errors)
                            self.assertFalse(parser.stack, parser.stack)


if __name__ == "__main__":
    unittest.main()
