from bot.i18n import tr, raw
from asyncio import create_subprocess_exec
from asyncio.subprocess import PIPE
from random import SystemRandom
from os import path as ospath, remove as osremove, walk
from string import ascii_letters, digits
from bot import (
    GLOBAL_EXTENSION_FILTER,
    status_dict,
    status_dict_lock,
    remotes_multi,
    config_dict,
    user_data,
)
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.ext_utils.human_format import get_readable_file_size
from bot.helper.telegram_helper.message_utils import sendStatusMessage
from bot.helper.ext_utils.misc_utils import count_files_and_folders
from bot.helper.ext_utils.rclone_utils import (
    get_rclone_path,
    get_rclone_upload_target,
    is_gdrive_remote,
    setRcloneFlags,
)
from bot.helper.ext_utils.template_utils import apply_upload_template, join_upload_path
from bot.helper.ext_utils.exceptions import NotRclonePathFound
from bot.helper.mirror_leech_utils.status_utils.rclone_status import RcloneStatus
from bot.helper.mirror_leech_utils.status_utils.status_utils import MirrorStatus


class RcloneMirror:
    def __init__(self, path, name, size, user_id, listener):
        self.__path = path
        self.__listener = listener
        self.message = self.__listener.message
        self.__user_id = user_id
        self.name = name
        self.size = size
        self.process = None
        self.__is_cancelled = False
        self.status_type = MirrorStatus.STATUS_UPLOADING

    async def mirror(self):
        await self.delete_files_with_extensions()

        if ospath.isdir(self.__path):
            mime_type = "Folder"
        else:
            mime_type = "File"

        try:
            conf_path = await get_rclone_path(self.__user_id, self.message, for_upload=True)
            rc_remote, base_dir = get_rclone_upload_target(self.__user_id)
        except (NotRclonePathFound, ValueError, OSError) as error:
            await self.__listener.onUploadError(str(error))
            return
        folder_name = self.name.replace(".", "")
        is_multi_remote_up = config_dict["MULTI_REMOTE_UP"]
        is_sudo_filter = await CustomFilters.sudo_filter("", self.message)

        if config_dict["MULTI_RCLONE_CONFIG"] or is_sudo_filter:
            if is_multi_remote_up and len(remotes_multi) > 0:
                upload_remotes = tuple(remotes_multi)
                for index, rc_remote in enumerate(upload_remotes):
                    self.__listener.multi_remote_upload = index < len(upload_remotes) - 1
                    if not await self.upload(
                        self.__path,
                        conf_path,
                        mime_type,
                        rc_remote,
                        folder_name,
                    ):
                        return
                return

        await self.upload(
            self.__path, conf_path, mime_type, rc_remote, folder_name, base_dir
        )

    async def upload(
        self, path, conf_path, mime_type, remote, folder_name, base_dir=""
    ):
        if self.__is_cancelled:
            return False
        # Get user settings for template
        user_dict = user_data.get(self.__user_id, {})
        template = user_dict.get("upload_template") or config_dict.get("UPLOAD_PATH_TEMPLATE", "")

        # Apply template if configured
        if template:
            username = self.message.from_user.username or str(self.__user_id)
            category = user_dict.get("category", "")
            dynamic_path = apply_upload_template(
                template,
                self.__user_id,
                username,
                category=category,
                task_type="mirror"
            )
            try:
                base_dir = join_upload_path(base_dir, dynamic_path)
            except ValueError as error:
                await self.__listener.onUploadError(str(error))
                return False

        if mime_type == "Folder":
            self.name = folder_name
            if base_dir:
                rclone_path = f"{remote}:{base_dir}/{folder_name}".replace("//", "/")
            else:
                rclone_path = f"{remote}:/{folder_name}"
        else:
            if base_dir:
                rclone_path = f"{remote}:{base_dir}".replace("//", "/")
            else:
                rclone_path = f"{remote}:/"

        cmd = [
            "rclone",
            "copy",
            f"--config={conf_path}",
            f"{path}",
            rclone_path,
            "-P",
        ]

        is_gdrive = await is_gdrive_remote(remote, conf_path)
        await setRcloneFlags(cmd, "upload")

        if ospath.isdir(path):
            folders, files = await count_files_and_folders(path)
        else:
            if path.lower().endswith(tuple(GLOBAL_EXTENSION_FILTER)):
                await self.__listener.onUploadError(
                    tr('helpers.text.this_file_extension_is_excluded_by_extension_filter', _html=False)
                )
                return
            folders = 0
            files = 1

        gid = "".join(SystemRandom().choices(ascii_letters + digits, k=10))
        async with status_dict_lock:
            status = RcloneStatus(self, self.__listener, gid)
            status_dict[self.__listener.uid] = status
        await sendStatusMessage(self.message)

        self.process = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
        await status.start()
        return_code = await self.process.wait()
        if self.__is_cancelled:
            return
        if return_code == 0:
            size = get_readable_file_size(self.size)

            await self.__listener.onUploadComplete(
                None,
                size,
                files,
                folders,
                mime_type,
                self.name,
                rclone_config=conf_path,
                rclone_path=rclone_path,
                is_gdrive=is_gdrive,
            )
            return not self.__is_cancelled
        else:
            error = (await self.process.stderr.read()).decode().strip()
            await self.__listener.onUploadError(tr('helpers.task.backend_error', value1=error, _html=False))

    async def delete_files_with_extensions(self):
        for dirpath, _, files in walk(self.__path):
            for file in files:
                if file.lower().endswith(tuple(GLOBAL_EXTENSION_FILTER)):
                    try:
                        del_file = ospath.join(dirpath, file)
                        osremove(del_file)
                    except Exception:
                        return

    async def cancel_task(self):
        self.__is_cancelled = True
        if self.process is not None:
            try:
                self.process.kill()
            except Exception:
                pass
        await self.__listener.onUploadError(tr('helpers.text.upload_cancelled', _html=False, _user_id=self.__listener.user_id))
