# EPUB Browser

> 私有 EPUB 阅读服务，以及自包含的静态站点生成器。

[English](https://github.com/dfface/epub-browser/blob/main/README.md) | [简体中文](https://github.com/dfface/epub-browser/blob/main/README.zh-CN.md)

<p align="center">
  <img src="https://github.com/dfface/epub-browser/blob/aff1def01252481f74c25ebf5b17d142b7db3c5e/epub_browser/assets/logo-lockup-color.png" alt="EPUB Browser 标志" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](License.txt)

EPUB Browser 提供两个职责清晰的模式：

| | `ssg` | `server` |
| --- | --- | --- |
| 部署方式 | 静态托管、Pages、对象存储、Nginx | 持久化的私有阅读服务 |
| 账户 | 无 | 本地账户；可选受信任代理身份 |
| 进度、标注、书架 | 仅当前浏览器 | SQLite 中的已登录账户数据 |
| 源文件更新 | 重新运行 `ssg` | 重启服务或使用 `--watch` |
| 运行时数据库 | 无 | 必需 |

如果产物必须是普通静态文件，请使用 `ssg`；如果需要账户、跨设备数据、书籍访问控制或自动监听源文件，请使用 `server`。

## 环境要求与安装

- Python 3.9 或更高版本
- 一个或多个 `.epub` 文件、包含 EPUB 的多级目录，或 Calibre 风格的书库目录

从 PyPI 安装：

```bash
pip install epub-browser
```

查看分模式的命令帮助：

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

## 快速开始

### 生成静态站点

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist
```

请通过 HTTP 提供 `dist/`，不要用 `file://` 直接打开生成页面。浏览器存储、模块、清单和 Service Worker 都依赖 HTTP 源。

如果站点部署在 URL 子路径下，需要单独指定公开路径：

```bash
epub-browser ssg /path/to/books \
  --output-dir /path/to/dist \
  --base-path /my-repository/
```

`--base-path` 只改变生成后的 URL，不改变文件写入位置。设为 `/my-repository/` 后，链接、图标、清单、书籍元数据和 Service Worker 条目都会带此前缀，文件仍直接写在 `dist/` 中。

### 运行持久化 Server 书库

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

打开 `http://127.0.0.1:8000/`。首次访问时，页面会引导创建初始管理员。完成这次性设置之前，书库不会开始扫描，也不会对外暴露。

## 输入源与稳定书籍身份

每个位置参数 `SOURCE` 都可以是 EPUB 文件或目录；目录会递归搜索。一个命令可传入多个来源：

```bash
epub-browser server book.epub /srv/library /srv/periodicals \
  --server-dir /srv/epub-browser \
  --watch
```

每本书会获得稳定的 `book_id`，它在生成 URL 和浏览器数据中也称为 `book_hash`。通用 CLI 默认使用：

```bash
--book-id-storage sidecar
```

Sidecar 模式会在 EPUB 旁写入可见的身份文件，例如 `BOOK.epub.epub-browser.json`，不会改变 EPUB 本身的字节。Sidecar 包含稳定 ID 和经过验证的 SHA-256 源文件指纹。

若要把 ID 写入 OPF 元数据，请为本次命令选择 embedded：

```bash
--book-id-storage embedded
```

Embedded 模式可能重建 EPUB ZIP，因此源文件必须可写且适合修改。EPUB Browser 不会悄悄回退为“仅数据库 ID”。当两个载体 ID 不一致、活动源文件存在重复 ID、载体无效，或目标载体无法写入时，命令会停止。

切换存储方式时，既有 ID 会复制到所选载体，另一个有效载体不会被删除。从 v2.0.4 升级时，既有 embedded ID 会复制到默认 sidecar，不会重写 EPUB。

## SSG 模式详解

SSG 会先在相邻的 staging 目录生成完整快照并验证，最后才替换目标目录。任何书籍转换失败时，旧目标目录保持不变。生成结果不包含 Server 数据库、迁移状态、账户页面或运行时缓存元数据。

SSG 有意保持本地化且不包含账户体系：

- 阅读进度和标注存储在当前站点源的浏览器存储中。
- 书架支持本地 JSON 导入、导出，没有云端 Sync 操作。
- 不生成登录、账户设置、Server API 或依赖用户身份的控件。
- 存储位置固定为浏览器本地，不向用户显示存储方式选择器。
- 静态产物包含离线资源所需的 Service Worker。

应用所需的 JavaScript、CSS、字体和图标都会写入产物。唯一的可选网络请求见[自包含与网络行为](#自包含与网络行为)。

## Server 模式详解

### 首次设置、账户与权限

全新的持久化状态目录会把普通页面重定向到 `/setup`。创建初始管理员之前，API、事件流、生成资源和书籍都会返回“需要设置”。首次设置应在 loopback 或可信私有网络中完成：第一个成功提交设置表单的访问者会取得管理员账户。

设置完成后：

- 不开放公共注册，用户由管理员创建和管理。
- 账户角色为 `administrator` 或 `member`。
- 普通书籍对所有已登录账户可见。
- 受限书籍只对管理员和被明确授权的用户可见。
- 每位用户独立拥有书架、进度、标注和活跃会话。
- 用户可以修改自己的密码和撤销自己的会话。
- 管理员可以管理用户、角色、密码、会话、外部身份和书籍授权。
- 会话使用 HttpOnly Cookie、CSRF 防护和 30 天滑动有效期。

无人值守的首次启动可传入管理员名和密码文件：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --admin-username admin \
  --admin-password-file /run/secrets/epub-browser-admin-password \
  --no-browser
```

密码文件建议设置为 `0600`。EPUB Browser 会去掉一个末尾换行符、保存 Argon2id 哈希，并且绝不打印明文密码。配置不完整、文件为空或无法读取时，启动会停止。首次设置完成后，后续启动不会再读取这份引导密钥。

对应环境变量是 `EPUB_BROWSER_ADMIN_USERNAME` 和 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`。只有未配置密码文件时，才会使用明文环境变量 `EPUB_BROWSER_ADMIN_PASSWORD` 作为后备。CLI 中的密码文件路径优先于环境变量密码来源。

### 浏览器启动与日志

默认情况下，Server 在 HTTP 监听器启动后，会尝试打开操作系统的默认浏览器。`--no-browser` 只阻止这次本机启动动作，**不会关闭 Web 界面，也不会禁止浏览器访问**；它只是跳过本机的 `webbrowser.open(...)` 调用。Docker、systemd、SSH、无图形界面的主机和脚本中都建议使用它。

未指定 `--log` 时，CLI 会避免输出日常信息，以免破坏终端进度展示。交互式终端只打印一次监听 URL；Docker 和服务等非交互环境保持安静。`--log` 会开启运行日志和 HTTP 访问日志。

首次扫描和监听扫描的进度显示在 Web 页面，而不是终端 `tqdm`。全部成功时摘要会自动关闭；有失败时会保留到用户手动关闭。使用 `--watch` 时，修复或替换源文件就会触发下一次扫描，无需手动 Retry。

### 持久化与临时状态

持久化 Server 必须使用 `--server-dir`。一次性运行可改用 `--ephemeral`：

```bash
epub-browser server book.epub --ephemeral
```

临时状态会在服务退出时删除。数据库每次都是全新的，因此每次也需要重新设置管理员；无人值守时可提供引导凭据。

持久化目录结构：

```text
<server-dir>/
├── .server.lock                 # 可复用的进程锁元数据
├── data/
│   ├── epub-browser.db          # 权威账户、书籍、授权和阅读数据
│   ├── migration-state.json     # 可安全重启的迁移状态
│   └── backups/                 # 已验证的迁移前数据库副本
└── cache/
    ├── catalog.json             # 生成缓存状态
    ├── public/                  # Web 应用和转换后的书籍
    └── staging/                 # 可替换的转换工作目录
```

只有 `data/` 是权威数据；`cache/` 可以删除并重建。升级和替换容器时必须保留 `data/`。进程独占由操作系统锁控制，正常退出后留下的 `.server.lock` 只是诊断元数据。

### 局域网、反向代理与 OIDC

Server 默认监听 `127.0.0.1:8000`。若要在可信局域网访问：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --port 8080 \
  --no-browser
```

不要把内置 HTTP Server 直接暴露到公网。请在反向代理处终止 TLS、设置网络访问控制，并启用安全 Cookie。

EPUB Browser 本身不是 OAuth/OIDC 客户端。要接入 OIDC，请在前面部署支持 OIDC 的认证代理，并把稳定的已认证 subject 传给 EPUB Browser：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --cookie-secure \
  --trusted-proxy-cidr 10.42.0.0/16 \
  --proxy-subject-header X-Remote-User \
  --proxy-display-name-header X-Remote-Name \
  --proxy-issuer https://login.example.com \
  --no-browser
```

受信任 CIDR 必须表示反向代理的**直接套接字网络**，不能写公网客户端地址段。代理应删除客户端传入的同名身份头，再设置自己的认证结果。来自不受信任对等端的头会被忽略。Uvicorn 的转发地址处理已禁用，因此 `X-Forwarded-For`、`Forwarded` 和 `FORWARDED_ALLOW_IPS` 都不能扩大这条信任边界。

`--proxy-subject-header` 应包含不可变的提供方 subject，不能使用可变显示名。`--proxy-issuer` 应在同一身份域中保持稳定。用户可以通过验证本地账户密码来关联未知的受信任身份，管理员也可以创建映射。本地管理员/密码登录始终作为恢复入口保留。

## Docker

镜像默认运行持久化 Server，并包含以下参数：

- `/app/Library` 作为书籍源
- `/app/EpubBrowserFiles` 作为持久化状态
- `--watch`
- `--no-browser`
- `--host 0.0.0.0 --port 80`
- `--book-id-storage embedded`

Embedded 身份可能重写 EPUB，因此书库应以读写方式挂载。Server 状态也必须可写，并在替换容器时保留：

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  epub-browser:2.1.0
```

修改端口绑定或代理规则之前，请先访问 `http://127.0.0.1:8080/setup` 完成首次设置。

无人值守设置示例：

```bash
docker run -d \
  --name epub-browser \
  -p 127.0.0.1:8080:80 \
  -v /path/to/books:/app/Library:rw \
  -v /path/to/epub-browser-state:/app/EpubBrowserFiles \
  -e EPUB_BROWSER_ADMIN_USERNAME=admin \
  -e EPUB_BROWSER_ADMIN_PASSWORD_FILE=/run/secrets/epub-browser-admin-password \
  --mount type=bind,src=/path/to/admin-password,dst=/run/secrets/epub-browser-admin-password,readonly \
  epub-browser:2.1.0
```

首次成功启动后，可移除这次性密钥挂载。只有所有 EPUB 已经包含有效且匹配的 embedded ID 时，书库才可以只读挂载。把同一 ID 嵌入 EPUB 时，既有 sidecar 会保留。

只有迁移旧书架 JSON 时才挂载 `/app/SyncData:ro`：

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

示例把容器端口只发布到主机 loopback，从而让容器位于主机边界之后。远程访问时，请使用 TLS 反向代理，并配置其真实容器网络 CIDR、身份头和 `--cookie-secure`。

## 完整命令参考

### `epub-browser ssg SOURCE [SOURCE ...]`

| 参数 | 含义 |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | 必填；原子静态快照的目标目录。 |
| `--base-path PATH` | 公开 URL 前缀，默认 `/`；必须以 `/` 开头和结尾。 |
| `--book-id-storage sidecar\|embedded` | 本次命令中所有源文件的稳定身份载体，默认 `sidecar`。 |
| `--log` | 打印转换细节；未指定时日常输出保持安静。 |

### `epub-browser server SOURCE [SOURCE ...]`

`--server-dir` 与 `--ephemeral` 必须且只能选择一个。

| 参数 | 含义 |
| --- | --- |
| `--server-dir DIR` | 持久化权威数据与可替换缓存的根目录。 |
| `--ephemeral` | 使用一次性状态；与 `--server-dir` 互斥。 |
| `--watch`, `-w` | 监听并协调源文件新增、更新、移动和删除。 |
| `--host ADDRESS` | 监听地址，默认 `127.0.0.1`。 |
| `--port PORT`, `-p PORT` | 监听端口，默认 `8000`。 |
| `--no-browser` | 不启动本机默认浏览器；Web 界面仍可访问。 |
| `--log` | 开启运行日志和 HTTP 访问日志。 |
| `--legacy-sync-dir DIR` | 启动迁移时读取旧书架 JSON。 |
| `--book-id-storage sidecar\|embedded` | 本次命令中所有源文件的稳定身份载体，默认 `sidecar`。 |
| `--admin-username NAME` | 无人值守的初始管理员；后备为 `EPUB_BROWSER_ADMIN_USERNAME`。 |
| `--admin-password-file FILE` | 首选初始密钥文件；后备为 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`，未设置文件时再使用 `EPUB_BROWSER_ADMIN_PASSWORD`。 |
| `--trusted-proxy-cidr CIDR` | 可重复指定的直接代理网络信任边界；需要同时配置 subject 头和 issuer。 |
| `--proxy-subject-header NAME` | 包含不可变外部认证 subject 的请求头。 |
| `--proxy-display-name-header NAME` | 可选的显示名请求头。 |
| `--proxy-issuer VALUE` | 代理 subject 的稳定 issuer/安全域标识。 |
| `--cookie-secure` | 只通过浏览器侧 HTTPS 发送会话 Cookie。 |

### 旧版 v1 语法

整个 v2 主版本周期都会兼容旧语法：

| v1 命令 | v2 映射 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

旧版专用 `--keep-files` 会保留临时 Server 目录；持久化 Server 目录本来就不会删除。指定 `--log` 时，兼容适配器会打印等价 v2 命令，否则保持安静。

## 阅读功能与数据位置

- 递归发现 EPUB 和 Calibre 书库、元数据标签、搜索与拼音搜索
- 响应式 Library、书籍详情和章节阅读界面
- 滚动、翻页、连续阅读、内容宽度、字体、自定义 CSS、主题和纯净阅读模式
- 高亮、笔记、标注浏览、嵌套书架分组、标签和 JSON 导入/导出
- 英文和简体中文界面
- Kindle/Silk 的电子阅读器友好模式；部分依赖浏览器能力的功能可能精简

| 数据 | SSG | Server |
| --- | --- | --- |
| 阅读进度 | 浏览器本地 | 已登录用户的 SQLite 记录 |
| 高亮与笔记 | 浏览器本地 | 已登录用户的 SQLite 记录 |
| 书架 | 浏览器本地；导入/导出 | 已登录用户的版本化云端文档；自动保存 |
| 账户与会话 | 不存在 | `<server-dir>/data` 下的 SQLite |
| 书籍授权 | 不存在 | `<server-dir>/data` 下的 SQLite |

Server 不提供“本地/云端”存储选择器：已登录阅读数据固定存储在 Server。SSG 不探测 Server API，始终使用当前浏览器源的本地存储。

## 自包含与网络行为

阅读功能是自包含的：所需 JavaScript、CSS、字体、图标、清单和转换后的 EPUB 资源全部由本地提供，不依赖 CDN。阻断公网出站访问不会影响首次设置、登录、书库浏览、阅读、标注、进度、书架、后台管理或书籍转换。

页脚可能向 GitHub Releases API 发起一次可选请求，用于提示是否存在新版 EPUB Browser。离线、请求失败或被阻断时，只是不显示更新提示。OIDC 则依赖你明确配置并独立运行的认证代理和身份提供方，它不是内置依赖。

SSG 会发布静态 Service Worker。Server 会禁用并清退整个源范围的 Service Worker，避免一个账户收到另一个账户缓存过的受保护内容。

## 数据安全与迁移

升级持久化 Server 前，请备份源 EPUB 和 `<server-dir>/data`。替换容器时必须继续挂载同一个持久化状态目录。

启动迁移会自动执行，并可在中断后安全继续。它会验证旧数据库、创建备份、升级副本、把合格的旧书架/进度/标注数据归属给待创建的初始管理员，并只在成功检查点之后清退旧文件。普通请求不会扫描旧同步目录。数据库损坏、密码哈希无效、旧数据库含义不明确和 ID 冲突都会停止启动，而不是猜测或覆盖。

如果旧目录同时包含 `epub-browser.db` 与 `annotations.db`，启动会停止并保留原文件。备份、回滚、缓存重建和冲突恢复见[迁移到 v2](docs/migration-v2.md)。

## 常见问题

### 命令已启动，但没有自动打开浏览器

在有图形界面的本机运行时可移除 `--no-browser`，也可以手动打开监听 URL。Docker、systemd、SSH 和非交互环境通常都应手动访问。

### CLI 看起来没有输出

不使用 `--log` 时保持安静是预期行为，非交互环境尤其如此。需要运行和访问细节时添加 `--log`。Server 扫描进度显示在 Web 界面中。

### Docker 无法写入稳定 ID

镜像默认使用 embedded 身份。请把 `/app/Library` 以读写方式挂载，或预先嵌入有效且匹配的 ID。只有更适合可写 sidecar 时，才通过自定义命令改用 `--book-id-storage sidecar`。

### 部署到子路径后，SSG 链接失效

使用规范化的 `--base-path`（例如 `/reader/`）重新生成，并让静态主机把产物部署在同一 URL 前缀下。

### 升级后 Server 拒绝启动

保留数据和源文件，查看第一条迁移或验证错误，并参阅 [docs/migration-v2.md](docs/migration-v2.md)。不要通过删除权威 `data/` 目录来绕过错误。

## 参与贡献

欢迎在 [dfface/epub-browser](https://github.com/dfface/epub-browser) 提交 Issue 和 Pull Request。一份有效的问题报告应包含准确命令、浏览器/设备、复现步骤、相关日志，以及在法律和版权允许时附上的 EPUB。

## 许可证

[MIT](License.txt)
