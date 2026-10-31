from bot.i18n import tr, raw
from hashlib import sha256
from http.cookiejar import MozillaCookieJar
from json import loads
from os import path
from re import findall, match, search
from time import sleep
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
from bot.helper.ext_utils.bot_utils import is_share_link, speed_string_to_bytes
from bot.helper.ext_utils.help_messages import PASSWORD_ERROR_MESSAGE
from cloudscraper import create_scraper
from lxml.etree import HTML
from requests import Session, post
from requests import session as req_session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bot import config_dict
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException

_caches = {}


def direct_link_generator(link):
    """direct links generator"""
    domain = urlparse(link).hostname
    if not domain:
        raise DirectDownloadLinkException(tr('helpers.direct.error_invalid_url', _html=False))
    if "youtube.com" in domain or "youtu.be" in domain:
        raise DirectDownloadLinkException(tr('helpers.direct.error_use_ytdl_cmds_for_youtube_links', _html=False))
    elif "mediafire.com" in domain:
        return mediafire(link)
    elif "osdn.net" in domain:
        return osdn(link)
    elif "github.com" in domain:
        return github(link)
    elif "hxfile.co" in domain:
        return hxfile(link)
    elif "1drv.ms" in domain:
        return onedrive(link)
    elif "pixeldrain.com" in domain:
        return pixeldrain(link)
    elif "racaty" in domain:
        return racaty(link)
    elif "1fichier.com" in domain:
        return fichier(link)
    elif "solidfiles.com" in domain:
        return solidfiles(link)
    elif "krakenfiles.com" in domain:
        return krakenfiles(link)
    elif "upload.ee" in domain:
        return uploadee(link)
    elif "gofile.io" in domain:
        return gofile(link)
    elif "send.cm" in domain:
        return send_cm(link)
    elif "easyupload.io" in domain:
        return easyupload(link)
    elif "streamvid.net" in domain:
        return streamvid(link)
    elif "shrdsk.me" in domain:
        return shrdsk(link)
    elif "u.pcloud.link" in domain:
        return pcloud(link)
    elif any(x in domain for x in ["akmfiles.com", "akmfls.xyz"]):
        return akmfiles(link)
    elif any(
        x in domain
        for x in [
            "dood.watch",
            "doodstream.com",
            "dood.to",
            "dood.so",
            "dood.cx",
            "dood.la",
            "dood.ws",
            "dood.sh",
            "doodstream.co",
            "dood.pm",
            "dood.wf",
            "dood.re",
            "dood.video",
            "dooood.com",
            "dood.yt",
            "doods.yt",
            "dood.stream",
            "doods.pro",
            "ds2play.com",
        ]
    ):
        return doods(link)
    elif any(
        x in domain
        for x in [
            "streamtape.com",
            "streamtape.co",
            "streamtape.cc",
            "streamtape.to",
            "streamtape.net",
            "streamta.pe",
            "streamtape.xyz",
        ]
    ):
        return streamtape(link)
    elif any(x in domain for x in ["wetransfer.com", "we.tl"]):
        return wetransfer(link)
    elif any(
        x in domain
        for x in [
            "terabox.com",
            "nephobox.com",
            "4funbox.com",
            "mirrobox.com",
            "momerybox.com",
            "teraboxapp.com",
            "1024tera.com",
            "terabox.app",
        ]
    ):
        return terabox(link)
    elif any(
        x in domain
        for x in [
            "filelions.co",
            "filelions.site",
            "filelions.live",
            "filelions.to",
            "cabecabean.lol",
            "filelions.online",
            "embedwish.com",
            "streamwish.com",
            "kitabmarkaz.xyz",
            "wishfast.top",
            "streamwish.to",
        ]
    ):
        return filelions_and_streamwish(link)
    elif any(x in domain for x in ["streamhub.ink", "streamhub.to"]):
        return streamhub(link)
    elif any(x in domain for x in ["linkbox.to", "lbx.to"]):
        return linkBox(link)
    elif is_share_link(link):
        if "gdtot" in domain:
            return gdtot(link)
        elif "filepress" in domain:
            return filepress(link)
        else:
            return sharer_scraper(link)
    elif any(
        x in domain
        for x in [
            "anonfiles.com",
            "zippyshare.com",
            "letsupload.io",
            "hotfile.io",
            "bayfiles.com",
            "megaupload.nz",
            "letsupload.cc",
            "filechan.org",
            "myfile.is",
            "vshare.is",
            "rapidshare.nu",
            "lolabits.se",
            "openload.cc",
            "share-online.is",
            "upvid.cc",
            "uptobox.com",
            "uptobox.fr",
        ]
    ):
        raise DirectDownloadLinkException(tr('helpers.direct.error_r_i_p', value1=domain, _html=False))
    elif "zowflk.com" in domain or "zowflk.co" in domain:
        return zowflk(link)
    elif "dropbox.com" in domain or "dropboxusercontent.com" in domain:
        return dropbox(link)
    elif "workupload.com" in domain:
        return workupload(link)
    elif "uploadhaven.com" in domain:
        return uploadhaven(link)
    elif "mexa.sh" in domain:
        return mexa_sh(link)
    elif "katfile.com" in domain:
        return katfile(link)
    elif "rockfile.co" in domain:
        return rockfile(link)
    elif "daofile.com" in domain:
        return daofile(link)
    elif "suprafiles.me" in domain or "suprafiles.org" in domain:
        return suprafiles(link)
    elif "shortflix.net" in domain or "shortflix.com" in domain:
        return shortflix(link)
    elif "kickbox.com" in domain or "kickbox.io" in domain:
        return kickbox(link)
    else:
        raise DirectDownloadLinkException(tr('helpers.direct.no_direct_link_function_found_for', value1=link, _html=False))


def get_captcha_token(session, params):
    recaptcha_api = "https://www.google.com/recaptcha/api2"
    res = session.get(f"{recaptcha_api}/anchor", params=params)
    anchor_html = HTML(res.text)
    if not (anchor_token := anchor_html.xpath('//input[@id="recaptcha-token"]/@value')):
        return
    params["c"] = anchor_token[0]
    params["reason"] = "q"
    res = session.post(f"{recaptcha_api}/reload", params=params)
    if token := findall(r'"rresp","(.*?)"', res.text):
        return token[0]


def mediafire(url, session=None):
    if "/folder/" in url:
        return mediafireFolder(url)
    if final_link := findall(
        r"https?:\/\/download\d+\.mediafire\.com\/\S+\/\S+\/\S+", url
    ):
        return final_link[0]
    if session is None:
        session = Session()
        parsed_url = urlparse(url)
        url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    try:
        html = HTML(session.get(url).text)
    except Exception as e:
        session.close()
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if error := html.xpath('//p[@class="notranslate"]/text()'):
        session.close()
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=error[0], _html=False))
    if not (final_link := html.xpath("//a[@id='downloadButton']/@href")):
        session.close()
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_no_links_found_in_this_page_try_again', _html=False)
        )
    if final_link[0].startswith("//"):
        return mediafire(f"https://{final_link[0][2:]}", session)
    session.close()
    return final_link[0]


def osdn(url):
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if not (direct_link := html.xapth('//a[@class="mirror_link"]/@href')):
            raise DirectDownloadLinkException(tr('helpers.direct.error_direct_link_not_found', _html=False))
        return f"https://osdn.net{direct_link[0]}"


def github(url):
    """GitHub direct links generator"""
    try:
        findall(r"\bhttps?://.*github\.com.*releases\S+", url)[0]
    except IndexError:
        raise DirectDownloadLinkException(tr('helpers.direct.no_github_releases_links_found', _html=False))
    with create_scraper() as session:
        _res = session.get(url, stream=True, allow_redirects=False)
        if "location" in _res.headers:
            return _res.headers["location"]
        raise DirectDownloadLinkException(tr('helpers.direct.error_can_t_extract_the_link', _html=False))


def hxfile(url):
    with create_scraper() as session:
        try:
            file_code = url.split("/")[-1]
            html = HTML(
                session.post(url, data={"op": "download2", "id": file_code}).text
            )
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if direct_link := html.xpath('//a[@class="btn btn-dow"]/@href'):
        return direct_link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_direct_download_link_not_found', _html=False))


def onedrive(link):
    """Onedrive direct link generator
    By https://github.com/junedkh"""
    with create_scraper() as session:
        try:
            link = session.get(link).url
            parsed_link = urlparse(link)
            link_data = parse_qs(parsed_link.query)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if not link_data:
            raise DirectDownloadLinkException(tr('helpers.direct.error_unable_to_find_link_data', _html=False))
        folder_id = link_data.get("resid")
        if not folder_id:
            raise DirectDownloadLinkException(tr('helpers.direct.error_folder_id_not_found', _html=False))
        folder_id = folder_id[0]
        authkey = link_data.get("authkey")
        if not authkey:
            raise DirectDownloadLinkException(tr('helpers.direct.error_authkey_not_found', _html=False))
        authkey = authkey[0]
        boundary = uuid4()
        headers = {"content-type": f"multipart/form-data;boundary={boundary}"}
        data = f"--{boundary}\r\nContent-Disposition: form-data;name=data\r\nPrefer: Migration=EnableRedirect;FailOnMigratedFiles\r\nX-HTTP-Method-Override: GET\r\nContent-Type: application/json\r\n\r\n--{boundary}--"
        try:
            resp = session.get(
                f'https://api.onedrive.com/v1.0/drives/{folder_id.split("!", 1)[0]}/items/{folder_id}?$select=id,@content.downloadUrl&ump=1&authKey={authkey}',
                headers=headers,
                data=data,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if "@content.downloadUrl" not in resp:
        raise DirectDownloadLinkException(tr('helpers.direct.error_direct_link_not_found', _html=False))
    return resp["@content.downloadUrl"]


def pixeldrain(url):
    """Based on https://github.com/yash-dk/TorToolkit-Telegram"""
    url = url.strip("/ ")
    file_id = url.split("/")[-1]
    if url.split("/")[-2] == "l":
        info_link = f"https://pixeldrain.com/api/list/{file_id}"
        dl_link = f"https://pixeldrain.com/api/list/{file_id}/zip?download"
    else:
        info_link = f"https://pixeldrain.com/api/file/{file_id}/info"
        dl_link = f"https://pixeldrain.com/api/file/{file_id}?download"
    with create_scraper() as session:
        try:
            resp = session.get(info_link).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if resp["success"]:
        return dl_link
    else:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_cant_t_download_due', value1=resp['message'], _html=False)
        )


def streamtape(url):
    splitted_url = url.split("/")
    _id = splitted_url[4] if len(splitted_url) >= 6 else splitted_url[-1]
    try:
        with Session() as session:
            html = HTML(session.get(url).text)
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if not (script := html.xpath("//script[contains(text(),'ideoooolink')]/text()")):
        raise DirectDownloadLinkException(tr('helpers.direct.error_requeries_script_not_found', _html=False))
    if not (link := findall(r"(&expires\S+)'", script[0])):
        raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))
    return f"https://streamtape.com/get_video?id={_id}{link[-1]}"


def racaty(url):
    with create_scraper() as session:
        try:
            url = session.get(url).url
            json_data = {"op": "download2", "id": url.split("/")[-1]}
            html = HTML(session.post(url, data=json_data).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if direct_link := html.xpath("//a[@id='uniqueExpirylink']/@href"):
        return direct_link[0]
    else:
        raise DirectDownloadLinkException(tr('helpers.direct.error_direct_link_not_found', _html=False))


def fichier(link):
    """1Fichier direct link generator
    Based on https://github.com/Maujar
    """
    regex = r"^([http:\/\/|https:\/\/]+)?.*1fichier\.com\/\?.+"
    gan = match(regex, link)
    if not gan:
        raise DirectDownloadLinkException(tr('helpers.direct.error_the_link_you_entered_is_wrong', _html=False))
    if "::" in link:
        pswd = link.split("::")[-1]
        url = link.split("::")[-2]
    else:
        pswd = None
        url = link
    cget = create_scraper().request
    try:
        if pswd is None:
            req = cget("post", url)
        else:
            pw = {"pass": pswd}
            req = cget("post", url, data=pw)
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if req.status_code == 404:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_file_not_found_the_link_you_entered_is_wrong', _html=False)
        )
    html = HTML(req.text)
    if dl_url := html.xpath('//a[@class="ok btn-general btn-orange"]/@href'):
        return dl_url[0]
    if not (ct_warn := html.xpath('//div[@class="ct_warn"]')):
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_error_trying_to_generate_direct_link_from_1fichier', _html=False)
        )
    if len(ct_warn) == 3:
        str_2 = ct_warn[-1].text
        if "you must wait" in str_2.lower():
            if numbers := [int(word) for word in str_2.split() if word.isdigit()]:
                raise DirectDownloadLinkException(
                    tr('helpers.direct.error_1fichier_is_on_a_limit_please_wait_minute', value1=numbers[0], _html=False)
                )
            else:
                raise DirectDownloadLinkException(
                    tr('helpers.direct.error_1fichier_is_on_a_limit_please_wait_a_few_minutes_hour', _html=False)
                )
        elif "protect access" in str_2.lower():
            raise DirectDownloadLinkException(
                raw(f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(link)}")
            )
        else:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_failed_to_generate_direct_link_from_1fichier', _html=False)
            )
    elif len(ct_warn) == 4:
        str_1 = ct_warn[-2].text
        str_3 = ct_warn[-1].text
        if "you must wait" in str_1.lower():
            if numbers := [int(word) for word in str_1.split() if word.isdigit()]:
                raise DirectDownloadLinkException(
                    tr('helpers.direct.error_1fichier_is_on_a_limit_please_wait_minute', value1=numbers[0], _html=False)
                )
            else:
                raise DirectDownloadLinkException(
                    tr('helpers.direct.error_1fichier_is_on_a_limit_please_wait_a_few_minutes_hour', _html=False)
                )
        elif "bad password" in str_3.lower():
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_the_password_you_entered_is_wrong', _html=False)
            )
    raise DirectDownloadLinkException(
        tr('helpers.direct.error_error_trying_to_generate_direct_link_from_1fichier', _html=False)
    )


def solidfiles(url):
    """Solidfiles direct link generator
    Based on https://github.com/Xonshiz/SolidFiles-Downloader
    By https://github.com/Jusidama18"""
    with create_scraper() as session:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.125 Safari/537.36"
            }
            pageSource = session.get(url, headers=headers).text
            mainOptions = str(
                search(r"viewerOptions\'\,\ (.*?)\)\;", pageSource).group(1)
            )
            return loads(mainOptions)["downloadUrl"]
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))


def krakenfiles(url):
    with Session() as session:
        try:
            _res = session.get(url)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        html = HTML(_res.text)
        if post_url := html.xpath('//form[@id="dl-form"]/@action'):
            post_url = f"https:{post_url[0]}"
        else:
            raise DirectDownloadLinkException(tr('helpers.direct.error_unable_to_find_post_link', _html=False))
        if token := html.xpath('//input[@id="dl-token"]/@value'):
            data = {"token": token[0]}
        else:
            raise DirectDownloadLinkException(tr('helpers.direct.error_unable_to_find_token_for_post', _html=False))
        try:
            _json = session.post(post_url, data=data).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_while_send_post_request', value1=e.__class__.__name__, _html=False)
            )
    if _json["status"] != "ok":
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_unable_to_find_download_after_post_request', _html=False)
        )
    return _json["url"]


def uploadee(url):
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[@id='d_l']/@href"):
        return link[0]
    else:
        raise DirectDownloadLinkException(tr('helpers.direct.uploadee_link_missing', _html=False))


def terabox(url):
    if not path.isfile("terabox.txt"):
        raise DirectDownloadLinkException(tr('helpers.direct.error_terabox_txt_not_found', _html=False))
    try:
        jar = MozillaCookieJar("terabox.txt")
        jar.load()
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    cookies = {}
    for cookie in jar:
        cookies[cookie.name] = cookie.value
    details = {"contents": [], "title": "", "total_size": 0}
    details["header"] = " ".join(f"{key}: {value}" for key, value in cookies.items())

    def __fetch_links(session, dir_="", folderPath=""):
        params = {"app_id": "250528", "jsToken": jsToken, "shorturl": shortUrl}
        if dir_:
            params["dir"] = dir_
        else:
            params["root"] = "1"
        try:
            _json = session.get(
                "https://www.1024tera.com/share/list", params=params, cookies=cookies
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if _json["errno"] not in [0, "0"]:
            if "errmsg" in _json:
                raise DirectDownloadLinkException(tr('helpers.direct.error', value1=_json['errmsg'], _html=False))
            else:
                raise DirectDownloadLinkException(tr('helpers.direct.terabox_response_invalid', _html=False))

        if "list" not in _json:
            return
        contents = _json["list"]
        for content in contents:
            if content["isdir"] in ["1", 1]:
                if not folderPath:
                    if not details["title"]:
                        details["title"] = content["server_filename"]
                        newFolderPath = path.join(details["title"])
                    else:
                        newFolderPath = path.join(
                            details["title"], content["server_filename"]
                        )
                else:
                    newFolderPath = path.join(folderPath, content["server_filename"])
                __fetch_links(session, content["path"], newFolderPath)
            else:
                if not folderPath:
                    if not details["title"]:
                        details["title"] = content["server_filename"]
                    folderPath = details["title"]
                item = {
                    "url": content["dlink"],
                    "filename": content["server_filename"],
                    "path": path.join(folderPath),
                }
                if "size" in content:
                    size = content["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    with Session() as session:
        try:
            _res = session.get(url, cookies=cookies)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if jsToken := findall(r"window\.jsToken.*%22(.*)%22", _res.text):
            jsToken = jsToken[0]
        else:
            raise DirectDownloadLinkException(tr('helpers.direct.error_jstoken_not_found', _html=False))
        shortUrl = parse_qs(urlparse(_res.url).query).get("surl")
        if not shortUrl:
            raise DirectDownloadLinkException(tr('helpers.direct.error_could_not_find_surl', _html=False))
        try:
            __fetch_links(session)
        except Exception as e:
            raise DirectDownloadLinkException(e)
    if len(details["contents"]) == 1:
        return details["contents"][0]["url"]
    return details


def filepress(url):
    with create_scraper() as session:
        try:
            url = session.get(url).url
            raw = urlparse(url)
            json_data = {
                "id": raw.path.split("/")[-1],
                "method": "publicDownlaod",
            }
            api = f"{raw.scheme}://{raw.hostname}/api/file/downlaod/"
            res2 = session.post(
                api,
                headers={"Referer": f"{raw.scheme}://{raw.hostname}"},
                json=json_data,
            ).json()
            json_data2 = {
                "id": res2["data"],
                "method": "publicUserDownlaod",
            }
            api2 = "https://new2.filepress.store/api/file/downlaod2/"
            res = session.post(
                api2,
                headers={"Referer": f"{raw.scheme}://{raw.hostname}"},
                json=json_data2,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if "data" not in res:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=res['statusText'], _html=False))
    return f'https://drive.google.com/uc?id={res["data"]}&export=download'


def gdtot(url):
    cget = create_scraper().request
    try:
        res = cget("GET", f'https://gdtot.pro/file/{url.split("/")[-1]}')
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    token_url = HTML(res.text).xpath(
        "//a[contains(@class,'inline-flex items-center justify-center')]/@href"
    )
    if not token_url:
        try:
            url = cget("GET", url).url
            p_url = urlparse(url)
            res = cget(
                "GET", f"{p_url.scheme}://{p_url.hostname}/ddl/{url.split('/')[-1]}"
            )
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if (
            drive_link := findall(r"myDl\('(.*?)'\)", res.text)
        ) and "drive.google.com" in drive_link[0]:
            return drive_link[0]
        else:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_drive_link_not_found_try_in_your_broswer', _html=False)
            )
    token_url = token_url[0]
    try:
        token_page = cget("GET", token_url)
    except Exception as e:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_with', value1=e.__class__.__name__, value2=token_url, _html=False)
        )
    path = findall(r'\("(.*?)"\)', token_page.text)
    if not path:
        raise DirectDownloadLinkException(tr('helpers.direct.error_cannot_bypass_this', _html=False))
    path = path[0]
    raw = urlparse(token_url)
    final_url = f"{raw.scheme}://{raw.hostname}{path}"
    return sharer_scraper(final_url)


def sharer_scraper(url):
    cget = create_scraper().request
    try:
        url = cget("GET", url).url
        raw = urlparse(url)
        header = {
            "useragent": "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.10 (KHTML, like Gecko) Chrome/7.0.548.0 Safari/534.10"
        }
        res = cget("GET", url, headers=header)
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    key = findall(r'"key",\s+"(.*?)"', res.text)
    if not key:
        raise DirectDownloadLinkException(tr('helpers.direct.error_key_not_found', _html=False))
    key = key[0]
    if not HTML(res.text).xpath("//button[@id='drc']"):
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_this_link_don_t_have_direct_download_button', _html=False)
        )
    boundary = uuid4()
    headers = {
        "Content-Type": f"multipart/form-data; boundary=----WebKitFormBoundary{boundary}",
        "x-token": raw.hostname,
        "useragent": "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/534.10 (KHTML, like Gecko) Chrome/7.0.548.0 Safari/534.10",
    }

    data = (
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="action"\r\n\r\ndirect\r\n'
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="key"\r\n\r\n{key}\r\n'
        f'------WebKitFormBoundary{boundary}\r\nContent-Disposition: form-data; name="action_token"\r\n\r\n\r\n'
        f"------WebKitFormBoundary{boundary}--\r\n"
    )
    try:
        res = cget("POST", url, cookies=res.cookies, headers=headers, data=data).json()
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if "url" not in res:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_drive_link_not_found_try_in_your_broswer', _html=False)
        )
    if "drive.google.com" in res["url"]:
        return res["url"]
    try:
        res = cget("GET", res["url"])
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if (
        drive_link := HTML(res.text).xpath("//a[contains(@class,'btn')]/@href")
    ) and "drive.google.com" in drive_link[0]:
        return drive_link[0]
    else:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_drive_link_not_found_try_in_your_broswer', _html=False)
        )


def wetransfer(url):
    with create_scraper() as session:
        try:
            url = session.get(url).url
            splited_url = url.split("/")
            json_data = {"security_hash": splited_url[-1], "intent": "entire_transfer"}
            res = session.post(
                f"https://wetransfer.com/api/v4/transfers/{splited_url[-2]}/download",
                json=json_data,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if "direct_link" in res:
        return res["direct_link"]
    elif "message" in res:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=res['message'], _html=False))
    elif "error" in res:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=res['error'], _html=False))
    else:
        raise DirectDownloadLinkException(tr('helpers.direct.error_cannot_find_direct_link', _html=False))


def akmfiles(url):
    with create_scraper() as session:
        try:
            html = HTML(
                session.post(
                    url, data={"op": "download2", "id": url.split("/")[-1]}
                ).text
            )
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if direct_link := html.xpath("//a[contains(@class,'btn btn-dow')]/@href"):
        return direct_link[0]
    else:
        raise DirectDownloadLinkException(tr('helpers.direct.error_direct_link_not_found', _html=False))


def shrdsk(url):
    with create_scraper() as session:
        try:
            _json = session.get(
                f'https://us-central1-affiliate2apk.cloudfunctions.net/get_data?shortid={url.split("/")[-1]}'
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if "download_data" not in _json:
            raise DirectDownloadLinkException(tr('helpers.direct.error_download_data_not_found', _html=False))
        try:
            _res = session.get(
                f"https://shrdsk.me/download/{_json['download_data']}",
                allow_redirects=False,
            )
            if "Location" in _res.headers:
                return _res.headers["Location"]
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    raise DirectDownloadLinkException(tr('helpers.direct.error_cannot_find_direct_link_in_headers', _html=False))


def linkBox(url: str):
    parsed_url = urlparse(url)
    try:
        shareToken = parsed_url.path.split("/")[-1]
    except Exception:
        raise DirectDownloadLinkException(tr('helpers.direct.linkbox_url_invalid', _html=False))

    details = {"contents": [], "title": "", "total_size": 0}

    def __singleItem(session, itemId):
        try:
            _json = session.get(
                "https://www.linkbox.to/api/file/detail", params={"itemId": itemId}
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        data = _json["data"]
        if not data:
            if "msg" in _json:
                raise DirectDownloadLinkException(tr('helpers.direct.error', value1=_json['msg'], _html=False))
            raise DirectDownloadLinkException(tr('helpers.direct.error_data_not_found', _html=False))
        itemInfo = data["itemInfo"]
        if not itemInfo:
            raise DirectDownloadLinkException(tr('helpers.direct.error_iteminfo_not_found', _html=False))
        filename = itemInfo["name"]
        sub_type = itemInfo.get("sub_type")
        if sub_type and not filename.endswith(sub_type):
            filename += f".{sub_type}"
        if not details["title"]:
            details["title"] = filename
        item = {
            "path": "",
            "filename": filename,
            "url": itemInfo["url"],
        }
        if "size" in itemInfo:
            size = itemInfo["size"]
            if isinstance(size, str) and size.isdigit():
                size = float(size)
            details["total_size"] += size
        details["contents"].append(item)

    def __fetch_links(session, _id=0, folderPath=""):
        params = {
            "shareToken": shareToken,
            "pageSize": 1000,
            "pid": _id,
        }
        try:
            _json = session.get(
                "https://www.linkbox.to/api/file/share_out_list", params=params
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        data = _json["data"]
        if not data:
            if "msg" in _json:
                raise DirectDownloadLinkException(tr('helpers.direct.error', value1=_json['msg'], _html=False))
            raise DirectDownloadLinkException(tr('helpers.direct.error_data_not_found', _html=False))
        if data["shareType"] == "singleItem":
            return __singleItem(session, data["itemId"])
        if not details["title"]:
            details["title"] = data["dirName"]
        contents = data["list"]
        if not contents:
            return
        for content in contents:
            if content["type"] == "dir" and "url" not in content:
                if not folderPath:
                    newFolderPath = path.join(details["title"], content["name"])
                else:
                    newFolderPath = path.join(folderPath, content["name"])
                if not details["title"]:
                    details["title"] = content["name"]
                __fetch_links(session, content["id"], newFolderPath)
            elif "url" in content:
                if not folderPath:
                    folderPath = details["title"]
                filename = content["name"]
                if (sub_type := content.get("sub_type")) and not filename.endswith(
                    sub_type
                ):
                    filename += f".{sub_type}"
                item = {
                    "path": path.join(folderPath),
                    "filename": filename,
                    "url": content["url"],
                }
                if "size" in content:
                    size = content["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    try:
        with Session() as session:
            __fetch_links(session)
    except DirectDownloadLinkException as e:
        raise e
    return details


def gofile(url):
    try:
        if "::" in url:
            _password = url.split("::")[-1]
            _password = sha256(_password.encode("utf-8")).hexdigest()
            url = url.split("::")[-2]
        else:
            _password = ""
        _id = url.split("/")[-1]
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))

    def __get_token(session):
        if "gofile_token" in _caches:
            __url = f"https://api.gofile.io/getAccountDetails?token={_caches['gofile_token']}"
        else:
            __url = "https://api.gofile.io/createAccount"
        try:
            __res = session.get(__url, verify=False).json()
            if __res["status"] != "ok":
                if "gofile_token" in _caches:
                    del _caches["gofile_token"]
                return __get_token(session)
            _caches["gofile_token"] = __res["data"]["token"]
            return _caches["gofile_token"]
        except Exception as e:
            raise e

    def __fetch_links(session, _id, folderPath=""):
        _url = f"https://api.gofile.io/getContent?contentId={_id}&token={token}&websiteToken=7fd94ds12fds4&cache=true"
        if _password:
            _url += f"&password={_password}"
        try:
            _json = session.get(_url, verify=False).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if _json["status"] in "error-passwordRequired":
            raise DirectDownloadLinkException(
                raw(f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}")
            )
        if _json["status"] in "error-passwordWrong":
            raise DirectDownloadLinkException(tr('helpers.direct.error_this_password_is_wrong', _html=False))
        if _json["status"] in "error-notFound":
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_file_not_found_on_gofile_s_server', _html=False)
            )
        if _json["status"] in "error-notPublic":
            raise DirectDownloadLinkException(tr('helpers.direct.error_this_folder_is_not_public', _html=False))

        data = _json["data"]

        if not details["title"]:
            details["title"] = data["name"] if data["type"] == "folder" else _id

        contents = data["contents"]
        for content in contents.values():
            if content["type"] == "folder":
                if not content["public"]:
                    continue
                if not folderPath:
                    newFolderPath = path.join(details["title"], content["name"])
                else:
                    newFolderPath = path.join(folderPath, content["name"])
                __fetch_links(session, content["id"], newFolderPath)
            else:
                if not folderPath:
                    folderPath = details["title"]
                item = {
                    "path": path.join(folderPath),
                    "filename": content["name"],
                    "url": content["link"],
                }
                if "size" in content:
                    size = content["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    details = {"contents": [], "title": "", "total_size": 0}
    with Session() as session:
        try:
            token = __get_token(session)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        details["header"] = f"Cookie: accountToken={token}"
        try:
            __fetch_links(session, _id)
        except Exception as e:
            raise DirectDownloadLinkException(e)

    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], details["header"])
    return details


def mediafireFolder(url):
    try:
        raw = url.split("/", 4)[-1]
        folderkey = raw.split("/", 1)[0]
        folderkey = folderkey.split(",")
    except Exception:
        raise DirectDownloadLinkException(tr('helpers.direct.error_could_not_parse', _html=False))
    if len(folderkey) == 1:
        folderkey = folderkey[0]
    details = {"contents": [], "title": "", "total_size": 0, "header": ""}

    session = req_session()
    adapter = HTTPAdapter(
        max_retries=Retry(total=10, read=10, connect=10, backoff_factor=0.3)
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session = create_scraper(
        browser={"browser": "firefox", "platform": "windows", "mobile": False},
        delay=10,
        sess=session,
    )
    folder_infos = []

    def __get_info(folderkey):
        try:
            if isinstance(folderkey, list):
                folderkey = ",".join(folderkey)
            _json = session.post(
                "https://www.mediafire.com/api/1.5/folder/get_info.php",
                data={
                    "recursive": "yes",
                    "folder_key": folderkey,
                    "response_format": "json",
                },
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_while_getting_info', value1=e.__class__.__name__, _html=False)
            )
        _res = _json["response"]
        if "folder_infos" in _res:
            folder_infos.extend(_res["folder_infos"])
        elif "folder_info" in _res:
            folder_infos.append(_res["folder_info"])
        elif "message" in _res:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=_res['message'], _html=False))
        else:
            raise DirectDownloadLinkException(tr('helpers.direct.folder_response_invalid', _html=False))

    try:
        __get_info(folderkey)
    except Exception as e:
                    raise DirectDownloadLinkException(e)

    details["title"] = folder_infos[0]["name"]

    def __scraper(url):
        try:
            html = HTML(session.get(url).text)
        except Exception:
            return
        if final_link := html.xpath("//a[@id='downloadButton']/@href"):
            return final_link[0]

    def __get_content(folderKey, folderPath="", content_type="folders"):
        try:
            params = {
                "content_type": content_type,
                "folder_key": folderKey,
                "response_format": "json",
            }
            _json = session.get(
                "https://www.mediafire.com/api/1.5/folder/get_content.php",
                params=params,
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_while_getting_content', value1=e.__class__.__name__, _html=False)
            )
        _res = _json["response"]
        if "message" in _res:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=_res['message'], _html=False))
        _folder_content = _res["folder_content"]
        if content_type == "folders":
            folders = _folder_content["folders"]
            for folder in folders:
                if folderPath:
                    newFolderPath = path.join(folderPath, folder["name"])
                else:
                    newFolderPath = path.join(folder["name"])
                __get_content(folder["folderkey"], newFolderPath)
            __get_content(folderKey, folderPath, "files")
        else:
            files = _folder_content["files"]
            for file in files:
                item = {}
                if not (_url := __scraper(file["links"]["normal_download"])):
                    continue
                item["filename"] = file["filename"]
                if not folderPath:
                    folderPath = details["title"]
                item["path"] = path.join(folderPath)
                item["url"] = _url
                if "size" in file:
                    size = file["size"]
                    if isinstance(size, str) and size.isdigit():
                        size = float(size)
                    details["total_size"] += size
                details["contents"].append(item)

    try:
        for folder in folder_infos:
            __get_content(folder["folderkey"], folder["name"])
    except Exception as e:
                raise DirectDownloadLinkException(e)
    finally:
        session.close()
    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], details["header"])
    return details


def cf_bypass(url):
    "DO NOT ABUSE THIS"
    try:
        data = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
        _json = post(
            "https://cf.jmdkh.eu.org/v1",
            headers={"Content-Type": "application/json"},
            json=data,
        ).json()
        if _json["status"] == "ok":
            return _json["solution"]["response"]
    except Exception as e:
        e
    raise DirectDownloadLinkException(tr('helpers.direct.error_con_t_bypass_cloudflare', _html=False))


def send_cm_file(url, file_id=None):
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ""
    _passwordNeed = False
    with create_scraper() as session:
        if file_id is None:
            try:
                html = HTML(session.get(url).text)
            except Exception as e:
                raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
            if html.xpath("//input[@name='password']"):
                _passwordNeed = True
            if not (file_id := html.xpath("//input[@name='id']/@value")):
                raise DirectDownloadLinkException(tr('helpers.direct.error_file_id_not_found', _html=False))
        try:
            data = {"op": "download2", "id": file_id}
            if _password and _passwordNeed:
                data["password"] = _password
            _res = session.post("https://send.cm/", data=data, allow_redirects=False)
            if "Location" in _res.headers:
                return (_res.headers["Location"], "Referer: https://send.cm/")
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if _passwordNeed:
            raise DirectDownloadLinkException(
                raw(f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}")
            )
        raise DirectDownloadLinkException(tr('helpers.direct.error_direct_link_not_found', _html=False))


def send_cm(url):
    if "/d/" in url:
        return send_cm_file(url)
    elif "/s/" not in url:
        file_id = url.split("/")[-1]
        return send_cm_file(url, file_id)
    splitted_url = url.split("/")
    details = {
        "contents": [],
        "title": "",
        "total_size": 0,
        "header": "Referer: https://send.cm/",
    }
    if len(splitted_url) == 5:
        url += "/"
        splitted_url = url.split("/")
    if len(splitted_url) >= 7:
        details["title"] = splitted_url[5]
    else:
        details["title"] = splitted_url[-1]
    session = Session()

    def __collectFolders(html):
        folders = []
        folders_urls = html.xpath("//h6/a/@href")
        folders_names = html.xpath("//h6/a/text()")
        for folders_url, folders_name in zip(folders_urls, folders_names):
            folders.append(
                {
                    "folder_link": folders_url.strip(),
                    "folder_name": folders_name.strip(),
                }
            )
        return folders

    def __getFile_link(file_id):
        try:
            _res = session.post(
                "https://send.cm/",
                data={"op": "download2", "id": file_id},
                allow_redirects=False,
            )
            if "Location" in _res.headers:
                return _res.headers["Location"]
        except Exception:
            pass

    def __getFiles(html):
        files = []
        hrefs = html.xpath('//tr[@class="selectable"]//a/@href')
        file_names = html.xpath('//tr[@class="selectable"]//a/text()')
        sizes = html.xpath('//tr[@class="selectable"]//span/text()')
        for href, file_name, size_text in zip(hrefs, file_names, sizes):
            files.append(
                {
                    "file_id": href.split("/")[-1],
                    "file_name": file_name.strip(),
                    "size": speed_string_to_bytes(size_text.strip()),
                }
            )
        return files

    def __writeContents(html_text, folderPath=""):
        folders = __collectFolders(html_text)
        for folder in folders:
            _html = HTML(cf_bypass(folder["folder_link"]))
            __writeContents(_html, path.join(folderPath, folder["folder_name"]))
        files = __getFiles(html_text)
        for file in files:
            if not (link := __getFile_link(file["file_id"])):
                continue
            item = {"url": link, "filename": file["filename"], "path": folderPath}
            details["total_size"] += file["size"]
            details["contents"].append(item)

    try:
        mainHtml = HTML(cf_bypass(url))
    except DirectDownloadLinkException as e:
        session.close()
        raise e
    except Exception as e:
        session.close()
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_while_getting_mainhtml', value1=e.__class__.__name__, _html=False)
        )
    try:
        __writeContents(mainHtml, details["title"])
    except DirectDownloadLinkException as e:
        session.close()
        raise e
    except Exception as e:
        session.close()
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_while_writing_contents', value1=e.__class__.__name__, _html=False)
        )
    session.close()
    if len(details["contents"]) == 1:
        return (details["contents"][0]["url"], details["header"])
    return details


def doods(url):
    if "/e/" in url:
        url = url.replace("/e/", "/d/")
    parsed_url = urlparse(url)
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_while_fetching_token_link', value1=e.__class__.__name__, _html=False)
            )
        if not (link := html.xpath("//div[@class='download-content']//a/@href")):
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_token_link_not_found_or_maybe_not_allow_to_download_open', _html=False)
            )
        link = f"{parsed_url.scheme}://{parsed_url.hostname}{link[0]}"
        sleep(2)
        try:
            _res = session.get(link)
        except Exception as e:
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_while_fetching_download_link', value1=e.__class__.__name__, _html=False)
            )
    if not (link := search(r"window\.open\('(\S+)'", _res.text)):
        raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found_try_again', _html=False))
    return (link.group(1), f"Referer: {parsed_url.scheme}://{parsed_url.hostname}/")


def easyupload(url):
    if "::" in url:
        _password = url.split("::")[-1]
        url = url.split("::")[-2]
    else:
        _password = ""
    file_id = url.split("/")[-1]
    with create_scraper() as session:
        try:
            _res = session.get(url)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        first_page_html = HTML(_res.text)
        if (
            first_page_html.xpath("//h6[contains(text(),'Password Protected')]")
            and not _password
        ):
            raise DirectDownloadLinkException(
                raw(f"ERROR:\n{PASSWORD_ERROR_MESSAGE.format(url)}")
            )
        if not (
            match := search(
                r"https://eu(?:[1-9][0-9]?|100)\.easyupload\.io/action\.php", _res.text
            )
        ):
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_failed_to_get_server_for_easyupload_link', _html=False)
            )
        action_url = match.group()
        session.headers.update({"referer": "https://easyupload.io/"})
        recaptcha_params = {
            "k": "6LfWajMdAAAAAGLXz_nxz2tHnuqa-abQqC97DIZ3",
            "ar": "1",
            "co": "aHR0cHM6Ly9lYXN5dXBsb2FkLmlvOjQ0Mw..",
            "hl": "en",
            "v": "0hCdE87LyjzAkFO5Ff-v7Hj1",
            "size": "invisible",
            "cb": "c3o1vbaxbmwe",
        }
        if not (captcha_token := get_captcha_token(session, recaptcha_params)):
            raise DirectDownloadLinkException(tr('helpers.direct.error_captcha_token_not_found', _html=False))
        try:
            data = {
                "type": "download-token",
                "url": file_id,
                "value": _password,
                "captchatoken": captcha_token,
                "method": "regular",
            }
            json_resp = session.post(url=action_url, data=data).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if "download_link" in json_resp:
        return json_resp["download_link"]
    elif "data" in json_resp:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_failed_to_generate_direct_link_due_to', value1=json_resp['data'], _html=False)
        )
    raise DirectDownloadLinkException(
        tr('helpers.direct.error_failed_to_generate_direct_link_from_easyupload', _html=False)
    )


def filelions_and_streamwish(url):
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    scheme = parsed_url.scheme
    if any(
        x in hostname
        for x in [
            "filelions.co",
            "filelions.live",
            "filelions.to",
            "filelions.site",
            "cabecabean.lol",
            "filelions.online",
        ]
    ):
        apiKey = config_dict["FILELION_API"]
        apiUrl = "https://api.filelions.co"
    elif any(
        x in hostname
        for x in [
            "embedwish.com",
            "streamwish.com",
            "kitabmarkaz.xyz",
            "wishfast.top",
            "streamwish.to",
        ]
    ):
        apiKey = config_dict["STREAMWISH_API"]
        apiUrl = "https://api.streamwish.com"
    if not apiKey:
        raise DirectDownloadLinkException(
            tr('helpers.direct.error_api_is_not_provided_get_it_from', value1=scheme, value2=hostname, _html=False)
        )
    file_code = url.split("/")[-1]
    quality = ""
    if bool(file_code.endswith(("_o", "_h", "_n", "_l"))):
        spited_file_code = file_code.rsplit("_", 1)
        quality = spited_file_code[1]
        file_code = spited_file_code[0]
    url = f"{scheme}://{hostname}/{file_code}"
    with Session() as session:
        try:
            _res = session.get(
                f"{apiUrl}/api/file/direct_link",
                params={"key": apiKey, "file_code": file_code, "hls": "1"},
            ).json()
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if _res["status"] != 200:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=_res['msg'], _html=False))
    result = _res["result"]
    if not result["versions"]:
        raise DirectDownloadLinkException(tr('helpers.direct.error_file_not_found', _html=False))
    error = tr('helpers.direct.provide_a_quality_to_download_the_video_available_quality', _html=False)
    for version in result["versions"]:
        if quality == version["name"]:
            return version["url"]
        elif version["name"] == "l":
            error += tr('helpers.direct.low', _html=False)
        elif version["name"] == "n":
            error += tr('helpers.direct.normal', _html=False)
        elif version["name"] == "o":
            error += tr('helpers.direct.original', _html=False)
        elif version["name"] == "h":
            error += tr('helpers.direct.hd', _html=False)
        error += f" <code>{url}_{version['name']}</code>"
    raise DirectDownloadLinkException(tr('helpers.direct.error', value1=error, _html=False))


def streamvid(url: str):
    file_code = url.split("/")[-1]
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.hostname}/d/{file_code}"
    quality_defined = bool(url.endswith(("_o", "_h", "_n", "_l")))
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if quality_defined:
            data = {}
            if not (inputs := html.xpath('//form[@id="F1"]//input')):
                raise DirectDownloadLinkException(tr('helpers.direct.error_no_inputs_found', _html=False))
            for i in inputs:
                if key := i.get("name"):
                    data[key] = i.get("value")
            try:
                html = HTML(session.post(url, data=data).text)
            except Exception as e:
                raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
            if not (
                script := html.xpath(
                    '//script[contains(text(),"document.location.href")]/text()'
                )
            ):
                if error := html.xpath(
                    '//div[@class="alert alert-danger"][1]/text()[2]'
                ):
                    raise DirectDownloadLinkException(tr('helpers.direct.error', value1=error[0], _html=False))
                raise DirectDownloadLinkException(
                    tr('helpers.direct.error_direct_link_script_not_found', _html=False)
                )
            if directLink := findall(r'document\.location\.href="(.*)"', script[0]):
                return directLink[0]
            raise DirectDownloadLinkException(
                tr('helpers.direct.error_direct_link_not_found_in_the_script', _html=False)
            )
        elif (qualities_urls := html.xpath('//div[@id="dl_versions"]/a/@href')) and (
            qualities := html.xpath('//div[@id="dl_versions"]/a/text()[2]')
        ):
            error = tr('helpers.direct.provide_a_quality_to_download_the_video_available_quality', _html=False)
            for quality_url, quality in zip(qualities_urls, qualities):
                error += f"\n{quality.strip()} <code>{quality_url}</code>"
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=error, _html=False))
        elif error := html.xpath('//div[@class="not-found-text"]/text()'):
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=error[0], _html=False))
        raise DirectDownloadLinkException(tr('helpers.direct.error_something_went_wrong', _html=False))


def streamhub(url):
    file_code = url.split("/")[-1]
    parsed_url = urlparse(url)
    url = f"{parsed_url.scheme}://{parsed_url.hostname}/d/{file_code}"
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if not (inputs := html.xpath('//form[@name="F1"]//input')):
            raise DirectDownloadLinkException(tr('helpers.direct.error_no_inputs_found', _html=False))
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value")
        session.headers.update({"referer": url})
        sleep(1)
        try:
            html = HTML(session.post(url, data=data).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
        if directLink := html.xpath(
            '//a[@class="btn btn-primary btn-go downloadbtn"]/@href'
        ):
            return directLink[0]
        if error := html.xpath('//div[@class="alert alert-danger"]/text()[2]'):
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=error[0], _html=False))
        raise DirectDownloadLinkException(tr('helpers.direct.streamhub_link_missing', _html=False))


def pcloud(url):
    with create_scraper() as session:
        try:
            res = session.get(url)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := findall(r".downloadlink.:..(https:.*)..", res.text):
        return link[0].replace(r"\/", "/")
    raise DirectDownloadLinkException(tr('helpers.direct.error_direct_link_not_found', _html=False))


def zowflk(url):
    """Zowflk direct link generator"""
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if script := html.xpath("//script[contains(text(),'sources')]/text()"):
        if link := findall(r'"file":"([^"]+)"', script[0]):
            return link[0].replace("\\", "")
    raise DirectDownloadLinkException(tr('helpers.direct.error_video_link_not_found', _html=False))


def dropbox(url):
    """Dropbox direct link generator"""
    try:
        if "?dl=0" in url:
            return url.replace("?dl=0", "?dl=1")
        elif "?dl=1" not in url:
            return f"{url}?dl=1"
        return url
    except Exception as e:
        raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))


def workupload(url):
    """Workupload direct link generator"""
    with create_scraper() as session:
        try:
            file_id = url.split("/")[-1]
            html = HTML(session.get(f"https://workupload.com/file/{file_id}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if script := html.xpath("//script[contains(text(),'fileUrl')]/text()"):
        if link := findall(r'"fileUrl":"([^"]+)"', script[0]):
            return link[0].replace("\\", "")
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def uploadhaven(url):
    """Uploadhaven direct link generator"""
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
            if form := html.xpath("//form[@id='downloadForm']"):
                inputs = html.xpath("//form[@id='downloadForm']//input")
                data = {}
                for i in inputs:
                    if key := i.get("name"):
                        data[key] = i.get("value", "")
                sleep(5)
                res = session.post(url, data=data)
                html = HTML(res.text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[@class='btn btn-primary btn-lg']/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def mexa_sh(url):
    """Mexa.sh direct link generator"""
    with create_scraper() as session:
        try:
            file_code = url.split("/")[-1]
            html = HTML(session.get(f"https://mexa.sh/{file_code}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if form := html.xpath("//form[@name='F1']"):
        inputs = html.xpath("//form[@name='F1']//input")
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value", "")
        try:
            sleep(3)
            res = session.post(url, data=data)
            html = HTML(res.text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[contains(@class,'btn-download')]/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def katfile(url):
    """Katfile direct link generator"""
    with create_scraper() as session:
        try:
            file_id = url.split("/")[-1]
            html = HTML(session.get(f"https://katfile.com/{file_id}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if form := html.xpath("//form[@name='F1']"):
        inputs = html.xpath("//form[@name='F1']//input")
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value", "")
        try:
            sleep(3)
            res = session.post(url, data=data)
            html = HTML(res.text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[contains(@class,'btn-download')]/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def rockfile(url):
    """Rockfile direct link generator"""
    with create_scraper() as session:
        try:
            file_id = url.split("/")[-1]
            html = HTML(session.get(f"https://rockfile.co/{file_id}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if form := html.xpath("//form[@name='F1']"):
        inputs = html.xpath("//form[@name='F1']//input")
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value", "")
        try:
            sleep(3)
            res = session.post(url, data=data)
            html = HTML(res.text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[contains(@class,'btn-download')]/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def daofile(url):
    """Daofile direct link generator"""
    with create_scraper() as session:
        try:
            file_id = url.split("/")[-1]
            html = HTML(session.get(f"https://daofile.com/{file_id}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if form := html.xpath("//form[@name='F1']"):
        inputs = html.xpath("//form[@name='F1']//input")
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value", "")
        try:
            sleep(3)
            res = session.post(url, data=data)
            html = HTML(res.text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[contains(@class,'btn-download')]/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def suprafiles(url):
    """Suprafiles direct link generator"""
    with create_scraper() as session:
        try:
            file_id = url.split("/")[-1]
            html = HTML(session.get(f"https://suprafiles.me/{file_id}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if form := html.xpath("//form[@name='F1']"):
        inputs = html.xpath("//form[@name='F1']//input")
        data = {}
        for i in inputs:
            if key := i.get("name"):
                data[key] = i.get("value", "")
        try:
            sleep(3)
            res = session.post(url, data=data)
            html = HTML(res.text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[contains(@class,'btn-download')]/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))


def shortflix(url):
    """Shortflix direct link generator"""
    with create_scraper() as session:
        try:
            html = HTML(session.get(url).text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if script := html.xpath("//script[contains(text(),'sources')]/text()"):
        if link := findall(r'"file":"([^"]+)"', script[0]):
            return link[0].replace("\\", "")
    raise DirectDownloadLinkException(tr('helpers.direct.error_video_link_not_found', _html=False))


def kickbox(url):
    """Kickbox direct link generator"""
    with create_scraper() as session:
        try:
            file_id = url.split("/")[-1]
            html = HTML(session.get(f"https://kickbox.com/{file_id}").text)
        except Exception as e:
            raise DirectDownloadLinkException(tr('helpers.direct.error', value1=e.__class__.__name__, _html=False))
    if link := html.xpath("//a[contains(@class,'download-btn')]/@href"):
        return link[0]
    raise DirectDownloadLinkException(tr('helpers.direct.error_download_link_not_found', _html=False))
