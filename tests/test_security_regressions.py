import ast
from asyncio import run as run_async
from importlib.util import module_from_spec, spec_from_file_location
import logging
import os
from pathlib import Path
import pickle
from shutil import copyfile
from subprocess import CalledProcessError, run
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlencode

from flask import Flask, abort, request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_functions(relative_path, names, namespace):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=functions, type_ignores=[]), relative_path, "exec"), namespace)
    return namespace


class YtdlpSecurityTests(unittest.TestCase):
    def test_command_expression_is_not_executed(self):
        called = Mock(return_value="best")
        namespace = {"payload_executed": called}
        try:
            from ytdlp_options import parse_ytdlp_options
            namespace["parse_ytdlp_options"] = parse_ytdlp_options
        except ModuleNotFoundError:
            pass
        parser = load_functions("bot/modules/ytdlp.py", {"arg_parser"}, namespace)["arg_parser"]
        with self.assertRaises(ValueError):
            parser(["-opt", "{'format': payload_executed()}"], {"link": ""})
        called.assert_not_called()

    def test_dictionary_and_legacy_values(self):
        from ytdlp_options import parse_ytdlp_options
        self.assertEqual(parse_ytdlp_options("{'format': 'best', 'quiet': True}"), {"format": "best", "quiet": True})
        self.assertEqual(parse_ytdlp_options('{"quiet":true}'), {"quiet": True})
        self.assertEqual(
            parse_ytdlp_options("format:best|playlist_items:1:3|retries:^5|quiet:true|http_headers:{'A': 'B'}"),
            {"format": "best", "playlist_items": "1:3", "retries": 5, "quiet": True, "http_headers": {"A": "B"}},
        )

    def test_unsafe_and_invalid_options_are_rejected(self):
        from ytdlp_options import parse_ytdlp_options
        for value in ["{'x': __import__('os').getcwd()}", "http_headers:{'x': sum([1])}", "[]", "bad", "{'postprocessors':[{'key':'Exec','exec_cmd':'echo bad'}]}", "external_downloader:/tmp/run", "ffmpeg_location:/tmp/run"]:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                parse_ytdlp_options(value)

    def test_normal_postprocessing_and_ranges_keep_their_values(self):
        tree = ast.parse((ROOT / "bot/helper/mirror_leech_utils/download_utils/yt_dlp_helper.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "YoutubeDLHelper")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_set_options")
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "yt_dlp_helper.py", "exec"), namespace)
        downloader = SimpleNamespace(opts={"postprocessors": []}, keep_thumb=False)
        namespace["_set_options"](downloader, "postprocessors:{'key':'FFmpegExtractAudio'}|download_ranges:[{'start_time': 1, 'end_time': 5}]|writethumbnail:true")
        self.assertEqual(downloader.opts["postprocessors"], [{"key": "FFmpegExtractAudio"}])
        self.assertEqual(downloader.opts["download_ranges"](None, None), [{"start_time": 1, "end_time": 5}])
        self.assertTrue(downloader.keep_thumb)

    def test_runtime_and_netrc_commands_are_rejected(self):
        from ytdlp_options import parse_ytdlp_options
        values = [
            {"netrc_cmd": "echo fixture"}, "netrc_cmd:echo fixture",
            {"js_runtimes": {"deno": {"path": "/tmp/program"}}},
            "js_runtimes:{'deno': {'path': '/tmp/program'}}",
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_ytdlp_options(value)

    def test_external_downloader_execution_hooks_are_rejected(self):
        from ytdlp_options import parse_ytdlp_options
        cases = [
            ("aria2c", ["--on-download-start=echo fixture"]),
            ("aria2c", ["--on-download-sta=echo fixture"]),
            ("aria2c", ["--conf-path=/tmp/config"]),
            ("wget", ["--use-askpass=/tmp/program"]),
            ("wget", ["-qeuse_askpass=/tmp/program"]),
            ("curl", ["-sK/tmp/config"]),
            ("curl", ["--engine=/tmp/library"]),
        ]
        for downloader, arguments in cases:
            value = {"external_downloader": downloader, "external_downloader_args": {downloader: arguments}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_ytdlp_options(value)
        with self.assertRaises(ValueError):
            parse_ytdlp_options("external_downloader:aria2c|external_downloader_args:{'aria2c':['--on-download-start=echo fixture']}")

    def test_normal_external_downloader_arguments_remain_available(self):
        from ytdlp_options import parse_ytdlp_options
        for downloader, arguments in [
            ("aria2c", ["-x", "8", "--split=8", "--max-download-limit=1M"]),
            ("curl", ["-e", "https://example.invalid/", "--retry", "3"]),
            ("wget", ["-UExampleAgent", "--timeout=30", "-K"]),
            ("ffmpeg", ["-metadata", "title=example"]),
        ]:
            value = {"external_downloader": downloader, "external_downloader_args": {"default": arguments}}
            self.assertEqual(parse_ytdlp_options(value), value)


class _ExecutablePickle:
    def __reduce__(self):
        return eval, ("1 + 2",)


class DriveCredentialSecurityTests(unittest.TestCase):
    def setUp(self):
        from datetime import datetime
        from google.oauth2.credentials import Credentials
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "token.pickle"
        self.credentials = Credentials("access-token", refresh_token="refresh-token", token_uri="https://oauth2.googleapis.com/token", client_id="client", client_secret="secret", scopes=["https://www.googleapis.com/auth/drive"])
        self.credentials.expiry = datetime(2030, 1, 1)

    def test_standard_legacy_tokens_keep_fields_across_protocols(self):
        from drive_credentials import read_drive_credentials
        for protocol in [2, 3, 4, 5]:
            with self.subTest(protocol=protocol):
                self.path.write_bytes(pickle.dumps(self.credentials, protocol=protocol))
                actual = read_drive_credentials(self.path)
                self.assertEqual(actual.token, self.credentials.token)
                self.assertEqual(actual.refresh_token, self.credentials.refresh_token)
                self.assertEqual(actual.client_secret, self.credentials.client_secret)
                self.assertEqual(actual.scopes, self.credentials.scopes)
                self.assertEqual(actual.expiry, self.credentials.expiry)

    def test_expired_token_remains_refreshable(self):
        from datetime import datetime
        from drive_credentials import read_drive_credentials, write_drive_credentials
        self.credentials.expiry = datetime(2000, 1, 1)
        write_drive_credentials(self.credentials, self.path)
        actual = read_drive_credentials(self.path)
        self.assertTrue(actual.expired)
        self.assertEqual(actual.refresh_token, "refresh-token")

    def test_executable_and_cached_extension_pickles_are_rejected(self):
        from drive_credentials import read_drive_credentials
        for value in [pickle.dumps(_ExecutablePickle()), b"\x80\x02\x82\x01.", b"invalid", pickle.dumps({"token": "bad"})]:
            with self.subTest(payload=value[:12]), self.assertRaises(ValueError):
                self.path.write_bytes(value)
                read_drive_credentials(self.path)

    def test_failed_validation_does_not_replace_a_working_token(self):
        from drive_credentials import read_drive_credentials, write_drive_credentials
        write_drive_credentials(self.credentials, self.path)
        original = self.path.read_bytes()
        self.credentials.token = ["bad"]
        with self.assertRaises(ValueError):
            write_drive_credentials(self.credentials, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(read_drive_credentials(self.path).token, "access-token")

    def test_token_size_is_bounded(self):
        from drive_credentials import MAX_TOKEN_SIZE, read_drive_credentials
        self.path.write_bytes(b"x" * (MAX_TOKEN_SIZE + 1))
        with self.assertRaises(ValueError):
            read_drive_credentials(self.path)

    def test_drive_authorize_uses_validated_credentials(self):
        from drive_credentials import read_drive_credentials, write_drive_credentials
        write_drive_credentials(self.credentials, self.path)
        tree = ast.parse((ROOT / "bot/helper/mirror_leech_utils/gd_utils/helper.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GoogleDriveHelper")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "authorize")
        namespace = {"read_drive_credentials": read_drive_credentials, "ospath": os.path, "LOGGER": Mock(), "build": Mock(return_value="drive-service")}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "gd_helper.py", "exec"), namespace)
        self.assertEqual(namespace["authorize"](SimpleNamespace(use_sa=False, token_path=str(self.path))), "drive-service")
        self.assertEqual(namespace["build"].call_args.kwargs["credentials"].token, "access-token")

    def upload(self, payload, reported_size=None):
        from drive_credentials import MAX_TOKEN_SIZE, read_drive_credentials, write_drive_credentials
        sent = AsyncMock()
        response = SimpleNamespace(text=None, document=SimpleNamespace(file_name="token.pickle", file_size=len(payload) if reported_size is None else reported_size))
        async def download_media(message, file_name):
            Path(file_name).write_bytes(payload)
            return file_name
        client = SimpleNamespace(
            listen=SimpleNamespace(Message=AsyncMock(return_value=response)),
            send_message=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())),
            download_media=AsyncMock(side_effect=download_media),
        )
        namespace = {
            "getcwd": lambda: self.temporary.name, "ospath": os.path, "makedirs": os.makedirs,
            "osremove": Mock(), "copyfile": copyfile, "TemporaryDirectory": TemporaryDirectory,
            "MAX_TOKEN_SIZE": MAX_TOKEN_SIZE, "read_drive_credentials": read_drive_credentials,
            "write_drive_credentials": write_drive_credentials, "sendMessage": sent,
            "database": SimpleNamespace(enabled=False),
            "filters": SimpleNamespace(document=1, text=2, user=lambda user_id: user_id),
        }
        function = load_functions("bot/modules/botfiles.py", {"set_config_listener"}, namespace)["set_config_listener"]
        message = SimpleNamespace(chat=SimpleNamespace(id=1))
        run_async(function(client, None, message, forced_section="token", target_user_id=7))
        return client, sent

    def test_valid_upload_keeps_personal_token_path(self):
        from drive_credentials import read_drive_credentials
        client, sent = self.upload(pickle.dumps(self.credentials))
        actual = read_drive_credentials(Path(self.temporary.name) / "tokens/7.pickle")
        self.assertEqual(actual.refresh_token, "refresh-token")
        client.download_media.assert_awaited_once()
        self.assertIn("uploaded successfully", sent.await_args.args[0])

    def test_invalid_upload_preserves_previous_personal_token(self):
        from drive_credentials import write_drive_credentials
        target = Path(self.temporary.name) / "tokens/7.pickle"
        write_drive_credentials(self.credentials, target)
        previous = target.read_bytes()
        _, sent = self.upload(pickle.dumps(_ExecutablePickle()))
        self.assertEqual(target.read_bytes(), previous)
        self.assertIn("Invalid or unsafe", sent.await_args.args[0])

    def test_oversized_upload_is_rejected_before_downloading(self):
        from drive_credentials import MAX_TOKEN_SIZE
        client, sent = self.upload(b"placeholder", reported_size=MAX_TOKEN_SIZE + 1)
        client.download_media.assert_not_awaited()
        self.assertIn("too large", sent.await_args.args[0])


class WebSelectionSecurityTests(unittest.TestCase):
    def setUp(self):
        import selection_auth
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        key_patch = patch.object(selection_auth, "KEY_PATH", Path(self.temporary.name) / "selection.key")
        key_patch.start()
        self.addCleanup(key_patch.stop)
        self.app = Flask(__name__)
        self.qbit = Mock()
        self.qbit.torrents_files.return_value = []
        self.aria = Mock()
        self.namespace = {
            "app": self.app, "request": request, "abort": abort,
            "qbClient": Mock(return_value=self.qbit), "aria2": self.aria,
            "make_tree": lambda *args: ("files",), "sleep": lambda _: None,
            "re_verfiy": lambda *args: True, "LOGGER": Mock(),
            "NotFound404Error": RuntimeError,
            "page": "{My_content} {form_url}", "code_page": "{form_url}",
        }
        try:
            from selection_auth import selection_credentials, verify_selection
            from urllib.parse import urlencode
            from html import escape
            self.namespace.update(verify_selection=verify_selection, urlencode=urlencode, escape=escape)
        except ModuleNotFoundError:
            pass
        tree = ast.parse((ROOT / "qbitweb/wserver.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "code_page":
                self.namespace["code_page"] = ast.literal_eval(node.value)
        load_functions("qbitweb/wserver.py", {"_authorize_selection", "list_torrent_contents", "set_priority"}, self.namespace)
        self.client = self.app.test_client()

    def test_post_without_auth_never_calls_backend(self):
        result = self.client.post("/app/files/" + "a1" * 20, data={"filenode_0": "on"})
        self.assertEqual(result.status_code, 403)
        self.qbit.torrents_file_priority.assert_not_called()
        self.aria.client.change_option.assert_not_called()

    def test_task_id_derived_pin_is_rejected(self):
        result = self.client.get("/app/files/" + "a1" * 20 + "?pin_code=1111")
        self.assertEqual(result.status_code, 403)
        self.qbit.torrents_files.assert_not_called()

    def url(self, gid="a1" * 20, include_pin=True):
        from selection_auth import selection_credentials
        token, pin = selection_credentials(gid)
        query = {"token": token}
        if include_pin:
            query["pin_code"] = pin
        return f"/app/files/{gid}?{urlencode(query)}"

    def test_valid_qbit_get_and_post_preserve_selection(self):
        url = self.url()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, data={"filenode_0": "on", "filenode_1": "off"}).status_code, 200)
        self.qbit.torrents_file_priority.assert_any_call(torrent_hash="a1" * 20, file_ids="0", priority=1)
        self.qbit.torrents_file_priority.assert_any_call(torrent_hash="a1" * 20, file_ids="1", priority=0)

    def test_valid_aria_get_and_post_preserve_selection(self):
        url = self.url("a1" * 8)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, data={"filenode_1": "on"}).status_code, 200)
        self.aria.client.change_option.assert_called_once_with("a1" * 8, {"select-file": "1"})

    def test_manual_pin_form_preserves_task_signature(self):
        url = self.url(include_pin=False)
        result = self.client.get(url)
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'name="token"', result.data)
        self.assertIn(url.split("token=", 1)[1].encode(), result.data)
        self.assertEqual(self.client.post(url, data={"filenode_0": "on"}).status_code, 403)
        self.qbit.torrents_file_priority.assert_not_called()

    def test_wrong_pin_signature_duplicates_and_other_tasks_are_rejected(self):
        url = self.url()
        bad_urls = [url.rsplit("=", 1)[0] + "=wrong", url.replace("a1" * 20, "b2" * 20), url + "&token=invalid", url.replace("token=", "token=x")]
        for candidate in bad_urls:
            for method in [self.client.get, self.client.post]:
                with self.subTest(candidate=candidate, method=method.__name__):
                    self.assertEqual(method(candidate).status_code, 403)
        self.qbit.torrents_files.assert_not_called()
        self.qbit.torrents_file_priority.assert_not_called()

    def test_web_pincode_modes_generate_usable_buttons(self):
        from selection_auth import selection_credentials
        class Buttons:
            def __init__(self):
                self.buttons = []
            def url_buildbutton(self, text, value):
                self.buttons.append((text, value))
            cb_buildbutton = url_buildbutton
            def build_menu(self, columns):
                return self.buttons
        namespace = {"selection_credentials": selection_credentials, "ButtonMaker": Buttons, "config_dict": {"QB_BASE_URL": "http://localhost", "QB_SERVER_PORT": 18080}}
        function = load_functions("bot/helper/ext_utils/misc_utils.py", {"bt_selection_buttons"}, namespace)["bt_selection_buttons"]
        for enabled in [True, False]:
            namespace["config_dict"]["WEB_PINCODE"] = enabled
            buttons = function("a1" * 20)
            url = buttons[0][1].replace("http://localhost:18080", "")
            result = self.client.get(url)
            self.assertEqual(result.status_code, 200)
            self.assertEqual("pin_code=" in url, not enabled)

    def test_complete_web_module_preserves_403_and_private_response_headers(self):
        spec = spec_from_file_location("selection_web_smoke", ROOT / "qbitweb/wserver.py")
        module = module_from_spec(spec)
        backends = {
            "qbittorrentapi": SimpleNamespace(NotFound404Error=RuntimeError, Client=Mock()),
            "aria2p": SimpleNamespace(API=Mock(), Client=Mock()),
        }
        with patch.dict(sys.modules, backends), patch("logging.FileHandler", return_value=logging.NullHandler()), patch("logging.basicConfig"):
            spec.loader.exec_module(module)
        result = module.app.test_client().post("/app/files/" + "a1" * 20)
        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(result.headers["Cache-Control"], "no-store")


class SourceUpdateSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.upstream = self.base / "upstream"
        self.upstream.mkdir()
        self.git(self.upstream, "init", "--quiet", "-b", "main")
        (self.upstream / ".gitignore").write_text("data/\nconfig.env\n", encoding="utf-8")
        self.commit(self.upstream, "app.txt", "initial")

    @staticmethod
    def git(directory, *arguments):
        try:
            result = run(["git", "-c", "commit.gpgsign=false", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-C", str(directory), *arguments], capture_output=True, text=True, check=True)
        except CalledProcessError as error:
            raise AssertionError(error.stderr) from error
        return result.stdout.strip()

    def commit(self, directory, name, contents):
        (directory / name).write_text(contents, encoding="utf-8")
        self.git(directory, "add", "--all")
        self.git(directory, "commit", "--quiet", "-m", "fixture")

    def clone(self):
        target = self.base / "application"
        self.git(self.base, "clone", "--quiet", str(self.upstream), str(target))
        return target

    def test_fast_forward_preserves_history(self):
        from source_update import update_source
        target = self.clone()
        previous = self.git(target, "rev-parse", "HEAD")
        self.commit(self.upstream, "app.txt", "updated")
        update_source(str(self.upstream), "main", target)
        self.assertEqual((target / "app.txt").read_text(), "updated")
        self.git(target, "merge-base", "--is-ancestor", previous, "HEAD")

    def test_startup_logs_do_not_block_fast_forward(self):
        from source_update import update_source
        target = self.clone()
        (target / "log.txt").write_text("startup log")
        (target / "botlog.txt").write_text("bot log")
        self.commit(self.upstream, "app.txt", "updated")
        update_source(str(self.upstream), "main", target)
        self.assertEqual((target / "app.txt").read_text(), "updated")
        self.assertEqual((target / "log.txt").read_text(), "startup log")

    def test_local_edits_and_diverged_commits_are_preserved(self):
        from source_update import update_source
        target = self.clone()
        (target / "app.txt").write_text("local edit")
        self.commit(self.upstream, "app.txt", "remote edit")
        with self.assertRaises(ValueError):
            update_source(str(self.upstream), "main", target)
        self.assertEqual((target / "app.txt").read_text(), "local edit")
        self.git(target, "add", "app.txt")
        self.git(target, "commit", "--quiet", "-m", "local change")
        original = self.git(target, "rev-parse", "HEAD")
        with self.assertRaises(ValueError):
            update_source(str(self.upstream), "main", target)
        self.assertEqual(self.git(target, "rev-parse", "HEAD"), original)
        self.assertEqual((target / "app.txt").read_text(), "local edit")

    def test_source_only_bootstrap_keeps_backup_and_runtime_files(self):
        from source_update import update_source
        target = self.base / "application"
        target.mkdir()
        (target / "app.txt").write_text("old image")
        (target / "config.env").write_text("private local settings")
        update_source(str(self.upstream), "main", target)
        self.assertEqual((target / "app.txt").read_text(), "initial")
        self.assertEqual((target / "config.env").read_text(), "private local settings")
        self.assertEqual(next((target / "data/update-backups").glob("*/app.txt")).read_text(), "old image")
        self.assertTrue((target / ".git").is_dir())
        self.commit(self.upstream, "app.txt", "next update")
        update_source(str(self.upstream), "main", target)
        self.assertEqual((target / "app.txt").read_text(), "next update")

    def test_bootstrap_failure_restores_existing_files(self):
        import source_update
        target = self.base / "application"
        target.mkdir()
        (target / "app.txt").write_text("old image")
        self.commit(self.upstream, "new.txt", "new file")
        original_copy = source_update.copy2
        def fail_on_new_file(source, destination, *args, **kwargs):
            if Path(source).name == "new.txt":
                raise OSError("simulated write failure")
            return original_copy(source, destination, *args, **kwargs)
        with patch.object(source_update, "copy2", side_effect=fail_on_new_file), self.assertRaises(OSError):
            source_update.update_source(str(self.upstream), "main", target)
        self.assertEqual((target / "app.txt").read_text(), "old image")
        self.assertFalse((target / "new.txt").exists())
        self.assertFalse((target / ".git").exists())

    def test_unsafe_refs_transports_and_private_paths_are_rejected(self):
        from source_update import update_source
        target = self.clone()
        for repository, branch in [("ext::anything", "main"), (str(self.upstream), "main; echo bad"), (str(self.upstream), "--upload-pack=bad")]:
            with self.subTest(repository=repository, branch=branch), self.assertRaises(ValueError):
                update_source(repository, branch, target)
        (self.upstream / "config.env").write_text("untrusted settings")
        self.git(self.upstream, "add", "-f", "config.env")
        self.git(self.upstream, "commit", "--quiet", "-m", "private file")
        with self.assertRaises(ValueError):
            update_source(str(self.upstream), "main", target)
        self.assertFalse((target / "config.env").exists())


if __name__ == "__main__":
    unittest.main()
