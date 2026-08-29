# EPUB Browser

> 用同一套精致的 Web 阅读体验阅读 EPUB 和 PDF：既可以生成完全自包含的
> 静态站点，也可以运行带账户和同步能力的私有阅读服务。

**README：** [English](../../README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Español](README.es.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Русский](README.ru.md) | [Italiano](README.it.md) | [Português (Brasil)](README.pt-BR.md) | [العربية](README.ar.md) | [Bahasa Indonesia](README.id.md) | [हिन्दी](README.hi.md) | [Tiếng Việt](README.vi.md) | [ไทย](README.th.md) | [Bahasa Melayu](README.ms.md)

**界面语言（17 种）：** 英语、简体中文、繁体中文、日语、韩语、西班牙语、德语、法语、俄语、意大利语、巴西葡萄牙语、阿拉伯语、印尼语、印地语、越南语、泰语和马来语。

<p align="center">
  <img src="https://raw.githubusercontent.com/dfface/epub-browser/main/epub_browser/assets/logo-lockup-color.png" alt="EPUB Browser 标志" width="520">
</p>

[![PyPI version](https://img.shields.io/pypi/v/epub-browser)](https://pypi.org/project/epub-browser/)
[![Python versions](https://img.shields.io/pypi/pyversions/epub-browser)](https://pypi.org/project/epub-browser/)
[![License](https://img.shields.io/github/license/dfface/epub-browser)](../../License.txt)

![PDF 在 EPUB Browser 共用阅读器中渲染，保留原始页面、导航、主题与阅读工具。](../releases/assets/v2.8.0-pdf-reader.png)

EPUB Browser 现在同时接受 `.epub` 和 `.pdf`。两种格式共用 Library、书籍详情、
目录、阅读模式、主题、阅读进度和标注流程。PDF 不会被交给浏览器下载或另开一套预览器；
每一页都会成为阅读器中的一个章节，由本地 PDF.js 在现有阅读界面内渲染。

## 目录

- [项目概览](#项目概览)
  - [为什么选择 EPUB Browser](#为什么选择-epub-browser)
  - [技术栈](#技术栈)
  - [选择 SSG 或 Server](#选择-ssg-或-server)
  - [演示站点](#演示站点)
  - [AI 原生阅读](#ai-原生阅读仅-server-模式)
- [开始使用](#开始使用)
  - [选择安装方式](#选择安装方式)
  - [快速开始](#快速开始)
- [格式与阅读体验](#格式与阅读体验)
  - [输入源与稳定书籍身份](#输入源与稳定书籍身份)
  - [PDF：一页就是一个章节](#pdf一页就是一个章节)
- [部署](#部署)
  - [SSG](#ssg)
  - [Server](#server)
  - [Docker](#docker)
- [参考与运维](#参考与运维)
  - [命令参考](#命令参考)
  - [阅读数据与功能归属](#阅读数据与功能归属)
  - [Server API 与 WebHook](#server-api-与-webhook)
  - [数据安全与常见问题](#数据安全与迁移)
- [开发与许可证](#开发与许可证)
- [文档中心](../README.md)

## 项目概览

### 为什么选择 EPUB Browser

- **EPUB 与 PDF 共用一个阅读器**：EPUB 章节和 PDF 页面使用同一套导航、响应式布局、
  主题、全屏、搜索、书架、进度、阅读时长和书籍详情。
- **三种阅读行为**：可以按章节滚动、使用有界渲染窗口连续阅读，或者翻页阅读。
  PDF 还支持适合宽度、适合页面和任意比例缩放，页面始终留在阅读舞台中。
- **贴着原文的 AI 原生阅读**：Server 模式把章前导读、证据解释、词语辅助、思维导图和
  深入思考直接融入 EPUB 正文；还可以在保留阅读上下文的私密 Ask AI 中继续追问，
  而不是跳到一份脱离原文的泛化总结。
- **在原文上完成标注与查阅**：高亮、笔记、标注汇总与导出、词典和百科都在阅读现场完成。
  带文本层的 PDF 直接复用同一个选择弹窗；纯图片 PDF 会明确降级，不伪装成可选文字。
- **只属于你的阅读洞察**：通过活跃阅读时长、阅读日历、趋势、会话和最常阅读的书，
  回看真正投入阅读的时间与节奏；Server 模式下所有洞察仅当前账户可见。
- **真正的个人书库**：封面、元数据、标签、评分、书评、嵌套书架、搜索和阅读历史
  都依靠稳定书籍 ID 关联；Server 监控目录中的源文件暂时移走后再放回，也会恢复原记录。
- **私有且可治理的 Server**：账户、书籍权限、成员 AI 授权、跨设备阅读数据、管理后台、
  OpenAPI 与 WebHook 都由自己的服务掌控。
- **接入自己的单点登录**：Server 模式可连接 Authelia、Authentik、Keycloak 等通用 OIDC
  Provider，让读者安全绑定现有账户或自动创建成员，不会割裂已有阅读数据。
- **运行时完全自包含**：应用脚本、样式、字体、图标、PDF.js 和富文本渲染器都从本地提供，
  阅读过程不依赖 CDN。
- **17 种界面语言**：英语、简体中文、繁体中文、日语、韩语、西班牙语、德语、法语、
  俄语、意大利语、巴西葡萄牙语、阿拉伯语、印尼语、印地语、越南语、泰语和马来语。

![贴着 EPUB 原文生成的章节导读，以及保留章节上下文的私密 Ask AI 对话。](assets/ai-native-reading.png)

*AI 原生阅读把章前导读和私密追问留在原文旁边。*

![仅当前账户可见的阅读洞察：阅读日历与阅读时长趋势。](assets/reading-insights.png)

*阅读洞察把活跃阅读时长变成可回看的日历和趋势，并且只属于当前账户。*

### 技术栈

EPUB Browser 有意保持一套精简的服务端渲染 Web 技术栈。安装后的应用不使用 SPA
框架，也不要求 Node.js 运行时：

| 层次 | 技术 | 职责 |
| --- | --- | --- |
| 前端 | 语义化 HTML、CSS、基于 ES modules 和浏览器 API 的 **Vanilla JavaScript** | SSG 与 Server 共用同一套响应式界面 |
| CLI 与 Server | Python 3.9+、Starlette、Uvicorn | 转换命令、鉴权页面、API 与后台任务 |
| 数据 | SQLite 与可重建的 JSON 内容缓存 | 用户状态与 EPUB/PDF 派生内容彼此分离 |
| 书籍格式 | 项目内 EPUB 处理管线、pypdf、pypdfium2、PDF.js | EPUB 提取、PDF 元数据/封面和浏览器本地渲染 |
| 离线与资源 | Service Worker、带 hash 的不可变资源、锁定的 vendor 依赖 | 运行时不依赖 CDN 的自包含交付 |
| 发布 | PyPI、Docker、普通静态托管 | 同一份代码既可生成 SSG，也可运行持久化 Server |
| 可选 AI | OpenAI-compatible API，以及本地渲染的 Markdown、KaTeX、Mermaid | 仅 Server 模式下的 EPUB 学习层 |

Node.js 只供维护者运行浏览器侧测试，不属于读者侧的生产运行时。

### 选择 SSG 或 Server

两种模式复用同一套内容处理与页面模板。选择依据是阅读数据需要存在哪里，而不是书籍格式：

| 能力 | `ssg` | `server` |
| --- | --- | --- |
| EPUB 与 PDF | 支持 | 支持 |
| 交付方式 | 原子生成静态 HTML/资源，可部署到 Pages、对象存储或 Nginx | 动态返回已鉴权页面，内容来自可重建缓存 |
| 账户与访问控制 | 无 | 管理员/成员、受限书籍授权、Session 与 CSRF 保护 |
| OIDC 单点登录 | 不包含 | 通用 Provider、现有账户绑定与可选的成员自动创建 |
| 进度、标注、书架 | 当前浏览器本地保存 | 按已登录账户同步到 SQLite |
| 评分、书评、阅读时段 | 不生成 | 每个账户私有保存，并进入阅读洞察 |
| 源文件更新 | 重新运行 `ssg` | 重启、重新扫描或使用 `--watch` |
| 管理后台、标签、OpenAPI、WebHook | 不包含 | 包含 |
| AI 阅读与 Ask AI | 不包含 | 配置并授权后用于 EPUB；PDF 中隐藏 |
| 运行时数据库 | 无 | 持久化模式必需 |
| 适用场景 | 公共/静态托管、离线站点、简单个人发布 | 私有书库、多设备或多人阅读、自动化与访问治理 |

如果产物必须是普通静态文件，请使用 `ssg`；如果需要账户、跨设备数据、书籍访问控制或自动监听源文件，请使用 `server`。

### 演示站点

- **SSG 模式**：[epub-browser-test.yuhan.tech](https://epub-browser-test.yuhan.tech/)
- **Server 模式**：[epub.yuhan.tech](https://epub.yuhan.tech/) —— 演示账户和密码均为 `demo`。

### AI 原生阅读（仅 Server 模式）

对于 EPUB，Server 模式可以在不离开原文的前提下提供章节导读、证据解释、思维导图、
深入思考问题和私有 Ask AI 对话。结果继续服从书籍权限，成员必须获得显式授权；SSG
不会包含 AI 控件、任务、账户数据或 Provider 配置。PDF 中则明确隐藏 AI 阅读与 Ask AI。

完整交互见 [AI 原生阅读专题](../ai-native-reading.md)，富文本渲染与网络安全边界见
[本地 AI 富文本渲染器说明](../third-party-ai-renderers.md)。

## 开始使用

### 选择安装方式

EPUB Browser 提供两条安装路径。两者都支持一个或多个 `.epub` 或 `.pdf` 文件、包含书籍
的多级目录，或 Calibre 风格的书库目录。

| 安装方式 | 适用场景 | 主机要求 |
| --- | --- | --- |
| PyPI | SSG 或 Server 模式 | Python 3.9 或更高版本 |
| Docker | 持久化 Server 模式 | Docker Engine；镜像已包含 Python |

#### PyPI（SSG 或 Server）

安装命令行程序：

```bash
pip install epub-browser
```

查看分模式的命令帮助：

```bash
epub-browser --help
epub-browser ssg --help
epub-browser server --help
```

#### Docker（Server）

官方发布的 [`dfface/epub-browser`](https://hub.docker.com/r/dfface/epub-browser)
镜像默认运行 Server 模式，宿主机不需要安装 Python：

```bash
docker pull dfface/epub-browser:latest
```

体验当前版本可以使用 `latest`；生产部署建议固定到具体版本标签，保证升级可控。
书籍与状态目录挂载、Compose 快速启动、首次设置和网络安全说明见 [Docker](#docker)。

### 快速开始

#### 生成静态站点

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

#### 运行持久化 Server 书库

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/epub-browser-state \
  --watch
```

打开 `http://127.0.0.1:8000/`。首次访问时，页面会引导创建初始管理员。完成这次性设置之前，书库不会开始扫描，也不会对外暴露。

如果选择 Docker，请跳过上面的 Python 命令，直接使用
[Docker Compose 快速启动](#docker-compose)。

## 格式与阅读体验

### 输入源与稳定书籍身份

每个位置参数 `SOURCE` 都可以是 EPUB 文件、PDF 文件或目录；目录会递归搜索。
一个命令可传入多个来源：

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

切换存储方式时，既有 ID 会复制到所选载体，另一个有效载体不会被删除。从 v2.0.4 升级时，既有 embedded ID 会复制到默认 sidecar，不会重写 EPUB。对于 PDF，`--book-id-storage embedded` 必须回退到相邻的 sidecar（例如 `BOOK.pdf.epub-browser.json`）：PDF 是不可变文档，EPUB Browser 不能把 ID 写进 PDF 字节。这一回退只适用于 PDF，现有 EPUB 的 embedded/sidecar 语义保持不变。

### PDF：一页就是一个章节

两种部署模式都支持 PDF。阅读器把 PDF 的每一页当作普通的 EPUB Browser
章节，因此继续复用同一套书籍页、章节导航、目录、翻页、连续阅读、进度、阅读时段、
标注、词典和百科 UI 与数据模型：

| PDF 概念 | SSG | Server |
| --- | --- | --- |
| 第 1 页 URL | `chapter_0.html` | `/book/<book-id>/chapter_0.html` |
| 第 N 页 URL | `chapter_{N-1}.html` | `/book/<book-id>/chapter_{N-1}.html` |
| 页码和目录 | 本地生成；每页都会列出 | 从 PDF 元数据缓存动态渲染；每页都会列出 |
| 内嵌 outline | 在目标页目录项上显示 marker | 同样显示 marker，不会删除或重排页码项 |
| 滚动与翻页/分页 | 静态章节壳和本地 PDF.js | 动态共享章节壳和本地 PDF.js |
| 高亮、笔记、词典、百科 | 有文本层时使用共享的浏览器本地组件 | 有文本层时使用共享的已认证组件 |
| 原始 PDF 字节 | 静态书籍产物中只有一个 `document.pdf` | 仅 Session 可访问、支持 Range 的缓存文档路由 |

可见页码和 PDF.js 使用从 1 开始的页码；URL、状态、API 和 SQLite 中的章节索引从 0
开始。因此 PDF 第 1 页始终是 `chapter_0.html`，第 N 页是
`chapter_{N-1}.html`。规范化目录为每一页保留一个 `Page N` 项；PDF 内嵌的 outline
标题作为 marker 附加到目标页，且同一页的多个 marker 都会保留。

SSG 只写出一个 `document.pdf`，并为每页写出一个 `chapter_<index>.html` 壳。SSG
产物不含 Session 脚本、`/api/*` 请求、同步标注数据或 Server 依赖。Server 把完整且
逐字节一致的源文件缓存为 `book/<book-id>/pdf/document.pdf`，不拆页也不重写；书籍页、
目录和章节壳根据 PDF 元数据动态生成。源文件发生变化时，PDF 缓存（文档、元数据和派生
封面）会整体失效并全量刷新，不会混用新旧页面。EPUB 的 `content/` 缓存边界不受影响。

Server 的原始文档路由只接受 Session：
`GET`/`HEAD /api/books/<book-id>/document`。它会先检查登录、书籍可见性、格式和源/缓存
摘要，再提供有界的单一 Range 响应，并设置 `ETag`、`Accept-Ranges`、private 缓存、
`nosniff` 和 inline PDF disposition。路由不会暴露绝对路径，不接受 PAT，也不出现在
PAT/OpenAPI 接口面中。SSG 只有本地 `document.pdf`，没有原始文档 API。

有可用 PDF.js 文本层的 PDF 复用现有的精确选择操作弹窗和标注组件，提供 Highlight、Note、
Dictionary 和 Encyclopedia；标注存储、归属、导出、列表和深链接都共享现有实现，不新增
PDF 专用标注表或设置页。扫描版或纯图片 PDF 仍可阅读，但没有可用文本层时，基于选择的
Highlight、Note、Dictionary、Encyclopedia 和文档搜索会明确显示不可用。跨页选择可以继续
Copy，但标注和查词会显示本地化的不支持提示；页内选择仍按正常路径工作。

PDF.js 不是第二套 viewer 外壳。构建或发布前，先 hydrate 并验证锁定的第三方资源：

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
```

运行时使用本地带 hash 的 PDF.js module 和 worker 资源，绝不从 CDN 获取。图片 lightbox
使用锁定的 GLightbox 依赖；Fancyapps/Fancybox 不是运行时依赖，也不会被重新分发。锁定
资源和发布流程见 [third_party/README.md](../../third_party/README.md)。

## 部署

### SSG

SSG 会先在相邻的 staging 目录生成完整快照并验证，最后才替换目标目录。任何书籍转换失败时，旧目标目录保持不变。生成结果不包含 Server 数据库、迁移状态、账户页面或运行时缓存元数据。

SSG 有意保持本地化且不包含账户体系：

- 阅读进度和标注存储在当前站点源的浏览器存储中。
- 书架支持本地 JSON 导入、导出，没有云端 Sync 操作。
- 不生成登录、账户设置、Server API 或依赖用户身份的控件。
- 存储位置固定为浏览器本地，不向用户显示存储方式选择器。
- 静态产物包含离线资源所需的 Service Worker。

应用所需的 JavaScript、CSS、字体和图标都会写入产物。唯一的可选网络请求见[自包含与网络行为](#自包含与网络行为)。

### Server

#### 首次设置、账户与权限

全新的持久化状态目录会把普通页面重定向到 `/setup`。创建初始管理员之前，API、事件流、生成资源和书籍都会返回“需要设置”。首次设置应在 loopback 或可信私有网络中完成：第一个成功提交设置表单的访问者会取得管理员账户。

设置完成后：

- 不开放公共注册，用户由管理员创建和管理。
- 账户角色为 `administrator` 或 `member`。
- 普通书籍对所有已登录账户可见。
- 受限书籍只对管理员和被明确授权的用户可见。
- 每位用户独立拥有书架、进度、标注和活跃会话。
- 用户可以修改自己的密码和撤销自己的会话。
- 管理员可以管理用户、角色、密码、会话和书籍授权。
- 会话使用 HttpOnly Cookie、CSRF 防护和 30 天滑动有效期。

#### OIDC 单点登录与账户绑定

Server 模式可以接入一个通用 OpenID Connect（OIDC）Provider，例如 Authelia、
Keycloak、Authentik 或其他兼容服务。在 **管理后台 → OIDC 登录** 中填写向用户展示的
Provider 名称、Issuer URL、客户端 ID、客户端密钥、完整回调 URI、Scopes 和用户名
Claim。EPUB Browser 使用 discovery、Authorization Code 与 S256 PKCE，验证签名后的
ID Token，并且只用 `(issuer, sub)` 标识外部身份；邮件地址和用户名 Claim 只用于展示与
创建账户，绝不会作为身份主键。

请在 Provider 中登记完整且逐字一致的回调地址，包括协议和主机名：

```text
https://reader.example.com/auth/oidc/callback
```

已有用户可先用本地密码登录，再从“账户设置”绑定 Provider；未知外部身份也可以通过一次
现有本地用户名和密码验证完成绑定。可选的自动创建只会生成**无密码成员**，绝不会导入
管理员角色。应先让已有用户完成绑定：过早开启自动创建可能产生**重复的本地账户**。
即使关闭成员的本地密码登录，**本地管理员**密码入口也始终保留；请定期验证并妥善保管
这份恢复凭据。退出只结束 EPUB Browser 本地会话，不会触发 Provider 全局退出；系统也
不会保存 Provider access token 或 refresh token。

Authelia 需要配置 confidential client。下面只展示 OIDC client 片段，值均为测试占位符，
并假设 Authelia 必需的 Provider 密钥和策略已另行配置。请在 Authelia 中保存强随机客户端
密钥的哈希，然后只在 EPUB Browser 中输入一次对应的原始密钥：

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'epub-browser'
        client_name: 'EPUB Browser'
        client_secret: '<AUTHELIA_HASH_OF_A_RANDOM_SECRET>'
        public: false
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        redirect_uris:
          - 'https://reader.example.com/auth/oidc/callback'
        scopes: ['openid', 'profile', 'email']
        response_types: ['code']
        grant_types: ['authorization_code']
        token_endpoint_auth_method: 'client_secret_basic'
```

EPUB Browser 侧可填写 Issuer `https://auth.example.com`、客户端 ID `epub-browser`、
Scopes `openid profile email` 和用户名 Claim `preferred_username`。保存时会实时执行
discovery 与能力校验；如果校验失败，原配置会保持不变。

#### 配置与治理 AI 阅读

管理员可在 **管理后台**（用户管理之后、书籍管理之前）配置 OpenAI-compatible Base
URL、API Key、模型、超时、聊天上下文预算、并发上限和默认每日调用限制。AI 阅读默认对
成员关闭；管理员需逐一授权，并可设置成员的每日上限（`0` 表示不限）。

章节共享学习层与整书导读按可访问用户和界面语言共享；后续 Ask AI 对话则仅归对应账户。
结果、任务状态、自定义标签、书籍 AI 分类和私有问答都保存在 SQLite。模型配置变化后，
旧结果仍然可用，直到管理员显式重新生成。

当用户生成导读或提出问题时，选中的 EPUB 正文与压缩后的会话上下文会发送给已配置的
外部 Provider。只有在读者被允许将内容发送给该 Provider 时才应启用此能力。API Key
不会返回浏览器，也不会由 API 暴露；请保护好 Server 状态目录。

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

#### 浏览器启动与日志

默认情况下，Server 在 HTTP 监听器启动后，会尝试打开操作系统的默认浏览器。`--no-browser` 只阻止这次本机启动动作，**不会关闭 Web 界面，也不会禁止浏览器访问**；它只是跳过本机的 `webbrowser.open(...)` 调用。Docker、systemd、SSH、无图形界面的主机和脚本中都建议使用它。

默认使用 `--log-level warning`，CLI 会避免输出日常信息，以免破坏终端进度展示。交互式终端只打印一次监听 URL；Docker 和服务等非交互环境保持安静。使用 `--log-level info` 开启运行日志和 HTTP 访问日志，使用 `--log-level debug` 获取最详细的信息。`--log` 保留为 `--log-level info` 的兼容别名。

首次扫描和监听扫描的进度显示在 Web 页面，而不是终端 `tqdm`。全部成功时摘要会自动关闭；有失败时会保留到用户手动关闭。使用 `--watch` 时，修复或替换源文件就会触发下一次扫描，无需手动 Retry。

#### 持久化与临时状态

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

持久化的 `data/epub-browser.db` 必须位于本地文件系统；共享或网络文件系统不支持 WAL 并发。已验证的备份仍保存在 `data/backups/`，其中包含所有已提交的 WAL 数据。

#### 局域网与反向代理

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

要让活跃会话和登录限流在反向代理后记录真实客户端 IP，配置反向代理的**直接套接字网络**（不能写公网客户端地址段）：

```bash
epub-browser server /path/to/books \
  --server-dir /path/to/state \
  --watch \
  --host 0.0.0.0 \
  --trusted-proxy-cidr 172.32.11.1/32 \
  --trusted-proxy-cidr 10.42.0.0/16 \
  --cookie-secure \
  --no-browser
```

每个直连代理地址或网段重复传入一次 `--trusted-proxy-cidr`。只有直连对等端属于其中任一 CIDR 的请求才会使用 `X-Forwarded-For`；其他来源只记录直连地址。Uvicorn 的转发地址处理已禁用，因此 `Forwarded` 和 `FORWARDED_ALLOW_IPS` 都不能扩大该信任边界。仅当浏览器通过 HTTPS 访问服务时才使用 `--cookie-secure`。

### Docker

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
  dfface/epub-browser:latest
```

修改端口绑定或代理规则之前，请先访问 `http://127.0.0.1:8080/setup` 完成首次设置。

#### Docker Compose

仓库提供了 [docker-compose.yml](../../docker-compose.yml)，供偏好 Compose 的用户使用。在仓库目录下创建 `Library/` 并放入 EPUB 或 PDF 后，执行：

```bash
docker compose up -d --build
```

示例只发布到 `127.0.0.1:8080`，源 EPUB/PDF 图书放在 `./Library`，Server 状态持久化到 `./EpubBrowserFiles`。文件中显式写出了完整的 Server `command`，可直接在此追加部署专用参数，而无需覆盖镜像的隐式默认值。请访问 `http://127.0.0.1:8080/setup` 完成一次性初始化。远程访问时，应保留 loopback 绑定，并在前方部署带认证的 TLS 反向代理。

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
  dfface/epub-browser:latest
```

首次成功启动后，可移除这次性密钥挂载。只有所有 EPUB 已经包含有效且匹配的 embedded ID 时，书库才可以只读挂载。把同一 ID 嵌入 EPUB 时，既有 sidecar 会保留。

只有迁移旧书架 JSON 时才挂载 `/app/SyncData:ro`：

```bash
-v /path/to/legacy-sync:/app/SyncData:ro
```

示例把容器端口只发布到主机 loopback，从而让容器位于主机边界之后。远程访问时，请使用 TLS 反向代理，并配置其真实容器网络 CIDR 和 `--cookie-secure`。

## 参考与运维

### 命令参考

#### `epub-browser ssg SOURCE [SOURCE ...]`

| 参数 | 含义 |
| --- | --- |
| `--output-dir DIR`, `-o DIR` | 必填；原子静态快照的目标目录。 |
| `--base-path PATH` | 公开 URL 前缀，默认 `/`；必须以 `/` 开头和结尾。 |
| `--book-id-storage sidecar\|embedded` | 本次命令中所有源文件的稳定身份载体，默认 `sidecar`。 |
| `--log` | `--log-level info` 的兼容别名。 |
| `--log-level debug\|info\|warning\|error` | 运行日志详细程度；默认 `warning`，日常转换输出保持安静。 |

#### `epub-browser server SOURCE [SOURCE ...]`

`--server-dir` 与 `--ephemeral` 必须且只能选择一个。

| 参数 | 含义 |
| --- | --- |
| `--server-dir DIR` | 持久化权威数据与可替换缓存的根目录。 |
| `--ephemeral` | 使用一次性状态；与 `--server-dir` 互斥。 |
| `--watch`, `-w` | 监听并协调源文件新增、更新、移动和删除。 |
| `--host ADDRESS` | 监听地址，默认 `127.0.0.1`。 |
| `--port PORT`, `-p PORT` | 监听端口，默认 `8000`。 |
| `--no-browser` | 不启动本机默认浏览器；Web 界面仍可访问。 |
| `--log` | `--log-level info` 的兼容别名。 |
| `--log-level debug\|info\|warning\|error` | 运行日志详细程度；默认 `warning`。`info` 和 `debug` 会开启 HTTP 访问日志。 |
| `--legacy-sync-dir DIR` | 启动迁移时读取旧书架 JSON。 |
| `--book-id-storage sidecar\|embedded` | 本次命令中所有源文件的稳定身份载体，默认 `sidecar`。 |
| `--admin-username NAME` | 无人值守的初始管理员；后备为 `EPUB_BROWSER_ADMIN_USERNAME`。 |
| `--admin-password-file FILE` | 首选初始密钥文件；后备为 `EPUB_BROWSER_ADMIN_PASSWORD_FILE`，未设置文件时再使用 `EPUB_BROWSER_ADMIN_PASSWORD`。 |
| `--trusted-proxy-cidr CIDR` | 可重复指定的直接代理网络信任边界，用于安全解析 `X-Forwarded-For` 中的客户端 IP。 |
| `--cookie-secure` | 只通过浏览器侧 HTTPS 发送会话 Cookie。 |

#### 旧版 v1 语法

整个 v2 主版本周期都会兼容旧语法：

| v1 命令 | v2 映射 |
| --- | --- |
| `epub-browser BOOKS` | `epub-browser server BOOKS --ephemeral` |
| `epub-browser BOOKS --output-dir STATE` | `epub-browser server BOOKS --server-dir STATE` |
| `epub-browser BOOKS --no-server --output-dir DIST` | `epub-browser ssg BOOKS --output-dir DIST` |
| `--sync-dir DIR` | `server --legacy-sync-dir DIR` |

旧版专用 `--keep-files` 会保留临时 Server 目录；持久化 Server 目录本来就不会删除。指定 `--log` 时，兼容适配器会打印等价 v2 命令，否则保持安静。

### 阅读数据与功能归属

- 递归发现 EPUB 和 Calibre 书库、元数据标签、搜索与拼音搜索
- 响应式 Library、书籍详情和章节阅读界面
- 滚动、翻页、连续阅读、内容宽度、字体、自定义 CSS、主题和纯净阅读模式
- 高亮、笔记、标注浏览、嵌套书架分组、标签和 JSON 导入/导出
- 支持英文、简体中文、繁体中文、韩语、日语、西班牙语、德语、法语、俄语、
  意大利语、巴西葡萄牙语、阿拉伯语、印尼语、印地语、越南语、泰语和马来语界面
- Kindle/Silk 的电子阅读器友好模式；部分依赖浏览器能力的功能可能精简

| 数据 | SSG | Server |
| --- | --- | --- |
| 阅读进度 | 浏览器本地 | 已登录用户的 SQLite 记录 |
| 高亮与笔记 | 浏览器本地 | 已登录用户的 SQLite 记录 |
| 私人评分、书评与阅读时段历史 | 不存在 | 已登录用户的 SQLite 记录 |
| 书架 | 浏览器本地；导入/导出 | 已登录用户的版本化云端文档；自动保存 |
| 账户与会话 | 不存在 | `<server-dir>/data` 下的 SQLite |
| 书籍授权 | 不存在 | `<server-dir>/data` 下的 SQLite |

Server 不提供“本地/云端”存储选择器：已登录阅读数据固定存储在 Server。详细的私人阅读时段历史绝不会输出到 SSG。SSG 不探测 Server API，始终使用当前浏览器源的本地存储。

### 自包含与网络行为

阅读功能是自包含的：所需 JavaScript、CSS、字体、图标、清单和转换后的 EPUB 资源全部由本地提供，不依赖 CDN。阻断公网出站访问不会影响首次设置、登录、书库浏览、阅读、标注、进度、书架、后台管理或书籍转换。

页脚可能向 GitHub Releases API 发起一次可选请求，用于提示是否存在新版 EPUB Browser。离线、请求失败或被阻断时，只是不显示更新提示。

SSG 会发布静态 Service Worker。Server 会禁用并清退整个源范围的 Service Worker，避免一个账户收到另一个账户缓存过的受保护内容。

### Server API 与 WebHook

Server 账户可在“账户设置”中创建带作用域的个人访问令牌（PAT）。外部客户端通过 `Authorization: Bearer <PAT>` 访问版本化的 `/api/v1/*`；浏览器 Cookie 不能认证这些路由。接口覆盖可见书籍与章节正文、令牌所有者的书架、进度、标注和书评；带 `admin:data:read` 的管理员 PAT 还可只读访问所有用户的非敏感数据。

OpenAPI 3.1 文档位于 `/openapi.json`，登录后可在 `/api-docs` 浏览本地接口参考。例如：`curl -H 'Authorization: Bearer …' https://reader.example/api/v1/books`。章节接口默认返回已清洗 HTML，添加 `?format=text` 可返回纯文本。

管理员可在“后台管理”中维护 WebHook。签名密钥只在创建或轮换时显示；投递会持久化、签名并对非 2xx 结果重试。书评事件只含用户 ID、书籍 ID、动作和时间，不包含评分或书评正文。

### 数据安全与迁移

升级持久化 Server 前，请备份源 EPUB/PDF 图书和 `<server-dir>/data`。替换容器时必须继续挂载同一个持久化状态目录。

启动迁移会自动执行，并可在中断后安全继续。它会验证旧数据库、创建备份、升级副本、把合格的旧书架/进度/标注数据归属给待创建的初始管理员，并只在成功检查点之后清退可重新生成的旧公开资源。普通请求不会扫描旧同步目录。数据库损坏、密码哈希无效、旧数据库含义不明确和 ID 冲突都会停止启动，而不是猜测或覆盖。

迁移后的根目录 `epub-browser.db` 或 `annotations.db` 会作为敏感的非权威恢复副本保留；`data/epub-browser.db` 才是权威数据库，Server 请求不会读取保留的根目录文件。请严格限制该恢复副本的访问权限。只有在 Server 已停止、权威数据库与迁移状态中记录的备份均已验证，并且不再需要回滚到 v1 时，才可由运维人员手动删除；EPUB Browser 不会自动删除它。

如果旧目录同时包含 `epub-browser.db` 与 `annotations.db`，启动会停止并保留原文件。备份、回滚、缓存重建和冲突恢复见[迁移到 v2](../migration-v2.md)。

### 常见问题

#### 命令已启动，但没有自动打开浏览器

在有图形界面的本机运行时可移除 `--no-browser`，也可以手动打开监听 URL。Docker、systemd、SSH 和非交互环境通常都应手动访问。

#### CLI 看起来没有输出

不使用 `--log` 时保持安静是预期行为，非交互环境尤其如此。需要运行和访问细节时添加 `--log`。Server 扫描进度显示在 Web 界面中。

#### Docker 无法写入稳定 ID

镜像默认使用 embedded 身份。请把 `/app/Library` 以读写方式挂载，或预先嵌入有效且匹配的 ID。只有更适合可写 sidecar 时，才通过自定义命令改用 `--book-id-storage sidecar`。

#### 部署到子路径后，SSG 链接失效

使用规范化的 `--base-path`（例如 `/reader/`）重新生成，并让静态主机把产物部署在同一 URL 前缀下。

#### 升级后 Server 拒绝启动

保留数据和源文件，查看第一条迁移或验证错误，并参阅 [docs/migration-v2.md](../migration-v2.md)。不要通过删除权威 `data/` 目录来绕过错误。

## 开发与许可证

### 参与贡献

欢迎在 [dfface/epub-browser](https://github.com/dfface/epub-browser) 提交 Issue 和 Pull Request。一份有效的问题报告应包含准确命令、浏览器/设备、复现步骤、相关日志，以及在法律和版权允许时附上的 EPUB 或 PDF。

#### 开发维护约束

修改内容处理、页面模板、缓存、权限、资源或部署行为之前，请先阅读
[AGENTS.md](../../AGENTS.md)。其中定义了 EPUB/PDF 格式边界、SSG/Server 职责、
独立缓存修订、动态 i18n、安全检查和提交前验证要求。*reader chapter*、
*reading window*、*reading stage*、*content cache* 等统一术语见
[CONTEXT.md](../../CONTEXT.md)。

简要原则是：只维护一套阅读器 UI；Server 专属数据不能进入 SSG；EPUB/PDF 派生缓存
必须与 SQLite 用户数据分离；运行时不能新增 CDN 依赖。改动共享界面时，应在适用范围内
同时覆盖两种格式与两种部署模式。

#### 从源码仓库开发

第三方浏览器文件是构建输入，不是本项目源码，因此 Git 会故意忽略
`epub_browser/assets/vendor/`。开发或构建前需要显式生成锁定版本的资源，
再离线验证：

```bash
python3 tools/sync_vendor_assets.py fetch
python3 tools/sync_vendor_assets.py verify
python3 -m unittest tests.test_vendor_assets -v
python3 -m build
```

上述命令只有 `fetch` 会下载浏览器 vendor 资源。锁文件记录不可变的 npm
tarball、文件摘要、允许列表和许可证；`verify`、测试、已生成资源的源码构建以及
安装后的阅读器都不会下载浏览器资源。标准的隔离构建命令 `python3 -m build`
仍可能从 Python 包索引获取构建依赖。若要在完全断网的环境构建，需在断网前生成 vendor
资源并预装 `build`、`setuptools` 和 `wheel`，断网后再运行
`PIP_NO_INDEX=1 python3 -m build --no-isolation`。wheel、sdist、Docker 镜像和生成的
SSG 站点均包含已验证文件，运行时不依赖 CDN。更新、发布和仓库清洁度流程见
[third_party/README.md](../../third_party/README.md)。

### 许可证

[MIT](../../License.txt)
