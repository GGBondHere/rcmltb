"""Language preferences use the same user record as other settings."""

from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from bot import bot, user_data
from bot.i18n import tr, get_language
from bot.i18n.commands import publish_commands
from bot.helper.ext_utils.bot_utils import update_user_ldata
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMarkup, editMessage


def language_menu(user_id):
    buttons = ButtonMaker()
    selected = user_data.get(user_id, {}).get("ui_language")
    for language, label in (("zh-CN", "简体中文"), ("en", "English")):
        buttons.cb_buildbutton(("✓ " if selected == language else "") + label,
                               f"uilang {user_id} {language}")
    buttons.cb_buildbutton(("✓ " if not selected else "") + tr("settings.language.follow", _html=False),
                           f"uilang {user_id} global")
    buttons.cb_buildbutton(tr("common.close", _html=False), f"uilang {user_id} close")
    return tr("settings.language.prompt", language=get_language(user_id)), buttons.build_menu(1)


async def language_command(client, message):
    text, buttons = language_menu(message.from_user.id)
    await sendMarkup(text, message, buttons)


async def language_callback(client, query):
    data = query.data.split()
    if len(data) != 3 or not data[1].isdigit() or query.from_user.id != int(data[1]):
        await query.answer(tr("common.menu_not_yours", _html=False), show_alert=True)
        return
    user_id = query.from_user.id
    action = data[2]
    if action == "close":
        await query.answer()
        await query.message.delete()
        return
    if not await CustomFilters.user_callback_filter(client, query):
        await query.answer(tr("common.access_denied", _html=False), show_alert=True)
        return
    if action not in ("menu", "global", "zh-CN", "en"):
        await query.answer(tr("settings.language.invalid", _html=False), show_alert=True)
        return
    if action != "menu":
        update_user_ldata(user_id, "ui_language", "" if action == "global" else action)
        if database.enabled:
            await database.update_user_data(user_id)
        await publish_commands(client, user_id=user_id)
    await query.answer()
    text, buttons = language_menu(user_id)
    await editMessage(text, query.message, buttons)


bot.add_handler(MessageHandler(language_command,
    filters=filters.command(BotCommands.LanguageCommand) & (CustomFilters.user_filter | CustomFilters.chat_filter)))
bot.add_handler(CallbackQueryHandler(language_callback, filters=filters.regex(r"^uilang ")))
