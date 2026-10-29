
<div align="center">

# 🤖 rcmltb

### **基于 Rclone 的 Telegram 镜像与转存机器人**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-Async-blue.svg)](https://docs.pyrogram.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-GPL--3.0-green.svg)](LICENSE)

一个用于在云存储服务与 Telegram 之间传输文件的**异步** Telegram 机器人。

**Mirror（镜像）** → 云存储 | **Leech（转存）** → Telegram | **Clone（克隆）** → 云端到云端

[功能](#features) • [命令](#bot-commands) • [部署](#deployment) • [配置](#configuration)

</div>

---

> ⚠️ **稳定性提示**：项目目前正在进行大规模重构。在重构完成前，运行行为可能不稳定，更新之间也可能出现不兼容的变更。

---

<a id="features"></a>

## 🌟 功能

### ☁️ Rclone

- 在云存储之间复制文件或文件夹
- 将云端文件或文件夹转存到 Telegram
- 将链接、种子、磁力链接、MEGA 和 Telegram 文件镜像到云端
- 同时将 Telegram 文件镜像到多个云存储
- 通过 Telegram 导航按钮菜单操作云存储
- 文件管理器：查看大小、新建文件夹、删除、去重和重命名
- 支持服务账号及自动切换
- 以 HTTP 或 WebDAV 服务的形式创建云存储索引
- 在云存储之间同步（不支持文件夹间同步）
- 搜索云端文件
- 清空云存储回收站
- 查看云存储信息

### 🔧 核心功能

| 功能 | 说明 |
|---------|-------------|
| **队列系统** | 通过 `QUEUE_ALL`、`QUEUE_DOWNLOAD`、`QUEUE_UPLOAD` 限制并发任务 |
| **私有频道** | 从 Telegram 私有频道镜像或转存文件 |
| **上传路径模板** | 使用 `{username}`、`{date}`、`{category}` 等变量生成动态路径 |
| **媒体元数据** | 提供详细的媒体说明和实时状态信息 |
| **截图** | 用户可配置截图生成方式 |
| **名称替换** | 按规则重命名文件（`old::new`） |
| **强制开始** | 让紧急任务跳过队列 |
| **JDownloader** | 集成 JDownloader |
| **状态筛选** | 按聊天分页显示，并支持下载、上传、做种、克隆和排队状态筛选 |

### 📦 其他功能

- 通过机器人发送 rclone 配置文件
- Telegram 文件重命名菜单
- 索引支持（为所有 remote 提供 rclone 索引）
- 搜索 TMDB 影视条目
- 批量镜像或转存 Telegram 私有频道及受限频道中的文件
- 批量镜像或转存 `.txt` 文件中的链接
- 将 Telegram 链接或文件解压、压缩后上传到云端
- 将云端文件夹或文件解压、压缩后上传到 Telegram
- 镜像到本地主机（不上传云端）
- 已重构为使用 Pyrogram 和 asyncio
- 基于 Docker 的镜像（Ubuntu）
- 兼容 Linux `amd64`、`arm64/v8`、`arm/v7`

---

<a id="bot-commands"></a>

## 🤖 机器人命令

通过 [@BotFather](https://t.me/BotFather) 设置以下命令。

### 📥 镜像命令

| 命令 | 说明 |
|---------|-------------|
| `mirror` 或 `/m` | 镜像到选定的云存储 |
| `mirror_batch` 或 `/mb` | 批量镜像 Telegram 文件或链接 |
| `mirror_select` 或 `/ms` | 为镜像任务选定固定的云存储或文件夹 |
| `jdmirror` 或 `/jm` | 通过 JDownloader 镜像 |
| `ytdl` 或 `/y` | 镜像 yt-dlp 支持的链接 |
| `ytdleech` 或 `/yl` | 转存 yt-dlp 支持的链接到 Telegram |
| `jdleech` 或 `/jl` | 通过 JDownloader 转存到 Telegram |

### 📤 转存命令

| 命令 | 说明 |
|---------|-------------|
| `leech` 或 `/l` | 将云端文件或链接转存到 Telegram |
| `leech_batch` 或 `/lb` | 批量转存 Telegram 文件或链接 |

### ☁️ 云存储管理

| 命令 | 说明 |
|---------|-------------|
| `copy` | 在云存储之间复制 |
| `clone` | 克隆 Google Drive 链接中的文件或文件夹 |
| `count` | 统计 Google Drive 链接中的文件和文件夹 |
| `rcfm` | Rclone 文件管理器 |
| `sync` | 同步两个云存储 |
| `bisync` | 云存储双向同步 |
| `cleanup` | 清空云存储回收站 |
| `storage` | 查看云存储详细信息 |
| `serve` | 将云存储作为网页索引提供服务 |

### ⚙️ 系统与工具

| 命令 | 说明 |
|---------|-------------|
| `files` 或 `/bf` | 机器人配置文件 |
| `cancel` | 取消任务 |
| `force_start` 或 `/fs` | 强制开始排队中的任务 |
| `usetting` | 用户设置 |
| `bsetting` | 所有者设置 |
| `tmdb` | 搜索影视条目 |
| `torrsch` | 搜索种子 |
| `cancel_all` | 取消所有任务 |

### 📊 状态与信息

| 命令 | 说明 |
|---------|-------------|
| `status` | 查看任务状态消息 |
| `stats` | 机器人统计信息 |
| `log` | 机器人日志 |
| `ip` | 显示 IP 地址 |
| `ping` | 检查机器人响应 |

### 🔧 管理命令

| 命令 | 说明 |
|---------|-------------|
| `shell` | 在 shell 中运行命令 |
| `exec` | 运行 Python 代码 |
| `restart` | 重启机器人 |

---

<a id="deployment"></a>

## 🚀 部署

### 1️⃣ 安装所需组件

**克隆仓库：**
```bash
git clone https://github.com/Sam-Max/rcmltb rcmltb/ && cd rcmltb
```

**Debian 及其衍生发行版：**
```bash
sudo apt install python3 python3-pip
```

按照 [Docker 官方文档](https://docs.docker.com/engine/install/debian/)安装 Docker。

**Arch 及其衍生发行版：**
```bash
sudo pacman -S docker python
```

**安装配置辅助脚本的依赖：**
```bash
pip3 install -r requirements-cli.txt
```

---

<a id="configuration"></a>

### 2️⃣ 配置

复制示例配置文件：
```bash
cp sample_config.env config.env
```

> **注意**：所有值都必须填写在引号内，即使类型是 `Int`、`Bool` 或 `List`。

#### 必填配置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `TELEGRAM_API_ID` | 从 https://my.telegram.org 获取 | `Int` |
| `TELEGRAM_API_HASH` | 从 https://my.telegram.org 获取 | `Str` |
| `BOT_TOKEN` | 从 [@BotFather](https://t.me/BotFather) 获取 Telegram 机器人 Token | `Str` |
| `OWNER_ID` | 你的 Telegram 用户 ID（不是用户名） | `Int` |

---

#### 可选配置

##### 常规设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `DOWNLOAD_DIR` | 本地下载文件夹路径 | `Str` |
| `SUDO_USERS` | 拥有 sudo 权限的用户 ID，以空格分隔 | `Str` |
| `ALLOWED_CHATS` | 允许使用的聊天 ID，以空格分隔 | `Str` |
| `AUTO_MIRROR` | 自动镜像发送给机器人的文件。默认：`False` | `Bool` |
| `DATABASE_URL` | MongoDB 连接字符串 | `Str` |
| `CMD_INDEX` | 附加到命令后的索引编号 | `Str` |
| `GD_INDEX_URL` | Google Drive 索引地址 | `Str` |
| `VIEW_LINK` | 使用预览链接按钮代替直接下载。默认：`False` | `Bool` |
| `STATUS_LIMIT` | 状态消息中显示的任务数量 | `Int` |
| `LOCAL_MIRROR` | 将文件保留在主机上。默认：`False` | `Bool` |
| `TORRENT_TIMEOUT` | 无活跃下载的种子超时时间（qBittorrent） | `Int` |
| `AUTO_DELETE_MESSAGE_DURATION` | 经过指定秒数后自动删除消息，设为 `-1` 可禁用 | `Int` |
| `TMDB_API_KEY` | TMDB API 密钥（[在此获取](https://www.themoviedb.org/settings/api)） | `Str` |
| `TMDB_LANGUAGE` | TMDB 搜索语言。默认：`en` | `Str` |
| `PARALLEL_TASKS` | 队列允许的并行任务数量 | `Int` |

##### 更新设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `UPSTREAM_REPO` | GitHub 仓库链接（支持通过 Token 访问私有仓库） | `Str` |
| `UPSTREAM_BRANCH` | 上游分支。默认：`master` | `Str` |

> **注意**：如果 Docker 配置或依赖发生变化，需要重新构建镜像才能生效。

---

##### ☁️ Rclone 设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `DEFAULT_OWNER_REMOTE` | 所有者的默认 remote | `Str` |
| `DEFAULT_GLOBAL_REMOTE` | 全局配置中的默认 remote | `Str` |
| `MULTI_RCLONE_CONFIG` | 允许每位用户使用自己的配置。默认：`False` | `Bool` |
| `REMOTE_SELECTION` | 每次镜像时选择云存储。默认：`False` | `Bool` |
| `MULTI_REMOTE_UP` | 上传到多个云存储。默认：`False` | `Bool` |
| `USE_SERVICE_ACCOUNTS` | 启用服务账号。默认：`False` | `Bool` |
| `SERVICE_ACCOUNTS_REMOTE` | 共享云端硬盘的 remote 名称 | `Str` |
| `SERVER_SIDE` | 启用服务端复制。默认：`False` | `Bool` |
| `RCLONE_COPY_FLAGS` | 复制参数（`key:value,key`） | `Str` |
| `RCLONE_UPLOAD_FLAGS` | 上传参数 | `Str` |
| `RCLONE_DOWNLOAD_FLAGS` | 下载参数 | `Str` |
| `RC_INDEX_URL` | 索引的公网 IP 或域名 | `Str` |
| `RC_INDEX_PORT` | 索引端口。默认：`8080` | `Str` |
| `RC_INDEX_USER` | 索引用户名。默认：`admin` | `Str` |
| `RC_INDEX_PASS` | 索引密码。默认：`admin` | `Str` |
| `UPLOAD_PATH_TEMPLATE` | 动态路径模板，例如 `"remote:/{username}/{category}/{date}/"` | `Str` |

**模板变量：** `{username}`、`{user_id}`、`{date}`、`{year}`、`{month}`、`{day}`、`{category}`、`{task_type}`

---

##### 📁 Google Drive 设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `GDRIVE_FOLDER_ID` | 文件夹或共享云端硬盘 ID，也可填 `root` | `Str` |
| `IS_TEAM_DRIVE` | 使用共享云端硬盘时设为 `True` | `Bool` |
| `EXTENSION_FILTER` | 排除的文件扩展名，以空格分隔 | `Str` |

> **注意**：使用克隆功能时，将 `token.pickle` 放到根目录。也可通过机器人的 `/files` 命令添加。

---

##### 📤 转存设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `LEECH_SPLIT_SIZE` | 上传大小限制（非 Premium 账号 2GB，Premium 账号 4GB） | `Int` |
| `EQUAL_SPLITS` | 分割为大小相等的分卷。默认：`False` | `Bool` |
| `USER_SESSION_STRING` | Pyrogram 会话字符串（[生成方法](#session-generation)） | `Str` |
| `LEECH_LOG` | 接收上传文件的聊天 ID，以空格分隔，并添加 `-100` 前缀 | `Str` |
| `BOT_PM` | 将文件发送到用户私聊。默认：`False` | `Bool` |
| `NAME_SUBSTITUTE` | 文件名替换规则（`old::new\|old2::new2`） | `Str` |

---

##### ☁️ MEGA 设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `MEGA_EMAIL` | MEGA 账号邮箱 | `Str` |
| `MEGA_PASSWORD` | MEGA 账号密码 | `Str` |

---

##### ⬇️ JDownloader 设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `JD_EMAIL` | JDownloader 账号邮箱 | `Str` |
| `JD_PASSWORD` | JDownloader 账号密码 | `Str` |

---

##### 📊 队列系统设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `QUEUE_ALL` | 最大总并发任务数（`0` 表示不限） | `Int` |
| `QUEUE_DOWNLOAD` | 最大并发下载数（`0` 表示不限） | `Int` |
| `QUEUE_UPLOAD` | 最大并发上传数（`0` 表示不限） | `Int` |

---

##### 🌐 qBittorrent/Aria2c 设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `QB_BASE_URL` | 用于 qBittorrent 网页选种的机器人地址 | `Str` |
| `QB_SERVER_PORT` | 端口。默认：`80` | `Int` |
| `WEB_PINCODE` | 选种时要求输入 PIN 码。默认：`False` | `Bool` |

> **qBittorrent 提示**：如果内存占用有问题，可限制 `MaxConnecs`、减小 `AsyncIOThreadsCount`，并将 `DiskWriteCacheSize` 设为 32。

---

##### 🔍 种子搜索设置

| 变量 | 说明 | 类型 |
|----------|-------------|------|
| `SEARCH_API_LINK` | 种子搜索 API（[部署方法](https://github.com/Ryuk-me/Torrent-Api-py)） | `Str` |
| `SEARCH_LIMIT` | 每个站点的结果数量。默认：`0` | `Int` |
| `SEARCH_PLUGINS` | qBittorrent 搜索插件 URL | `List` |

---

### 3️⃣ 使用 Docker 部署

**构建 Docker 镜像：**
```bash
sudo docker build . -t rcmltb
```

**运行镜像：**
```bash
sudo docker run -p 80:80 -p 8080:8080 rcmltb
```

**停止容器：**
```bash
sudo docker ps
sudo docker stop <container_id>
```

**清理容器：**
```bash
sudo docker container prune
```

**删除镜像：**
```bash
sudo docker image prune -a
```

---

### 4️⃣ 使用 Docker Compose 部署

> **注意**：如果不使用 80（种子）或 8080（rclone）端口，请修改 `docker-compose.yml` 中的端口设置。

**安装 docker-compose：**
```bash
sudo apt install docker-compose
```

**构建并运行：**
```bash
sudo docker-compose up
```

**修改文件后：**
```bash
sudo docker-compose up --build
```

**停止与启动：**
```bash
sudo docker-compose stop
sudo docker-compose start
```

---

<a id="session-generation"></a>

## 🔐 会话生成

生成 `USER_SESSION_STRING`：

```bash
python3 session_generator.py
```

在你的电脑上进入仓库目录后运行此命令。

---

## 🗄️ MongoDB 配置

### 通过 Docker Compose 使用本地 MongoDB（无认证）

`docker-compose.yml` 包含带持久化存储的本地 `mongo` 服务。

1. 在 `config.env` 中设置 `DATABASE_URL`：

```env
DATABASE_URL="mongodb://mongo:27017/rcmltb"
```

2. 启动服务：

```bash
docker compose up -d
```

3. 检查两个容器：

```bash
docker compose ps
```

MongoDB 数据持久化保存在 `mongo_data` 卷中。

### MongoDB Atlas（云端）

1. 前往 [mongodb.com](https://mongodb.com/) 注册账号
2. 创建 Shared Cluster（免费）
3. 添加 `username` 和 `password`，点击 `Add my current IP Address`
4. 点击 `Connect` → `Connect your application`
5. 选择驱动：**Python**，版本：**3.6 或更高**
6. 复制连接字符串，将 `<password>` 替换为数据库用户的密码
7. 进入 `Network Access`，点击 Edit → `Allow access from anywhere` → Confirm

---

## ☁️ Rclone 配置

**视频教程：** [YouTube 指南](https://www.youtube.com/watch?v=Sp9lG_BYlSg)

### 使用提示：

- 在 `rclone.conf` 中添加至少两个账号，以便进行云存储间复制
- Android 用户可使用 [RCX 应用](https://play.google.com/store/apps/details?id=io.github.x0b.rcx)

### 支持的服务：

1Fichier、Amazon Drive、Amazon S3、Backblaze B2、Box、Ceph、DigitalOcean Spaces、Dreamhost、**Dropbox**、Enterprise File Fabric、FTP、GetSky、Google Cloud Storage、**Google Drive**、Google Photos、HDFS、HTTP、Hubic、IBM COS S3、Koofr、Mail.ru Cloud、**Mega**、Microsoft Azure Blob Storage、**Microsoft OneDrive**、**Nextcloud**、OVH、OpenDrive、Oracle Cloud Storage、ownCloud、pCloud、premiumize.me、put.io、Scaleway、Seafile、SFTP、**WebDAV**、Yandex Disk 等。

[查看所有服务](https://rclone.org/#providers)

---

## 🔑 Google OAuth 配置

> **环境要求**：操作系统需配有浏览器。Windows 用户需要安装 Python3 和 pip。

1. 访问 [Google Cloud Console](https://console.developers.google.com/apis/credentials)
2. 进入 OAuth 同意屏幕标签页，填写信息并保存
3. 进入凭据标签页 → 创建凭据 → OAuth 客户端 ID
4. 选择**桌面应用**并创建
5. 发布 OAuth 同意屏幕，防止 Token 过期
6. 下载凭据，移到机器人根目录，并重命名为 `credentials.json`
7. 访问 [Google API 库](https://console.developers.google.com/apis/library)
8. 搜索并启用 **Google Drive API**
9. 生成 Token：

```bash
pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib
python3 generate_drive_token.py
```

---

## 🌱 BitTorrent 做种

单独使用 `-d` 时，采用 aria2c/qBittorrent 的全局选项。

### qBittorrent 全局选项：

- `qbittorrent.conf` 中的 `GlobalMaxRatio` 和 `GlobalMaxSeedingMinutes`
- `-1` 表示不限
- **不要修改 `MaxRatioAction`**

---

## 🔧 服务账号（Google Drive）

> 设置 `USE_SERVICE_ACCOUNTS="True"` 启用。建议仅用于共享云端硬盘。

### 限制

- 1 个服务账号约为 750 GB/天
- 1 个项目 = 100 个服务账号，约为 75 TB/天

### 生成服务账号

**列出项目：**
```bash
python3 gen_sa_accounts.py --list-projects
```

**启用服务：**
```bash
python3 gen_sa_accounts.py --enable-services $PROJECTID
```

**创建服务账号：**
```bash
python3 gen_sa_accounts.py --create-sas $PROJECTID
```

**下载密钥：**
```bash
python3 gen_sa_accounts.py --download-keys $PROJECTID
```

**快速配置（新项目）：**
```bash
python3 gen_sa_accounts.py --quick-setup 1 --new-only
```

### 添加到共享云端硬盘

**方法一：通过 Google 群组（推荐）**
```bash
cd accounts
# Extract emails
grep -oPh '"client_email": "\K[^"]+' *.json > emails.txt
cd ..
# Add emails.txt to Google Group, then add Group to Team Drive as Manager
```

**方法二：直接添加：**
```bash
python3 add_to_team_drive.py -d SharedTeamDriveSrcID
```

---

## 🔐 .netrc 认证

使用 yt-dlp 高级账号或受保护的索引链接时，创建 `.netrc`：

```
machine host login username password my_password
```

**示例：**
```
machine instagram login user.name password mypassword
```

**注意：**

- **Instagram**：即使访问公开帖子也必须登录；使用新 IP 登录时需确认
- **YouTube**：请改用 [cookies.txt](https://github.com/ytdl-org/youtube-dl#how-do-i-pass-cookies-to-youtube-dl)

**Aria2c 索引链接示例：**
```
machine example.workers.dev password index_password
```

---

## ☕ 支持

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/sammax09)

---
