from bot.i18n import tr, display_status
from asyncio import sleep
from bot.modules.queue import queue
from pyrogram.filters import regex
from bot import (
    status_dict_lock,
    OWNER_ID,
    bot,
    status_dict,
    user_data,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram import filters
from bot.helper.telegram_helper.message_utils import sendMarkup, sendMessage
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.misc_utils import getAllTasks, getTaskByGid
from bot.helper.mirror_leech_utils.status_utils.status_utils import MirrorStatus


async def cancel_task(client, message):
    user_id = message.from_user.id if message.from_user else message.sender_chat.id
    msg = message.text.split()
    if len(msg) > 1:
        gid = msg[1]
        task = await getTaskByGid(gid)
        if task is None:
            await sendMessage(tr('commands.task.not_found', gid=gid), message)
            return
    elif reply_to_id := message.reply_to_message_id:
        async with status_dict_lock:
            task = status_dict.get(reply_to_id, None)
        if task is None:
            await sendMessage(tr('commands.task.no_active'), message)
            return
    elif len(msg) == 1:
        cmds = BotCommands.CancelCommand
        help_msg = (
            tr('commands.cancel.help', command=cmds[0])
        )
        await sendMessage(help_msg, message)
        return

    if (
        OWNER_ID != user_id
        and task.message.from_user.id != user_id
        and (user_id not in user_data or not user_data[user_id].get("is_sudo"))
    ):
        await sendMessage(tr('commands.task.access_denied'), message)
        return

    obj = task.task()
    if task.type() == "RcloneSync":
        obj.kill
    else:
        await obj.cancel_task()


async def cancell_all_buttons(client, message):
    async with status_dict_lock:
        count = len(status_dict)
    if count == 0:
        await sendMessage(tr('commands.cancel.empty'), message)
        return
    buttons = ButtonMaker()
    buttons.cb_buildbutton(tr('commands.cancel.downloading', _html=False), f"canall {MirrorStatus.STATUS_DOWNLOADING}")
    buttons.cb_buildbutton(tr('commands.cancel.uploading', _html=False), f"canall {MirrorStatus.STATUS_UPLOADING}")
    buttons.cb_buildbutton(tr('commands.cancel.seeding', _html=False), f"canall {MirrorStatus.STATUS_SEEDING}")
    buttons.cb_buildbutton(tr('commands.cancel.cloning', _html=False), f"canall {MirrorStatus.STATUS_CLONING}")
    buttons.cb_buildbutton(tr('commands.cancel.splitting', _html=False), f"canall {MirrorStatus.STATUS_SPLITTING}")
    buttons.cb_buildbutton(tr('commands.cancel.extracting', _html=False), f"canall {MirrorStatus.STATUS_EXTRACTING}")
    buttons.cb_buildbutton(tr('commands.cancel.archiving', _html=False), f"canall {MirrorStatus.STATUS_ARCHIVING}")
    buttons.cb_buildbutton(tr('commands.cancel.queued_download', _html=False), f"canall {MirrorStatus.STATUS_QUEUEDL}")
    buttons.cb_buildbutton(tr('commands.cancel.queued_upload', _html=False), f"canall {MirrorStatus.STATUS_QUEUEUP}")
    buttons.cb_buildbutton(tr('commands.cancel.paused', _html=False), f"canall {MirrorStatus.STATUS_PAUSED}")
    buttons.cb_buildbutton(tr('commands.cancel.all', _html=False), "canall all")
    buttons.cb_buildbutton(tr('commands.button.close', _html=False), "canall close")
    await sendMarkup(tr('commands.cancel.category'), message, buttons.build_menu(2))


async def cancel_all_update(client, query):
    message = query.message
    data = query.data.split()
    await query.answer()
    if data[1] == "close":
        await query.message.delete()
    else:
        res = await cancel_all_(data[1])
        if not res:
            await sendMessage(tr('commands.cancel.no_match', status=display_status(data[1])), message)


async def cancel_all_(status):
    tasks = await getAllTasks(status)
    if not tasks:
        return False
    for task in tasks:
        obj = task.task()
        await obj.cancel_task()
        await sleep(2)
    return True


bot.add_handler(
    MessageHandler(
        cancel_task,
        filters.command(BotCommands.CancelCommand)
        & (CustomFilters.user_filter | CustomFilters.chat_filter),
    )
)
bot.add_handler(
    MessageHandler(
        cancell_all_buttons,
        filters=filters.command(BotCommands.CancelAllCommand)
        & (CustomFilters.owner_filter | CustomFilters.sudo_filter),
    )
)
bot.add_handler(
    CallbackQueryHandler(
        cancel_all_update,
        filters=regex("canall")
        & (CustomFilters.owner_filter | CustomFilters.sudo_filter),
    )
)
