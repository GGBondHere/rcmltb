from bot.i18n import tr, raw
import asyncio
from html import escape
from os import remove as osremove, path as ospath, mkdir
from PIL import Image
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram import filters
from bot import (
    IS_PREMIUM_USER,
    TG_MAX_SPLIT_SIZE,
    bot,
    config_dict,
    user_data,
)
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.ext_utils.bot_utils import run_sync_to_async, update_user_ldata
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    editMessage,
    sendFile,
    sendMarkup,
    sendMessage,
)
from bot.helper.telegram_helper.button_build import ButtonMaker


def get_user_settings(from_user):
    user_id = from_user.id
    name = from_user.first_name
    buttons = ButtonMaker()
    buttons.cb_buildbutton(tr("settings.language.button", _html=False), f"uilang {user_id} menu")
    thumbpath = f"Thumbnails/{user_id}.jpg"
    rclone_conf = f"rclone/{user_id}/rclone.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    user_dict = user_data.get(user_id, {})

    if (
        user_dict.get("as_doc", False)
        or "as_doc" not in user_dict
        and config_dict["AS_DOCUMENT"]
    ):
        ltype = tr("settings.document", _html=False)
        buttons.cb_buildbutton(tr("settings.send_media", _html=False), f"userset {user_id} doc")
    else:
        ltype = tr("settings.media", _html=False)
        buttons.cb_buildbutton(tr("settings.send_document", _html=False), f"userset {user_id} doc")

    buttons.cb_buildbutton(tr("settings.splits", _html=False), f"userset {user_id} lss")
    if user_dict.get("split_size", False):
        split_size = user_dict["split_size"]
    else:
        split_size = config_dict["LEECH_SPLIT_SIZE"]

    if (
        user_dict.get("equal_splits", False)
        or "equal_splits" not in user_dict
        and config_dict["EQUAL_SPLITS"]
    ):
        equal_splits = tr("settings.enabled", _html=False)
    else:
        equal_splits = tr("settings.disabled", _html=False)

    rccmsg = tr("settings.exists", _html=False) if ospath.exists(rclone_conf) else tr("settings.not_exists", _html=False)

    tokenmsg = tr("settings.exists", _html=False) if ospath.exists(token_pickle) else tr("settings.not_exists", _html=False)

    index = user_dict["index_url"] if user_dict.get("index_url", False) else tr("settings.none", _html=False)

    if user_dict.get("gdrive_id", False):
        gdrive_id = user_dict["gdrive_id"]
    elif GI := config_dict["GDRIVE_FOLDER_ID"]:
        gdrive_id = GI
    else:
        gdrive_id = tr("settings.none", _html=False)

    buttons.cb_buildbutton(tr("settings.ytdlp", _html=False), f"userset {user_id} yto")
    if user_dict.get("yt_opt", False):
        ytopt = user_dict["yt_opt"]
    elif "yt_opt" not in user_dict and (YTO := config_dict["YT_DLP_OPTIONS"]):
        ytopt = YTO
    else:
        ytopt = tr("settings.none", _html=False)

    buttons.cb_buildbutton(tr("settings.name_substitute", _html=False), f"userset {user_id} ns")
    if user_dict.get("name_sub", False):
        name_sub = user_dict["name_sub"]
    elif "name_sub" not in user_dict and (NS := config_dict["NAME_SUBSTITUTE"]):
        name_sub = NS
    else:
        name_sub = tr("settings.none", _html=False)

    buttons.cb_buildbutton(tr("settings.thumbnail", _html=False), f"userset {user_id} sthumb")
    if ospath.exists(thumbpath):
        thumbmsg = tr("settings.exists", _html=False)
    else:
        thumbmsg = tr("settings.not_exists", _html=False)

    buttons.cb_buildbutton(tr("settings.screenshots", _html=False), f"userset {user_id} sscreenshots")
    screenshots_count = user_dict.get("screenshots_count", 0)
    if screenshots_count == 0:
        screenshots_msg = tr("settings.disabled", _html=False)
    else:
        screenshots_msg = tr("settings.shots", screenshots_count=screenshots_count, _html=False)

    buttons.cb_buildbutton(tr("settings.category", _html=False), f"userset {user_id} category")
    category = user_dict.get("category", "")
    category_keys = {
        "Movies": "settings.category.movies", "TV Shows": "settings.category.tv_shows",
        "Music": "settings.category.music", "Books": "settings.category.books",
        "Software": "settings.category.software", "Others": "settings.category.others",
    }
    category_msg = tr(category_keys[category], _html=False) if category in category_keys else category or tr("settings.none", _html=False)

    buttons.cb_buildbutton(tr("settings.upload_template", _html=False), f"userset {user_id} utemplate")
    upload_template = user_dict.get("upload_template", "")
    if upload_template:
        template_msg = tr("settings.custom", _html=False)
    elif config_dict.get("UPLOAD_PATH_TEMPLATE"):
        template_msg = tr("settings.global", _html=False)
    else:
        template_msg = tr("settings.none", _html=False)

    buttons.cb_buildbutton(tr("settings.close_menu", _html=False), f"userset {user_id} close")

    text = tr("settings.settings_summary", name=name, ltype=ltype, thumbmsg=thumbmsg, screenshots_msg=screenshots_msg, category_msg=category_msg, template_msg=template_msg, split_size=split_size, equal_splits=equal_splits, yt_options=raw(escape(ytopt)), name_pattern=raw(escape(name_sub)), rccmsg=rccmsg, tokenmsg=tokenmsg, gdrive_id=gdrive_id, index=index)

    return text, buttons.build_menu(1)


async def update_user_settings(query):
    msg, button = get_user_settings(query.from_user)
    await editMessage(msg, query.message, button)


async def user_settings(_, message):
    msg, button = get_user_settings(message.from_user)
    await sendMarkup(msg, message, button)


async def set_yt_options(_, message, query):
    user_id = message.from_user.id
    value = message.text
    update_user_ldata(user_id, "yt_opt", value)
    await message.delete()
    await update_user_settings(query)
    if database.enabled:
        await database.update_user_data(user_id)


async def set_name_substitute(_, message, query):
    user_id = message.from_user.id
    value = message.text
    update_user_ldata(user_id, "name_sub", value)
    await message.delete()
    await update_user_settings(query)
    if database.enabled:
        await database.update_user_data(user_id)


async def leech_split_size(_, message, query):
    user_id = message.from_user.id
    value = min(int(message.text), TG_MAX_SPLIT_SIZE)
    update_user_ldata(user_id, "split_size", value)
    await message.delete()
    await update_user_settings(query)
    if database.enabled:
        await database.update_user_data(user_id)


async def edit_user_settings(client, query):
    message = query.message
    user_id = query.from_user.id
    from_user = query.from_user
    data = query.data.split()
    user_dict = user_data.get(user_id, {})
    thumb_path = f"Thumbnails/{user_id}.jpg"

    if user_id != int(data[1]):
        await query.answer(text=tr("settings.not_yours", _html=False), show_alert=True)
    elif data[2] == "doc":
        update_user_ldata(user_id, "as_doc", not user_dict.get("as_doc", False))
        await query.answer()
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "vthumb":
        await query.answer()
        await sendFile(message, thumb_path, from_user.mention)
        await update_user_settings(query)
    elif data[2] == "dthumb":
        if ospath.lexists(thumb_path):
            await query.answer()
            osremove(thumb_path)
            update_user_ldata(user_id, "thumb", "")
            await update_user_settings(query)
            if database.enabled:
                await database.update_thumb(user_id)
        else:
            await query.answer(text=tr("settings.old_settings", _html=False), show_alert=True)
            await update_user_settings(query)
    elif data[2] == "sthumb":
        await query.answer()
        buttons = ButtonMaker()
        if ospath.exists(thumb_path):
            buttons.cb_buildbutton(tr("settings.view_thumbnail", _html=False), f"userset {user_id} vthumb")
            buttons.cb_buildbutton(tr("settings.delete_thumbnail", _html=False), f"userset {user_id} dthumb")
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        question = await editMessage(
            tr("settings.photo_prompt", _html=False), message, buttons.build_menu(1)
        )
        try:
            if response := await client.listen.Message(
                filters.photo, id=filters.user(user_id), timeout=60
            ):
                try:
                    path = "Thumbnails/"
                    if not ospath.isdir(path):
                        mkdir(path)
                    photo_dir = await client.download_media(response)
                    des_dir = ospath.join(path, f"{user_id}.jpg")
                    await run_sync_to_async(
                        Image.open(photo_dir).convert("RGB").save, des_dir, "JPEG"
                    )
                    osremove(photo_dir)
                    update_user_ldata(user_id, "thumb", des_dir)
                    await update_user_settings(query)
                    if database.enabled:
                        await database.update_thumb(user_id, des_dir)
                except Exception as ex:
                    await editMessage(tr("common.technical_error", detail=str(ex)), question)
        except asyncio.TimeoutError:
            await sendMessage(tr("settings.timeout", _html=False), message)
    elif data[2] == "yto":
        await query.answer()
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        if user_dict.get("yt_opt", False) or config_dict["YT_DLP_OPTIONS"]:
            buttons.cb_buildbutton(
                tr("settings.remove_ytdlp", _html=False), f"userset {user_id} ryto", "header"
            )
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        rmsg = tr("settings.ytdlp_help")
        await editMessage(rmsg, message, buttons.build_menu(1))
        try:
            if response := await client.listen.Message(
                filters.text, id=filters.user(user_id), timeout=60
            ):
                await set_yt_options(client, response, query)
        except asyncio.TimeoutError:
            await sendMessage(tr("settings.timeout", _html=False), message)
    elif data[2] == "ryto":
        await query.answer()
        update_user_ldata(user_id, "yt_opt", "")
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "ns":
        await query.answer()
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        if user_dict.get("name_sub", False) or config_dict["NAME_SUBSTITUTE"]:
            buttons.cb_buildbutton(
                tr("settings.remove_name", _html=False), f"userset {user_id} rns", "header"
            )
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        rmsg = tr("settings.name_help")
        await editMessage(rmsg, message, buttons.build_menu(1))
        try:
            if response := await client.listen.Message(
                filters.text, id=filters.user(user_id), timeout=60
            ):
                await set_name_substitute(client, response, query)
        except asyncio.TimeoutError:
            await sendMessage(tr("settings.timeout", _html=False), message)
    elif data[2] == "rns":
        await query.answer()
        update_user_ldata(user_id, "name_sub", "")
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "lss":
        await query.answer()
        buttons = ButtonMaker()
        if user_dict.get("split_size", False):
            buttons.cb_buildbutton(tr("settings.reset_split", _html=False), f"userset {user_id} rlss")
        if (
            user_dict.get("equal_splits", False)
            or "equal_splits" not in user_dict
            and config_dict["EQUAL_SPLITS"]
        ):
            buttons.cb_buildbutton(tr("settings.disable_equal", _html=False), f"userset {user_id} esplits")
        else:
            buttons.cb_buildbutton(tr("settings.enable_equal", _html=False), f"userset {user_id} esplits")
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        await editMessage(
            tr("settings.split_prompt", IS_PREMIUM_USER=IS_PREMIUM_USER),
            message,
            buttons.build_menu(1),
        )
        try:
            if response := await client.listen.Message(
                filters.text, id=filters.user(user_id), timeout=60
            ):
                await leech_split_size(client, response, query)
        except asyncio.TimeoutError:
            await sendMessage(tr("settings.timeout", _html=False), message)
    elif data[2] == "rlss":
        await query.answer()
        update_user_ldata(user_id, "split_size", "")
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "esplits":
        await query.answer()
        update_user_ldata(
            user_id, "equal_splits", not user_dict.get("equal_splits", False)
        )
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "sscreenshots":
        await query.answer()
        buttons = ButtonMaker()
        current_count = user_dict.get("screenshots_count", 0)
        if current_count > 0:
            buttons.cb_buildbutton(tr("settings.disable_screenshots", _html=False), f"userset {user_id} ss_disable")
        for count in [3, 5, 8, 10]:
            btn_text = tr("settings.shots_count", count=count, _html=False)
            if current_count == count:
                btn_text = tr("settings.shots_selected", count=count, _html=False)
            buttons.cb_buildbutton(btn_text, f"userset {user_id} ss_count {count}")

        # Album option
        is_album = user_dict.get("screenshots_as_album", True)
        album_text = tr("settings.album_selected", _html=False) if is_album else tr("settings.album", _html=False)
        buttons.cb_buildbutton(album_text, f"userset {user_id} ss_album")

        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        await editMessage(
            tr("settings.screenshots_prompt", _html=False),
            message,
            buttons.build_menu(2)
        )
    elif data[2] == "ss_disable":
        await query.answer()
        update_user_ldata(user_id, "screenshots_count", 0)
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "ss_count":
        await query.answer()
        count = int(data[3])
        update_user_ldata(user_id, "screenshots_count", count)
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "ss_album":
        await query.answer()
        current = user_dict.get("screenshots_as_album", True)
        update_user_ldata(user_id, "screenshots_as_album", not current)
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "category":
        await query.answer()
        buttons = ButtonMaker()
        categories = ["Movies", "TV Shows", "Music", "Books", "Software", "Others"]
        current_category = user_dict.get("category", "")
        for cat in categories:
            category_keys = {
                "Movies": "settings.category.movies", "TV Shows": "settings.category.tv_shows",
                "Music": "settings.category.music", "Books": "settings.category.books",
                "Software": "settings.category.software", "Others": "settings.category.others",
            }
            label = tr(category_keys[cat], _html=False)
            btn_text = f"✓ {label}" if current_category == cat else label
            buttons.cb_buildbutton(btn_text, f"userset {user_id} set_cat {cat}")
        if current_category:
            buttons.cb_buildbutton(tr("settings.clear_category", _html=False), f"userset {user_id} clear_cat", "header")
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        await editMessage(
            tr("settings.category_prompt", _html=False),
            message,
            buttons.build_menu(2)
        )
    elif data[2] == "set_cat":
        await query.answer()
        category = data[3]
        update_user_ldata(user_id, "category", category)
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "clear_cat":
        await query.answer()
        update_user_ldata(user_id, "category", "")
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "utemplate":
        await query.answer()
        buttons = ButtonMaker()
        current_template = user_dict.get("upload_template", "")
        global_template = config_dict.get("UPLOAD_PATH_TEMPLATE", "")

        if current_template or global_template:
            buttons.cb_buildbutton(tr("settings.remove_template", _html=False), f"userset {user_id} rutemplate", "header")

        buttons.cb_buildbutton(tr("settings.set_template", _html=False), f"userset {user_id} set_utemplate")
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} back")
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")

        template_preview = current_template or global_template or tr("settings.not_set", _html=False)
        preview_path = ""
        if current_template or global_template:
            from bot.helper.ext_utils.template_utils import apply_upload_template
            username = from_user.username or str(user_id)
            preview_path = apply_upload_template(
                template_preview,
                user_id,
                username,
                category=user_dict.get("category", ""),
                task_type="mirror"
            )

        rmsg = tr("settings.template_details", template_preview=template_preview, preview_path=preview_path or tr("settings.none", _html=False))
        await editMessage(rmsg, message, buttons.build_menu(1))
    elif data[2] == "set_utemplate":
        await query.answer()
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr("settings.back", _html=False), f"userset {user_id} utemplate")
        buttons.cb_buildbutton(tr("settings.close", _html=False), f"userset {user_id} close")
        rmsg = tr("settings.template_help")
        await editMessage(rmsg, message, buttons.build_menu(1))
        try:
            if response := await client.listen.Message(
                filters.text, id=filters.user(user_id), timeout=60
            ):
                if "/ignore" in response.text:
                    await client.listen.Cancel(filters.user(user_id))
                else:
                    template = response.text.strip()
                    update_user_ldata(user_id, "upload_template", template)
                    await update_user_settings(query)
                    if database.enabled:
                        await database.update_user_data(user_id)
        except asyncio.TimeoutError:
            await sendMessage(tr("settings.timeout", _html=False), message)
    elif data[2] == "rutemplate":
        await query.answer()
        update_user_ldata(user_id, "upload_template", "")
        await update_user_settings(query)
        if database.enabled:
            await database.update_user_data(user_id)
    elif data[2] == "back":
        await client.listen.Cancel(filters.user(user_id))
        await query.answer()
        await update_user_settings(query)
    elif data[2] == "close":
        await client.listen.Cancel(filters.user(user_id))
        await query.answer()
        await message.delete()
    else:
        await query.answer()
        await query.message.delete()
        await query.message.reply_to_message.delete()


bot.add_handler(
    MessageHandler(
        user_settings,
        filters=filters.command(BotCommands.UserSetCommand)
        & (CustomFilters.user_filter | CustomFilters.chat_filter),
    )
)
bot.add_handler(
    CallbackQueryHandler(edit_user_settings, filters=filters.regex("userset"))
)
