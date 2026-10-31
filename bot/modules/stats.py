from psutil import (
    disk_usage,
    cpu_percent,
    swap_memory,
    cpu_count,
    virtual_memory,
    net_io_counters,
    boot_time,
)
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command
from time import time
from os import path as ospath
from bot.helper.telegram_helper.message_utils import sendMessage
from bot import bot, botUptime
from bot.i18n import tr, raw
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import cmd_exec, get_readable_time
from bot.helper.ext_utils.human_format import get_readable_file_size
from bot.helper.telegram_helper.filters import CustomFilters


async def stats(client, message):
    if ospath.exists(".git"):
        last_commit = await cmd_exec(
            "git log -1 --date=short --pretty=format:'%cd <b>From</b> %cr'", True
        )
        last_commit = last_commit[0]
    else:
        last_commit = tr("core.stats.no_upstream")
    total, used, free, disk = disk_usage("/")
    swap = swap_memory()
    memory = virtual_memory()
    stats = tr("core.stats.summary", commit=raw(last_commit),
               bot_uptime=get_readable_time(time() - botUptime), os_uptime=get_readable_time(time() - boot_time()),
               disk_total=get_readable_file_size(total), disk_used=get_readable_file_size(used),
               disk_free=get_readable_file_size(free), disk_percent=disk,
               sent=get_readable_file_size(net_io_counters().bytes_sent), received=get_readable_file_size(net_io_counters().bytes_recv),
               cpu=cpu_percent(interval=0.5), physical_cores=cpu_count(logical=False), total_cores=cpu_count(logical=True),
               memory_total=get_readable_file_size(memory.total), memory_used=get_readable_file_size(memory.used),
               memory_free=get_readable_file_size(memory.available), memory_percent=memory.percent,
               swap_total=get_readable_file_size(swap.total), swap_percent=swap.percent)
    await sendMessage(stats, message)


bot.add_handler(
    MessageHandler(
        stats,
        filters=command(BotCommands.StatsCommand)
        & (CustomFilters.user_filter | CustomFilters.chat_filter),
    )
)
