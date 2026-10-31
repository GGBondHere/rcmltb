"""Telegram command descriptions, using the same language preferences as messages."""

from bot.i18n import get_language, locale_context, tr
import logging


COMMANDS = (
    ("StartCommand", "start"), ("MirrorCommand", "mirror"),
    ("YtdlMirrorCommand", "ytdl"), ("LeechCommand", "leech"),
    ("YtdlLeechCommand", "ytdleech"), ("CloneCommand", "clone"),
    ("CopyCommand", "copy"), ("StatusCommand", "status"),
    ("StatsCommand", "stats"), ("CancelCommand", "cancel"),
    ("CancelAllCommand", "cancel_all"), ("TorrentSearchCommand", "search"),
    ("ServeCommand", "serve"), ("UserSetCommand", "user_settings"),
    ("OwnerSetCommand", "bot_settings"), ("LanguageCommand", "language"),
    ("PingCommand", "ping"), ("LogsCommand", "logs"),
    ("RestartCommand", "restart"), ("HelpCommand", "help"),
)


async def publish_commands(client, user_id=None, language=None):
    from pyrogram.types import BotCommand, BotCommandScopeChat
    from bot import user_data
    from bot.helper.telegram_helper.bot_commands import BotCommands

    options = {}
    if user_id is not None:
        options["scope"] = BotCommandScopeChat(user_id)
        if not language and not user_data.get(user_id, {}).get("ui_language"):
            try:
                await client.delete_bot_commands(**options)
            except Exception as error:
                logging.getLogger(__name__).warning("Could not refresh Telegram command descriptions: %s", error)
            return
    language = language or get_language(user_id, global_default=user_id is None)
    with locale_context(user_id, language=language):
        commands = []
        for attribute, key in COMMANDS:
            command = getattr(BotCommands, attribute)
            if isinstance(command, (list, tuple)):
                command = command[0]
            commands.append(BotCommand(command, tr(f"core.commands.{key}", _html=False)))
        try:
            await client.set_bot_commands(commands, **options)
        except Exception as error:
            logging.getLogger(__name__).warning("Could not refresh Telegram command descriptions: %s", error)
