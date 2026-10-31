from bot.i18n import tr, raw
from asyncio import TimeoutError, create_subprocess_exec, create_subprocess_shell
from pyrogram.filters import regex, command
from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from bot import (
    GLOBAL_EXTENSION_FILTER,
    LOGGER,
    TG_MAX_SPLIT_SIZE,
    bot,
    Interval,
    config_dict,
    aria2_options,
    aria2c_global,
    qbit_options,
    status_reply_dict_lock,
    status_dict,
    leech_log,
)
from bot.core.torrent_manager import TorrentManager
from bot.core.config_manager import Config
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import run_sync_to_async, setInterval
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    editMarkup,
    sendFile,
    sendMarkup,
    sendMessage,
    update_all_messages,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.rclone_data_holder import update_rclone_data
from bot.modules.torr_search import initiate_search_tools


START = 0
STATE = "view"
default_values = {
    "AUTO_DELETE_MESSAGE_DURATION": 30,
    "DOWNLOAD_DIR": "/usr/src/app/downloads/",
    "UPSTREAM_BRANCH": "master",
    "STATUS_UPDATE_INTERVAL": 10,
    "LEECH_SPLIT_SIZE": TG_MAX_SPLIT_SIZE,
    "SEARCH_LIMIT": 0,
    "BOT_UI_LANGUAGE": "zh-CN",
}


async def handle_ownerset(client, message):
    text, buttons = get_env_menu()
    await sendMarkup(text, message, reply_markup=buttons.build_menu(2))


async def edit_menus(message, edit_type="env"):
    if edit_type == "env":
        text, buttons = get_env_menu()
        await editMarkup(text, message, reply_markup=buttons.build_menu(2))
    elif edit_type == "aria":
        text, buttons = get_aria_menu()
        await editMarkup(text, message, reply_markup=buttons.build_menu(2))
    elif edit_type == "qbit":
        text, buttons = get_qbit_menu()
        await editMarkup(text, message, reply_markup=buttons.build_menu(2))


def get_env_menu():
    msg = tr("settings.owner_title")
    msg += tr("settings.state", state=tr("settings.state_" + STATE, _html=False))
    buttons = ButtonMaker()
    for k in list(config_dict.keys())[START : 10 + START]:
        buttons.cb_buildbutton(k, f"ownersetmenu^env^editenv^{k}")
    if STATE == "view":
        buttons.cb_buildbutton(tr("settings.edit", _html=False), "ownersetmenu^edit^env")
    else:
        buttons.cb_buildbutton(tr("settings.view", _html=False), "ownersetmenu^view^env")
    buttons.cb_buildbutton(tr("settings.aria", _html=False), "ownersetmenu^aria^aria_menu")
    buttons.cb_buildbutton(tr("settings.qbit", _html=False), "ownersetmenu^qbit^qbit_menu")
    pages = 0
    for x in range(0, len(config_dict) - 1, 10):
        pages = int(x / 10)
    buttons.cb_buildbutton(f"🗓 {int(START/10)}/{pages}", "ownersetmenu^page")
    buttons.cb_buildbutton(tr("settings.previous", _html=False), "ownersetmenu^back^env", "footer")
    buttons.cb_buildbutton(tr("settings.next", _html=False), f"ownersetmenu^next^env", "footer")
    buttons.cb_buildbutton(tr("settings.close_menu", _html=False), "ownersetmenu^close", "footer_second")
    return msg, buttons


def get_qbit_menu():
    msg = tr("settings.qbit_title", _html=False)
    msg += tr("settings.state", state=tr("settings.state_" + STATE, _html=False))
    buttons = ButtonMaker()
    for k in list(qbit_options.keys())[START : 10 + START]:
        buttons.cb_buildbutton(k, f"ownersetmenu^qbit^editqbit^{k}")
    if STATE == "view":
        buttons.cb_buildbutton(tr("settings.edit", _html=False), "ownersetmenu^edit^qbit")
    else:
        buttons.cb_buildbutton(tr("settings.view", _html=False), "ownersetmenu^view^qbit")
    pages = 0
    for x in range(0, len(qbit_options) - 1, 10):
        pages = int(x / 10)
    buttons.cb_buildbutton(f"🗓 {int(START/10)}/{pages}", "ownersetmenu^page")
    buttons.cb_buildbutton(tr("settings.previous", _html=False), "ownersetmenu^back^qbit", "footer")
    buttons.cb_buildbutton(tr("settings.next", _html=False), f"ownersetmenu^next^qbit", "footer")
    buttons.cb_buildbutton(tr("settings.back_arrow", _html=False), "ownersetmenu^back_menu", "footer_second")
    buttons.cb_buildbutton(tr("settings.close_menu", _html=False), "ownersetmenu^close", "footer_third")
    return msg, buttons


def get_aria_menu():
    msg = tr("settings.aria_title", _html=False)
    msg += tr("settings.state", state=tr("settings.state_" + STATE, _html=False))
    buttons = ButtonMaker()
    for k in list(aria2_options.keys())[START : 10 + START]:
        buttons.cb_buildbutton(k, f"ownersetmenu^aria^editaria^{k}")
    if STATE == "view":
        buttons.cb_buildbutton(tr("settings.edit", _html=False), "ownersetmenu^edit^aria")
    else:
        buttons.cb_buildbutton(tr("settings.view", _html=False), "ownersetmenu^view^aria")
    buttons.cb_buildbutton(tr("settings.add_key", _html=False), "ownersetmenu^aria^editaria^newkey")
    pages = 0
    for x in range(0, len(aria2_options) - 1, 10):
        pages = int(x / 10)
    buttons.cb_buildbutton(f"🗓 {int(START/10)}/{pages}", "ownersetmenu^page")
    buttons.cb_buildbutton(tr("settings.previous", _html=False), "ownersetmenu^back^aria", "footer")
    buttons.cb_buildbutton(tr("settings.next", _html=False), "ownersetmenu^next^aria", "footer")
    buttons.cb_buildbutton(tr("settings.back_arrow", _html=False), "ownersetmenu^back_menu", "footer_second")
    buttons.cb_buildbutton(tr("settings.close_menu", _html=False), "ownersetmenu^close", "footer_third")
    return msg, buttons


async def update_buttons(message, key, edit_type=None):
    buttons = ButtonMaker()
    msg = tr("settings.select_option", config_key=key)
    if key == "BOT_UI_LANGUAGE" and edit_type == "editenv":
        buttons.cb_buildbutton("简体中文", "ownersetmenu^language^zh-CN")
        buttons.cb_buildbutton("English", "ownersetmenu^language^en")
    if edit_type == "editenv":
        buttons.cb_buildbutton(tr("settings.send", _html=False), f"ownersetmenu^send^env^{key}")
        if key not in ["TELEGRAM_HASH", "TELEGRAM_API", "OWNER_ID", "BOT_TOKEN"]:
            buttons.cb_buildbutton(tr("settings.default", _html=False), f"ownersetmenu^env^resetenv^{key}")
        buttons.cb_buildbutton(tr("settings.back", _html=False), "ownersetmenu^back^env", "footer")
        buttons.cb_buildbutton(tr("settings.close", _html=False), "ownersetmenu^close", "footer")
    elif edit_type == "editaria":
        buttons.cb_buildbutton(tr("settings.send", _html=False), f"ownersetmenu^send^aria^{key}")
        if key != "newkey":
            buttons.cb_buildbutton(tr("settings.empty", _html=False), f"ownersetmenu^aria^emptyaria^{key}")
            buttons.cb_buildbutton(tr("settings.default", _html=False), f"ownersetmenu^aria^resetaria^{key}")
        buttons.cb_buildbutton(tr("settings.back", _html=False), "ownersetmenu^back^aria", "footer")
        buttons.cb_buildbutton(tr("settings.close", _html=False), "ownersetmenu^close", "footer")
    elif edit_type == "editqbit":
        buttons.cb_buildbutton(tr("settings.send", _html=False), f"ownersetmenu^send^qbit^{key}")
        buttons.cb_buildbutton(tr("settings.empty", _html=False), f"ownersetmenu^qbit^emptyqbit^{key}")
        buttons.cb_buildbutton(tr("settings.back", _html=False), "ownersetmenu^back^qbit", "footer")
        buttons.cb_buildbutton(tr("settings.close", _html=False), "ownersetmenu^close", "footer")
    await editMarkup(msg, message, reply_markup=buttons.build_menu(2))


async def ownerset_callback(client, callback_query):
    query = callback_query
    data = query.data
    data = data.split("^")
    message = query.message
    user_id = query.from_user.id
    from bot import OWNER_ID
    language_action = data[1] == "language" or (len(data) > 3 and data[3] == "BOT_UI_LANGUAGE")
    if language_action and user_id != OWNER_ID:
        await query.answer(tr("common.access_denied", _html=False), show_alert=True)
        return

    if data[1] == "language":
        try:
            value = Config._convert("BOT_UI_LANGUAGE", data[2])
        except ValueError:
            await query.answer(tr("settings.language.invalid", _html=False), show_alert=True)
            return
        Config.set("BOT_UI_LANGUAGE", value)
        config_dict["BOT_UI_LANGUAGE"] = value
        if database.enabled:
            await database.update_config({"BOT_UI_LANGUAGE": value})
        from bot.i18n.commands import publish_commands
        await publish_commands(client)
        await query.answer()
        await edit_menus(message, "env")
    elif data[1] == "env":
        if data[2] == "editenv" and STATE == "edit":
            if data[3] in [
                "PARALLEL_TASKS",
                "SUDO_USERS",
                "RC_INDEX_USER",
                "RC_INDEX_PASS",
                "RC_INDEX_URL",
                "RC_INDEX_PORT",
                "ALLOWED_CHATS",
                "USER_SESSION_STRING",
                "AUTO_MIRROR",
                "CMD_INDEX",
                "TELEGRAM_API_HASH",
                "TELEGRAM_API_ID",
                "BOT_TOKEN",
                "OWNER_ID",
                "DOWNLOAD_DIR",
                "DATABASE_URL",
            ]:
                await query.answer(
                    text=tr("settings.restart", _html=False), show_alert=True
                )
            else:
                await query.answer()
            await update_buttons(message, data[3], data[2])
        elif data[2] == "editenv" and STATE == "view":
            value = config_dict[data[3]]
            if len(str(value)) > 200:
                await query.answer()
                filename = f"{data[2]}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"{value}")
                await sendFile(message, filename)
                return
            if value == "":
                value = tr("settings.none", _html=False)
            await query.answer(text=f"{value}", show_alert=True)
        elif data[2] == "resetenv":
            value = ""
            if data[3] in default_values:
                value = default_values[data[3]]
                if data[3] == "STATUS_UPDATE_INTERVAL" and len(status_dict) != 0:
                    async with status_reply_dict_lock:
                        if Interval:
                            Interval[0].cancel()
                            Interval.clear()
                            Interval.append(setInterval(value, update_all_messages))
            elif data[3] == "DEFAULT_OWNER_REMOTE":
                update_rclone_data("MIRROR_SELECT_REMOTE", value, user_id)
                update_rclone_data("MIRROR_SELECT_BASE_DIR", value, user_id)
            elif data[3] == "EXTENSION_FILTER":
                GLOBAL_EXTENSION_FILTER.clear()
                GLOBAL_EXTENSION_FILTER.extend([".aria2", "!qB"])
            elif data[3] == "TORRENT_TIMEOUT":
                downloads = await TorrentManager.aria2.tellActive()
                for download in downloads:
                    try:
                        await TorrentManager.aria2.changeOption(
                            download.get("gid"),
                            {"bt-stop-timeout": "0"},
                        )
                    except Exception as e:
                        LOGGER.error(e)
                aria2_options["bt-stop-timeout"] = "0"
                if database.enabled:
                    await database.update_aria2("bt-stop-timeout", "0")
            elif data[3] == "QB_BASE_URL":
                await (
                    await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                ).wait()
            elif data[3] == "QB_SERVER_PORT":
                if config_dict["BASE_URL"]:
                    await (
                        await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                    ).wait()
                    await create_subprocess_shell(
                        f"gunicorn qbitweb.wserver:app --bind 0.0.0.0:80 --worker-class gevent"
                    )
            await query.answer(tr("settings.reset", _html=False))
            config_dict[data[3]] = value
            if hasattr(Config, data[3]):
                Config.set(data[3], value)
            if database.enabled:
                await database.update_config({data[3]: value})
            if data[3] == "BOT_UI_LANGUAGE":
                from bot.i18n.commands import publish_commands
                await publish_commands(client)
            if data[3] in ["SEARCH_PLUGINS", "SEARCH_API_LINK"]:
                await initiate_search_tools()
            await edit_menus(message, "env")
    elif data[1] == "aria":
        if data[2] == "aria_menu":
            globals()["START"] = 0
            await edit_menus(message, "aria")
        elif data[2] == "editaria" and (STATE == "edit" or data[3] == "newkey"):
            await update_buttons(message, data[3], data[2])
        elif data[2] == "editaria" and STATE == "view":
            value = aria2_options[data[3]]
            if len(value) > 200:
                await query.answer()
                filename = f"{data[2]}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"{value}")
                await sendFile(message, filename)
                return
            elif value == "":
                value = tr("settings.none", _html=False)
            await query.answer(text=f"{value}", show_alert=True)
        elif data[2] == "resetaria":
            aria2_defaults = await TorrentManager.get_aria2_options()
            if aria2_defaults.get(data[3], "") == aria2_options.get(data[3], ""):
                await query.answer(
                    text=tr("settings.aria_same", _html=False), show_alert=True
                )
                return
            await query.answer()
            value = aria2_defaults.get(data[3], "")
            aria2_options[data[3]] = value
            await edit_menus(message, "aria")
            await TorrentManager.change_aria2_option(data[3], value)
            if database.enabled:
                await database.update_aria2(data[3], value)
        elif data[2] == "emptyaria":
            await query.answer()
            aria2_options[data[3]] = ""
            await edit_menus(message, "aria")
            await TorrentManager.change_aria2_option(data[3], "")
            if database.enabled:
                await database.update_aria2(data[3], "")
    elif data[1] == "qbit":
        if data[2] == "qbit_menu":
            globals()["START"] = 0
            await edit_menus(message, "qbit")
        elif data[2] == "editqbit" and STATE == "edit":
            await update_buttons(message, data[3], data[2])
        elif data[2] == "editqbit" and STATE == "view":
            value = qbit_options[data[3]]
            if len(str(value)) > 200:
                await query.answer()
                filename = f"{data[2]}.txt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"{value}")
                await sendFile(message, filename)
                return
            if value == "":
                value = tr("settings.none", _html=False)
            await query.answer(text=f"{value}", show_alert=True)
        elif data[2] == "emptyqbit":
            await query.answer()
            await TorrentManager.set_qbit_preferences({data[3]: ""})
            qbit_options[data[3]] = ""
            await edit_menus(message, "qbit")
            if database.enabled:
                await database.update_qbittorrent(data[3], "")
    elif data[1] == "edit":
        await query.answer()
        globals()["STATE"] = "edit"
        await edit_menus(message, data[2])
    elif data[1] == "view":
        await query.answer()
        globals()["STATE"] = "view"
        await edit_menus(message, data[2])
    elif data[1] == "next":
        await query.answer()
        globals()["START"] += 10
        if START > len(config_dict):
            globals()["START"] = START - 10
        await edit_menus(message, data[2])
    elif data[1] == "back":
        await query.answer()
        globals()["START"] -= 10
        if START < 0:
            globals()["START"] += 10
        await edit_menus(message, data[2])
    elif data[1] == "send":
        if data[2] == "env":
            await start_env_listener(client, query, user_id, data[3])
        elif data[2] == "aria":
            await start_aria_listener(client, query, user_id, data[3])
        else:
            await start_qbit_listener(client, query, user_id, data[3])
    elif data[1] == "back_menu":
        await query.answer()
        globals()["START"] = 0
        key = data[2] if len(data) == 3 else "env"
        await edit_menus(message, key)
    elif data[1] == "page":
        await query.answer()
    elif data[1] == "close":
        globals()["START"] = 0
        globals()["STATE"] = "view"
        await query.answer()
        await message.delete()


async def start_env_listener(client, query, user_id, key):
    message = query.message
    question = await sendMessage(
        tr("settings.value_prompt", _html=False),
        message,
    )
    try:
        response = await client.listen.Message(
            filters.text, id=filters.user(user_id), timeout=60
        )
    except TimeoutError:
        await client.send_message(message.chat.id, text=tr("settings.timeout_clock", _html=False))
        return
    else:
        if response:
            try:
                if "/ignore" in response.text:
                    await client.listen.Cancel(filters.user(user_id))
                else:
                    value = response.text.strip()
                    if key == "BOT_UI_LANGUAGE":
                        try:
                            value = Config._convert(key, value)
                        except ValueError:
                            await sendMessage(tr("settings.language.invalid"), message)
                            return
                    elif value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    elif value.isdigit():
                        value = int(value)
                    elif key == "STATUS_LIMIT":
                        value = int(value)
                        async with status_reply_dict_lock:
                            try:
                                if Interval:
                                    Interval[0].cancel()
                                    Interval.clear()
                            except Exception:
                                pass
                            finally:
                                Interval.append(setInterval(value, update_all_messages))
                    elif key == "STATUS_UPDATE_INTERVAL":
                        value = int(value)
                        if len(status_dict) != 0:
                            async with status_reply_dict_lock:
                                if Interval:
                                    Interval[0].cancel()
                                    Interval.clear()
                                    Interval.append(
                                        setInterval(value, update_all_messages)
                                    )
                    elif key == "TORRENT_TIMEOUT":
                        value = int(value)
                        await TorrentManager.change_aria2_option(
                            "bt-stop-timeout", f"{value}"
                        )
                        aria2_options["bt-stop-timeout"] = f"{value}"
                    elif key == "DEFAULT_OWNER_REMOTE":
                        update_rclone_data("MIRROR_SELECT_REMOTE", value, user_id)
                    elif key == "DOWNLOAD_DIR":
                        if not value.endswith("/"):
                            value = f"{value}/"
                    elif key == "LEECH_SPLIT_SIZE":
                        value = min(int(value), TG_MAX_SPLIT_SIZE)
                    elif key == "LEECH_LOG":
                        leech_log.clear()
                        aid = value.split()
                        for id_ in aid:
                            leech_log.append(int(id_.strip()))
                    elif key == "QB_SERVER_PORT":
                        value = int(value)
                        if config_dict["BASE_URL"]:
                            await (
                                await create_subprocess_exec(
                                    "pkill", "-9", "-f", "gunicorn"
                                )
                            ).wait()
                            await create_subprocess_shell(
                                f"gunicorn qbitweb.wserver:app --bind 0.0.0.0:{value} --worker-class gevent"
                            )
                    elif key == "EXTENSION_FILTER":
                        fx = value.split()
                        GLOBAL_EXTENSION_FILTER.clear()
                        GLOBAL_EXTENSION_FILTER.extend([".aria2", "!qB"])
                        for x in fx:
                            if x.strip().startswith("."):
                                x = x.lstrip(".")
                            GLOBAL_EXTENSION_FILTER.append(x.strip().lower())
                    config_dict[key] = value
                    if hasattr(Config, key):
                        Config.set(key, value)
                    if database.enabled:
                        await database.update_config({key: value})
                    if key == "BOT_UI_LANGUAGE":
                        from bot.i18n.commands import publish_commands
                        await publish_commands(client)
                    await edit_menus(message, "env")
                    if key in ["SEARCH_PLUGINS", "SEARCH_API_LINK"]:
                        await initiate_search_tools()
            except KeyError:
                await query.answer(tr("settings.value_missing", _html=False))
    finally:
        await question.delete()


async def start_aria_listener(client, query, user_id, key):
    message = query.message
    if key == "newkey":
        question = await sendMessage(
            tr("settings.key_prompt", _html=False),
            message,
        )
    else:
        question = await sendMessage(
            tr("settings.value_prompt", _html=False),
            message,
        )
    try:
        response = await client.listen.Message(
            filters.text, id=filters.user(user_id), timeout=60
        )
    except TimeoutError:
        await client.send_message(message.chat.id, text=tr("settings.timeout_clock", _html=False))
        return
    else:
        if response:
            try:
                if "/ignore" in response.text:
                    await client.listen.Cancel(filters.user(user_id))
                    return
                else:
                    value = response.text.strip()
                    if key == "newkey":
                        key, value = [x.strip() for x in value.split(":", 1)]
                    elif value.lower() == "true":
                        value = "true"
                    elif value.lower() == "false":
                        value = "false"
                    if key in aria2c_global:
                        await TorrentManager.set_aria2_options({key: value})
                    else:
                        await TorrentManager.change_aria2_option(key, value)
                    aria2_options[key] = value
                    await edit_menus(message, "aria")
                    if database.enabled:
                        await database.update_aria2(key, value)
            except KeyError:
                await query.answer(tr("settings.value_missing", _html=False))
    finally:
        await question.delete()


async def start_qbit_listener(client, query, user_id, key):
    message = query.message
    question = await sendMessage(
        tr("settings.value_prompt", _html=False),
        message,
    )
    try:
        response = await client.listen.Message(
            filters.text, id=filters.user(user_id), timeout=60
        )
    except TimeoutError:
        await client.send_message(message.chat.id, text=tr("settings.timeout_clock", _html=False))
        return
    else:
        if response:
            try:
                if "/ignore" in response.text:
                    await client.listen.Cancel(filters.user(user_id))
                    return
                else:
                    value = response.text.strip()
                    if value.lower() == "true":
                        value = True
                    elif value.lower() == "false":
                        value = False
                    elif key == "max_ratio":
                        value = float(value)
                    elif value.isdigit():
                        value = int(value)
                    await TorrentManager.set_qbit_preferences({key: value})
                    qbit_options[key] = value
                    await edit_menus(message, "qbit")
                    if database.enabled:
                        await database.update_qbittorrent(key, value)
            except KeyError:
                await query.answer(tr("settings.value_missing", _html=False))
    finally:
        await question.delete()


bot.add_handler(
    MessageHandler(
        handle_ownerset,
        filters=command(BotCommands.OwnerSetCommand) & (CustomFilters.owner_filter),
    )
)
bot.add_handler(CallbackQueryHandler(ownerset_callback, filters=regex(r"ownersetmenu")))
