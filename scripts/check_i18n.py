"""Offline resource and Telegram UI coverage audit; no bot startup required."""

import argparse
import ast
from collections import Counter, defaultdict
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from string import Formatter
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "bot/i18n/locales"
SINKS = {
    "sendMessage": (0,), "sendMarkup": (0,), "editMessage": (0,),
    "editMarkup": (0,), "sendPhoto": (0,), "sendFile": (2,),
    "cb_buildbutton": (0,), "url_buildbutton": (0,), "answer": (0,),
    "reply_text": (0,), "reply": (0,), "BotCommand": (1,),
    "send_message": (), "edit_message_text": (), "send_document": (),
    "send_video": (), "send_photo": (), "send_animation": (),
    "reply_document": (), "reply_video": (), "reply_photo": (),
    "InlineKeyboardButton": (),
}
TEXT_KEYWORDS = {"text", "caption", "message", "description"}
TECHNICAL = {"GitHub", "Google Drive", "Telegram", "TMDB", "API", "OAuth", "Token", "rclone", "WebDAV",
             "HTTP", "HTTPS", "CPU", "RAM", "SWAP", "Docker", "aria2", "aria2c", "qBittorrent", "yt-dlp",
             "Deno", "English", "Language", "UTF-8", "N/A", "RCMLTB", "URL", "IP", "ID", "BT", "KB", "MB", "GB", "TB"}
REVIEWED_TECHNICAL = {
    "/leech {dynamic} -au {dynamic} -ap {dynamic}": "Generated Telegram command, including unchanged authentication flags",
    "/mirror {dynamic} -au {dynamic} -ap {dynamic}": "Generated Telegram command, including unchanged authentication flags",
    "/leech -i {dynamic}": "Generated batch command; command names and flags are protocol data",
    "/mirror -i {dynamic}": "Generated batch command; command names and flags are protocol data",
    "YT-DLP": "Tool name; yt-dlp is intentionally retained",
    "Api": "Existing API tool label; technical name rather than prose",
    "{dynamic}-mp4": "Media format identifier",
    "{dynamic}-webm": "Media format identifier",
    "{dynamic}p{dynamic}-{dynamic}": "Video resolution/FPS/format specification",
    "{dynamic}K ({dynamic})": "Audio bitrate/codec specification",
    "{dynamic}K-mp3": "Audio bitrate and format specification",
}
HTML_FRAGMENTS = {"helpers.text.metadata", "helpers.text.subtitles"}
FORMATTER = Formatter()


def load_resources(language):
    entries = {}
    for path in sorted((LOCALES / language).glob("*.json")):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"{path}: duplicate key {key}")
                result[key] = value
            return result
        values = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if entries.keys() & values.keys():
            raise ValueError(f"{path}: duplicate domain keys")
        entries.update(values)
    return entries


def placeholders(text):
    return Counter((field, spec, conversion) for _, field, spec, conversion in FORMATTER.parse(text) if field is not None)


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        self.events.append((tag, tuple(sorted(name for name, _ in attrs))))
        if tag not in {"br", "hr", "img"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        self.events.append(("/" + tag, ()))
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unmatched closing {tag}")
        else:
            self.stack.pop()


def check_resources():
    english, chinese = load_resources("en"), load_resources("zh-CN")
    errors = []
    for language, missing in (("zh-CN", english.keys() - chinese.keys()), ("en", chinese.keys() - english.keys())):
        errors.extend(f"Missing {language}: {key}" for key in sorted(missing))
    fragments = []
    for key in sorted(english.keys() & chinese.keys()):
        if not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", key) or re.search(r"_[0-9a-f]{6}$", key):
            errors.append(f"{key}: use a stable semantic key without line/hash identifiers")
        en, zh = english[key], chinese[key]
        if type(en) is not type(zh):
            errors.append(f"{key}: entry types differ")
            continue
        if isinstance(en, dict):
            if en.keys() != zh.keys() or set(en) != {"one", "other"}:
                errors.append(f"{key}: plural forms must be one/other in both languages")
            variants = [(form, en[form], zh[form]) for form in en.keys() & zh.keys()]
        else:
            variants = [("", en, zh)]
        for form, source, target in variants:
            label = key + ("." + form if form else "")
            if not isinstance(source, str) or not isinstance(target, str) or not target.strip():
                errors.append(f"{label}: empty or invalid translation")
                continue
            if source.startswith("ERROR:") and not target.startswith("ERROR:"):
                errors.append(f"{label}: preserve the ERROR: control-flow marker")
            try:
                if placeholders(source) != placeholders(target):
                    errors.append(f"{label}: placeholders or formatting differ")
                for field, spec, conversion in placeholders(source):
                    if not field.isidentifier() or "{" in spec or conversion not in (None, "s", "r"):
                        errors.append(f"{label}: unsafe placeholder {field}")
            except ValueError as error:
                errors.append(f"{label}: {error}")
            en_html, zh_html = Markup(), Markup()
            en_html.feed(source)
            zh_html.feed(target)
            if Counter(en_html.events) != Counter(zh_html.events):
                errors.append(f"{label}: HTML structure/attributes differ")
            # Existing composed fragments are audited separately, never hidden as complete HTML.
            if en_html.stack or en_html.errors or zh_html.stack or zh_html.errors:
                fragments.append(label)
                if key not in HTML_FRAGMENTS:
                    errors.append(f"{label}: unbalanced HTML without a reviewed composition exception")
            for language, text in (("en", source), ("zh-CN", target)):
                if "\ufffd" in text or any(ord(char) < 32 and char not in "\n\t\r" for char in text):
                    errors.append(f"{label}: invalid special character in {language}")
    return errors, {"keys": len(english), "html_fragments": fragments}


def call_name(call):
    return call.func.id if isinstance(call.func, ast.Name) else call.func.attr if isinstance(call.func, ast.Attribute) else ""


def human_text(text):
    text = unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"\{[^}]*\}", "", text)
    text = re.sub(r"https?://\S+|tg://\S+|/[a-z][\w/-]*", "", text)
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text)
    return any(word not in TECHNICAL and not re.fullmatch(r"[A-Z][A-Z0-9_]+", word) for word in words)


def audit_sources():
    findings = {}
    references = []
    inventory = Counter()
    dynamic = Counter()
    technical = {}
    english = load_resources("en")

    for path in sorted((ROOT / "bot").rglob("*.py")):
        if "i18n" in path.relative_to(ROOT / "bot").parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        relative = path.relative_to(ROOT).as_posix()
        scopes = [tree] + [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        globals_ = defaultdict(list)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for name in node.targets:
                    if isinstance(name, ast.Name):
                        globals_[name.id].append(node.value)

        for scope in scopes:
            scope_name = getattr(scope, "name", "<module>")
            nodes = []
            def visit(node):
                if node is not scope and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    return
                nodes.append(node)
                for child in ast.iter_child_nodes(node):
                    visit(child)
            visit(scope)
            values = {key: list(value) for key, value in globals_.items()}
            for node in nodes:
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for name in targets:
                        if isinstance(name, ast.Name) and node.value is not None:
                            values.setdefault(name.id, []).append(node.value)

            def collect(expression, seen):
                if isinstance(expression, ast.Call):
                    name = call_name(expression)
                    if name in {"tr", "ui_error", "display_status"}:
                        return []
                    if name in {"raw", "str", "escape"} and expression.args:
                        return collect(expression.args[0], seen)
                    if isinstance(expression.func, ast.Attribute) and expression.func.attr in {"format", "replace", "join", "strip"}:
                        return collect(expression.func.value, seen)
                    return []
                if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
                    return [(expression, expression.value)]
                if isinstance(expression, ast.JoinedStr):
                    text = "".join(part.value if isinstance(part, ast.Constant) else "{dynamic}" for part in expression.values)
                    nested = []
                    for part in expression.values:
                        if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.IfExp):
                            nested.extend(collect(part.value, seen))
                    return [(expression, text)] + nested
                if isinstance(expression, ast.Name):
                    if expression.id in seen:
                        return []
                    return [entry for value in values.get(expression.id, []) for entry in collect(value, seen | {expression.id})]
                if isinstance(expression, ast.BinOp):
                    return collect(expression.left, seen) + collect(expression.right, seen)
                if isinstance(expression, ast.IfExp):
                    return collect(expression.body, seen) + collect(expression.orelse, seen)
                if isinstance(expression, (ast.List, ast.Tuple)):
                    return [entry for value in expression.elts for entry in collect(value, seen)]
                return []

            for node in nodes:
                if not isinstance(node, ast.Call):
                    continue
                name = call_name(node)
                if name == "tr" and node.args and isinstance(node.args[0], ast.Constant):
                    key = node.args[0].value
                    if isinstance(key, str):
                        references.append((relative, node.lineno, key))
                        entry = english.get(key)
                        if isinstance(entry, dict):
                            entry = entry.get("other")
                        if isinstance(entry, str) and not any(kw.arg is None for kw in node.keywords):
                            required = {field for field, _, _ in placeholders(entry)}
                            supplied = {kw.arg for kw in node.keywords}
                            absent = required - supplied
                            if absent:
                                references.append((relative, node.lineno, f"<missing parameters {sorted(absent)} in {key}>"))
                    continue
                if name not in SINKS:
                    continue
                inventory[relative] += 1
                expressions = [node.args[index] for index in SINKS[name] if len(node.args) > index]
                expressions += [kw.value for kw in node.keywords if kw.arg in TEXT_KEYWORDS]
                # Pyrogram positional send_message(chat_id, text) / edit_message_text(chat_id, id, text).
                if name == "send_message" and len(node.args) > 1:
                    expressions.append(node.args[1])
                elif name == "edit_message_text" and len(node.args) > 2:
                    expressions.append(node.args[2])
                for expression in expressions:
                    found = collect(expression, set())
                    if not found:
                        dynamic[relative] += 1
                    for origin, text in found:
                        if human_text(text):
                            item = {"file": relative, "line": origin.lineno, "scope": scope_name, "sink": name, "text": text}
                            if text in REVIEWED_TECHNICAL:
                                technical[(relative, origin.lineno, text)] = {**item, "reason": REVIEWED_TECHNICAL[text]}
                            else:
                                findings[(relative, origin.lineno, text)] = item
    missing = [f"{path}:{line}: unknown translation key {key}" for path, line, key in references if key not in english]
    return missing, {"sinks": sum(inventory.values()), "modules": dict(inventory), "dynamic_outputs": dict(dynamic),
                     "hardcoded": list(findings.values()), "technical_exceptions": list(technical.values()),
                     "static_translation_calls": len(references)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Write the complete inspectable coverage inventory")
    args = parser.parse_args()
    errors, resources = check_resources()
    missing, sources = audit_sources()
    errors.extend(missing)
    report = {"resources": resources, "sources": sources, "errors": errors}
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for error in errors:
        print(error)
    for item in sources["hardcoded"]:
        print(f"{item['file']}:{item['line']}: {item['text'][:130]!r}")
    print(f"{resources['keys']} keys; {sources['sinks']} Telegram sinks; {len(sources['hardcoded'])} hardcoded UI strings; {len(errors)} errors")
    return bool(errors or sources["hardcoded"])


if __name__ == "__main__":
    sys.exit(main())
