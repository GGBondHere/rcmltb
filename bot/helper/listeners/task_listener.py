from bot.i18n import tr, raw, task_locale, error_detail
from html import escape
from inspect import iscoroutine
from json import loads as jsonloads
from os import path as ospath, remove as osremove, walk

from aiofiles.os import listdir, makedirs
from asyncio import create_subprocess_exec, sleep
from aioshutil import move
from requests import utils as rutils

from bot import (
    LOGGER,
    status_dict,
    status_dict_lock,
    user_data,
    config_dict,
)
from bot.core.telegram_manager import TgClient
from bot.core.torrent_manager import TorrentManager
from bot.helper.common import TaskConfig
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.human_format import (
    get_readable_file_size,
    human_readable_bytes,
)
from bot.helper.telegram_helper.message_utils import (
    delete_all_messages,
    sendMarkup,
    sendMessage,
    update_all_messages,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.files_utils import (
    clean_download,
    clean_target,
    get_path_size,
    split_file,
)
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.ext_utils.rclone_utils import get_id
from bot.helper.mirror_leech_utils.status_utils.tg_upload_status import TgUploadStatus
from bot.helper.mirror_leech_utils.upload_utils.rclone_mirror import RcloneMirror
from bot.helper.mirror_leech_utils.upload_utils.telegram_uploader import (
    TelegramUploader,
)


class TaskListener(TaskConfig):
    def __init__(
        self,
        message,
        tag,
        user_id,
        compress=None,
        extract=None,
        select=False,
        seed=False,
        isLeech=False,
        screenshots=False,
        sameDir={},
    ):
        super().__init__()
        self.message = message
        self.tag = tag
        self.uid = message.id
        self.user_id = user_id
        self.compress = compress
        self.extract = extract
        self.sameDir = sameDir
        self.isLeech = isLeech
        self.seed = seed
        self.select = select
        self.screenshots = screenshots
        self.dir = f"{config_dict['DOWNLOAD_DIR']}{self.uid}"
        self.newDir = ""
        self.isSuperGroup = message.chat.type.name in ["SUPERGROUP", "CHANNEL"]
        self.suproc = None
        self.user_dict = user_data.get(self.user_id, {})

    async def onDownloadStart(self):
        pass

    @task_locale
    async def onDownloadComplete(self):
        # Check for queued tasks when download completes
        from bot.helper.ext_utils.task_manager import start_from_queued
        await start_from_queued()

        multi_links = False
        while True:
            if self.sameDir:
                if (
                    self.sameDir["total"] in [1, 0]
                    or self.sameDir["total"] > 1
                    and len(self.sameDir["tasks"]) > 1
                ):
                    break
            else:
                break
            await sleep(0.2)

        async with status_dict_lock:
            if self.sameDir and self.sameDir["total"] > 1:
                self.sameDir["tasks"].remove(self.uid)
                self.sameDir["total"] -= 1
                folder_name = self.sameDir["name"]
                spath = f"{self.dir}/{folder_name}"
                des_path = (
                    f"{config_dict['DOWNLOAD_DIR']}{list(self.sameDir['tasks'])[0]}/{folder_name}"
                )
                await makedirs(des_path, exist_ok=True)
                for item in await listdir(spath):
                    if item.endswith((".aria2", ".!qB")):
                        continue
                    item_path = f"{self.dir}/{folder_name}/{item}"
                    if item in await listdir(des_path):
                        await move(item_path, f"{des_path}/{self.uid}-{item}")
                    else:
                        await move(item_path, f"{des_path}/{item}")
                multi_links = True
            download = status_dict[self.uid]
            name = str(download.name()).replace("/", "")
            gid_attr = download.gid
            if callable(gid_attr):
                gid_result = gid_attr()
                gid = await gid_result if iscoroutine(gid_result) else gid_result
            else:
                gid = gid_attr

        if not config_dict["NO_TASKS_LOGS"]:
            LOGGER.info(f"Download completed: {name}")

        if multi_links:
            await self.onUploadError(tr('helpers.text.downloaded_waiting_for_other_tasks', _html=False))
            return

        if name == "None" or not ospath.exists(f"{self.dir}/{name}"):
            try:
                files = await listdir(self.dir)
            except Exception as e:
                await self.onUploadError(str(e))
                return
            name = files[-1]
            if name == "yt-dlp-thumb":
                name = files[0]

        path = ""
        m_path = f"{self.dir}/{name}"
        size = await get_path_size(m_path)
        user_dict = user_data.get(self.message.from_user.id, {})

        if self.compress is not None:
            pswd = self.compress
            if self.seed and self.isLeech:
                self.newDir = f"{self.dir}10000"
                path = f"{self.newDir}/{name}.zip"
            else:
                path = f"{m_path}.zip"
            async with status_dict_lock:
                from bot.helper.mirror_leech_utils.status_utils.zip_status import ZipStatus
                status_dict[self.uid] = ZipStatus(name, size, gid, self)
            LEECH_SPLIT_SIZE = (
                user_dict.get("split_size", False) or config_dict["LEECH_SPLIT_SIZE"]
            )
            if pswd:
                if self.isLeech and int(size) > LEECH_SPLIT_SIZE:
                    cmd = [
                        "7z",
                        f"-v{LEECH_SPLIT_SIZE}b",
                        "a",
                        "-mx=0",
                        f"-p{pswd}",
                        path,
                        m_path,
                    ]
                else:
                    cmd = ["7z", "a", "-mx=0", f"-p{pswd}", path, m_path]
            elif self.isLeech and int(size) > LEECH_SPLIT_SIZE:
                cmd = ["7z", f"-v{LEECH_SPLIT_SIZE}b", "a", "-mx=0", path, m_path]
            else:
                cmd = ["7z", "a", "-mx=0", path, m_path]
            self.suproc = await create_subprocess_exec(*cmd)
            await self.suproc.wait()
            if self.suproc.returncode == -9:
                return
            elif not self.seed:
                await clean_target(m_path)

        if self.extract is not None:
            pswd = self.extract
            try:
                from bot.helper.ext_utils.files_utils import (
                    get_base_name,
                    is_archive,
                    is_archive_split,
                    is_first_archive_split,
                )

                if ospath.isfile(m_path):
                    path = get_base_name(m_path)
                if not config_dict["NO_TASKS_LOGS"]:
                    LOGGER.info(f"Extracting: {name}")
                async with status_dict_lock:
                    from bot.helper.mirror_leech_utils.status_utils.extract_status import ExtractStatus
                    status_dict[self.uid] = ExtractStatus(name, size, gid, self)
                if ospath.isdir(m_path):
                    if self.seed:
                        self.newDir = f"{self.dir}10000"
                        path = f"{self.newDir}/{name}"
                    else:
                        path = m_path
                    for dirpath, _, files in walk(m_path, topdown=False):
                        for file in files:
                            if (
                                is_first_archive_split(file)
                                or is_archive(file)
                                and not file.endswith(".rar")
                            ):
                                f_path = ospath.join(dirpath, file)
                                if self.seed:
                                    t_path = dirpath.replace(self.dir, self.newDir)
                                else:
                                    t_path = dirpath
                                if pswd:
                                    cmd = [
                                        "7z",
                                        "x",
                                        f"-p{pswd}",
                                        f_path,
                                        f"-o{t_path}",
                                        "-aot",
                                        "-xr!@PaxHeader",
                                    ]
                                else:
                                    cmd = [
                                        "7z",
                                        "x",
                                        f_path,
                                        f"-o{t_path}",
                                        "-aot",
                                        "-xr!@PaxHeader",
                                    ]
                                self.suproc = await create_subprocess_exec(*cmd)
                                await self.suproc.wait()
                                if self.suproc.returncode == -9:
                                    return
                                elif self.suproc.returncode != 0:
                                    LOGGER.error("Unable to extract archive splits!")
                        if (
                            not self.seed
                            and self.suproc is not None
                            and self.suproc.returncode == 0
                        ):
                            for file_ in files:
                                if is_archive_split(file_) or is_archive(file_):
                                    del_path = ospath.join(dirpath, file_)
                                    try:
                                        osremove(del_path)
                                    except Exception:
                                        return
                else:
                    if self.seed and self.isLeech:
                        self.newDir = f"{self.dir}10000"
                        path = path.replace(self.dir, self.newDir)
                    if pswd:
                        cmd = [
                            "7z",
                            "x",
                            f"-p{pswd}",
                            m_path,
                            f"-o{path}",
                            "-aot",
                            "-xr!@PaxHeader",
                        ]
                    else:
                        cmd = ["7z", "x", m_path, f"-o{path}", "-aot", "-xr!@PaxHeader"]
                    self.suproc = await create_subprocess_exec(*cmd)
                    await self.suproc.wait()
                    if self.suproc.returncode == -9:
                        return
                    elif self.suproc.returncode == 0:
                        LOGGER.info(f"Extracted Path: {path}")
                        if not self.seed:
                            try:
                                osremove(m_path)
                            except Exception:
                                return
                    else:
                        LOGGER.error("Unable to extract archive! Uploading anyway")
                        self.newDir = ""
                        path = m_path
            except Exception:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                self.newDir = ""
                path = m_path

        if self.compress is None and self.extract is None:
            path = m_path

        LOGGER.info(f"OnDownloadComplete: {path}")

        up_dir, up_name = path.rsplit("/", 1)
        size = await get_path_size(up_dir)

        # Apply name substitution to upload name
        from bot.helper.ext_utils.misc_utils import apply_name_substitute
        name_sub = self.user_dict.get("name_sub") or config_dict.get("NAME_SUBSTITUTE", "")
        if name_sub:
            up_name = apply_name_substitute(up_name, name_sub)
            # Rename the file/folder if needed
            new_path = f"{up_dir}/{up_name}"
            if new_path != path and await aiopath.exists(path):
                from aiofiles.os import rename
                await rename(path, new_path)
                path = new_path

        # Check queue limits for uploads
        is_queued, event = await check_running_tasks(self, state="up")
        if is_queued:
            from bot.helper.telegram_helper.message_utils import sendMessage
            await sendMessage(
                tr('helpers.text.your_task_has_been_added_to_the_upload_queue'),
                self.message
            )
            if event:
                await event.wait()

        if self.isLeech:
            m_size = []
            o_files = []
            if self.compress is None:
                checked = False
                LEECH_SPLIT_SIZE = (
                    user_dict.get("split_size", False)
                    or config_dict["LEECH_SPLIT_SIZE"]
                )
                for dirpath, _, files in walk(up_dir, topdown=False):
                    for file_ in files:
                        f_path = ospath.join(dirpath, file_)
                        f_size = ospath.getsize(f_path)
                        if f_size > LEECH_SPLIT_SIZE:
                            if self.user_transmission:
                                max_split = TgClient.MAX_SPLIT_SIZE
                            else:
                                from bot import TG_MAX_SPLIT_SIZE
                                max_split = TG_MAX_SPLIT_SIZE
                            if not checked:
                                checked = True
                                async with status_dict_lock:
                                    from bot.helper.mirror_leech_utils.status_utils.split_status import SplitStatus
                                    status_dict[self.uid] = SplitStatus(
                                        up_name, f_size, gid, self
                                    )
                                LOGGER.info(f"Splitting: {up_name}")
                            res = await split_file(
                                f_path, f_size, file_, dirpath, LEECH_SPLIT_SIZE, self
                            )
                            if not res:
                                return
                            if res == "errored":
                                if f_size <= max_split:
                                    continue
                                else:
                                    try:
                                        osremove(f_path)
                                    except Exception:
                                        return
                            elif not self.seed or self.newDir:
                                try:
                                    osremove(f_path)
                                except Exception:
                                    return
                            else:
                                m_size.append(f_size)
                                o_files.append(file_)

            size = await get_path_size(up_dir)
            for s in m_size:
                size = size - s

            if not config_dict["NO_TASKS_LOGS"]:
                LOGGER.info(f"Leech Name: {up_name}")

            tg_up = TelegramUploader(up_dir, up_name, size, self)
            async with status_dict_lock:
                status_dict[self.uid] = TgUploadStatus(tg_up, size, gid, self)
            await update_all_messages()
            await tg_up.upload()
        else:
            if config_dict["LOCAL_MIRROR"]:
                size = get_readable_file_size(size)
                msg = tr('helpers.text.name', value1=raw(escape(name)))
                msg += tr('helpers.task.local_size', value1=size)
                msg += tr('helpers.task.local_initiator', value1=raw(self.tag))
                await sendMessage(msg, self.message)

                async with status_dict_lock:
                    if self.uid in status_dict.keys():
                        del status_dict[self.uid]
                    count = len(status_dict)

                if count == 0:
                    await self.clean()
                else:
                    await update_all_messages()
            else:
                size = await get_path_size(path)

                if not config_dict["NO_TASKS_LOGS"]:
                    LOGGER.info(f"Upload Name: {up_name}")

                rcm = RcloneMirror(path, up_name, size, self.user_id, self)
                await rcm.mirror()

    async def _get_cloud_link(
        self, rclone_config, rclone_path, name, mime_type, is_gdrive, link=None
    ):
        from urllib.parse import quote, urlsplit

        try:
            if is_gdrive and rclone_path:
                file_id = await get_id(rclone_path, rclone_config, name, mime_type)
                if not file_id or file_id == "err":
                    return ""
                file_id = quote(file_id, safe="")
                if mime_type == "Folder":
                    link = f"https://drive.google.com/drive/folders/{file_id}"
                else:
                    link = f"https://drive.google.com/uc?id={file_id}&export=download"
            elif not is_gdrive and rclone_path:
                target = (
                    rclone_path if mime_type == "Folder"
                    else f"{rclone_path.rstrip('/')}/{name}"
                )
                out, err, code = await cmd_exec(
                    ["rclone", "link", f"--config={rclone_config}", target]
                )
                if code != 0:
                    LOGGER.warning("Could not generate the cloud link: %s", err)
                    return ""
                # rclone may print informational lines before the final URL.
                link = out.strip().splitlines()[-1] if out.strip() else ""

            if not isinstance(link, str):
                return ""
            link = link.strip()
            parsed = urlsplit(link)
            # Accessing port also validates malformed or out-of-range ports.
            parsed.port
            if (
                parsed.scheme in ("http", "https") and parsed.hostname
                and not parsed.username and not parsed.password
                and not any(
                    char.isspace() or ord(char) < 32 or ord(char) == 127
                    or char in '<>"\\' for char in link
                )
            ):
                return link
            LOGGER.warning("The cloud link is empty or is not a valid HTTP(S) URL")
        except Exception as error:
            LOGGER.warning("Could not generate the cloud link: %s", error)
        return ""

    async def _send_rclone_completion(self, msg, rclone_path, reply_markup):
        if not rclone_path:
            await sendMessage(msg, self.message, reply_markup)
            return

        saved_dir = f"{rclone_path.rstrip('/')}/"
        location = tr("helpers.task.saved_to", path=saved_dir)
        if len((msg + location).encode("utf-16-le")) <= 7800:
            await sendMessage(msg + location, self.message, reply_markup)
            return

        # Keep the complete path without making the success message too long.
        await sendMessage(msg, self.message, reply_markup)
        for offset in range(0, len(saved_dir), 500):
            await sendMessage(
                tr("helpers.task.saved_to", path=saved_dir[offset:offset + 500]),
                self.message,
            )

    @task_locale
    async def onRcloneCopyComplete(self, rc_config, rclone_path, folder_name, is_gdrive):
        async with status_dict_lock:
            if self.uid in status_dict.keys():
                del status_dict[self.uid]
            count = len(status_dict)

        button = ButtonMaker()

        cmd = [
            "rclone",
            "size",
            f"--config={rc_config}",
            "--json",
            rclone_path,
        ]
        out, err, rc = await cmd_exec(cmd)
        if rc == 0:
            data = jsonloads(out)
        else:
            await sendMessage(tr('helpers.text.error', value1=err), self.message)
            return

        msg = tr('helpers.text.total_files', value1=data['count'])
        size = human_readable_bytes(data['bytes'])
        msg += tr('helpers.text.total_size', value1=size)
        msg += tr('helpers.text.cc', value1=raw(self.tag))

        link = await self._get_cloud_link(
            rc_config, rclone_path, folder_name, "Folder", is_gdrive
        )
        if link:
            button.url_buildbutton(tr('helpers.text.cloud_link', _html=False), link)
        msg += tr("helpers.task.cloud_link_access" if link else "helpers.task.cloud_link_unavailable")

        await self._send_rclone_completion(
            msg, rclone_path, button.build_menu(1) if link else None
        )

        await clean_download(self.dir)
        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

    @task_locale
    async def onRcloneSyncComplete(self, msg):
        async with status_dict_lock:
            if self.uid in status_dict.keys():
                del status_dict[self.uid]
            count = len(status_dict)

        await sendMessage(msg, self.message)

        await clean_download(self.dir)

        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

    @task_locale
    async def onUploadComplete(
        self,
        link,
        size,
        files,
        folders,
        mime_type,
        name,
        rclone_config="",
        rclone_path="",
        is_gdrive=False,
        dir_id="",
        private=False,
    ):
        self.upload_succeeded = True
        msg = tr('helpers.text.name', value1=raw(escape(name)))
        msg += tr('helpers.text.size', value1=size)

        if self.isLeech:
            msg += tr('helpers.task.completed_total_files', value1=folders)
            if mime_type != 0:
                msg += tr('helpers.text.corrupted_files', value1=mime_type)
            msg += tr('helpers.task.leech_initiator', value1=raw(self.tag))
            if not files:
                await sendMessage(msg, self.message)
            else:
                fmsg = ""
                for index, (link, name) in enumerate(files.items(), start=1):
                    fmsg += f"{index}. <a href='{link}'>{name}</a>\n"
                    if len(fmsg.encode() + msg.encode()) > 4000:
                        await sendMessage(msg + fmsg, self.message)
                        await sleep(1)
                        fmsg = ""
                if fmsg != "":
                    await sendMessage(msg + fmsg, self.message)
            if self.seed:
                if getattr(self, "multi_remote_upload", False):
                    return
                if self.newDir:
                    await clean_target(self.newDir)
                return
        else:
            mime_label = tr("common.folder") if mime_type == "Folder" else tr("common.file") if mime_type == "File" else mime_type
            msg += tr('helpers.text.type', value1=mime_label)
            if mime_type == "Folder":
                msg += tr('helpers.text.subfolders', value1=folders)
                msg += tr('helpers.text.files', value1=files)

            buttons = ButtonMaker()

            link = await self._get_cloud_link(
                rclone_config, rclone_path, name, mime_type, is_gdrive, link
            )
            if link:
                buttons.url_buildbutton(tr('helpers.text.cloud_link', _html=False), link)
            has_buttons = bool(link)

            if is_gdrive or not rclone_path and dir_id:
                GD_INDEX_URL = ""
                if private:
                    GD_INDEX_URL = (
                        self.user_dict["index_url"]
                        if self.user_dict.get("index_url")
                        else ""
                    )
                elif config_dict["GD_INDEX_URL"]:
                    GD_INDEX_URL = config_dict["GD_INDEX_URL"]
                if GD_INDEX_URL:
                    has_buttons = True
                    share_url = f"{GD_INDEX_URL}findpath?id={dir_id}"
                    buttons.url_buildbutton(tr('helpers.text.index_link', _html=False), share_url)
                    if mime_type.startswith(("image", "video", "audio")):
                        share_urls = f"{GD_INDEX_URL}findpath?id={dir_id}&?a=view"
                        buttons.url_buildbutton(tr('helpers.text.view_link', _html=False), share_urls)
            elif (
                rclone_path
                and (RC_INDEX_URL := config_dict["RC_INDEX_URL"])
                and not private
            ):
                RC_INDEX_PORT = config_dict["RC_INDEX_PORT"]
                remote, path = rclone_path.split(":", 1)
                url_path = rutils.quote(f"{path}")
                share_url = f"{RC_INDEX_URL}:{RC_INDEX_PORT}/[{remote}:]{url_path}"
                if mime_type == "Folder":
                    share_url += "/"
                buttons.url_buildbutton(tr('helpers.text.rclone_link', _html=False), share_url)
                has_buttons = True

            msg += tr('helpers.task.mirror_initiator', value1=raw(self.tag))
            msg += tr("helpers.task.cloud_link_access" if link else "helpers.task.cloud_link_unavailable")
            await self._send_rclone_completion(
                msg, rclone_path, buttons.build_menu(1) if has_buttons else None
            )

            if self.seed:
                if getattr(self, "multi_remote_upload", False):
                    return
                if self.newDir:
                    await clean_target(self.newDir)
                elif self.compress:
                    await clean_target(f"{self.dir}/{name}")
                return

        if not getattr(self, "multi_remote_upload", False):
            await clean_download(self.dir)

        async with status_dict_lock:
            if self.uid in status_dict.keys():
                del status_dict[self.uid]
            count = len(status_dict)

        # Check for queued tasks when upload completes
        from bot.helper.ext_utils.task_manager import start_from_queued
        await start_from_queued()

        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

    @task_locale
    async def onDownloadError(self, error, button=None):
        self.upload_succeeded = False
        async with status_dict_lock:
            if self.uid in status_dict.keys():
                del status_dict[self.uid]
            count = len(status_dict)

        if self.sameDir and self.uid in self.sameDir["tasks"]:
            self.sameDir["tasks"].remove(self.uid)
            self.sameDir["total"] -= 1

        msg = tr('helpers.text.download_stopped_due_to', value1=raw(self.tag), value2=error_detail(error))
        if button:
            await sendMarkup(msg, self.message, button)
        else:
            await sendMessage(msg, self.message)

        if count == 0:
            await self.clean()
        else:
            await update_all_messages()

    @task_locale
    async def onUploadError(self, error):
        self.upload_succeeded = False
        async with status_dict_lock:
            if self.uid in status_dict.keys():
                del status_dict[self.uid]
            count = len(status_dict)

        await sendMessage(tr("helpers.task.upload_error", tag=raw(self.tag), error=error_detail(error)), self.message)

        if count == 0:
            await self.clean()
        else:
            await update_all_messages()
