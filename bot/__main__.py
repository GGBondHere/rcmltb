from asyncio import create_subprocess_exec, gather
from signal import signal, SIGINT, SIGTERM, SIGTSTP, SIG_IGN
from aiofiles import open as aiopen
from time import time
from os import path as ospath, remove as osremove, execl as osexecl
from sys import executable

from bot import (
    LOGGER,
    bot_loop,
    config_dict,
)
from bot.core.telegram_manager import TgClient
from bot.core.startup import (
    load_settings,
    load_configurations,
    save_settings,
    update_variables,
    update_aria2_options,
    update_qbit_options,
)
from bot.core.torrent_manager import TorrentManager
from bot.helper.ext_utils.help_messages import (
    create_batch_help_buttons,
    create_leech_help_buttons,
    create_mirror_help_buttons,
    create_ytdl_help_buttons,
)
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.misc_utils import clean_all, exit_clean_up, start_cleanup
from bot.helper.telegram_helper.message_utils import sendMessage
from bot.i18n import tr
from bot.i18n.commands import publish_commands
from bot.helper.telegram_helper.bot_commands import BotCommands


async def main():
    await database.connect()

    # 1. Load settings from DB
    await load_settings()
    LOGGER.info("Settings loaded from database")

    # 2. Start Telegram clients (concurrently)
    await gather(TgClient.start_bot(), TgClient.start_user())
    LOGGER.info("Telegram clients started")

    # 3. Start services and load configurations
    try:
        await load_configurations()
        LOGGER.info("Configurations loaded")
    except Exception as e:
        LOGGER.warning(f"load_configurations error (non-fatal): {e}")

    # 4. Initialize TorrentManager
    await TorrentManager.initiate()
    LOGGER.info("TorrentManager initiated")

    # 5. Start cleanup
    await start_cleanup()
    LOGGER.info("Cleanup done")

    # 6. Update derived variables
    await update_variables()
    LOGGER.info("Variables updated")

    # 7. Update aria2 and qbit options
    await gather(update_aria2_options(), update_qbit_options())
    LOGGER.info("Aria2/qBittorrent options updated")

    # 8. Create help buttons and init telegraph
    from bot.helper.ext_utils.telegraph_helper import init_telegraph
    await gather(
        create_mirror_help_buttons(),
        create_ytdl_help_buttons(),
        create_leech_help_buttons(),
        create_batch_help_buttons(),
        init_telegraph(),
    )
    LOGGER.info("Help buttons and telegraph created")

    # 9. Initialize search tools
    from bot.modules import torr_search
    await torr_search.initiate_search_tools()

    # 10. Start aria2 listener
    from bot.helper.listeners.aria2_listener import add_aria2_callbacks
    add_aria2_callbacks()

    # 11. Register handlers
    from bot.core.handlers import add_handlers
    add_handlers()

    # 12. Boot JDownloader if configured
    if getattr(config_dict, "JD_EMAIL", "") and getattr(config_dict, "JD_PASSWORD", ""):
        from bot.core.jdownloader_booter import jdownloader_boot
        jdownloader_boot()
        LOGGER.info("JDownloader boot initiated")

    # 13. Handle restart message
    if ospath.isfile(".restartmsg"):
        with open(".restartmsg") as f:
            chat_id, msg_id = map(int, f)
        try:
            await TgClient.bot.edit_message_text(chat_id, msg_id, tr("core.restart.complete", _user_id=chat_id if chat_id > 0 else None))
        except Exception:
            pass
        osremove(".restartmsg")

    # 14. Set bot commands
    await publish_commands(TgClient.bot)

    # 15. Save settings to DB
    await save_settings()

    LOGGER.info("Bot Started!")
    signal(SIGINT, exit_clean_up)
    signal(SIGTERM, exit_clean_up)
    signal(SIGTSTP, SIG_IGN)


bot_loop.run_until_complete(main())
bot_loop.run_forever()
