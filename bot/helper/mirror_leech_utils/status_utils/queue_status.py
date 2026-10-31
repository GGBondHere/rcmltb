from bot.i18n import tr, raw
from bot.helper.ext_utils.bot_utils import MirrorStatus


class QueueStatus:
    def __init__(self, listener, gid, status):
        self.__listener = listener
        self.__gid = gid
        self.__status = status
        self.message = listener.message

    def gid(self):
        return self.__gid

    def name(self):
        if self.__status == "dl":
            return tr('helpers.text.waiting_for_download', value1=self.__listener.name, _html=False)
        return tr('helpers.text.waiting_for_upload', value1=self.__listener.name, _html=False)

    def size(self):
        return ""

    def progress(self):
        return ""

    def speed(self):
        return ""

    def eta(self):
        return ""

    def status(self):
        if self.__status == "dl":
            return MirrorStatus.STATUS_QUEUEDL
        return MirrorStatus.STATUS_QUEUEUP

    def processed_bytes(self):
        return ""

    def processed_raw(self):
        return 0

    def task(self):
        return self

    async def cancel_task(self):
        await self.__listener.onDownloadError(tr('helpers.text.task_cancelled_from_queue', _html=False, _user_id=self.__listener.user_id))
