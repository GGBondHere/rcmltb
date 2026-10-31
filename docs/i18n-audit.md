# Telegram 简体中文与英文界面审计

默认界面语言为 `zh-CN`，可选 `en`。翻译资源完全随项目发布，不调用翻译 API，也不增加运行时联网依赖。

## 使用与持久化

- 使用 `/lang` 或 `/language`，也可从 `/usetting` 的“🌐 语言 / Language”入口进入语言菜单。
- 选择“简体中文”“English”或“跟随全局”。个人偏好优先于全局默认值，切换立即生效。
- 所有者在 `/bsetting` 中选择 `BOT_UI_LANGUAGE`，可通过按钮或输入 `zh-CN` / `en` 修改默认语言；不必修改 Compose。其他值会被拒绝，重置值为 `zh-CN`。
- 个人语言保存在原有用户记录的 `ui_language` 字段，空字符串表示跟随全局。SQLite 和 MongoDB 均沿用现有用户设置写入与恢复入口。
- 全局语言保存在现有配置记录中。Mongo 恢复后同步新增语言键到现有运行字典，避免旧部署语言覆盖恢复结果；不改变其他配置的恢复流程。
- 公共群组和频道的共享任务进度、无任务统计使用全局语言；个人反馈及私聊状态使用个人偏好。更改显示语言不会修改任务状态、上传目标、路径或权限。
- 语言回调验证菜单操作者及现有授权。原有 Telegram 命令、CMD_INDEX 后缀和已有 callback data 保留，仅新增语言命令、`uilang` 路由及管理员语言选择动作。
- Telegram 原生命令说明随语言设置更新；选择跟随全局会移除个人作用域的说明覆盖。原生命令说明更新失败只记录日志，不回滚已经保存的语言偏好。

## 资源与运行结构

```text
bot/i18n/
├── __init__.py       # ContextVar 语言上下文、英文兜底、安全格式化、状态显示
├── commands.py       # Telegram 原生命令说明与用户作用域
└── locales/
    ├── zh-CN/        # 简体中文，按 common/core/settings/commands/helpers 拆分
    └── en/           # 相同语义键与参数的英文资源
```

| 资源域 | 每种语言的键数 |
| --- | ---: |
| `commands.json` | 252 |
| `common.json` | 31 |
| `core.json` | 32 |
| `helpers.json` | 328 |
| `settings.json` | 122 |
| 合计 | 765 |

业务代码通过 `tr("domain.semantic_key", **params)` 获取文案；不按原英文做运行时查找或全局替换。动态参数默认 HTML 转义，纯按钮/弹窗使用 `_html=False`。已经转义的正文或受控 HTML 片段才使用 `raw()`；文件名、路径、用户名、ID、配置键和第三方数据不作内容翻译。

数量资源支持 `one` / `other`，两种语言保持相同的命名占位符、数量、格式精度及转换规则。资源缺失时记录开发日志并使用英文兜底；两种语言都缺失时返回可定位的键标记。正式检查不允许缺失键、哈希/行号键、未匹配参数或未批准的硬编码英文。

处理器只在 ContextVar 中保存操作者身份，每次翻译重新读取其偏好，避免冻结语言或并发覆盖。普通异步任务、线程桥接及原有排队任务传播该上下文；aria2、qBittorrent、JDownloader 等后台回调按任务发起者选语言。管理员取消他人任务时，取消原因使用任务发起者语言，管理员自身操作反馈仍使用管理员语言。

帮助文本与帮助菜单在访问时构建，yt-dlp 临时质量回调也绑定用户上下文，返回主菜单时仅刷新显示标签，保留质量选择与 callback data。

## 按模块覆盖

静态扫描遍历整个 `bot/`，追踪消息、按钮、caption、弹窗参数以及局部变量、拼接和分支文案。当前直接 Telegram 出口共 **773** 处，分布于 **47** 个文件；发现 **0** 处未批准的硬编码英文、**0** 个完整性错误。原生命令说明另外覆盖在 `bot/i18n/commands.py`，通过专门测试验证。

| 模块 | 直接出口数 | 覆盖内容 |
| --- | ---: | --- |
| `bot/__main__.py` | 1 | 启动完成与命令说明 |
| `bot/core/handlers.py` | 10 | 欢迎、重启、延迟、IP 与日志 |
| `bot/helper/ext_utils/bot_utils.py` | 6 | 状态进度、筛选、分页与统计 |
| `bot/helper/ext_utils/help_messages.py` | 14 | 运行时帮助文本与菜单 |
| `bot/helper/ext_utils/menu_utils.py` | 2 | 启动完成与命令说明 |
| `bot/helper/ext_utils/misc_utils.py` | 5 | 启动完成与命令说明 |
| `bot/helper/ext_utils/rclone_utils.py` | 44 | 配置检查、网盘与目录选择 |
| `bot/helper/listeners/task_listener.py` | 23 | 任务完成、失败、上传链接与发起者 |
| `bot/helper/mirror_leech_utils/download_utils/aria2_download.py` | 2 | 下载反馈与上层错误显示 |
| `bot/helper/mirror_leech_utils/download_utils/gd_downloader.py` | 1 | 下载反馈与上层错误显示 |
| `bot/helper/mirror_leech_utils/download_utils/jd_download.py` | 7 | 下载反馈与上层错误显示 |
| `bot/helper/mirror_leech_utils/download_utils/mega_download.py` | 1 | 下载反馈与上层错误显示 |
| `bot/helper/mirror_leech_utils/download_utils/qbit_downloader.py` | 5 | 下载反馈与上层错误显示 |
| `bot/helper/mirror_leech_utils/download_utils/telegram_downloader.py` | 1 | 下载反馈与上层错误显示 |
| `bot/helper/mirror_leech_utils/upload_utils/telegram_uploader.py` | 9 | 上传反馈、媒体说明与取消 |
| `bot/helper/telegram_helper/button_build.py` | 6 | 按钮出口，数据标识保持原样 |
| `bot/helper/telegram_helper/message_utils.py` | 14 | 消息/附件发送、编辑及惰性文本渲染 |
| `bot/modules/batch.py` | 13 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/bisync.py` | 6 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/botfiles.py` | 48 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/cancel.py` | 20 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/cleanup.py` | 6 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/clone.py` | 7 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/copy.py` | 9 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/exec.py` | 4 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/force_start.py` | 5 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/gd_count.py` | 3 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/help.py` | 5 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/language.py` | 10 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/leech.py` | 19 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/mirror_leech.py` | 23 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/mirror_select.py` | 10 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/myfilesset.py` | 58 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/owner_settings.py` | 83 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/queue.py` | 1 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/rcfm.py` | 18 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/serve.py` | 13 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/shell.py` | 4 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/stats.py` | 1 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/status.py` | 2 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/storage.py` | 8 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/sync.py` | 3 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/tmdb.py` | 60 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/torr_search.py` | 44 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/torr_select.py` | 15 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/user_settings.py` | 84 | 命令反馈、菜单、按钮与弹窗 |
| `bot/modules/ytdlp.py` | 40 | 命令反馈、菜单、按钮与弹窗 |

除直接出口外，还覆盖 `bot/helper/common.py`、`ext_utils/files_utils.py`、`links_utils.py`、`media_utils.py`、`task_manager.py`、`template_utils.py`、`telegraph_helper.py`、后台监听器、Google Drive 辅助模块及各状态/传输实现中传递给这些出口的文案。直链解析器的人类提示已本地化；技术异常保留原诊断，并在 Telegram 显示层添加对应语言说明。

扫描范围不包含将 CLI 输出当成界面翻译的做法：启动日志、shell/exec 的原始命令结果、第三方 API 返回的数据及 qbitweb 网页不属于本次 Telegram 静态文案。根目录会话生成等脚本仅向终端输出，没有新增 Telegram 文案出口。

## 术语与语境

| 英文/标识 | 简体中文显示与约定 |
| --- | --- |
| Downloading | 正在下载，指从 Telegram、链接或网盘到服务器 |
| Uploading | 正在上传，指从服务器到网盘或 Telegram |
| Processed | 下载阶段为“已下载”，上传阶段为“已上传”，其他阶段为“已处理” |
| FREE / Free Disk | 磁盘可用空间 |
| UPTIME | Bot / 机器人运行时长，与系统运行时长区分 |
| ETA | 预计剩余时间 |
| cc | 发起者，不是原视频作者 |
| Cloud Link | 网盘链接，不表示已经公开分享 |
| Seed / Seeding | BT 做种 |
| Clone / Cloning | 云端复制，不改 `/clone` 命令或内部状态 |
| Nothing to show | 目录选择时为“当前没有子文件夹”；包含文件的浏览菜单说明没有可显示的文件或文件夹 |
| None | 按菜单语境显示“未设置”“无”等，不翻译业务值或 Python 的 `None` |
| rclone、Google Drive、WebDAV、Telegram、Docker、API、OAuth、Token、CPU、RAM | 保留技术名称；内存等字段按语境补充中文说明 |
| `rclone.conf`、`gdrive:`、`UPLOAD_PATH_TEMPLATE`、`{username}`、`{user_id}` | 原样保留；资源中的示例大括号经过转义，不参与翻译插值 |

管理员设置保留实际配置键。分类的显示名称可翻译为“电影”“电视剧”等，但保存的原分类值和 callback data 不变。TMDB 标题/剧情、搜索结果、网盘路径和文件名均作为数据保留。

## 明确保留的技术内容

审计记录了 12 处技术文案例外，采用精确文本白名单，并附理由，未按文件或目录整体跳过：

- 批处理内部生成的 `/mirror`、`/leech` 命令以及 `-au`、`-ap`、`-i` 参数。
- YT-DLP/API 工具名，以及 mp4、webm、MP3、分辨率、FPS、码率和编码格式规格。
- `MirrorStatus`、`TaskType` 等原始状态值，以及 callback data、handler 标识、MIME、CLI 参数和 API 字段。它们只在显示时转换，不能把翻译结果送回业务比较。
- 直链解析使用的 `ERROR:` 分类前缀保持原样。没有此前缀的 provider 异常仍按原有 fallback 处理，不能因翻译而变成提前终止。
- 原始网络/认证等技术异常、Git/shell/exec 输出和第三方内容可以保留原文；外围说明本地化，不把所有异常当成可信 HTML。
- 密码帮助属于受控静态 HTML；其未来动态参数仍转义。普通诊断中的尖括号、引号和 `&` 只转义一次。
- `helpers.text.metadata` 与 `helpers.text.subtitles` 是已有媒体说明的组合片段，随后由同一格式化函数补全 `</code>`。检查器显式列出这两个例外，并测试最终组合 HTML，而非把所有不完整 HTML 放行。
- Telegraph 搜索结果保留其 `h4` / `br` / 链接结构，标签翻译，结果地址和名称不变。

消息与 caption 的长度限制、HTML 及 callback data 约束遵循 [Telegram Bot API](https://core.telegram.org/bots/api)。资源和已测试菜单保持在相应长度内，保留既有长任务列表/长内容处理，不引入新的截断或传输机制。

## 检查与测试

```powershell
python scripts/check_i18n.py
python scripts/check_i18n.py --json i18n-report.json
python -m unittest discover -s tests -p "test_*.py"
```

检查脚本不启动机器人、下载器或网络服务。JSON 报告列出资源、模块出口、静态翻译调用、动态输出及每项技术例外；测试会注入新的未翻译提示，验证扫描器确实能发现直接和间接文案。

新增测试覆盖：

- 中英文键、占位符数量/精度、单复数、HTML、转义、特殊字符和资源长度。
- 个人、全局、跟随全局的优先级；两个并发用户、后台回调、线程与队列的语言隔离。
- 语言菜单操作者检查；已有配置键、命令名、callback data、原始状态和优先级保持。
- 真实 SQLite 关闭/重开恢复，现有 Mongo 写入方法及 Mongo 启动恢复链路的隔离测试。
- 帮助和设置菜单、任务状态/筛选/分页、上传成功/失败/取消/排队、网盘及搜索菜单。
- 文件、视频、转发媒体和 Telegram 消息链接沿用现有输入分派；动态名称、路径、搜索词和第三方内容保持。
- yt-dlp 临时回调与菜单切换、错误 HTML、密码帮助、直链 fallback 和管理员跨用户取消。
- 原有安全、共享 rclone、持久化和 downloads 清理回归。

以上为离线源代码/资源及模拟边界验证。未启动真实 Telegram、MongoDB、rclone 或 Docker 容器，不将这些检查描述为在线部署验收。

本次完整测试集执行结果为 **118 项全部通过**，包含原有 60 项业务回归；国际化检查输出为 **765 keys / 773 Telegram sinks / 0 hardcoded UI strings / 0 errors**。集中复核发现的临时质量菜单、Mongo 恢复、HTML 错误边界、直链 fallback 和跨用户取消问题均已加入回归并修正。
