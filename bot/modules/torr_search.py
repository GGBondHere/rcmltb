from bot.i18n import tr, ui_error
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.filters import command, regex
from aiohttp import ClientSession
from html import escape
from urllib.parse import quote
from bot import bot, LOGGER, config_dict, tmdb_titles
from bot.core.torrent_manager import TorrentManager
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import editMessage, sendMessage
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.ext_utils.bot_utils import get_readable_file_size


SITES = None
TELEGRAPH_LIMIT = 300
PLUGINS = []


async def initiate_search_tools():
    qb_plugins = await TorrentManager.qbittorrent.search.plugins()
    if SEARCH_PLUGINS := config_dict["SEARCH_PLUGINS"]:
        globals()["PLUGINS"] = []
        src_plugins = eval(SEARCH_PLUGINS)
        if qb_plugins:
            names = [plugin.name for plugin in qb_plugins]
            await TorrentManager.qbittorrent.search.uninstall_plugins(names=names)
        await TorrentManager.qbittorrent.search.install_plugins(src_plugins)
    elif qb_plugins:
        for plugin in qb_plugins:
            await TorrentManager.qbittorrent.search.uninstall_plugins(names=[plugin.name])
        globals()["PLUGINS"] = []

    if SEARCH_API_LINK := config_dict["SEARCH_API_LINK"]:
        global SITES
        try:
            async with ClientSession(trust_env=True) as c:
                async with c.get(f"{SEARCH_API_LINK}/api/v1/sites") as res:
                    data = await res.json()
            SITES = {
                str(site): str(site).capitalize() for site in data["supported_sites"]
            }
            SITES["all"] = "All"
        except Exception as e:
            LOGGER.error(
                f"{e} Can't fetching sites from SEARCH_API_LINK make sure use latest version of API"
            )
            SITES = None


async def _search(key, site, message, method):
    if method.startswith("api"):
        SEARCH_API_LINK = config_dict["SEARCH_API_LINK"]
        SEARCH_LIMIT = config_dict["SEARCH_LIMIT"]
        if method == "apisearch":
            LOGGER.info(f"API Searching: {key} from {site}")
            if site == "all":
                api = f"{SEARCH_API_LINK}/api/v1/all/search?query={key}&limit={SEARCH_LIMIT}"
            else:
                api = f"{SEARCH_API_LINK}/api/v1/search?site={site}&query={key}&limit={SEARCH_LIMIT}"
        elif method == "apitrend":
            LOGGER.info(f"API Trending from {site}")
            if site == "all":
                api = f"{SEARCH_API_LINK}/api/v1/all/trending?limit={SEARCH_LIMIT}"
            else:
                api = f"{SEARCH_API_LINK}/api/v1/trending?site={site}&limit={SEARCH_LIMIT}"
        elif method == "apirecent":
            LOGGER.info(f"API Recent from {site}")
            if site == "all":
                api = f"{SEARCH_API_LINK}/api/v1/all/recent?limit={SEARCH_LIMIT}"
            else:
                api = (
                    f"{SEARCH_API_LINK}/api/v1/recent?site={site}&limit={SEARCH_LIMIT}"
                )
        try:
            async with ClientSession(trust_env=True) as c:
                async with c.get(api) as res:
                    search_results = await res.json()
            if "error" in search_results or search_results["total"] == 0:
                await editMessage(
                    tr('commands.search.no_api_results', query=key, site_name=tr('commands.search.all') if site == 'all' else SITES.get(site)),
                    message,
                )
                return
            msg = tr('commands.search.api_count', results=min(search_results['total'], TELEGRAPH_LIMIT))
            if method == "apitrend":
                msg += tr('commands.search.trending_results', site_name=tr('commands.search.all') if site == 'all' else SITES.get(site))
            elif method == "apirecent":
                msg += tr('commands.search.recent_results', site_name=tr('commands.search.all') if site == 'all' else SITES.get(site))
            else:
                msg += tr('commands.search.api_results', query=key, site_name=tr('commands.search.all') if site == 'all' else SITES.get(site))
            search_results = search_results["data"]
        except Exception as e:
            await editMessage(ui_error(e), message)
            return
    else:
        LOGGER.info(f"PLUGINS Searching: {key} from {site}")
        search = await TorrentManager.qbittorrent.search.start(
            pattern=key, plugins=[site], category="all"
        )
        search_id = search.id
        while True:
            result_status = await TorrentManager.qbittorrent.search.status(search_id)
            status = result_status[0].status
            if status != "Running":
                break
        dict_search_results = await TorrentManager.qbittorrent.search.results(
            search_id, limit=TELEGRAPH_LIMIT
        )
        search_results = dict_search_results.results
        total_results = dict_search_results.total
        if total_results == 0:
            await editMessage(
                tr('commands.search.no_plugin_results', query=key, site_name=tr('commands.search.all') if site == 'all' else site.capitalize()),
                message,
            )
            return
        msg = tr('commands.search.plugin_count', results=min(total_results, TELEGRAPH_LIMIT))
        msg += tr('commands.search.plugin_results', query=key, site_name=tr('commands.search.all') if site == 'all' else site.capitalize())
        await TorrentManager.qbittorrent.search.delete(search_id)

    link = await __getResult(search_results, key, message, method)
    buttons = ButtonMaker()
    buttons.url_buildbutton(tr('commands.search.view', _html=False), link)
    button = buttons.build_menu(1)
    await editMessage(msg, message, button)


async def __getResult(search_results, key, message, method):
    telegraph_content = []
    if method == "apirecent":
        msg = tr('commands.search.page_recent')
    elif method == "apisearch":
        msg = tr('commands.search.page_search', query=key)
    elif method == "apitrend":
        msg = tr('commands.search.page_trending')
    else:
        msg = tr('commands.search.page_plugins', query=key)
    for index, result in enumerate(search_results, start=1):
        if method.startswith("api"):
            try:
                if "name" in result.keys():
                    msg += f"<code><a href='{result['url']}'>{escape(result['name'])}</a></code><br>"
                if "torrents" in result.keys():
                    for subres in result["torrents"]:
                        msg += tr('commands.search.quality_type', quality=subres['quality'], type=subres['type'])
                        msg += tr('commands.search.sub_size', size=subres['size'])
                        if "torrent" in subres.keys():
                            msg += tr('commands.search.sub_direct', torrent=subres['torrent'])
                        elif "magnet" in subres.keys():
                            msg += tr('commands.search.share_magnet')
                            msg += f"<a href='http://t.me/share/url?url={subres['magnet']}'>Telegram</a><br>"
                    msg += "<br>"
                else:
                    msg += tr('commands.search.size', size=result['size'])
                    try:
                        msg += tr('commands.search.api_peers', seeders=result['seeders'], leechers=result['leechers'])
                    except Exception:
                        pass
                    if "torrent" in result.keys():
                        msg += tr('commands.search.api_direct', torrent=result['torrent'])
                    elif "magnet" in result.keys():
                        msg += tr('commands.search.share_magnet')
                        msg += f"<a href='http://t.me/share/url?url={quote(result['magnet'])}'>Telegram</a><br><br>"
                    else:
                        msg += "<br>"
            except Exception:
                continue
        else:
            msg += f"<a href='{result.descrLink}'>{escape(result.fileName)}</a><br>"
            msg += tr('commands.search.plugin_size', size=get_readable_file_size(result.fileSize))
            msg += tr('commands.search.plugin_peers', seeders=result.nbSeeders, leechers=result.nbLeechers)
            link = result.fileUrl
            if link.startswith("magnet:"):
                msg += tr('commands.search.plugin_magnet', magnet=quote(link))
            else:
                msg += tr('commands.search.plugin_direct', link=link)

        if len(msg.encode("utf-8")) > 39000:
            telegraph_content.append(msg)
            msg = ""

        if index == TELEGRAPH_LIMIT:
            break

    if msg != "":
        telegraph_content.append(msg)

    await editMessage(
        tr('commands.search.creating_pages', pages=len(telegraph_content)), message
    )
    path = [
        (
            await telegraph.create_page(
                title=tr('commands.search.page_title'), content=content
            )
        )["path"]
        for content in telegraph_content
    ]
    if len(path) > 1:
        await editMessage(
            tr('commands.search.editing_pages', pages=len(telegraph_content)), message
        )
        await telegraph.edit_telegraph(path, telegraph_content)
    return f"https://telegra.ph/{path[0]}"


async def tmdbSearch(message, id):
    buttons = ButtonMaker()
    user_id = message.from_user.id
    SEARCH_PLUGINS = config_dict["SEARCH_PLUGINS"]
    if SITES is None and not SEARCH_PLUGINS:
        await editMessage(
            tr('commands.search.not_configured'), message
        )
    elif SITES is not None and SEARCH_PLUGINS:
        buttons.cb_buildbutton("Api", f"torser^{user_id}^apisearch^_^{id}")
        buttons.cb_buildbutton(tr('commands.search.plugins', _html=False), f"torser^{user_id}^plugin^_^{id}")
        buttons.cb_buildbutton(tr('commands.button.cancel', _html=False), f"torser^{user_id}^cancel")
        button = buttons.build_menu(2)
        await editMessage(tr('commands.search.tool'), message, button)
    elif SITES is not None:
        button = __api_buttons(user_id, "apisearch", id, True)
        await editMessage(tr('commands.search.api_site'), message, button)
    else:
        button = await _plugin_buttons(user_id, id, True)
        await editMessage(tr('commands.search.plugin_site'), message, button)


async def torrentSearch(_, message):
    user_id = message.from_user.id
    buttons = ButtonMaker()
    key = message.text.split()
    SEARCH_PLUGINS = config_dict["SEARCH_PLUGINS"]
    if SITES is None and not SEARCH_PLUGINS:
        await sendMessage(
            tr('commands.search.not_configured'), message
        )
    elif len(key) == 1 and SITES is None:
        await sendMessage(tr('commands.search.keyword'), message)
    elif len(key) == 1:
        buttons.cb_buildbutton(tr('commands.search.trending', _html=False), f"torser^{user_id}^apitrend")
        buttons.cb_buildbutton(tr('commands.search.recent', _html=False), f"torser^{user_id}^apirecent")
        buttons.cb_buildbutton(tr('commands.button.cancel', _html=False), f"torser^{user_id}^cancel")
        button = buttons.build_menu(2)
        await sendMessage(tr('commands.search.keyword'), message, button)
    elif SITES is not None and SEARCH_PLUGINS:
        buttons.cb_buildbutton("Api", f"torser^{user_id}^apisearch")
        buttons.cb_buildbutton(tr('commands.search.plugins', _html=False), f"torser^{user_id}^plugin")
        buttons.cb_buildbutton(tr('commands.button.cancel', _html=False), f"torser^{user_id}^cancel")
        button = buttons.build_menu(2)
        await sendMessage(tr('commands.search.tool'), message, button)
    elif SITES is not None:
        button = __api_buttons(user_id, "apisearch")
        await sendMessage(tr('commands.search.api_site'), message, button)
    else:
        button = await _plugin_buttons(user_id)
        await sendMessage(tr('commands.search.plugin_site'), message, button)


def __api_buttons(user_id, method, id=None, is_tdmb=False):
    buttons = ButtonMaker()
    for data, name in SITES.items():
        label = tr('commands.search.all', _html=False) if data == "all" else name
        if is_tdmb:
            buttons.cb_buildbutton(label, f"torser^{user_id}^{data}^{method}^{id}")
        else:
            buttons.cb_buildbutton(label, f"torser^{user_id}^{data}^{method}")
    buttons.cb_buildbutton(tr('commands.button.cancel', _html=False), f"torser^{user_id}^cancel")
    return buttons.build_menu(2)


async def _plugin_buttons(user_id, id=None, is_tdmb=False):
    buttons = ButtonMaker()
    if not PLUGINS:
        pl = await TorrentManager.qbittorrent.search.plugins()
        for name in pl:
            PLUGINS.append(name.name)
    for siteName in PLUGINS:
        if is_tdmb:
            buttons.cb_buildbutton(
                siteName.capitalize(), f"torser^{user_id}^{siteName}^plugin^{id}"
            )
        else:
            buttons.cb_buildbutton(
                siteName.capitalize(), f"torser^{user_id}^{siteName}^plugin"
            )
    if is_tdmb:
        buttons.cb_buildbutton(tr('commands.search.all', _html=False), f"torser^{user_id}^all^plugin^{id}")
    else:
        buttons.cb_buildbutton(tr('commands.search.all', _html=False), f"torser^{user_id}^all^plugin")
    buttons.cb_buildbutton(tr('commands.button.cancel', _html=False), f"torser^{user_id}^cancel")
    return buttons.build_menu(2)


async def torrentSearchUpdate(_, query):
    message = query.message
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id
    data = query.data.split("^")
    if len(data) > 4:
        title = tmdb_titles.get(int(data[4]), "")
        key = title
    else:
        key = message.reply_to_message.text.split(maxsplit=1)
        if len(key) > 1:
            key = key[1].strip()
        else:
            key = None
    if user_id != int(data[1]):
        await query.answer(tr('commands.search.not_yours', _html=False), show_alert=True)
    elif data[2].startswith("api"):
        await query.answer()
        if len(data) > 4:
            button = __api_buttons(user_id, data[2], data[4], True)
        else:
            button = __api_buttons(user_id, "apisearch", id, True)
        await editMessage(tr('commands.search.api_site'), message, button)
    elif data[2] == "plugin":
        button = await _plugin_buttons(user_id)
        await editMessage(tr('commands.search.choose_site'), message, button)
    elif data[2] != "cancel":
        await query.answer()
        site = data[2]
        method = data[3]
        if method.startswith("api"):
            if key is None:
                if method == "apirecent":
                    endpoint = tr('commands.search.recent')
                elif method == "apitrend":
                    endpoint = tr('commands.search.trending')
                await editMessage(
                    tr('commands.search.listing', endpoint=endpoint, site_name=tr('commands.search.all') if site == 'all' else SITES.get(site)),
                    message,
                )
            else:
                await editMessage(
                    tr('commands.search.searching_api', query=key, site_name=tr('commands.search.all') if site == 'all' else SITES.get(site)),
                    message,
                )
        else:
            await editMessage(
                tr('commands.search.searching_plugin', query=key, site_name=tr('commands.search.all') if site == 'all' else site.capitalize()),
                message,
            )
        await _search(key, site, message, method)
    else:
        await query.answer()
        await editMessage(tr('commands.search.cancelled'), message)


bot.add_handler(
    MessageHandler(torrentSearch, filters=command(BotCommands.TorrentSearchCommand))
)
bot.add_handler(CallbackQueryHandler(torrentSearchUpdate, filters=regex("^torser")))
