from bot.i18n import tr, raw, ui_error
from asyncio.subprocess import PIPE, create_subprocess_exec as exec
from json import loads as jsonloads
from asyncio import sleep, TimeoutError
from os.path import splitext
from bot.helper.telegram_helper.message_utils import (
    editMarkup,
    editMessage,
    sendMarkup,
    sendMessage,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.misc_utils import get_readable_size
from pyrogram import filters
from bot.helper.ext_utils.rclone_utils import get_rclone_path


async def myfiles_settings(message, remote, remote_path, edit=False, is_folder=False):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id

    buttons = ButtonMaker()

    if len(remote_path) == 0:
        buttons.cb_buildbutton(tr('commands.files.folder_size', _html=False), f"myfilesmenu^size^{user_id}")
        buttons.cb_buildbutton(
            tr('commands.files.create_directory', _html=False), f"myfilesmenu^mkdir^{user_id}"
        )
        buttons.cb_buildbutton(
            tr('commands.files.delete_empty', _html=False), f"myfilesmenu^rmdir^{user_id}"
        )
        buttons.cb_buildbutton(
            tr('commands.files.delete_duplicates', _html=False), f"myfilesmenu^dedupe^{user_id}"
        )
    else:
        if is_folder:
            buttons.cb_buildbutton(
                tr('commands.files.folder_size', _html=False), f"myfilesmenu^size^{user_id}"
            )
            buttons.cb_buildbutton(
                tr('commands.files.delete_duplicates', _html=False), f"myfilesmenu^dedupe^{user_id}"
            )
            buttons.cb_buildbutton(
                tr('commands.files.delete_folder', _html=False), f"myfilesmenu^delete^folder^{user_id}"
            )
            buttons.cb_buildbutton(
                tr('commands.files.create_directory', _html=False), f"myfilesmenu^mkdir^{user_id}"
            )
            buttons.cb_buildbutton(
                tr('commands.files.delete_empty', _html=False), f"myfilesmenu^rmdir^{user_id}"
            )
        else:
            buttons.cb_buildbutton(tr('commands.files.rename', _html=False), f"myfilesmenu^rename^file^{user_id}")
            buttons.cb_buildbutton(tr('commands.files.delete', _html=False), f"myfilesmenu^delete^file^{user_id}")

    buttons.cb_buildbutton(
        tr('commands.button.back_arrow', _html=False), f"myfilesmenu^back_remotes_menu^{user_id}", "footer"
    )
    buttons.cb_buildbutton(tr('commands.button.close_menu', _html=False), f"myfilesmenu^close^{user_id}", "footer")

    msg = tr('commands.files.path', remote=remote, remote_path=remote_path)

    if edit:
        await editMessage(msg, message, reply_markup=buttons.build_menu(2))
    else:
        await sendMarkup(msg, message, reply_markup=buttons.build_menu(2))


async def calculate_size(message, remote_path, remote, user_id):
    buttons = ButtonMaker()
    path = await get_rclone_path(user_id, message)
    data = await rclone_size(message, remote_path, remote, path)
    if data is not None:
        total_size = get_readable_size(data[1])
        msg = tr('commands.files.size', files=data[0], total_size=total_size)
        buttons.cb_buildbutton(
            tr('commands.button.back_arrow', _html=False), f"myfilesmenu^back_remotes_menu^{user_id}", "footer"
        )
        buttons.cb_buildbutton(tr('commands.button.close_menu', _html=False), f"myfilesmenu^close^{user_id}", "footer")
        await editMessage(msg, message, reply_markup=buttons.build_menu(1))


async def search_action(client, message, query, remote, user_id):
    conf_path = await get_rclone_path(user_id, message)
    question = await sendMessage(tr('commands.files.search_name'), message)
    try:
        response = await client.listen.Message(
            filters.text, id=filters.user(user_id), timeout=60
        )
    except TimeoutError:
        await sendMessage(tr('commands.files.timeout'), message)
    else:
        if response:
            text = response.text
            try:
                if "/ignore" in text:
                    await client.listen.Cancel(filters.user(user_id))
                else:
                    search_msg = await sendMessage(
                        tr('commands.files.searching'),
                        question,
                    )
                    conf_path = await get_rclone_path(user_id, message)
                    cmd = [
                        "rclone",
                        "lsjson",
                        "--files-only",
                        "--fast-list",
                        "--no-modtime",
                        "--ignore-case",
                        "-R",
                        f"--config={conf_path}",
                        "--include",
                        f"*{text}*",
                        f"{remote}:",
                    ]
                    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
                    out, err = await process.communicate()
                    out = out.decode().strip()
                    return_code = await process.wait()
                    if return_code != 0:
                        err = err.decode().strip()
                        await sendMessage(tr('commands.error.detail', err=err), message)
                        return
                    if len(out) > 0:
                        data = jsonloads(out)
                        msg = tr('commands.files.found', files=len(data))
                        for index, file in enumerate(data, start=1):
                            name = file["Name"]
                            path = file["Path"]
                            cmd = [
                                "rclone",
                                "link",
                                f"--config={conf_path}",
                                f"{remote}:{path}",
                            ]
                            process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
                            out, err = await process.communicate()
                            link = out.decode().strip()
                            return_code = await process.wait()
                            if return_code == 0:
                                msg += tr('commands.files.result_link', index=index, link=link, name=name)
                            else:
                                msg += tr('commands.files.result_name', index=index, name=name)
                            await sleep(0.5)
                        await search_msg.delete()
                        await sendMessage(msg, message)
                    else:
                        await sendMessage(tr('commands.files.no_results'), message)
            except Exception as ex:
                await sendMessage(ui_error(ex), message)
    finally:
        await question.delete()


async def delete_selection(message, user_id, is_folder=False):
    buttons = ButtonMaker()
    msg = ""
    if is_folder:
        buttons.cb_buildbutton(tr('commands.files.yes', _html=False), f"myfilesmenu^yes^folder^{user_id}")
        buttons.cb_buildbutton(tr('commands.files.no', _html=False), f"myfilesmenu^no^folder^{user_id}")
        msg += tr('commands.files.confirm_delete_folder')
    else:
        buttons.cb_buildbutton(tr('commands.files.yes', _html=False), f"myfilesmenu^yes^file^{user_id}")
        buttons.cb_buildbutton(tr('commands.files.no', _html=False), f"myfilesmenu^no^file^{user_id}")
        msg += tr('commands.files.confirm_delete_file')
    await editMessage(msg, message, reply_markup=buttons.build_menu(2))


async def delete_selected(message, user_id, remote_path, remote, is_folder=False):
    buttons = ButtonMaker()
    msg = ""
    conf_path = await get_rclone_path(user_id, message)
    if is_folder:
        await rclone_purge(message, remote_path, remote, conf_path)
        msg += tr('commands.files.folder_deleted')
    else:
        await rclone_delete(message, remote_path, remote, conf_path)
        msg += tr('commands.files.file_deleted')
    buttons.cb_buildbutton(
        tr('commands.button.back_arrow', _html=False), f"myfilesmenu^back_remotes_menu^{user_id}", "footer"
    )
    buttons.cb_buildbutton(tr('commands.button.close_menu', _html=False), f"myfilesmenu^close^{user_id}", "footer")
    await editMessage(msg, message, reply_markup=buttons.build_menu(1))


async def delete_empty_dir(message, user_id, remote, remote_path):
    buttons = ButtonMaker()
    conf_path = await get_rclone_path(user_id, message)
    await rclone_rmdirs(message, remote, remote_path, conf_path)
    buttons.cb_buildbutton(
        tr('commands.button.back_arrow', _html=False), f"myfilesmenu^back_remotes_menu^{user_id}", "footer"
    )
    buttons.cb_buildbutton(tr('commands.button.close_menu', _html=False), f"myfilesmenu^close^{user_id}", "footer")
    msg = tr('commands.files.directories_deleted')
    await editMessage(msg, message, reply_markup=buttons.build_menu(1))


async def rclone_size(message, remote_path, remote, conf_path):
    await editMessage(
        tr('commands.files.calculating_size'),
        message,
    )
    cmd = [
        "rclone",
        "size",
        "--fast-list",
        f"--config={conf_path}",
        f"{remote}:{remote_path}",
        "--json",
    ]
    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()
    stdout = stdout.decode().strip()
    return_code = await process.wait()
    if return_code != 0:
        err = stderr.decode().strip()
        await sendMessage(tr('commands.error.detail', err=err), message)
        return
    data = jsonloads(stdout)
    files = data["count"]
    size = data["bytes"]
    return (files, size)


async def rclone_purge(message, remote_path, remote, conf_path):
    cmd = ["rclone", "purge", f"--config={conf_path}", f"{remote}:{remote_path}"]
    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()
    stdout = stdout.decode().strip()
    return_code = await process.wait()
    if return_code != 0:
        err = stderr.decode().strip()
        await sendMessage(tr('commands.error.detail', err=err), message)


async def rclone_delete(message, remote_path, remote, conf_path):
    cmd = ["rclone", "delete", f"--config={conf_path}", f"{remote}:{remote_path}"]
    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()
    stdout = stdout.decode().strip()
    return_code = await process.wait()
    if return_code != 0:
        err = stderr.decode().strip()
        await sendMessage(tr('commands.error.detail', err=err), message)


async def rclone_rmdirs(message, remote, remote_path, conf_path):
    await editMessage(
        tr('commands.files.removing_empty'),
        message,
    )
    cmd = ["rclone", "rmdirs", f"--config={conf_path}", f"{remote}:{remote_path}"]
    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()
    stdout = stdout.decode().strip()
    return_code = await process.wait()
    if return_code != 0:
        err = stderr.decode().strip()
        await sendMessage(tr('commands.error.detail', err=err), message)


async def rclone_mkdir(client, message, remote, remote_path, tag):
    user_id = message.reply_to_message.from_user.id
    conf_path = await get_rclone_path(user_id, message)
    question = await sendMessage(tr('commands.files.directory_name'), message)
    try:
        response = await client.listen.Message(
            filters.text, id=filters.user(user_id), timeout=60
        )
    except TimeoutError:
        await sendMessage(tr('commands.batch.timeout'), message)
    else:
        if response:
            try:
                if "/ignore" in response.text:
                    await client.listen.Cancel(filters.user(user_id))
                else:
                    edit_mgs = await sendMessage(tr('commands.files.creating_directory'), message)
                    path = f"{remote_path}/{response.text}"
                    cmd = [
                        "rclone",
                        "mkdir",
                        f"--config={conf_path}",
                        f"{remote}:{path}",
                    ]
                    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
                    stdout, stderr = await process.communicate()
                    stdout = stdout.decode().strip()
                    return_code = await process.wait()
                    if return_code != 0:
                        err = stderr.decode().strip()
                        await sendMessage(tr('commands.error.detail', err=err), message)
                    else:
                        msg = tr('commands.files.directory_created')
                        msg += tr('commands.files.created_path', remote=remote, path=path)
                        msg += tr('commands.files.mention', tag=raw(tag))
                        await editMessage(msg, edit_mgs)
            except Exception as ex:
                await sendMessage(ui_error(ex), message)
    finally:
        await question.delete()


async def rclone_dedupe(message, remote, remote_path, user_id, tag):
    msg = tr('commands.files.dedupe_progress')
    msg += tr('commands.files.dedupe_wait')
    edit_msg = await editMessage(msg, message)
    conf_path = await get_rclone_path(user_id, message)
    cmd = [
        "rclone",
        "dedupe",
        "newest",
        "--tpslimit",
        "4",
        "--transfers",
        "1",
        "--fast-list",
        f"--config={conf_path}",
        f"{remote}:{remote_path}",
    ]
    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
    stdout, stderr = await process.communicate()
    stdout = stdout.decode().strip()
    return_code = await process.wait()
    if return_code != 0:
        err = stderr.decode().strip()
        await sendMessage(tr('commands.error.detail', err=err), message)
    else:
        msg = tr('commands.files.dedupe_complete')
        msg += tr('commands.files.dedupe_mention', tag=raw(tag))
        button = ButtonMaker()
        button.cb_buildbutton(
            tr('commands.button.back_arrow', _html=False), f"myfilesmenu^back_remotes_menu^{user_id}", "footer"
        )
        await editMarkup(msg, edit_msg, reply_markup=button.build_menu(1))


async def rclone_rename(client, message, remote, remote_path, tag):
    user_id = message.reply_to_message.from_user.id
    conf_path = await get_rclone_path(user_id, message)
    question = await sendMessage(tr('commands.files.new_name'), message)
    try:
        response = await client.listen.Message(
            filters.text, id=filters.user(user_id), timeout=60
        )
    except TimeoutError:
        await sendMessage(tr('commands.files.timeout'), message)
    else:
        if response:
            try:
                if "/ignore" in response.text:
                    await client.listen.Cancel(filters.user(user_id))
                else:
                    new_name = response.text
                    edit_msg = await sendMessage(tr('commands.files.renaming'), message)
                    list_base = remote_path.split("/")
                    if len(list_base) > 1:
                        dest = list_base[:-1]
                        dest = "/".join(dest)
                        file = list_base[-1]
                        _, ext = splitext(file)
                        path = f"{dest}/{new_name}{ext}"
                    else:
                        file = list_base[0]
                        _, ext = splitext(file)
                        path = f"{new_name}{ext}"
                    cmd = [
                        "rclone",
                        "moveto",
                        f"--config={conf_path}",
                        f"{remote}:{remote_path}",
                        f"{remote}:{path}",
                    ]
                    process = await exec(*cmd, stdout=PIPE, stderr=PIPE)
                    stdout, stderr = await process.communicate()
                    stdout = stdout.decode().strip()
                    return_code = await process.wait()
                    if return_code != 0:
                        err = stderr.decode().strip()
                        await sendMessage(tr('commands.error.detail', err=err), message)
                    else:
                        msg = tr('commands.files.renamed')
                        msg += (
                            tr('commands.files.old_path', remote=remote, remote_path=remote_path)
                        )
                        msg += tr('commands.files.new_path', remote=remote, path=path)
                        msg += tr('commands.files.rename_mention', tag=raw(tag))
                        await editMessage(msg, edit_msg)
            except Exception as ex:
                await sendMessage(ui_error(ex), message)
    finally:
        await question.delete()
