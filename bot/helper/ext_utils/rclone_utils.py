from bot.i18n import tr, raw, ui_error
from os import path as ospath
from asyncio import create_subprocess_exec
from asyncio.subprocess import PIPE
from json import loads as jsonloads
from configparser import ConfigParser, Error as ConfigError
from bot import GLOBAL_EXTENSION_FILTER, LOGGER, OWNER_ID, config_dict, remotes_multi, user_data
from bot.helper.ext_utils.bot_utils import cmd_exec, run_sync_to_async
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.exceptions import NotRclonePathFound
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.ext_utils.menu_utils import (
    Menus,
    rcloneListButtonMaker,
    rcloneListNextPage,
)
from bot.helper.telegram_helper.message_utils import (
    editMessage,
    sendMarkup,
    sendMessage,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.rclone_data_holder import get_rclone_data, update_rclone_data


def can_manage_rclone(user_id):
    return bool(config_dict["MULTI_RCLONE_CONFIG"] or user_id == OWNER_ID
                or user_data.get(user_id, {}).get("is_sudo"))


def is_shared_owner_upload(user_id):
    return not can_manage_rclone(user_id) and not config_dict["DEFAULT_GLOBAL_REMOTE"]


def get_rclone_upload_target(user_id):
    if not can_manage_rclone(user_id):
        if remote := config_dict["DEFAULT_GLOBAL_REMOTE"]:
            return remote, ""
        user_id = OWNER_ID
        remote = get_rclone_data("MIRROR_SELECT_REMOTE", user_id)
        if not remote:
            raise ValueError(tr('helpers.text.the_owner_must_select_an_upload_destination_with_ms_first', _html=False))
        conf = ConfigParser(interpolation=None)
        try:
            conf.read(f"rclone/{OWNER_ID}/rclone.conf")
        except (ConfigError, OSError, UnicodeError):
            raise ValueError(tr('helpers.text.the_owner_s_rclone_conf_could_not_be_read_ask_the_owner', _html=False)) from None
        if not conf.has_section(remote):
            raise ValueError(tr('helpers.text.the_owner_s_selected_remote_is_missing_from_rclone_conf_ask_the', _html=False))
    else:
        remote = get_rclone_data("MIRROR_SELECT_REMOTE", user_id)
    return remote, get_rclone_data("MIRROR_SELECT_BASE_DIR", user_id)


async def is_remote_selected(user_id, message, open_selector=False):
    try:
        if is_shared_owner_upload(user_id):
            try:
                get_rclone_upload_target(user_id)
                return True
            except (ValueError, OSError) as error:
                await sendMessage(ui_error(error), message)
                return False
        if get_rclone_data("MIRROR_SELECT_REMOTE", user_id):
            return True
        if await CustomFilters.sudo_filter("", message):
            if DEFAULT_OWNER_REMOTE := config_dict["DEFAULT_OWNER_REMOTE"]:
                update_rclone_data("MIRROR_SELECT_REMOTE", DEFAULT_OWNER_REMOTE, user_id)
                return True
        if config_dict["MULTI_RCLONE_CONFIG"]:
            if get_rclone_data("MIRROR_SELECT_REMOTE", user_id):
                return True
            elif len(remotes_multi) > 0:
                return True
            else:
                if open_selector:
                    await list_remotes(message, menu_type=Menus.MIRROR_SELECT)
                else:
                    await sendMessage(
                        tr('helpers.text.select_a_cloud_first_use', value1=BotCommands.MirrorSelectCommand[0], _html=False),
                        message,
                    )
                return False
        else:
            return True
    except NotRclonePathFound:
        return False


async def is_rclone_config(user_id, message, isLeech=False, show_prompt=False, *, for_upload=False):
    is_sudo_user = user_id == OWNER_ID or user_data.get(user_id, {}).get("is_sudo")

    if not for_upload and not can_manage_rclone(user_id):
        if isLeech:
            return True
        await sendMessage(tr('helpers.text.shared_storage_is_for_uploads_only_cloud_management_is_not_allowed', _html=False), message)
        return False

    if config_dict["MULTI_RCLONE_CONFIG"]:
        path = f"rclone/{user_id}/rclone.conf"
        no_path_msg = tr('helpers.text.send_a_rclone_config_file_use_files_command', _html=False)
    else:
        if is_sudo_user:
            path = f"rclone/{user_id}/rclone.conf"
            no_path_msg = tr('helpers.text.send_a_rclone_config_file_use_files_command', _html=False)
        else:
            if is_shared_owner_upload(user_id):
                path = f"rclone/{OWNER_ID}/rclone.conf"
                no_path_msg = tr('helpers.text.the_owner_must_upload_rclone_conf_with_files_first', _html=False)
            else:
                path = "rclone/rclone_global/rclone.conf"
                no_path_msg = tr('helpers.text.rclone_config_file_not_found', _html=False)

    if ospath.exists(path):
        return True
    else:
        if isLeech:
            return True
        else:
            if show_prompt and (config_dict["MULTI_RCLONE_CONFIG"] or is_sudo_user):
                await send_rclone_config_upload_prompt(user_id, message)
            else:
                await sendMessage(no_path_msg, message)
            return False


async def send_rclone_config_upload_prompt(user_id, message):
    buttons = ButtonMaker()
    buttons.cb_buildbutton(
        tr('helpers.text.upload_rclone_conf', _html=False), f"configmenu^upload^rclone^{user_id}"
    )
    buttons.cb_buildbutton(tr('helpers.text.close_menu', _html=False), f"configmenu^close^{user_id}", "footer")
    await sendMarkup(
        tr('helpers.text.rclone_conf_not_found_upload_a_rclone_config_file_to_continue'),
        message,
        reply_markup=buttons.build_menu(1),
    )


async def get_rclone_path(user_id, message=None, *, for_upload=False):
    is_sudo_user = user_id == OWNER_ID or user_data.get(user_id, {}).get("is_sudo")

    if not for_upload and not can_manage_rclone(user_id):
        raise NotRclonePathFound(tr('helpers.text.shared_storage_is_for_uploads_only_cloud_management_is_not_allowed', _html=False))

    if config_dict["MULTI_RCLONE_CONFIG"]:
        path = f"rclone/{user_id}/rclone.conf"
    else:
        if is_sudo_user:
            path = f"rclone/{user_id}/rclone.conf"
        else:
            path = (f"rclone/{OWNER_ID}/rclone.conf" if is_shared_owner_upload(user_id)
                    else "rclone/rclone_global/rclone.conf")

    if ospath.exists(path):
        return path
    else:
        if for_upload and is_shared_owner_upload(user_id):
            raise NotRclonePathFound(tr('helpers.text.the_owner_must_upload_rclone_conf_with_files_first', _html=False))
        await sendMessage(tr('helpers.text.rclone_path_not_found', _html=False), message)
        raise NotRclonePathFound(tr('helpers.text.error_rclone_path_not_found', _html=False))


async def setRcloneFlags(cmd, type):
    cmd.extend(("--exclude", "*.{" + ",".join(GLOBAL_EXTENSION_FILTER) + "}"))
    if config_dict["SERVER_SIDE"]:
        cmd.append("--drive-server-side-across-configs")
    if type == "copy":
        if flags := config_dict.get("RCLONE_COPY_FLAGS"):
            append_flags(flags, cmd)
    elif type == "upload":
        if flags := config_dict.get("RCLONE_UPLOAD_FLAGS"):
            append_flags(flags, cmd)
    elif type == "download":
        if flags := config_dict.get("RCLONE_DOWNLOAD_FLAGS"):
            append_flags(flags, cmd)


def append_flags(flags, cmd):
    rcflags = flags.split(",")
    for flag in rcflags:
        if ":" in flag:
            key, value = flag.split(":")
            cmd.extend((key, value))
        elif len(flag) > 0:
            cmd.append(flag)


async def is_gdrive_remote(remote, config_file):
    conf = ConfigParser()
    conf.read(config_file)
    is_gdrive = False
    if conf.get(remote, "type") == "drive":
        is_gdrive = True
    elif conf.get(remote, "type") == "crypt":
        remote_path = conf.get(remote, "remote")
        real_remote = remote_path.split(":")[0]
        if conf.get(real_remote, "type") == "drive":
            is_gdrive = True
    return is_gdrive


async def list_remotes(
    message, menu_type, remote_type="remote", is_second_menu=False, edit=False
):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id
    path = await get_rclone_path(user_id, message)
    conf = ConfigParser()
    conf.read(path)
    buttons = ButtonMaker()
    for remote in conf.sections():
        prev_icon = ""
        crypt_icon = ""
        is_crypt = False
        if conf.get(remote, "type") == "crypt":
            is_crypt = True
            crypt_icon = "🔐"
        if await CustomFilters.sudo_filter("", message) and config_dict["MULTI_REMOTE_UP"]:
            if remote in remotes_multi:
                prev_icon = "✅"
            buttons.cb_buildbutton(
                f"{prev_icon} {crypt_icon} 📁 {remote}",
                f"{menu_type}^{remote_type}^{remote}^{is_crypt}^{user_id}",
            )
        else:
            buttons.cb_buildbutton(
                f"{crypt_icon} 📁 {remote}",
                f"{menu_type}^{remote_type}^{remote}^{is_crypt}^{user_id}",
            )
    if menu_type == Menus.REMOTE_SELECT:
        msg = tr('helpers.text.select_cloud_where_you_want_to_mirror_the_file', _html=False)
    if menu_type == Menus.CLEANUP:
        msg = tr('helpers.text.select_cloud_to_delete_trash', _html=False)
    elif menu_type == Menus.STORAGE:
        msg = tr('helpers.text.select_cloud_to_view_info', _html=False)
    elif menu_type == Menus.MIRROR_SELECT:
        if config_dict["MULTI_REMOTE_UP"]:
            msg = tr('helpers.text.choose_destination_clouds_for_mirror_uploads', _html=False)
            buttons.cb_buildbutton(tr('helpers.text.clear_selected', _html=False), f"{menu_type}^reset^{user_id}", "footer")
        else:
            remote = get_rclone_data("MIRROR_SELECT_REMOTE", user_id)
            base_dir = get_rclone_data("MIRROR_SELECT_BASE_DIR", user_id)
            current_path = f"{remote}:{base_dir}" if remote else tr('helpers.text.not_set', _html=False)
            msg = (
                tr('helpers.text.choose_destination_cloud_for_mirror_uploads_current', value1=current_path)
            )
    elif menu_type == Menus.SYNC:
        remote_label = tr(f"helpers.rclone.{remote_type}") if remote_type in ("source", "origin", "destination") else remote_type
        msg = tr('helpers.text.select_cloud', value1=remote_label)
        msg += tr('helpers.text.note_sync_make_source_and_destination_identical_modifying_destination_only')
    else:
        msg = tr('helpers.text.select_cloud_where_your_files_are_stored', _html=False)
    if is_second_menu:
        msg = tr('helpers.text.select_folder_where_you_want_to_copy', _html=False)
    buttons.cb_buildbutton(tr('helpers.rclone.cancel_button', _html=False), f"{menu_type}^close^{user_id}", "footer")
    if edit:
        await editMessage(msg, message, reply_markup=buttons.build_menu(2))
    else:
        await sendMarkup(msg, message, reply_markup=buttons.build_menu(2))


async def is_valid_path(remote, path, message):
    user_id = message.reply_to_message.from_user.id
    rc_path = await get_rclone_path(user_id, message)
    cmd = ["rclone", "lsjson", f"--config={rc_path}", f"{remote}:{path}"]
    process = await create_subprocess_exec(*cmd, stdout=PIPE)
    return_code = await process.wait()
    if return_code != 0:
        LOGGER.info("Error: Path not valid")
        return False
    else:
        return True


async def list_folder(
    message,
    rclone_remote,
    base_dir,
    menu_type,
    is_second_menu=False,
    is_crypt=False,
    edit=False,
):
    user_id = message.reply_to_message.from_user.id
    buttons = ButtonMaker()
    path = await get_rclone_path(user_id, message)
    msg = ""
    next_type = ""
    dir_callback = "remote_dir"
    file_callback = ""
    back_callback = "back"

    cmd = ["rclone", "lsjson", f"--config={path}", f"{rclone_remote}:{base_dir}"]

    if menu_type == Menus.LEECH:
        next_type = "next_leech"
        file_callback = "leech_file"
        try:
            cmd.extend(["--fast-list", "--no-modtime"])
            buttons.cb_buildbutton(
                tr('helpers.text.select_this_folder', _html=False), f"{menu_type}^leech_folder^{user_id}"
            )
            msg = tr('helpers.text.select_folder_or_file_that_you_want_to_leech_path', value1=rclone_remote, value2=base_dir)
        except KeyError:
            raise ValueError("Invalid key")
    elif menu_type == Menus.MIRROR_SELECT:
        rc_path = f"{rclone_remote}:{base_dir}"
        conf = ConfigParser()
        conf.read(path)
        if is_crypt:
            if (
                rclone_remote in conf.sections()
                and conf.get(rclone_remote, "type") == "crypt"
            ):
                rc_path = conf.get(rclone_remote, "remote")
                msg = (
                    tr('helpers.text.crypt_destination_path', value1=rc_path)
                )
                buttons.cb_buildbutton(tr('helpers.text.use_this_destination', _html=False), f"{menu_type}^close^{user_id}")
                buttons.cb_buildbutton(
                    tr('helpers.text.back', _html=False), f"{menu_type}^{back_callback}^{user_id}", "footer_second"
                )
                buttons.cb_buildbutton(
                    tr('helpers.rclone.cancel_button', _html=False), f"{menu_type}^close^{user_id}", "footer_third"
                )
                await editMessage(msg, message, reply_markup=buttons.build_menu(1))
                return
        else:
            next_type = "next_ms"
            cmd.extend(["--dirs-only", "--fast-list", "--no-modtime"])
            buttons.cb_buildbutton(
                tr('helpers.text.use_this_folder', _html=False), f"{menu_type}^close^{user_id}"
            )
            msg = (
                tr('helpers.text.choose_destination_folder_path', value1=rc_path)
            )
    elif menu_type == Menus.MYFILES:
        next_type = "next_myfiles"
        file_callback = "file_action"
        cmd.extend(["--fast-list", "--no-modtime"])
        buttons.cb_buildbutton(
            tr('helpers.text.folder_options', _html=False), f"{menu_type}^folder_action^{user_id}"
        )
        buttons.cb_buildbutton(tr('helpers.text.search', _html=False), f"myfilesmenu^search^{user_id}")
        msg = tr('helpers.text.your_cloud_files_are_listed_below_path', value1=rclone_remote, value2=base_dir)
    elif menu_type == Menus.COPY:
        next_type = "next_copy"
        if is_second_menu:
            file_callback = "copy"
            dir_callback = "dest_dir"
            back_callback = "back_dest"
            buttons.cb_buildbutton(
                tr('helpers.text.select_this_folder', _html=False), f"{menu_type}^copy^{user_id}"
            )
            cmd.extend(["--dirs-only", "--fast-list", "--no-modtime"])
            msg = tr('helpers.text.select_folder_where_you_want_to_copy_path', value1=rclone_remote, value2=base_dir)
        else:
            file_callback = "second_menu"
            dir_callback = "origin_dir"
            back_callback = "back_origin"
            buttons.cb_buildbutton(
                tr('helpers.text.select_this_folder', _html=False), f"{menu_type}^second_menu^_^False^{user_id}"
            )
            cmd.extend(["--fast-list", "--no-modtime"])
            msg = tr('helpers.text.select_file_or_folder_which_you_want_to_copy_path', value1=rclone_remote, value2=base_dir)

    res, err, rc = await cmd_exec(cmd)
    if rc != 0:
        await sendMessage(tr('helpers.text.error', value1=err), message)
        return

    info = jsonloads(res)
    if is_second_menu:
        sinfo = sorted(info, key=lambda x: x["Name"])
    else:
        sinfo = sorted(info, key=lambda x: x["Size"])

    total = len(info)
    update_rclone_data("info", sinfo, user_id)

    if total == 0:
        folders_only = menu_type == Menus.MIRROR_SELECT or menu_type == Menus.COPY and is_second_menu
        buttons.cb_buildbutton(tr('helpers.rclone.no_folders' if folders_only else 'helpers.text.nothing_to_show', _html=False), f"{menu_type}^pages^{user_id}")
    else:
        page, next_offset = await run_sync_to_async(rcloneListNextPage, info)

        await run_sync_to_async(
            rcloneListButtonMaker,
            info=page,
            button=buttons,
            menu_type=menu_type,
            dir_callback=dir_callback,
            file_callback=file_callback,
            user_id=user_id,
        )

        if total <= 10:
            buttons.cb_buildbutton(
                f"🗓 {round(0 / 10) + 1} / {round(total / 10)}",
                f"{menu_type}^pages^{user_id}" "footer",
            )
        else:
            buttons.cb_buildbutton(
                f"🗓 {round(0 / 10) + 1} / {round(total / 10)}",
                f"{menu_type}^pages^{user_id}" "footer",
            )
            buttons.cb_buildbutton(
                tr('helpers.text.next', _html=False),
                f"{next_type} {next_offset} {is_second_menu} {back_callback}",
                "footer",
            )

    buttons.cb_buildbutton(
        tr('helpers.text.back', _html=False), f"{menu_type}^{back_callback}^{user_id}", "footer_second"
    )
    buttons.cb_buildbutton(
        tr('helpers.rclone.cancel_button', _html=False), f"{menu_type}^close^{user_id}", "footer_third"
    )

    if edit:
        await editMessage(msg, message, reply_markup=buttons.build_menu(1))
    else:
        await sendMarkup(msg, message, reply_markup=buttons.build_menu(1))


async def create_next_buttons(
    next_offset,
    prev_offset,
    _next_offset,
    data_back_cb,
    total,
    user_id,
    buttons,
    filter,
    menu_type,
    is_second_menu=False,
):
    if next_offset == 0:
        buttons.cb_buildbutton(
            f"🗓 {round(int(next_offset) / 10) + 1} / {round(total / 10)}", 
            f"{menu_type}^pages",
            "footer",
        )
        buttons.cb_buildbutton(
            tr('helpers.text.next', _html=False),
            f"{filter} {_next_offset} {is_second_menu} {data_back_cb}",
            "footer",
        )
    elif next_offset >= total:
        buttons.cb_buildbutton(
            tr('helpers.rclone.previous_page', _html=False),
            f"{filter} {prev_offset} {is_second_menu} {data_back_cb}",
            "footer",
        )
        buttons.cb_buildbutton(
            f"🗓 {round(int(next_offset) / 10) + 1} / {round(total / 10)}",
            f"{menu_type}^pages",
            "footer",
        )
    elif next_offset + 10 > total:
        buttons.cb_buildbutton(
            tr('helpers.rclone.previous_page', _html=False),
            f"{filter} {prev_offset} {is_second_menu} {data_back_cb}",
            "footer",
        )
        buttons.cb_buildbutton(
            f"🗓 {round(int(next_offset) / 10) + 1} / {round(total / 10)}", 
            f"{menu_type}^pages",
            "footer",
        )
    else:
        buttons.cb_buildbutton(
            tr('helpers.rclone.previous_page', _html=False),
            f"{filter} {prev_offset} {is_second_menu} {data_back_cb}",
            "footer_second",
        )
        buttons.cb_buildbutton(
            f"🗓 {round(int(next_offset) / 10) + 1} / {round(total / 10)}",
            f"{menu_type}^pages" "footer",
        )
        buttons.cb_buildbutton(
            tr('helpers.text.next', _html=False),
            f"{filter} {_next_offset} {is_second_menu} {data_back_cb}",
            "footer_second",
        )
    buttons.cb_buildbutton(
        tr('helpers.text.back', _html=False), f"{menu_type}^{data_back_cb}^{user_id}", "footer_third"
    )
    buttons.cb_buildbutton(
        tr('helpers.rclone.cancel_button', _html=False), f"{menu_type}^close^{user_id}", "footer_third"
    )


async def get_id(rclone_path, config_path, name, mime_type):
    if mime_type != "Folder":
        rclone_path = f"{rclone_path.rstrip('/')}/{name}"
    cmd = [
        "rclone",
        "lsjson",
        f"--config={config_path}",
        "--stat",
        "--no-mimetype",
        "--no-modtime",
        rclone_path,
    ]

    res, err, code = await cmd_exec(cmd)
    if code != 0:
        LOGGER.error(f"Error while getting link. Error: {err}")
        return ""
    try:
        item = jsonloads(res)
    except (TypeError, ValueError):
        LOGGER.error("Invalid JSON while getting the uploaded item's ID")
        return ""
    item_id = item.get("ID") if isinstance(item, dict) else None
    if isinstance(item_id, str) and item_id and item_id != "err":
        return item_id
    LOGGER.warning("The uploaded item's ID is unavailable")
    return ""
