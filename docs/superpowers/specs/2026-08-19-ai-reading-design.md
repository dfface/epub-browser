# AI 阅读设计

日期：2026-08-19
状态：提案
基线：EPUB Browser v2.0.1（Server mode）

## 概要

AI 阅读让读者在当前章节内快速建立理解，并在不越过已读范围的前提下继续追问。它不是将整本书丢给模型的摘要器：服务端只发送当前章节、已生成的前文摘要和读者的问题；结果带有可回到原文的证据定位，并持久化在现有 SQLite 数据库中。

功能按依赖分为三个连续子项目：

1. I18N 基础设施与既有界面中英文迁移——已在 v1.11.3 落地，本项目只做 AI 新界面的覆盖审计。
2. AI 服务端基础——配置、正文提取、OpenAI-compatible 调用、调度、SQLite 缓存与无剧透上下文。
3. 自适应 AI 帮读——三类书籍策略、三层结果、脉络图、证据定位和后续追问。

## 目标

- 读者可以在 Server 模式的章节页打开“AI 阅读”，获得比快速浏览更有结构的理解。
- 技术书输出概念/依赖脉络；小说输出截至本章的发展脉络和故事梗概；其他书输出论述或知识脉络。
- 模型输出和界面随 English / 简体中文界面语言变化，EPUB 原文语言保持不变。
- 已生成的章节结果在 SQLite 中复用；相同输入不会重复消耗模型调用。
- 每个解释性结论至少可关联一个当前或已读章节的证据片段；不得引用未来章节。

## 非目标

- 不支持 SSG、离线静态站点或浏览器直连模型。
- 不支持把 API key、Provider URL 或模型设置开放给浏览器端修改。
- 不做整本书预读、向量数据库、RAG 服务或跨书对话。
- 不把模型原始响应、完整 prompt、绝对本地路径或 API key 保存到 SQLite、日志或浏览器。
- 不新增 E2E 测试。

## 用户体验

章节阅读页的固定工具栏新增“AI 阅读”入口。首次打开抽屉时，若服务未配置，显示本地化的不可用说明；配置后显示“开始帮读”及简短的隐私提示：当前章节文本会发送至本服务器配置的 AI Provider。生成期间显示可取消的等待状态，不阻塞阅读。

完成后按三层呈现：

| 层级 | 目的 | 技术书 | 小说 | 通用/非虚构 |
| --- | --- | --- | --- | --- |
| 快速掌握 | 30 秒知道本节讲什么 | 核心结论与术语 | 本节事件梗概 | 主旨与关键事实 |
| 脉络理解 | 看清关系与推进 | 概念、前提、推论图 | 人物、冲突、事件链 | 论点、证据、结构图 |
| 深入理解 | 形成可迁移理解 | 易错点、应用与自测 | 动机、张力、主题（截至本章） | 推理缺口、关联与反思问题 |

“证据”点击后定位到同章文本；前文章节证据通过书内章节链接打开。脉络图是无脚本 SVG/DOM 渲染的节点与边，节点同样可以跳转到证据。读者可提一个后续问题；回答与问题以当前用户隔离保存，且仍只能使用截止当前章的内容。

## 配置与安全

AI 只在以下环境变量均有效时启用：

    EPUB_BROWSER_AI_BASE_URL=https://provider.example/v1
    EPUB_BROWSER_AI_API_KEY=...
    EPUB_BROWSER_AI_MODEL=gpt-4.1-mini

可选变量：EPUB_BROWSER_AI_TIMEOUT_SECONDS（默认 60，范围 5–180）和 EPUB_BROWSER_AI_MAX_CONCURRENCY（默认 2，范围 1–4）。Base URL 必须为 https，或本机 loopback 的 http；客户端不能覆盖这些配置。以标准库 HTTP 调用 <base-url>/chat/completions，发送 bearer key。先请求 JSON object 输出；不支持该字段的兼容服务仅允许去掉 response_format 后重试一次。

服务端对用户问题限制为 2,000 UTF-8 字节，对提取正文限制为 24,000 字符，对前文摘要限制为 6,000 字符。每个生成请求都带超时、固定并发上限和同缓存键合并；失败信息经过净化后才返回前端。Provider 地址、密钥、原始异常、文件系统路径与完整 prompt 均不暴露。

## 内容范围与无剧透边界

给第 N 章生成时，输入只包括：

- 该书当前版本的第 N 章纯文本；
- 0..N-1 中已成功生成的短“前文桥接摘要”；
- 当前章节标题、书籍元数据和 UI locale；
- 用户的后续问题（如有）。

任何 N+1..end 的章节文本、TOC 未来标题、未来缓存结果和模型推测都不进入 prompt。系统提示明确要求“只陈述给定证据支持的内容；不预示、猜测或暗示后续发展”。解析响应时，所有 evidence 的 chapter_index 必须在 0..N，且 excerpt 必须是对应允许文本的规范化子串；否则整个结果作为 provider 协议错误，不缓存。

## 架构

    章节页 AI 阅读抽屉
              |
       Starlette /api/ai-reading
              |
    AIReadingService（有界任务调度）
       |          |           |
    提取正文   前文摘要链   OpenAI-compatible client
              |
          StateStore / SQLite

### 后端模块

- ai_config.py：不可变配置、环境变量解析与安全的 public availability payload。
- ai_client.py：兼容 OpenAI chat-completions 的标准库 HTTP 客户端。
- ai_reading.py：章节正文提取、策略选择、prompt 构造、结构化响应校验与有界任务服务。
- state.py：AI 结果和用户后续问答的迁移与持久化接口。
- server.py：仅 Server mode 挂载 availability、生成、任务状态、结果和 follow-up 路由。
- runtime.py：一次构造服务并在关闭时停止 worker；SSG 不构造该服务。

### SQLite 模型

ai_reading_results 是共享、可复用的章节结果。唯一键为 (book_id, chapter_index, source_fingerprint, locale, strategy, model, result_version)；保存已验证的结果 JSON、前文桥接摘要、内容哈希、创建时间。书籍更新或章节文本变化自然产生新键，旧记录可保留以便回滚。

ai_reading_followups 是用户隔离的问答。键含 username、结果 id、问题与回答；用户名语义与现有标注一致。问题和回答均不参与其他读者的缓存。

数据库 schema 升级必须只新增表/索引并递增 DB_SCHEMA_VERSION；从 v2.0.1 启动时不迁移或修改既有标注、书架、阅读进度和书籍行。

### API 合同

| 方法与路径 | 作用 | 成功响应 |
| --- | --- | --- |
| GET /api/ai-reading/availability | 是否已配置、容量是否可接受 | {enabled, model}，不含 Provider URL |
| POST /api/ai-reading/books/{book_id}/chapters/{chapter_index} | 获取缓存结果或入队生成 | 200 complete 或 202 queued |
| GET /api/ai-reading/jobs/{job_id} | 查询调用状态 | queued、running、complete 或 failed |
| GET /api/ai-reading/books/{book_id}/chapters/{chapter_index} | 读取已缓存当前版本的结果 | result 或 ai_result_not_found |
| POST /api/ai-reading/results/{result_id}/follow-ups | 为当前用户入队追问 | 202 job_id |

所有路由使用稳定 JSON code 错误字段，遵守当前 /api 的 Cache-Control: no-cache 行为。仅 POST 写入前检查 RuntimeStatus.is_ready()；读取基线 shell 与 availability 不被 reconciliation 阶段阻塞。未知书、非法章节、服务未启用、队列饱和、超时、Provider 响应无效均有独立错误码。

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

服务端限制数组长度、字符串长度、节点唯一性、边端点和 evidence 引用；用 textContent 渲染所有模型与 EPUB 文本。策略只能是 technical、fiction 或 general。策略由标题、元数据和当前文本的模型分类结果决定，但没有通过严格校验即回退 general。

## I18N

静态按钮、空状态、进度、错误、隐私告知和无障碍标签使用 window.EpubBrowserI18n 的 aiReading.* 键，英文和简体中文键树必须完全相同。模型输出使用当前 locale 明确要求的语言；正文/引用保持原文。新增 I18N 覆盖检查禁止 AI UI sink 写死英文。

## 验收标准

- 未配置环境变量时，SSG 没有 AI 资源，Server 页面显示本地化不可用状态，且没有模型网络调用。
- 已配置时，当前章节可生成三层结果；同一输入第二次返回 SQLite 缓存，不新建 Provider 调用。
- 技术、小说、通用策略分别产生对应字段与可渲染脉络图。
- 所有证据只能指向当前或更早章节，且 excerpt 在允许文本中逐字存在。
- 同一缓存键的并发请求合并为一个 job；用户可读取其终态；关闭 Server 不遗留 worker。
- UI 语言切换影响所有 AI 控件和新生成的模型语言；模型/EPUB 文本不进入 innerHTML。
- Python 与 Node focused/full suite 通过；不运行 E2E。

