from collections.abc import Mapping
from html import escape
from bot.i18n import tr, raw
from bot import bot
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import deleteMessage, editMessage
from pyrogram.filters import regex
from pyrogram.handlers import CallbackQueryHandler


def _build_help():
    # Build from the active actor on access; never retain startup-language text.
    YT_HELP_DICT = {}
    MIRROR_HELP_DICT = {}
    LEECH_HELP_DICT = {}
    ytdl = tr('helpers.help.ytdl')
    quality = tr('helpers.help.quality')
    options = tr('helpers.help.options')
    mirror = tr('helpers.help.mirror')
    new_name = tr('helpers.help.new_name')
    extract = tr('helpers.help.extract')
    zip = tr('helpers.help.zip')
    multi = tr('helpers.help.multi')
    same_multi = tr('helpers.help.same_multi')
    direct_link = tr('helpers.help.direct_link')
    tg_link = tr('helpers.help.tg_link_full')
    userbot = tr('helpers.help.userbot')
    torr_select = tr('helpers.help.torr_select')
    torr_seed = tr('helpers.help.torr_seed')
    screenshots = tr('helpers.help.screenshots')
    leech = tr('helpers.help.leech')
    CLONE_HELP_MESSAGE = tr('helpers.help.clone_help_message')
    PASSWORD_ERROR_MESSAGE = tr('helpers.help.password_error_message')
    batch = tr('helpers.help.batch')
    tg_link = tr('helpers.help.tg_link')
    url_link = tr('helpers.help.url_link')
    txt_file = tr('helpers.help.txt_file')
    MIRROR_HELP_DICT = {'Cmd': mirror, 'Menu': None, '✏️Rename': new_name, '🗜️Zip': zip, '📦Extract': extract, '🔢Multi': multi, '🔗Links': direct_link, '🌱Seeding': torr_seed, '🎯TorrentSelect': torr_select, '🖼️Screenshots': screenshots, '📡Telegram': tg_link, '👤UserTrans': userbot}
    LEECH_HELP_DICT = {'Cmd': leech, 'Menu': None, 'Rename': new_name.replace('<code>/cmd</code>', ''), 'Zip': zip.replace('<code>/cmd</code>', ''), 'Extract': extract.replace('<code>/cmd</code>', ''), 'Multi': multi.replace('<code>/cmd</code>', ''), 'Link': direct_link.replace('<code>/cmd</code>', ''), 'Seed': torr_seed.replace('<code>/cmd</code>', ''), 'Select': torr_select.replace('<code>/cmd</code>', ''), 'Screenshot': screenshots.replace('<code>/cmd</code>', ''), 'Telegram': tg_link.replace('<code>/cmd</code>', ''), 'UserTrans': userbot.replace('<code>/cmd</code>', '')}
    YT_HELP_DICT = {'Cmd': ytdl, 'Menu': None, 'Rename': tr('helpers.help.rename_note', name=raw(new_name)), 'Zip': zip, 'Quality': quality, 'Options': options, 'Multi': multi, 'Upload-Dest': tr('helpers.help.upload_dest'), 'Rclone-Flags': tr('helpers.help.rclone_flags'), 'Split-Size': tr('helpers.help.split_size'), 'Name-Sub': tr('helpers.help.name_sub'), 'Thumb': tr('helpers.help.thumb'), 'Leech-Type': tr('helpers.help.leech_type'), 'TG-Transmission': tr('helpers.help.tg_transmission'), 'Hybrid-Leech': tr('helpers.help.hybrid_leech'), 'Force-Start': tr('helpers.help.force_start'), 'Same-Directory': same_multi}
    BATCH_HELP_DICT = {'Cmd': batch, 'Menu': None, 'TG-Link': tg_link, 'Txt-File': txt_file, 'Url-Link': url_link}
    return locals()


class LocalizedHelpMap(Mapping):
    def __init__(self, name, route):
        self.name = name
        self.route = route

    def __iter__(self):
        return iter(_build_help()[self.name])

    def __len__(self):
        return len(_build_help()[self.name])

    def __getitem__(self, key):
        content = _build_help()[self.name]
        if key != "Menu":
            return content[key]
        buttons = ButtonMaker()
        for name in list(content)[2:]:
            buttons.cb_buildbutton(tr(_HELP_LABELS[name], _html=False), f"help {self.route} {name}")
        buttons.cb_buildbutton(tr("common.close", _html=False), "help close", "footer")
        return buttons.build_menu(3)


class LocalizedHelp:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return _build_help()[self.name]

    def format(self, *args, **kwargs):
        return raw(str(self).format(*(escape(str(value), quote=True) for value in args),
                                    **{key: escape(str(value), quote=True) for key, value in kwargs.items()}))


MIRROR_HELP_DICT = LocalizedHelpMap("MIRROR_HELP_DICT", "m")
LEECH_HELP_DICT = LocalizedHelpMap("LEECH_HELP_DICT", "l")
YT_HELP_DICT = LocalizedHelpMap("YT_HELP_DICT", "y")
BATCH_HELP_DICT = LocalizedHelpMap("BATCH_HELP_DICT", "b")
CLONE_HELP_MESSAGE = LocalizedHelp("CLONE_HELP_MESSAGE")
PASSWORD_ERROR_MESSAGE = LocalizedHelp("PASSWORD_ERROR_MESSAGE")

_HELP_LABELS = {'✏️Rename': 'helpers.help.button_mirror_rename', '🗜️Zip': 'helpers.help.button_mirror_zip', '📦Extract': 'helpers.help.button_mirror_extract', '🔢Multi': 'helpers.help.button_mirror_multi', '🔗Links': 'helpers.help.button_mirror_links', '🌱Seeding': 'helpers.help.button_mirror_seeding', '🎯TorrentSelect': 'helpers.help.button_mirror_torrentselect', '🖼️Screenshots': 'helpers.help.button_mirror_screenshots', '📡Telegram': 'helpers.help.button_mirror_telegram', '👤UserTrans': 'helpers.help.button_mirror_usertrans', 'Rename': 'helpers.help.button_rename', 'Zip': 'helpers.help.button_zip', 'Extract': 'helpers.help.button_extract', 'Multi': 'helpers.help.button_multi', 'Link': 'helpers.help.button_link', 'Seed': 'helpers.help.button_seed', 'Select': 'helpers.help.button_select', 'Screenshot': 'helpers.help.button_screenshot', 'Telegram': 'helpers.help.button_telegram', 'UserTrans': 'helpers.help.button_usertrans', 'Quality': 'helpers.help.button_quality', 'Options': 'helpers.help.button_options', 'Upload-Dest': 'helpers.help.button_upload_dest', 'Rclone-Flags': 'helpers.help.button_rclone_flags', 'Split-Size': 'helpers.help.button_split_size', 'Name-Sub': 'helpers.help.button_name_sub', 'Thumb': 'helpers.help.button_thumb', 'Leech-Type': 'helpers.help.button_leech_type', 'TG-Transmission': 'helpers.help.button_tg_transmission', 'Hybrid-Leech': 'helpers.help.button_hybrid_leech', 'Force-Start': 'helpers.help.button_force_start', 'Same-Directory': 'helpers.help.button_same_directory', 'TG-Link': 'helpers.help.button_tg_link', 'Txt-File': 'helpers.help.button_txt_file', 'Url-Link': 'helpers.help.button_url_link'}


async def create_mirror_help_buttons():
    return MIRROR_HELP_DICT["Menu"]


async def create_ytdl_help_buttons():
    return YT_HELP_DICT["Menu"]


async def create_leech_help_buttons():
    return LEECH_HELP_DICT["Menu"]


async def create_batch_help_buttons():
    return BATCH_HELP_DICT["Menu"]


async def help_callback(_, query):
    data = query.data.split()
    message = query.message
    if data[1] == 'close':
        await deleteMessage(message)
    elif data[1] == 'back':
        if data[2] == 'm':
            await editMessage(MIRROR_HELP_DICT['Cmd'], message, MIRROR_HELP_DICT['Menu'])
        elif data[2] == 'l':
            await editMessage(LEECH_HELP_DICT['Cmd'], message, LEECH_HELP_DICT['Menu'])
        elif data[2] == 'b':
            await editMessage(BATCH_HELP_DICT['Cmd'], message, BATCH_HELP_DICT['Menu'])
        else:
            await editMessage(YT_HELP_DICT['Cmd'], message, YT_HELP_DICT['Menu'])
    elif data[1] == 'm':
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr('common.back', _html=False), f'help back m')
        await editMessage(MIRROR_HELP_DICT[data[2]], message, buttons.build_menu())
    elif data[1] == 'y':
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr('common.back', _html=False), f'help back y')
        await editMessage(YT_HELP_DICT[data[2]], message, buttons.build_menu())
    elif data[1] == 'l':
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr('common.back', _html=False), f'help back l')
        await editMessage(LEECH_HELP_DICT[data[2]], message, buttons.build_menu())
    elif data[1] == 'b':
        buttons = ButtonMaker()
        buttons.cb_buildbutton(tr('common.back', _html=False), f'help back b')
        await editMessage(BATCH_HELP_DICT[data[2]], message, buttons.build_menu())


bot.add_handler(CallbackQueryHandler(help_callback, filters=regex("^help")))
