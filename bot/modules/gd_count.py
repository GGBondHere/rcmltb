from bot.i18n import tr, raw
from bot.helper.mirror_leech_utils.gd_utils.count import gdCount
from pyrogram.handlers import MessageHandler
from pyrogram.filters import command
from bot import bot
from bot.helper.telegram_helper.message_utils import deleteMessage, sendMessage
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import (
    is_gdrive_link,
    get_readable_file_size,
    run_sync_to_async,
)


async def count(_, message):
    args = message.text.split()
    user = message.from_user or message.sender_chat
    if username := user.username:
        tag = f"@{username}"
    else:
        tag = message.from_user.mention

    link = args[1] if len(args) > 1 else ""
    if len(link) == 0 and (reply_to := message.reply_to_message):
        link = reply_to.text.split(maxsplit=1)[0].strip()

    if is_gdrive_link(link):
        msg = await sendMessage(tr('commands.count.progress', link=link), message)
        name, mime_type, size, files, folders = await run_sync_to_async(
            gdCount().count, link, user.id
        )
        if mime_type is None:
            await sendMessage(tr('commands.count.error', detail=name), message)
            return
        await deleteMessage(msg)
        msg = tr('commands.count.complete')
        msg += tr('commands.count.name', name=name)
        msg += tr('commands.count.size', size=get_readable_file_size(size))
        msg += tr('commands.count.type', mime_type=tr('common.folder') if mime_type == 'Folder' else mime_type)
        if mime_type == "Folder":
            msg += tr('commands.count.folders', folders=folders)
            msg += tr('commands.count.files', files=files)
        msg += tr('commands.count.mention', tag=raw(tag))
    else:
        msg = (
            tr('commands.count.invalid_link')
        )

    await sendMessage(msg, message)


bot.add_handler(
    MessageHandler(
        count, filters=command(BotCommands.CountCommand) & CustomFilters.user_filter
    )
)
