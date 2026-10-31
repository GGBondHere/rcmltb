from bot.i18n import tr
from pyrogram.filters import command
from pyrogram.handlers import MessageHandler

from bot import bot
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMarkup


async def bot_help(_, message):
    buttons = ButtonMaker()
    buttons.cb_buildbutton(tr('commands.help.mirror', _html=False), "help back m")
    buttons.cb_buildbutton("YT-DLP", "help back y")
    buttons.cb_buildbutton(tr('commands.help.leech', _html=False), "help back l")
    buttons.cb_buildbutton(tr('commands.help.batch', _html=False), "help back b")

    help_text = (
        tr(
            'commands.help.overview',
            mirror_command=BotCommands.MirrorCommand[0],
            mirror_batch_command=BotCommands.MirrorBatchCommand[0],
            mirror_select_command=BotCommands.MirrorSelectCommand[0],
            leech_command=BotCommands.LeechCommand[0],
            leech_batch_command=BotCommands.LeechBatchCommand[0],
            ytdl_mirror_command=BotCommands.YtdlMirrorCommand[0],
            ytdl_leech_command=BotCommands.YtdlLeechCommand[0],
            clone_command=BotCommands.CloneCommand,
            copy_command=BotCommands.CopyCommand,
            sync_command=BotCommands.SyncCommand,
            bi_sync_command=BotCommands.BiSyncCommand,
            rcfm_command=BotCommands.RcfmCommand,
            storage_command=BotCommands.StorageCommand,
            cleanup_command=BotCommands.CleanupCommand,
            serve_command=BotCommands.ServeCommand,
            count_command=BotCommands.CountCommand,
            torrent_search_command=BotCommands.TorrentSearchCommand,
            tmdb_command=BotCommands.TMDB,
            status_command=BotCommands.StatusCommand,
            cancel_command=BotCommands.CancelCommand,
            cancel_all_command=BotCommands.CancelAllCommand,
            force_start_command=BotCommands.ForceStartCommand[0],
            select_command=BotCommands.SelectCommand,
            user_set_command=BotCommands.UserSetCommand,
            owner_set_command=BotCommands.OwnerSetCommand,
            stats_command=BotCommands.StatsCommand,
            ping_command=BotCommands.PingCommand,
        )
    )
    help_text += tr('commands.help.language', command=BotCommands.LanguageCommand[0])
    await sendMarkup(help_text, message, buttons.build_menu(2))


bot.add_handler(
    MessageHandler(
        bot_help,
        filters=command(BotCommands.HelpCommand)
        & (CustomFilters.user_filter | CustomFilters.chat_filter),
    )
)
