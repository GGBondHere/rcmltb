from bot.i18n import tr, raw, ui_error
from time import time
from asyncio import sleep
from os import path as ospath, remove as osremove
from aioqbt.api import AddFormBuilder

from bot import (
    status_dict,
    status_dict_lock,
    config_dict,
    LOGGER,
)
from bot.core.torrent_manager import TorrentManager
from bot.helper.telegram_helper.message_utils import (
    deleteMessage,
    sendMarkup,
    sendMessage,
    sendStatusMessage,
)
from bot.helper.ext_utils.misc_utils import bt_selection_buttons
from bot.helper.mirror_leech_utils.status_utils.qbit_status import QbitTorrentStatus


async def add_qb_torrent(link, path, listener, ratio, seed_time):
    ADD_TIME = time()
    try:
        form = AddFormBuilder.with_client(TorrentManager.qbittorrent)
        if ospath.exists(link):
            with open(link, "rb") as f:
                data = f.read()
            form = form.include_file(data)
        else:
            form = form.include_url(link)
        form = form.savepath(path).tags([f"{listener.uid}"])
        if ratio:
            form = form.ratio_limit(ratio)
        if seed_time:
            form = form.seeding_time_limit(int(seed_time))
        try:
            await TorrentManager.qbittorrent.torrents.add(form.build())
        except Exception as e:
            LOGGER.error(
                f"{e}. {listener.uid}. Already added torrent or unsupported link/file type!"
            )
            await sendMessage(
                tr('helpers.text.already_added_torrent_or_unsupported_link_file_type', value1=e, value2=listener.uid, _html=False),
                listener.message,
            )
            return

        tor_info = await TorrentManager.qbittorrent.torrents.info(tag=f"{listener.uid}")
        if len(tor_info) == 0:
            while True:
                tor_info = await TorrentManager.qbittorrent.torrents.info(
                    tag=f"{listener.uid}"
                )
                if len(tor_info) > 0:
                    break
                elif time() - ADD_TIME >= 120:
                    msg = tr('helpers.text.not_added_check_if_the_link_is_valid_or_not_if_it', _html=False)
                    await sendMessage(msg, listener.message)
                    return
                await sleep(1)

        tor_info = tor_info[0]
        ext_hash = tor_info.hash

        async with status_dict_lock:
            status_dict[listener.uid] = QbitTorrentStatus(listener)

        from bot.helper.listeners.qbit_listener import onDownloadStart

        await onDownloadStart(f"{listener.uid}")

        if not config_dict["NO_TASKS_LOGS"]:
            LOGGER.info(f"QbitDownload started: {tor_info.name} - Hash: {ext_hash}")

        if config_dict["QB_BASE_URL"] and listener.select:
            if link.startswith("magnet:"):
                metamsg = tr('helpers.text.downloading_metadata_wait_then_you_can_select_files_use_torrent_file_to', _html=False)
                meta = await sendMessage(metamsg, listener.message)
                while True:
                    tor_info = await TorrentManager.qbittorrent.torrents.info(
                        tag=f"{listener.uid}"
                    )
                    if len(tor_info) == 0:
                        await deleteMessage(meta)
                        return
                    try:
                        tor_info = tor_info[0]
                        if tor_info.state not in [
                            "metaDL",
                            "checkingResumeData",
                            "pausedDL",
                        ]:
                            await deleteMessage(meta)
                            break
                    except Exception:
                        await deleteMessage(meta)
                        return

            ext_hash = tor_info.hash
            await TorrentManager.qbittorrent.torrents.stop(hashes=[ext_hash])
            SBUTTONS = bt_selection_buttons(ext_hash)
            msg = tr('helpers.text.your_download_paused_choose_files_then_press_done_selecting_button_to_start', _html=False)
            await sendMarkup(msg, listener.message, SBUTTONS)
        else:
            await sendStatusMessage(listener.message)
    except Exception as e:
        await sendMessage(ui_error(e), listener.message)
    finally:
        if ospath.exists(link):
            osremove(link)
