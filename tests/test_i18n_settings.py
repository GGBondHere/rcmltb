import asyncio
import importlib.util
import json
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests.source_loader import ROOT, load_source


def load_i18n():
    spec = importlib.util.spec_from_file_location("settings_i18n", ROOT / "bot/i18n/__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Buttons:
    def __init__(self):
        self.items = []

    def cb_buildbutton(self, text, data, *args):
        self.items.append((text, data))

    def build_menu(self, columns):
        return self.items


class SettingsI18nTests(unittest.TestCase):
    def setUp(self):
        self.i18n = load_i18n()
        self.config = {"BOT_UI_LANGUAGE": "zh-CN", "AS_DOCUMENT": False,
                       "LEECH_SPLIT_SIZE": 1024, "EQUAL_SPLITS": False,
                       "GDRIVE_FOLDER_ID": "", "YT_DLP_OPTIONS": "", "NAME_SUBSTITUTE": ""}
        self.users = {}
        self.i18n.bind(self.config, self.users)

    def test_config_language_is_strict(self):
        config = load_source("bot/core/config_manager.py", ["Config"]).Config
        self.assertEqual(config.BOT_UI_LANGUAGE, "zh-CN")
        for value in ("en", "zh-CN"):
            config.set("BOT_UI_LANGUAGE", value)
            self.assertEqual(config.BOT_UI_LANGUAGE, value)
        for value in ("zh", "EN", "", None, " en ", True):
            with self.assertRaises(ValueError):
                config.set("BOT_UI_LANGUAGE", value)

    def test_resource_keys_and_placeholders_match(self):
        data = [json.loads((ROOT / f"bot/i18n/locales/{language}/settings.json").read_text(encoding="utf-8"))
                for language in ("en", "zh-CN")]
        self.assertEqual(data[0].keys(), data[1].keys())
        for key in data[0]:
            self.assertRegex(key, r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
            fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field}
            self.assertEqual(fields(data[0][key]), fields(data[1][key]), key)

    def test_user_menu_is_dynamic_and_escapes_names(self):
        from html import escape
        module = load_source("bot/modules/user_settings.py", ["get_user_settings"], {
            "tr": self.i18n.tr, "raw": self.i18n.raw, "escape": escape,
            "user_data": self.users, "config_dict": self.config, "ButtonMaker": Buttons,
            "ospath": SimpleNamespace(exists=lambda path: False)})
        actor = SimpleNamespace(id=7, first_name="<A&B>")
        self.users[7] = {"category": "TV Shows"}
        with self.i18n.locale_context(7):
            chinese, buttons = module.get_user_settings(actor)
            self.assertIn("&lt;A&amp;B&gt; 的设置", chinese)
            self.assertIn("分类：<b>电视剧</b>", chinese)
            self.assertEqual(self.users[7]["category"], "TV Shows")
            self.assertIn(("🌐 语言 / Language", "uilang 7 menu"), buttons)
            self.users[7] = {"ui_language": "en", "yt_opt": "a<b"}
            english, _ = module.get_user_settings(actor)
            self.assertIn("Settings for", english)
            self.assertIn("a&lt;b", english)
            self.assertNotIn("&amp;lt;", english)

    def test_language_switch_saves_existing_user_record_and_checks_actor(self):
        for backend in ("sqlite", "mongo"):
            with self.subTest(backend=backend):
                self.users.clear()
                self.config["BOT_UI_LANGUAGE"] = "zh-CN"
                database = SimpleNamespace(enabled=True, update_user_data=AsyncMock())
                publish = AsyncMock()
                namespace = {"tr": self.i18n.tr, "get_language": self.i18n.get_language,
                    "user_data": self.users, "ButtonMaker": Buttons, "database": database,
                    "CustomFilters": SimpleNamespace(user_callback_filter=AsyncMock(return_value=True)),
                    "publish_commands": publish, "editMessage": AsyncMock(),
                    "update_user_ldata": lambda uid, key, value: self.users.setdefault(uid, {}).__setitem__(key, value)}
                module = load_source("bot/modules/language.py", ["language_menu", "language_callback"], namespace)
                query = SimpleNamespace(data="uilang 7 en", from_user=SimpleNamespace(id=8),
                    answer=AsyncMock(), message=SimpleNamespace(delete=AsyncMock()))
                asyncio.run(module.language_callback(None, query))
                self.assertEqual(self.users, {})
                database.update_user_data.assert_not_awaited()
                query.from_user.id = 7
                with self.i18n.locale_context(7):
                    asyncio.run(module.language_callback(None, query))
                    self.assertEqual(self.i18n.get_language(), "en")
                    self.assertEqual(self.users[7]["ui_language"], "en")
                    database.update_user_data.assert_awaited_once_with(7)
                    publish.assert_awaited_once_with(None, user_id=7)
                    query.data = "uilang 7 global"
                    asyncio.run(module.language_callback(None, query))
                    self.assertEqual(self.i18n.get_language(), "zh-CN")
                    self.config["BOT_UI_LANGUAGE"] = "en"
                    self.assertEqual(self.i18n.get_language(), "en")
                    namespace["CustomFilters"].user_callback_filter.return_value = False
                    query.data = "uilang 7 zh-CN"
                    asyncio.run(module.language_callback(None, query))
                    self.assertEqual(self.users[7]["ui_language"], "")
                    self.assertTrue(query.answer.call_args.kwargs["show_alert"])

    def test_owner_menu_uses_current_language_and_preserves_config_keys(self):
        module = load_source("bot/modules/owner_settings.py", ["get_env_menu"], {
            "tr": self.i18n.tr, "ButtonMaker": Buttons, "STATE": "view", "START": 0,
            "config_dict": {"BOT_UI_LANGUAGE": "zh-CN"}})
        chinese, buttons = module.get_env_menu()
        self.assertIn("配置变量设置", chinese)
        self.assertIn(("BOT_UI_LANGUAGE", "ownersetmenu^env^editenv^BOT_UI_LANGUAGE"), buttons.items)
        self.config["BOT_UI_LANGUAGE"] = "en"
        english, _ = module.get_env_menu()
        self.assertIn("Config Variables Settings", english)

    def test_existing_sqlite_and_mongo_writers_keep_language(self):
        self.users[7] = {"ui_language": "en", "category": "Movies", "thumb": "private.jpg"}
        storage = SimpleNamespace(write=Mock())
        sqlite = load_source("bot/helper/ext_utils/sqlite_handler.py", ["SQLiteManager"], {
            "user_data": self.users, "local_storage": storage,
            "config_dict": {"ALLOWED_CHATS": "", "SUDO_USERS": ""}}).SQLiteManager()
        asyncio.run(sqlite.update_user_data(7))
        self.assertEqual(storage.write.call_args.args[2]["ui_language"], "en")
        self.assertEqual(storage.write.call_args.args[2]["category"], "Movies")
        mongo_class = load_source("bot/helper/ext_utils/db_handler.py", ["DbManager"],
                                  {"user_data": self.users}).DbManager
        update = AsyncMock()
        mongo_class._db = SimpleNamespace(users=SimpleNamespace(update_one=update))
        mongo = mongo_class()
        mongo._ensure_connected = AsyncMock(return_value=True)
        asyncio.run(mongo.update_user_data(7))
        self.assertEqual(update.call_args.args[1]["$set"], {"ui_language": "en", "category": "Movies"})

    def test_global_language_callback_validates_owner_and_value(self):
        config = load_source("bot/core/config_manager.py", ["Config"]).Config
        database = SimpleNamespace(enabled=True, update_config=AsyncMock())
        publish = AsyncMock()
        module = load_source("bot/modules/owner_settings.py", ["ownerset_callback"], {
            "tr": self.i18n.tr, "Config": config, "database": database,
            "config_dict": self.config, "edit_menus": AsyncMock()})
        query = SimpleNamespace(data="ownersetmenu^language^en", from_user=SimpleNamespace(id=8),
                                answer=AsyncMock(), message=object())
        with patch.dict("sys.modules", {"bot": SimpleNamespace(OWNER_ID=7),
             "bot.i18n.commands": SimpleNamespace(publish_commands=publish)}):
            asyncio.run(module.ownerset_callback(None, query))
            self.assertEqual(self.config["BOT_UI_LANGUAGE"], "zh-CN")
            query.from_user.id = 7
            asyncio.run(module.ownerset_callback(None, query))
            self.assertEqual(self.config["BOT_UI_LANGUAGE"], "en")
            query.from_user.id = 8
            query.data = "ownersetmenu^page"
            query.answer.reset_mock()
            asyncio.run(module.ownerset_callback(None, query))
            query.answer.assert_awaited_once_with()
            database.update_config.assert_awaited_once_with({"BOT_UI_LANGUAGE": "en"})
            publish.assert_awaited_once_with(None)
            query.data = "ownersetmenu^language^fr"
            asyncio.run(module.ownerset_callback(None, query))
            self.assertEqual(self.config["BOT_UI_LANGUAGE"], "en")


if __name__ == "__main__":
    unittest.main()
