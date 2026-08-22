# EPUB Browser 开发与维护指南

本仓库同时支持 **SSG** 和 **Server** 两种部署方式。新增功能时，优先维护同一份内容处理与页面模板；部署模式只决定内容何时、以什么方式交付给读者。

## 两种模式的职责

| 模式 | 交付方式 | 允许的能力 |
| --- | --- | --- |
| SSG | 转换 EPUB 时写出完整的 `index.html`、章节页和静态资源 | 纯静态阅读、无需服务端的数据与交互 |
| Server | 转换时缓存 EPUB 派生内容；请求页面时动态渲染当前页面壳 | 登录、权限、书库管理、标注、AI 阅读、AI 对话等服务端能力 |

Server 专属功能必须由服务端配置、权限或 API 显式保护，不能被打进 SSG 输出；SSG 页面也不能依赖 `/api/*`、登录态或 SQLite 数据。

## 共享代码与缓存边界

### 单一事实来源

- EPUB 解析、清洗、目录规范化和页面模板位于 `epub_browser/processor.py`。
- SSG 直接调用这些模板并写入 HTML 文件。
- Server 由 `epub_browser/server_pages.py` 读取内容缓存，再调用同一组 `EPUBProcessor` 模板动态返回 HTML。
- 不要为 Server 复制一套 `index.html`、章节页或目录页模板。模式差异应在共享模板内以小范围的 `deployment_mode` 分支表达。

### Server 内容缓存

Server 转换产物中的 `book/<id>/content/` 是**仅 EPUB 派生内容**，主要包括：

- `metadata.json`：书籍元数据与章节列表；
- `toc.json`：规范化目录；
- `chapter_<n>.json`：已清洗的章节正文和 EPUB 内联样式信息。

这些文件不是公开资源，也不包含当前页面 HTML、i18n 文案、权限结果、用户数据或编译后的 JS/CSS URL。浏览器请求 `index.html`、`chapter_<n>.html`、`toc.json` 时，Server 从内容缓存动态生成响应；不可变资源仍由资源发布器以哈希文件名静态提供。

因此：**Server 模式的 UI、i18n、权限、客户端行为和资源更新，只需要重启/部署，不应要求重新转换 EPUB。**

## 何时修改 Server 内容修订

`SERVER_OUTPUT_REVISION_FILE`（当前为 `.server-content-revision`）表示的是**内容缓存 schema 修订**，不是页面、UI 或资产修订。

仅在旧的 `content/` 缓存无法被新代码安全、完整地渲染时，才提高 `SERVER_OUTPUT_REVISION`。典型情形：

- 修改 `metadata.json`、`toc.json` 或 `chapter_<n>.json` 的结构/字段语义；
- 新渲染或 AI 任务必须依赖旧缓存中不存在的 EPUB 派生字段；
- 改变章节清洗、目录、资源引用等内容语义，导致旧缓存结果不可兼容；
- 增加新的必需内容缓存文件，并同步更新缓存校验与测试。

下列改动**不得**仅为使页面更新而提高内容修订：

- CSS、JavaScript、i18n、图标、页面排版、按钮和其它 UI；
- Server 权限判定、登录态、动态导航、AI 面板或客户端交互；
- 已由独立 SQLite migration 管理的标注、AI 结果、对话等应用数据。

若模板新增了对内容字段的依赖，先判断该字段是否来自 EPUB 内容缓存：是则同时升级 schema 和校验；否则把数据在请求时或应用数据库中获取，避免污染 EPUB 内容缓存。

## 新增或修改功能的流程

1. **先分类**：明确功能是 SSG+Server 共用、仅 Server，还是仅构建期能力。不要默认把 Server 功能暴露给 SSG。
2. **优先共用**：内容提取、正文渲染、目录、书籍卡片等相似结构应复用处理器/模板；只把不可避免的模式差异放在窄小条件分支中。
3. **明确数据归属**：EPUB 固有内容进入内容缓存；用户/权限/AI/对话等运行时数据进入 SQLite 或 API；不可变构建资源交给 asset publisher。
4. **保持缓存可演进**：改变 Server 内容缓存时更新修订、缓存校验和迁移/重建策略；只改变页面时确认无需重转 EPUB。
5. **守住权限边界**：Server 路由先鉴权与可见性过滤，再读取内容或返回 AI/标注数据。不要信任浏览器传来的书籍、用户或章节权限。
6. **保持 i18n 完整**：新增可见文案应进入现有翻译表；服务端返回的用户可见错误、帮助文本和管理配置说明也要翻译。
7. **避免双维护**：新增页面或组件时，优先抽成共享函数/模板；若确实只能 Server 使用，要在代码旁说明原因与访问保护。

## 提交前验证

- 涉及 EPUB 转换或页面模板：运行 SSG 和 Server 相关测试，确认两种模式都可渲染。
- 涉及 Server 内容缓存：验证全新转换只写 `content/` 而不依赖旧 HTML；验证动态 `index.html`、章节页和 `toc.json`；验证 AI 正文提取也可读取缓存 JSON。
- 涉及仅 UI/资源/i18n 的 Server 改动：重启 Server 后确认新页面/哈希资源立即生效，且不触发 EPUB 重转。
- 涉及权限、AI 或 SQLite：覆盖未登录、无权限、管理员及正常成员路径，并确保 SSG 没有引用该能力。
- 最后运行与改动范围相符的测试，并执行 `git diff --check`。

## 关键文件

- `epub_browser/processor.py`：EPUB 内容处理、共享页面模板、Server 内容缓存写入。
- `epub_browser/server_pages.py`：从 Server 内容缓存恢复渲染状态并调用共享模板。
- `epub_browser/server.py`：Server 路由、鉴权、动态页面响应和安全头。
- `epub_browser/server_library.py`：转换缓存校验、重建与书库协调。
- `epub_browser/ai_reading.py`：AI 阅读任务；必须兼容 Server 内容缓存而非假设章节 HTML 存在。
- `epub_browser/state_store.py`：Server 运行时 SQLite 数据与迁移。
