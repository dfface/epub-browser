# Server 本地词典与百科查阅：详细设计

**状态：已确认**

**范围：Server 模式 V1；不改变 EPUB 内容缓存、SSG 输出或现有标注数据模型。**

## 1. 产品边界

读者选中文字后有五个并列动作：**复制 / 高亮 / 笔记 / 查词 / 百科**。

| 动作 | 数据来源 | 联网 | 写入 |
| --- | --- | --- | --- |
| 复制 | 当前选区 | 否 | 否 |
| 高亮 | 当前选区 | 否 | annotations |
| 笔记 | 当前选区 | 否 | 仅确认保存时 |
| 查词 | 已安装的本地词典 | 否 | 否 |
| 百科 | Wikimedia / Wikipedia | 是 | 否 |

“查词”与“百科”不是同一功能的两种来源：前者是离线、可预期的词条释义；后者是在线百科摘要。两者均不创建标注、不记录查询历史，也不向 EPUB 内容缓存写入数据。

## 2. 本期范围与非目标

### 包含

- 仅向已登录且可阅读该书的 Server 阅读页提供查词和百科。
- 管理员安装用户合法持有的本地 **StarDict** 与 **MDict** 词典。
- StarDict 支持 `.ifo` + `.idx` + `.dict` 或 `.dict.dz`，可选 `.syn`；MDict 支持 `.mdx`，可选同名 `.mdd`。
- 每种输入语言可启用多个本地词典，并配置一个全局默认词典；首次仅顺序查询默认词典。
- 固定、无密钥的 Wikimedia 百科摘要服务；服务端代理请求、速率限制与归因。
- 五语言 i18n、键盘和触摸可达，以及 Server API 的认证、书籍 ACL、CSRF 和输入限制。

### 不包含

- Kindle/MOBI/AZW/KFX 导入、DRM 绕过、Amazon 连接或任何词典内容分发。
- 在线商业词典、机器翻译、查询记录、背单词、个人词典排序或用户上传。
- 词典全文搜索、富文本/脚本输出、词典内图片/音频渲染。
- SSG 中的查词、百科、词典资源或 `/api/*` 依赖。

## 3. 本地词典格式与安全

输入文件只作为管理员安装的受控运行时数据，存于 `<server-dir>/data/dictionaries/<uuid>/`，绝不写入 `book/<id>/content/`。

- 词典包须同一次上传提交并校验完整文件组合；文件名不参与最终路径。
- 各格式适配器产出统一的 `DictionaryEntry(headword, normalized_headword, aliases, definition_text)` 流。
- 释义仅保留受限纯文本；所有 HTML、脚本、外部 URL、图片和音频引用都会剥离。MDict 的 `.mdd` 在 V1 只用于识别并忽略资源，不发送给浏览器。
- 拒绝受密码保护、加密、损坏、超出大小/条目/展开限制，或未产生有效条目的词典。读取格式不表示项目有权分发其内容；管理员须确认拥有使用权。
- 词典导入时生成独立只读 SQLite 索引文件，而后删除原始上传。SQLite 只保存最终可查的词头、别名、纯文本释义和元数据，不存于主状态库，也不与 EPUB 正文重复混放。

首版只实现 StarDict 与 MDict；DSL、Dictd、XDXF 为后续可插拔适配器。每个适配器独立注册，增加格式不改变读者 API 或前端。

## 4. 数据与 API

主状态库新增词典目录和默认映射（格式、语言、显示名称、条目数、内容散列、启用状态、归因、创建时间），但不保存词典正文。主状态 schema 仅在本地词典功能实现时迁移。

```text
POST /api/books/{book_id}/dictionary/lookup { text }
  → require principal → book ACL → metadata language → default local dictionary
  → { found, query, dictionary, entries[] }

POST /api/books/{book_id}/encyclopedia/lookup { text }
  → require principal → book ACL → metadata language → Wikimedia page summary
  → { found, title, description?, extract?, source_url, attribution }
```

两条接口都使用 POST、`Cache-Control: private, no-store`，不接受浏览器指定的词典 ID、语言或上游 URL。查询文本最大 120 Unicode code points，拒绝控制字符。

管理员 API 负责安装、列出、启停、设默认与删除本地词典；所有写操作必须是管理员且经 CSRF。API 不返回上传路径、解析堆栈或原始词典内容。

## 5. 在线百科

百科服务固定访问语言匹配的 Wikipedia `page/summary` 端点；语言从受保护书籍 metadata 推导，而非用户提交。服务端使用固定主机白名单、描述性 User-Agent、3 秒超时、全进程最多 3 个并发请求，并遵从 `Retry-After`。它不将查询结果持久化；可用进程内短时缓存降低公共服务负担。

页面显示来源名称、原条目链接和 CC BY-SA 归因；外部 JSON 一律当作纯文本，以 `textContent` 渲染。网络失败、429 和未收录均是独立、可翻译的短提示；不会影响本地查词或阅读。

## 6. 页面与资产边界

共享章节模板仅在 `deployment_mode == "server"` 输出最小运行时标记及 Server-only `dictionary.js` / `dictionary.css`。SSG 仍只显示复制、高亮、笔记，绝不发布字典/百科资源、配置或 API URL。

选区菜单为 `role=toolbar`。五项皆为独立按钮，最小触摸面积 44px、间距至少 8px；窄屏允许菜单横向滚动但不隐藏动作。查词、百科结果各自使用可聚焦的非模态 dialog；加载时声明状态，Esc、点击正文、重新选择或翻页均关闭结果并取消请求。所有动态文本以 `textContent` 注入。

## 7. 验收

- 安装 StarDict 与 MDict 均能通过同一查词 API 命中词头和别名；停用/删除默认词典后不再查询。
- 未登录、无书籍权限、非管理员、无 CSRF、非法包和超限输入均被安全拒绝。
- 本地查词断网仍可用；百科失败不影响查词，且返回结果有来源归因。
- 查词/百科无数据库历史、无 URL 查询参数、无 EPUB 缓存改动；不提高 `SERVER_OUTPUT_REVISION`。
- SSG 不含第 4、5 项及其资产；Server 五项可通过键盘和触摸访问，所有可见文案覆盖 en、zh-CN、zh-TW、ko、ja。
