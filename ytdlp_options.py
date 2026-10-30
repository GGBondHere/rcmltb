"""Parse user-supplied yt-dlp options as data, never Python code."""

from ast import literal_eval
from json import loads


def _literal(value):
    try:
        return literal_eval(value)
    except (ValueError, SyntaxError, RecursionError):
        try:
            return loads(value)
        except (ValueError, TypeError, RecursionError) as error:
            raise ValueError("Invalid yt-dlp option value; only literal data is supported") from error


def _validate_downloader_arguments(options, downloaders):
    value = options.get("external_downloader_args")
    if value is None:
        return
    groups = value.items() if isinstance(value, dict) else [("default", value)]
    dangerous = {
        "--conf-path", "--config", "--execute", "--use-askpass", "--engine",
        "--on-bt-download-complete", "--on-download-start", "--on-download-stop",
        "--on-download-complete", "--on-download-error", "--on-download-pause",
    }
    short_options = {
        "curl": ("K", set("AbcCdDeEFHmoPQrTuwxyYz")),
        "wget": ("e", set("aoOiUPtTwDQXIAREl")),
    }
    for name, arguments in groups:
        if not isinstance(name, str) or not isinstance(arguments, (list, tuple)) or any(not isinstance(arg, str) for arg in arguments):
            raise ValueError("External downloader arguments must be lists of strings")
        tool = name.split("_", 1)[0]
        tools = {tool} if tool in short_options else set(downloaders) - {None, "native"}
        for argument in arguments:
            option = argument.split("=", 1)[0].split(None, 1)[0] if argument.strip() else ""
            if option.startswith("--") and any(flag.startswith(option) for flag in dangerous):
                raise ValueError("External downloader execution hooks and configuration files are not allowed")
            if not option.startswith("-") or option.startswith("--"):
                continue
            for selected in tools.intersection(short_options):
                forbidden, takes_value = short_options[selected]
                # Respect short-option clusters, while leaving their argument values alone.
                for character in option[1:]:
                    if character == forbidden:
                        raise ValueError("External downloader execution options are not allowed")
                    if character in takes_value:
                        break


def parse_ytdlp_options(options):
    if not options:
        return {}
    if isinstance(options, str):
        options = options.strip()
        if len(options) > 65536:
            raise ValueError("yt-dlp options are too large")
        if options.startswith("{"):
            options = _literal(options)
        else:
            result = {}
            for item in options.split("|"):
                key, separator, value = item.partition(":")
                if not separator or not key.strip():
                    raise ValueError("Use a dictionary or key:value|key:value for yt-dlp options")
                value = value.strip()
                if value.startswith("^"):
                    number = value[1:]
                    value = float(number) if any(c in number.lower() for c in ".einf") else int(number)
                elif value.lower() in {"true", "false"}:
                    value = value.lower() == "true"
                elif value.startswith(("{", "[", "(")):
                    value = _literal(value)
                result[key.strip()] = value
            options = result
    if not isinstance(options, dict) or any(not isinstance(key, str) or not key for key in options):
        raise ValueError("yt-dlp options must be a dictionary with string keys")

    # Exec postprocessors and arbitrary executable paths cross the download-user boundary.
    forbidden = {
        "exec_cmd", "exec_before_dl_cmd", "exec_after_dl_cmd", "ffmpeg_location",
        "plugin_dirs", "netrc_cmd", "js_runtimes", "remote_components",
    }
    if forbidden.intersection(options):
        raise ValueError("Executing commands or selecting executable paths is not allowed in yt-dlp options")
    downloader = options.get("external_downloader")
    downloaders = list(downloader.values()) if isinstance(downloader, dict) else [downloader]
    if any(value is not None and (not isinstance(value, str) or value not in {"native", "aria2c", "curl", "wget", "ffmpeg", "axel", "httpie"}) for value in downloaders):
        raise ValueError("Unsupported external downloader; use an installed downloader name")
    _validate_downloader_arguments(options, downloaders)
    processors = options.get("postprocessors", [])
    processors = [processors] if isinstance(processors, dict) else processors
    if not isinstance(processors, (list, tuple)):
        raise ValueError("postprocessors must be a dictionary or list")
    for processor in processors:
        if not isinstance(processor, dict) or not isinstance(processor.get("key"), str):
            raise ValueError("Each postprocessor must have a key")
        if processor["key"].lower().startswith("exec"):
            raise ValueError("Exec postprocessors are not allowed")
    return dict(options)
