# AI 阅读设计

日期：2026-08-19
状态：已实施，待人工验收
基线：EPUB Browser v2.1.0（Server mode）

## 概要

AI 阅读让读者在当前章节或明确选择的整书范围内快速建立理解并继续追问。章节模式只发送当前章节；书籍页提供无剧透导读、已读脉络和明确含剧透的全书复盘。全书复盘按章节桥接摘要后再汇总。结果、任务状态和私有追问持久化在现有 SQLite 数据库中。

功能按依赖分为三个连续子项目：

1. I18N 基础设施与既有界面中英文迁移——已在 v1.11.3 落地，本项目只做 AI 新界面的覆盖审计。
2. AI 服务端基础——配置、正文提取、OpenAI-compatible 调用、调度、SQLite 缓存与无剧透上下文。
3. 自适应 AI 帮读——三类书籍策略、三层结果、脉络图、证据定位和后续追问。

## 目标

- 读者可以在 Server 模式的章节页打开“AI 阅读”，获得比快速浏览更有结构的理解。
- 技术书输出概念/依赖脉络；小说输出截至本章的发展脉络和故事梗概；其他书输出论述或知识脉络。
- 模型输出和界面随 English / 简体中文界面语言变化，EPUB 原文语言保持不变。
- 已生成的章节结果在 SQLite 中复用；相同输入不会重复消耗模型调用。
- 结果提供可回到章节的证据片段；章节与已读模式不主动提供未来章节文本。

## 非目标

- 不支持 SSG、离线静态站点或浏览器直连模型。
- 不支持把 Provider API Key 返回给浏览器、写入 EPUB 或写入日志。
- 不做向量数据库、RAG 服务或跨书对话。
- 不把模型原始响应、完整 prompt、绝对本地路径或 API key 保存到 SQLite、日志或浏览器。
- 不新增 E2E 测试。

## 用户体验

章节阅读页的固定工具栏新增“AI 阅读”入口；书籍页的书籍操作区新增“AI 导读”入口。两者打开同一套面板，但书籍页先让用户选择帮读范围。未配置或未授权时入口隐藏；配置并授权后，面板展示生成状态、结果与追问。所选范围的文本会发送至本服务器配置的 AI Provider；生成不阻塞阅读。

完成后按三层呈现：

| 层级 | 目的 | 技术书 | 小说 | 通用/非虚构 |
| --- | --- | --- | --- | --- |
| 快速掌握 | 30 秒知道本节讲什么 | 核心结论与术语 | 本节事件梗概 | 主旨与关键事实 |
| 脉络理解 | 看清关系与推进 | 概念、前提、推论图 | 人物、冲突、事件链 | 论点、证据、结构图 |
| 深入理解 | 形成可迁移理解 | 易错点、应用与自测 | 动机、张力、主题（截至本章） | 推理缺口、关联与反思问题 |

“证据”点击后定位到同章文本；前文章节证据通过书内章节链接打开。脉络图是无脚本 SVG/DOM 渲染的节点与边，节点同样可以跳转到证据。读者可提一个后续问题；回答与问题以当前用户隔离保存，且仍只能使用该结果允许的内容范围。

### 书籍页的三种可选模式

书籍页的“AI 导读”不能默认读取全书。它展示三个互斥选项，并在结果顶部保留当前模式和范围：

| 模式 | 输入范围 | 适用时机 | 剧透规则 |
| --- | --- | --- | --- |
| 无剧透导读 | 书籍元数据、当前已读进度之前的桥接摘要；不读取未来章节或未来目录标题 | 开始阅读前或任何时候 | 不透露、推测或暗示后续事件/结论 |
| 已读脉络 | 从第 0 章到读者保存的当前阅读进度（无进度时仅使用当前书籍元数据） | 阅读过程中 | 仅总结已经读过的章节 |
| 全书复盘（含剧透） | 全部可提取章节 | 读完后或明确想复盘时 | 明确选择该模式后即可入队，不再显示二次确认 |

三种模式都使用同样的“快速掌握 / 脉络理解 / 深入理解”三层结果和证据图，但小说的事件线、技术书的概念依赖、通用书的论述结构均严格限制在所选输入范围。选择“全书复盘（含剧透）”并点击生成即代表该次范围选择；无须为了正文外发或剧透另弹确认。

## 后台配置、权限与安全

AI 的全局单模型配置由管理员在后台面板维护，位置固定在“用户管理”之后、“书籍可见性管理”之前。配置包含启用开关、OpenAI-compatible Base URL、API Key、模型名、超时、最大并发和默认每日调用额度；保存后新任务立即使用新配置，运行中的任务继续使用创建时的配置快照。

API Key 第一版按管理员的决定以明文保存在 SQLite，但只允许管理员替换或清除，任何 API 响应都只返回 api_key_configured，绝不回显密钥。数据库、备份与服务器文件读取权限因此属于部署者的安全责任，README 必须明确说明。

Base URL 必须是管理员设置的 HTTP(S) URL；浏览器端不能覆盖它。以标准库 HTTP 调用 <base-url>/chat/completions，发送 bearer key，并要求模型仅返回 JSON 文本。

管理员可按用户授予或撤销 AI 使用权。所有普通用户默认禁用；管理员默认可用。授权项支持覆盖全局默认每日额度（默认 20 次，0 表示不限额）。额度按实际启动的 Provider 调用数、按服务器本地自然日计数；缓存命中和调用前失败不计数。仅在尚未收到 Provider 响应的连接失败时自动重试一次，重试同样计数。

服务端对用户问题限制为 2,000 字符，对提取章节正文限制为 48,000 字符，对桥接摘要限制为 8,000 字符。每个生成请求都带超时和固定并发上限；失败信息经过净化后才返回前端。Provider 地址、密钥、原始异常、文件系统路径与完整 prompt 均不暴露。

## 内容范围与无剧透边界

给第 N 章生成时，输入只包括：

- 该书当前版本的第 N 章纯文本；
- 0..N-1 中已成功生成的短“前文桥接摘要”；
- 当前章节标题、书籍元数据和 UI locale；
- 用户的后续问题（如有）。

章节模式中的 N+1..end 文本、TOC 未来标题和未来缓存结果不进入 prompt。书籍模式将范围固定为无剧透导读的元数据、已读脉络的 0..progress，或全书复盘的全书集合；服务端绝不接受客户端给出的任意章节范围。模型输出作为不可信文本处理，所有结果都以 textContent 渲染。

## 架构

    章节页 AI 阅读 / 书籍页 AI 导读抽屉
              |
       Starlette /api/ai-reading
              |
    AIReadingService（有界任务调度）
       |          |           |
    提取正文   前文摘要链   OpenAI-compatible client
              |
          StateStore / SQLite

### 后端模块

- ai_client.py：兼容 OpenAI chat-completions 的标准库 HTTP 客户端。
- ai_reading.py：章节正文提取、策略选择、prompt 构造、结构化响应校验与有界任务服务。
- state.py：AI 结果和用户后续问答的迁移与持久化接口。
- server.py：仅 Server mode 挂载 availability、生成、任务状态、结果和 follow-up 路由。
- runtime.py：一次构造服务并在关闭时停止 worker；SSG 不构造该服务。

### SQLite 模型

ai_settings 是单行全局配置，保存 Provider 与额度设置及递增的 config_revision。ai_user_access 以 user_id 保存授权开关和可选额度覆盖。管理 API 返回 mask 后的配置，不返回 API Key。

ai_tags 与 book_ai_tags 保存管理员维护的扁平自定义标签和书籍关联。标签用 Unicode 规范化名称去重；EPUB dc:subject 不写入这两张表，始终来自书籍元数据。前台对两种来源按规范化名称合并显示，后台显示 EPUB（只读）与服务端标签（可编辑）。book_ai_profiles 是书籍独立的 AI 分类：auto、technical、fiction 或 general；它不由普通标签隐式改变。

ai_reading_results 是共享、可复用的章节或书籍结果。每个 generation 含 config_revision、书籍指纹、范围、locale、profile、内容哈希和结果 JSON；结果与一个不含配置版本的“当前版本”指针关联。配置变化不自动替换该指针，只有获授权用户主动重新生成才创建新的 generation 并更新默认结果。所有完成结果都持久化于 SQLite；管理员可按书、按配置版本或全量清除。

ai_reading_jobs 持久化最小任务状态（id、所有者 user_id、安全 cache key、状态、时间与安全错误码），但不保存正文、prompt 或 Provider 原始响应。启动后残留的 queued/running job 标记为 interrupted。ai_reading_followups 是用户隔离的问答；仅所有者可读取，管理员只能获得聚合用量和安全错误码。

数据库 schema 升级必须只新增表/索引并递增 DB_SCHEMA_VERSION；从 v2.1.0 启动时不迁移或修改既有标注、书架、阅读进度和书籍行。

### API 合同

| 方法与路径 | 作用 | 成功响应 |
| --- | --- | --- |
| GET /api/ai/status | 是否启用及当前用户是否获授权 | enabled、authorized、daily_limit |
| POST /api/ai/reading | 获取缓存结果或入队章节/书籍生成 | 200 complete 或 202 queued |
| GET /api/ai/jobs/{job_id} | 查询调用状态及完成结果 | queued、running、complete 或 failed |
| POST /api/ai/followups | 为当前用户入队追问 | 202 followup |
| GET /api/ai/results/{result_id}/followups | 读取当前用户的追问 | followups |
| GET/PUT /api/admin/ai/settings | 管理员读取/保存全局模型配置 | 永不返回 API Key |
| GET/PUT /api/admin/ai/users/{user_id} | 管理员读取/设置某用户 AI 授权和额度 | enabled 与 daily_limit |
| GET/POST/PUT/DELETE /api/admin/ai/tags | 管理员维护服务端标签目录 | 管理标签 |
| GET/PUT /api/admin/books/{book_id}/ai | 管理员设置独立 AI 阅读分类和服务端标签 | profile 与 tags |

所有 AI 路由都要求 v2.1 已认证 principal，且先检查 can_read_book() 再检查 AI 授权；撤销书籍或 AI 权限立即禁止读取/生成共享结果。所有路由使用稳定 JSON code 错误字段，遵守当前 /api 的 Cache-Control: no-cache 行为。仅 POST 写入前检查 RuntimeStatus.is_ready()；读取基线 shell 与 availability 不被 reconciliation 阶段阻塞。未知书、非法章节、服务未启用、未获授权、额度耗尽、队列饱和、超时、Provider 响应无效均有独立错误码。

## 结构化结果合同

模型返回 JSON，不信任任何 HTML：

    {
      "strategy": "technical",
      "quick_grasp": {"title": "", "summary": "", "takeaways": [""]},
      "narrative": {"summary": "", "items": [{"label": "", "detail": ""}]},
      "deep_dive": {"insights": [{"title": "", "explanation": "", "question": ""}]},
      "mind_map": {"nodes": [{"id": "n1", "label": "", "evidence_ids": ["e1"]}],
                   "edges": [{"from": "n1", "to": "n2", "label": "supports"}]},
      "evidence": [{"id": "e1", "chapter_index": 3, "excerpt": "", "explanation": ""}],
      "bridge_summary": ""
    }

服务端限制数组长度、字符串长度、节点唯一性、边端点和 evidence 引用；用 textContent 渲染所有模型与 EPUB 文本。策略只能是 technical、fiction 或 general。策略由标题、元数据和允许范围内文本的模型分类结果决定，但没有通过严格校验即回退 general。

## I18N

静态按钮、空状态、进度、错误、隐私告知和无障碍标签使用 window.EpubBrowserI18n 的 aiReading.* 键，英文和简体中文键树必须完全相同。模型输出使用当前 locale 明确要求的语言；正文/引用保持原文。新增 I18N 覆盖检查禁止 AI UI sink 写死英文。

## 验收标准

- 未配置后台模型时，SSG 没有 AI 资源，Server 的书籍/章节页面显示本地化不可用状态，且没有模型网络调用。
- 已配置时，当前章节可生成三层结果；同一输入第二次返回 SQLite 缓存，不新建 Provider 调用。
- 技术、小说、通用策略分别产生对应字段与可渲染脉络图。
- 所有证据只能指向当前或更早章节，且 excerpt 在允许文本中逐字存在。
- 同一缓存键的并发请求合并为一个 job；用户可读取其终态；关闭 Server 不遗留 worker。
- UI 语言切换影响所有 AI 控件和新生成的模型语言；模型/EPUB 文本不进入 innerHTML。
- 书籍页提供无剧透导读、已读脉络与全书复盘三个可选模式；全书复盘以明确模式名称提示剧透，不再二次确认。
- AI 授权、额度、书籍可见性、后台标签、书籍 AI 分类与缓存清理均能在管理员面板完成；普通用户不能读取 Key、追问内容或不可见书籍的 AI 数据。
- Python 与 Node focused/full suite 通过；不运行 E2E。
