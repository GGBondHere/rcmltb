from bot.i18n import tr, raw
"""JDownloader download helper."""

from base64 import b64encode
from asyncio import sleep
from os import path as ospath

from bot import LOGGER, status_dict, status_dict_lock
from bot.core.jdownloader_booter import jdownloader
from bot.helper.telegram_helper.message_utils import sendMessage, sendStatusMessage
from bot.helper.mirror_leech_utils.status_utils.jdownloader_status import (
    JDownloaderStatus,
)


async def add_jd_download(link, name, path, listener):
    """Add a download to JDownloader.

    Args:
        link: URL to download (HTTP link or DLC file path)
        name: Custom name for the download
        path: Download path
        listener: TaskListener instance
    """
    device = jdownloader.get_device()
    if not jdownloader.is_connected or not device:
        await sendMessage(tr('helpers.text.jdownloader_not_connected_please_check_configuration', _html=False), listener.message)
        return

    try:
        # Handle DLC files
        if link.endswith(".dlc") or "/dlc/" in link:
            if ospath.exists(link):
                # Read and encode DLC file
                with open(link, "rb") as f:
                    dlc_content = b64encode(f.read()).decode()
                await device.linkgrabber.add_container(
                    "DLC", f"data:;base64,{dlc_content}"
                )
            else:
                await sendMessage(tr('helpers.text.dlc_file_not_found', _html=False), listener.message)
                return
        else:
            # Add direct link
            await device.linkgrabber.add_links([
                {
                    "url": link,
                    "packageName": name or "",
                    "downloadFolder": path,
                }
            ])

        LOGGER.info(f"Added JDownloader link: {link}")

        # Wait for package to be added
        await sleep(5)

        # Query packages to get the new package ID
        packages = await device.linkgrabber.query_packages()
        if not packages:
            await sendMessage(tr('helpers.text.failed_to_add_link_to_jdownloader', _html=False), listener.message)
            return

        # Get the most recent package
        package = packages[-1]
        gid = package.get("uuid")

        # Create status object
        async with status_dict_lock:
            status_dict[listener.uid] = JDownloaderStatus(listener, gid)

        await listener.onDownloadStart()
        await sendStatusMessage(listener.message)

        # Start downloading
        await device.downloads.start_downloads(package_ids=[gid])
        
    except Exception as e:
        LOGGER.error(f"Error adding JDownloader download: {e}")
        await sendMessage(tr('helpers.text.error', value1=str(e)), listener.message)


async def handle_dlc_file(file_path, listener, path):
    """Handle DLC container file.

    Args:
        file_path: Path to DLC file
        listener: TaskListener instance
        path: Download path
    """
    device = jdownloader.get_device()
    if not jdownloader.is_connected or not device:
        await sendMessage(tr('helpers.text.jdownloader_not_connected', _html=False), listener.message)
        return

    try:
        with open(file_path, "rb") as f:
            dlc_content = b64encode(f.read()).decode()

        await device.linkgrabber.add_container(
            "DLC", f"data:;base64,{dlc_content}"
        )

        LOGGER.info(f"Added DLC file: {file_path}")

        await sleep(5)

        packages = await device.linkgrabber.query_packages()
        if not packages:
            await sendMessage(tr('helpers.text.failed_to_add_dlc_file', _html=False), listener.message)
            return

        package = packages[-1]
        gid = package.get("uuid")

        async with status_dict_lock:
            status_dict[listener.uid] = JDownloaderStatus(listener, gid)

        await listener.onDownloadStart()
        await sendStatusMessage(listener.message)

        await device.downloads.start_downloads(package_ids=[gid])

    except Exception as e:
        LOGGER.error(f"Error handling DLC file: {e}")
        await sendMessage(tr('helpers.text.error', value1=str(e)), listener.message)
