import ast
import asyncio
from contextvars import Context, copy_context
import dataclasses
from html import escape
import importlib.util
import json
import inspect
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
import sys
import typing
import unittest
from unittest.mock import AsyncMock, Mock

from source_loader import ROOT, load_source


spec = importlib.util.spec_from_file_location("commands_i18n", ROOT / "bot/i18n/__init__.py")
i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i18n)


class Buttons:
    def __init__(self):
        self.rows = []

    def cb_buildbutton(self, label, data, *args, **kwargs):
        self.rows.append((label, data))

    def url_buildbutton(self, label, url, *args, **kwargs):
        self.rows.append((label, url))

    def build_menu(self, *args):
        return self.rows


def load(name, definitions, **namespace):
    return load_source(f"bot/modules/{name}.py", definitions, {
        "tr": i18n.tr, "raw": i18n.raw, "ui_error": i18n.ui_error,
        "display_status": i18n.display_status, "locale_context": i18n.locale_context,
        "ButtonMaker": Buttons, "new_task": lambda func: func,
        **namespace,
    })


class CommandResourcesTests(unittest.TestCase):
    def test_resource_parity_and_render_every_message(self):
        catalogs = {
            language: json.loads((ROOT / f"bot/i18n/locales/{language}/commands.json").read_text(encoding="utf-8"))
            for language in ("en", "zh-CN")
        }
        self.assertEqual(catalogs["en"].keys(), catalogs["zh-CN"].keys())
        self.assertGreater(len(catalogs["en"]), 200)
        formatter = Formatter()
        for key, english in catalogs["en"].items():
            with self.subTest(key=key):
                fields = lambda text: {field for _, field, _, _ in formatter.parse(text) if field}
                variants = english if isinstance(english, dict) else {"one":english}
                for variant, text in variants.items():
                    chinese = catalogs["zh-CN"][key]
                    chinese = chinese[variant] if isinstance(chinese, dict) else chinese
                    self.assertEqual(fields(text), fields(chinese))
                    params = {field: "<dynamic&value>" for field in fields(text)}
                    for language in catalogs:
                        rendered = i18n.tr(key, _language=language, count=1 if variant == "one" else 2, **params)
                        self.assertNotIn("<dynamic&value>", rendered)
                        for field in params:
                            self.assertIn("&lt;dynamic&amp;value&gt;", rendered)

    def test_no_translation_is_frozen_at_module_import(self):
        excluded = {"stats", "user_settings", "owner_settings", "botfiles", "language", "__init__"}
        for path in (ROOT / "bot/modules").glob("*.py"):
            if path.stem in excluded:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for statement in tree.body:
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                calls = [node for node in ast.walk(statement) if isinstance(node, ast.Call)]
                self.assertFalse(any(isinstance(node.func, ast.Name) and node.func.id == "tr" for node in calls), path.name)


class CommandHandlersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {"BOT_UI_LANGUAGE": "zh-CN"}
        self.users = {1: {"ui_language": "en"}, 2: {"ui_language": "zh-CN"}}
        i18n.bind(self.config, self.users)

    async def test_help_translates_every_description_and_preserves_commands(self):
        attributes = {
            "MirrorCommand": ["mirror"], "MirrorBatchCommand": ["mbatch"],
            "MirrorSelectCommand": ["msel"], "LeechCommand": ["leech"],
            "LeechBatchCommand": ["lbatch"], "YtdlMirrorCommand": ["ytdl"],
            "YtdlLeechCommand": ["ytdlleech"], "ForceStartCommand": ["fs"],
            "LanguageCommand": ["lang"],
        }
        for name in ("Clone", "Copy", "Sync", "BiSync", "Rcfm", "Storage", "Cleanup", "Serve", "Count", "TorrentSearch", "Status", "Cancel", "CancelAll", "Select", "UserSet", "OwnerSet", "Stats", "Ping"):
            attributes[name + "Command"] = name.lower()
        attributes["TMDB"] = "tmdb"
        send = AsyncMock()
        module = load("help", {"bot_help"}, BotCommands=SimpleNamespace(**attributes), sendMarkup=send)
        with i18n.locale_context(2):
            await module.bot_help(None, object())
        chinese, _, buttons = send.call_args.args
        self.assertIn("使用 YT-DLP 下载", chinese)
        self.assertIn("双向同步网盘", chinese)
        self.assertIn("/lang</code> - 界面语言", chinese)
        self.assertEqual(chinese.count("• <code>/"), 28)
        self.assertLess(len(chinese), 4096)
        self.assertEqual([data for _, data in buttons], ["help back m", "help back y", "help back l", "help back b"])
        self.assertIn("转存网盘", buttons[0][0])
        with i18n.locale_context(1):
            await module.bot_help(None, object())
        english = send.call_args.args[0]
        self.assertIn("Mirror to cloud", english)
        self.assertIn("Interface language", english)
        self.assertEqual(chinese.count("<code>"), english.count("<code>"))

    async def test_cancel_categories_concurrent_actors_keep_original_status_payloads(self):
        states = SimpleNamespace(**{f"STATUS_{name}": value for name, value in {
            "DOWNLOADING": "⬇️ Downloading", "UPLOADING": "⬆️ Uploading",
            "SEEDING": "🌱 Seeding", "CLONING": "📥 Cloning", "SPLITTING": "✂️ Splitting",
            "EXTRACTING": "📂 Extracting", "ARCHIVING": "📦 Archiving 🔐",
            "QUEUEDL": "⏳ QueueDl", "QUEUEUP": "⏳ QueueUp", "PAUSED": "⏸️ Paused",
        }.items()})
        send = AsyncMock()
        module = load("cancel", {"cancell_all_buttons"}, status_dict_lock=asyncio.Lock(), status_dict={5: object()}, MirrorStatus=states, sendMarkup=send)

        async def render(actor):
            with i18n.locale_context(actor):
                await module.cancell_all_buttons(None, actor)
        await asyncio.gather(render(1), render(2))
        outputs = {call.args[1]: call.args[2] for call in send.call_args_list}
        self.assertEqual([data for _, data in outputs[1]], [data for _, data in outputs[2]])
        self.assertEqual(outputs[1][0], ("⬇️ Downloading", "canall ⬇️ Downloading"))
        self.assertEqual(outputs[2][0], ("⬇️ 下载中", "canall ⬇️ Downloading"))
        self.assertIn(("⏳ 等待上传", "canall ⏳ QueueUp"), outputs[2])

    async def test_full_queue_feedback_localizes_and_does_not_execute_task(self):
        send = AsyncMock()
        put = AsyncMock()
        task = AsyncMock()
        module = load("queue", {"add_to_queue"},
            LOGGER=Mock(), queue=SimpleNamespace(queue=SimpleNamespace(full=lambda:True), put=put),
            bot=SimpleNamespace(send_message=send), ReplyParameters=lambda **kwargs:kwargs)
        message = SimpleNamespace(chat=SimpleNamespace(id=2), id=9)
        with i18n.locale_context(2):
            await module.add_to_queue(message, task)
        self.assertEqual(send.call_args.kwargs["text"], "队列已满，请等待空闲位置。")
        self.assertEqual(send.call_args.kwargs["reply_parameters"], {"message_id":9})
        task.assert_not_called()
        put.assert_not_awaited()

    async def test_queued_jobs_and_done_callbacks_keep_actor_and_priority(self):
        queue = asyncio.PriorityQueue()
        module = load("queue", {"queue_worker", "safe_run", "QueueItem"},
            bot_loop=asyncio.get_running_loop(), sleep=asyncio.sleep,
            CancelledError=asyncio.CancelledError, AbstractEventLoop=asyncio.AbstractEventLoop,
            dataclasses=dataclasses, typing=typing, inspect=inspect, sys=sys,
            Context=Context, copy_context=copy_context, LOGGER=Mock())
        results = []
        completed = []
        async def job(label):
            await asyncio.sleep(0)
            results.append((label, i18n.tr("commands.exec.no_output")))
            return label
        async def done(value):
            completed.append((value, i18n.tr("commands.exec.no_error")))
        with i18n.locale_context(1):
            english = module.QueueItem(priority=2, task=job("english"), done_callback=done, pass_result_to_done_callback=True)
        with i18n.locale_context(2):
            chinese = module.QueueItem(priority=1, task=job("chinese"), done_callback=done, pass_result_to_done_callback=True)
        await queue.put(english)
        await queue.put(chinese)
        with i18n.locale_context(global_default=True):
            worker = asyncio.create_task(module.queue_worker("worker", queue))
        await asyncio.wait_for(queue.join(), 1)
        worker.cancel()
        await worker
        self.assertEqual(results, [("chinese", "无输出"), ("english", "No Output")])
        self.assertEqual(completed, [("chinese", "无错误"), ("english", "No Error")])

    async def test_queue_executor_and_error_callback_inherit_actor_context(self):
        module = load("queue", {"safe_run"}, typing=typing,
            AbstractEventLoop=asyncio.AbstractEventLoop, inspect=inspect, sys=sys,
            copy_context=copy_context, LOGGER=Mock())
        def output():
            return i18n.tr("commands.exec.no_output")
        errors = []
        def fail():
            raise ValueError("technical detail")
        def on_error(error):
            errors.append((str(error), i18n.tr("commands.exec.no_error")))
        with i18n.locale_context(1):
            result = await module.safe_run(output, (), None, (), asyncio.get_running_loop())
            await module.safe_run(fail, (), on_error, (), asyncio.get_running_loop())
        self.assertEqual(result, "No Output")
        self.assertEqual(errors, [("technical detail", "No Error")])

    async def test_file_manager_paths_are_escaped_without_modifying_callback_values(self):
        send = AsyncMock()
        module = load("myfilesset", {"myfiles_settings"}, sendMarkup=send)
        message = SimpleNamespace(reply_to_message=None, from_user=SimpleNamespace(id=2))
        path = "目录/Mirror<&>.mp4"
        with i18n.locale_context(2):
            await module.myfiles_settings(message, "云盘<&>", path)
        text, _, = send.call_args.args
        self.assertIn(escape("云盘<&>:" + path), text)
        self.assertIn("路径", text)
        rows = send.call_args.kwargs["reply_markup"]
        self.assertIn(("📝 重命名", "myfilesmenu^rename^file^2"), rows)
        self.assertIn(("🗑 删除", "myfilesmenu^delete^file^2"), rows)

    async def test_media_and_telegram_links_reach_existing_auto_transfer_unchanged(self):
        mirror = AsyncMock()
        downloader = Mock(return_value=SimpleNamespace(download=AsyncMock()))
        queued = AsyncMock()
        module = load("mirror_leech", {"handle_auto_mirror"},
            parse_tg_message_link=lambda value: ("channel", 9) if value.startswith("https://t.me/") else None,
            mirror_leech=mirror, is_rclone_config=AsyncMock(return_value=True),
            is_remote_selected=AsyncMock(return_value=True), DOWNLOAD_DIR="/downloads/",
            TaskListener=Mock(return_value=SimpleNamespace(uid=7)),
            TelegramDownloader=downloader, conditional_queue_add=queued)
        link = "https://t.me/c/123/9"
        message = SimpleNamespace(text=link)
        with i18n.locale_context(2):
            await module.handle_auto_mirror("client", message)
        mirror.assert_awaited_once_with("client", message, source_link=link)
        for uid in (1, 2):
            for media in ("document", "video", "audio", "photo", "voice", "video_note", "sticker", "animation", "forwarded_video"):
                message = SimpleNamespace(text=None, from_user=SimpleNamespace(id=uid, username="tester"), **{name:None for name in ("document", "video", "audio", "photo", "voice", "video_note", "sticker", "animation")})
                file = SimpleNamespace(mime_type="video/mp4", file_name="Mirror<&>.mp4")
                if media == "forwarded_video":
                    message.forward_from_chat = SimpleNamespace(id=-100123)
                    message.forward_from_message_id = 9
                    message.video = file
                else:
                    setattr(message, media, file)
                with i18n.locale_context(uid):
                    await module.handle_auto_mirror("client", message)
                self.assertIs(downloader.call_args.args[0], file)
                self.assertEqual(downloader.call_args.args[3], "/downloads/7/")
        self.assertEqual(queued.await_count, 18)

    async def test_rename_prompt_localizes_but_original_filename_reaches_downloader(self):
        filename = "电影 Mirror<&>.mp4"
        source = SimpleNamespace(id=9)
        file = object()
        listener = SimpleNamespace(uid=9)
        prompt = SimpleNamespace(delete=AsyncMock())
        client = SimpleNamespace(send_message=AsyncMock(return_value=prompt), listen=SimpleNamespace(Message=AsyncMock(return_value=SimpleNamespace(text=filename))))
        query = SimpleNamespace(data="mirrormenu^rename", from_user=SimpleNamespace(id=2), message=SimpleNamespace(reply_to_message=source, delete=AsyncMock()))
        original = SimpleNamespace(chat=SimpleNamespace(id=2))
        downloader = Mock(return_value=SimpleNamespace(download=AsyncMock()))
        module = load("mirror_leech", {"mirror_menu"}, listener_dict={9:[listener,file,original,False,2,"","download_client"]}, config_dict={"REMOTE_SELECTION":False}, filters=SimpleNamespace(text="text", user=lambda uid:uid), TelegramDownloader=downloader, conditional_queue_add=AsyncMock(), DOWNLOAD_DIR="/downloads/", TimeoutError=TimeoutError)
        with i18n.locale_context(2):
            await module.mirror_menu(client, query)
        self.assertIn("扩展名", client.send_message.call_args.kwargs["text"])
        self.assertEqual(downloader.call_args.args[-1], filename)
        self.assertEqual(downloader.call_args.args[1], "download_client")

    async def test_tmdb_dynamic_button_titles_remain_plain_and_callbacks_identical(self):
        title = "Mirror <&> 中文"
        api = SimpleNamespace(search=lambda query:[SimpleNamespace(title=title,id=9)])
        tv = SimpleNamespace(search=lambda query:[SimpleNamespace(name=title,id=10)])
        prompt = SimpleNamespace(delete=AsyncMock())
        send = AsyncMock(return_value=prompt)
        module = load("tmdb", {"tmdb_search_api"}, sendMessage=send, Movie=lambda:api, TV=lambda:tv, filters=SimpleNamespace(text="text", user=lambda uid:uid), TimeoutError=TimeoutError)
        client = SimpleNamespace(listen=SimpleNamespace(Message=AsyncMock(return_value=SimpleNamespace(text=title))))
        query = SimpleNamespace(message=object(), from_user=SimpleNamespace(id=2))
        with i18n.locale_context(2):
            await module.tmdb_search_api(client, query)
        self.assertEqual(send.call_args.args[2][0], ("[电影] " + title, "tmdbdetails^movie^9"))
        self.assertEqual(send.call_args.args[2][1], ("[剧集] " + title, "tmdbdetails^tv^10"))

    async def test_telegraph_result_labels_translate_and_keep_links_and_markup(self):
        pages = []
        async def create_page(**kwargs):
            pages.append(kwargs)
            return {"path":"result-page"}
        module = load("torr_search", {"__getResult"}, telegraph=SimpleNamespace(create_page=create_page), editMessage=AsyncMock(), TELEGRAPH_LIMIT=300, escape=escape, quote=lambda value:value, get_readable_file_size=lambda value:"1 GiB")
        result = SimpleNamespace(descrLink="https://example.org/item",fileName="Movie <&>",fileSize=1024,nbSeeders=2,nbLeechers=3,fileUrl="https://example.org/file.torrent")
        with i18n.locale_context(2):
            link = await module.__dict__["__getResult"]([result], "关键词<&>", object(), "plugin")
        content = pages[0]["content"]
        self.assertIn("<h4>插件搜索结果：关键词&lt;&amp;&gt;</h4>", content)
        self.assertIn("<b>做种数：</b>2", content)
        self.assertIn("Movie &lt;&amp;&gt;", content)
        self.assertIn("<a href='https://example.org/file.torrent'>下载直链</a><br><br>", content)
        self.assertEqual(link, "https://telegra.ph/result-page")

    async def test_site_all_label_changes_without_changing_shared_site_data(self):
        sites = {"all":"All", "example":"Example<&>"}
        module = load("torr_search", {"__api_buttons"}, SITES=sites)
        with i18n.locale_context(2):
            chinese = module.__dict__["__api_buttons"](2, "apisearch")
        with i18n.locale_context(1):
            english = module.__dict__["__api_buttons"](2, "apisearch")
        self.assertEqual(sites["all"], "All")
        self.assertEqual(chinese[0], ("全部站点", "torser^2^all^apisearch"))
        self.assertEqual(english[0], ("All", "torser^2^all^apisearch"))
        self.assertEqual(chinese[1], english[1])

    async def test_empty_shared_status_uses_live_global_language(self):
        send = AsyncMock(return_value=object())
        module = load("status", {"status_handler"}, status_dict_lock=asyncio.Lock(), status_dict={}, get_readable_time=lambda value:"1m", time=lambda:60, botUptime=0, DOWNLOAD_DIR="/downloads/", get_readable_file_size=lambda value:"1 GiB", disk_usage=lambda path:SimpleNamespace(free=1), cpu_percent=lambda:1, virtual_memory=lambda:SimpleNamespace(percent=2), sendMessage=send, auto_delete_message=AsyncMock())
        message = SimpleNamespace(chat=SimpleNamespace(id=-100))
        with i18n.locale_context(1):
            await module.status_handler(None, message)
        self.assertIn("没有进行中的任务", send.call_args.args[0])
        self.config["BOT_UI_LANGUAGE"] = "en"
        with i18n.locale_context(2):
            await module.status_handler(None, message)
        self.assertIn("No Active Tasks", send.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
