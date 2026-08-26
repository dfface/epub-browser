# Server Kindle 词典导入与查词：详细设计

**状态：待评审**

**范围：Server 模式 V1**

**不改变：EPUB 内容缓存、SSG 输出、现有标注数据模型**

## 1. 要解决的问题

读者在正文中选中一个词或短语时，需要快速得到自己安装的 Kindle 词典释义；这一次查词不应产生高亮、笔记或任何阅读记录。管理员可以导入合法的、无 DRM 的 Kindle 词典文件，给所有 Server 用户按书籍语言提供默认词典。

用户可见的选区菜单固定且精简为四项：**复制 / 高亮 / 笔记 / 查词**。不引入词典历史、单词本、翻译服务、个性化上传或复杂的词典选择器。

## 2. 范围与非目标

### 本期包含

- 仅在已登录、可阅读该书的 Server 阅读页显示“查词”。
- 导入用户已合法取得、未加密的 Kindle/Mobipocket 字典：`.mobi`、`.azw3`（含 KF8）。
- 管理员导入、查看状态、启用/停用、删除、为输入语言设置一个全局默认词典。
- 词典索引词、变形词与纯文本释义的本地查询。
- 以书籍语言决定默认词典；无法得到书籍语言时返回“未配置词典”，不猜测用户语言。
- 完整 i18n、键盘可达、屏幕阅读器状态提示，以及 Server API 的鉴权、ACL、CSRF 和输入限制。

### 本期明确不做

- SSG 查词、SSG 词典资源或任何 `/api/*` 依赖。
- 调用 Kindle 设备/应用已安装词典、Amazon 登录、购买、下载，或规避 DRM。
- KFX、加密 MOBI/AZW、普通 Kindle 图书作为词典、在线翻译、机器翻译。
- 用户私有上传、个人词典顺序、查询历史、背单词、词典内全文检索。
- 复杂富文本或原始 Kindle HTML 的输出；V1 只返回安全的纯文本释义。

## 3. 用户体验

### 3.1 选区菜单

正文选中有效文本后，`annotation.js` 只建立可撤销的临时选区草稿，随后在选区附近弹出四个等权按钮：

| 动作 | 结果 | 是否写入服务器 |
| --- | --- | --- |
| 复制 | 将选中文本复制到剪贴板，关闭菜单和临时草稿 | 否 |
| 高亮 | 立即以当前默认颜色创建无笔记标注 | 是，annotations |
| 笔记 | 打开笔记编辑器；只有点击保存才创建带笔记的标注 | 仅保存时 |
| 查词 | 移除临时高亮，显示暂态词典浮层 | 否 |

颜色不是第五个入口；高亮完成后，读者仍可在既有标注详情中调整颜色。笔记弹窗取消、关闭、Esc 或失焦时都清除临时草稿，不留下标注。查词结果也不转为标注，用户若想保留内容，主动使用“高亮”或“笔记”。

查词请求期间浮层显示加载状态。成功时显示“词头、词典名称、语言方向、最多 3 条释义”；找不到词、书籍无默认词典、网络失败分别显示可翻译的短消息。点击正文、Esc、重新选择文本或翻页都会关闭浮层并中止仍在进行的请求。结果以 `textContent` 写入 DOM，不拼接服务端字符串为 HTML。

菜单为 `role=toolbar`，按钮有可翻译 `aria-label`；浮层为可聚焦的非模态 `dialog`，打开后焦点进入标题，Esc 返回正文。触摸端使用同一菜单，不使用只有 hover 才可触发的入口。

### 3.2 管理员体验

账号管理页增加“词典”标签。管理员可：

1. 选择 `.mobi` 或 `.azw3` 文件并提交导入；文件上传后立即得到任务状态。
2. 看到“排队中 / 导入中 / 已完成 / 失败”的任务、文件名、失败原因及完成后词典条目数和语言方向。
3. 在已安装词典列表中启用或停用词典；每个输入语言只能有一个全局默认词典。
4. 删除不再需要的词典。删除操作使用明确确认提示；完成后不可再查词，关联的默认项同时删除。

上传完成前不改变默认项。失败任务保留诊断代码和安全、可翻译的用户说明，不暴露解析堆栈或服务器路径。

## 4. 内容、资产和部署边界

```text
Server 阅读页（已鉴权且通过书籍 ACL）
  └─ 选中文字 → POST /api/books/{book_id}/dictionary/lookup
       └─ DictionaryService
            ├─ 从 Server 内容缓存读取该书 metadata 的 language（只读）
            ├─ StateStore 找该语言的默认词典
            └─ 打开 data/dictionaries/{dictionary_id}.sqlite（只读）
                 └─ 命中词头/词形 → JSON 结果 → 暂态浮层

管理员上传
  └─ POST /api/admin/dictionaries/imports（原始二进制请求体）
       └─ 受限暂存文件 → 导入任务 → Kindle 解析适配器
            └─ 临时 SQLite → 校验 → 原子 rename 到 data/dictionaries/
                 └─ StateStore 写目录、任务和默认映射
```

- `book/<id>/content/` 仍只保存 EPUB 派生的 metadata、TOC 与章节内容。词典属于 Server 运行时资源，绝不写入这里。
- 不读取或重写 `chapter_*.json`；查词只在请求时读取已存在的 `metadata.json` 语言字段。因此不提高 `SERVER_OUTPUT_REVISION`，也不要求重转 EPUB。
- 新前端词典资产加入 `SERVER_ONLY_ASSET_PATHS`。Server 的 `AssetPublisher` 发布它们；SSG 的 `EPUBLibrary`、SSG processor 和 SSG CLI 通过既有排除表不发布、不预缓存也不引用它们。
- 共享章节模板只在 `deployment_mode == "server"` 时写入最小化的启用标记及词典资产 URL；`server_pages.py` 继续复用同一模板，所以部署后立即生效，无须转换既有书籍。

## 5. 持久化设计

### 5.1 主状态库：`data/epub-browser.db`

`DB_SCHEMA_VERSION` 从 13 升至 14。新增表只存目录、任务和默认关系，不存词典正文：

```sql
CREATE TABLE dictionaries (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  source_language TEXT NOT NULL,
  target_language TEXT NOT NULL,
  entry_count INTEGER NOT NULL CHECK(entry_count > 0),
  content_sha256 TEXT NOT NULL UNIQUE,
  attribution TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
  created_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dictionary_defaults (
  source_language TEXT PRIMARY KEY,
  dictionary_id TEXT NOT NULL REFERENCES dictionaries(id) ON DELETE CASCADE,
  updated_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE dictionary_import_jobs (
  id TEXT PRIMARY KEY,
  original_filename TEXT NOT NULL,
  content_sha256 TEXT,
  status TEXT NOT NULL CHECK(status IN ('queued','running','complete','failed','interrupted')),
  error_code TEXT,
  dictionary_id TEXT REFERENCES dictionaries(id) ON DELETE SET NULL,
  requested_by_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK((status = 'failed') = (error_code IS NOT NULL))
);
```

另建 `(status, created_at, id)` 的部分任务队列索引、`dictionaries(source_language, enabled)` 索引和 `dictionary_import_jobs(dictionary_id)` 索引。迁移初始化时把残留 `running` 任务改成 `interrupted`；系统启动后可安全地由管理员重试，不会尝试恢复半解析文件。`dictionary_defaults` 必须指向启用词典：服务层在停用、删除、设置默认时在同一事务中维持该不变量。

### 5.2 每部词典库：`data/dictionaries/{uuid}.sqlite`

路径只由服务端 UUID 生成；浏览器传入的文件名永不参与路径拼接。每个库以只读 URI 打开，包含：

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE entries (
  id INTEGER PRIMARY KEY,
  headword TEXT NOT NULL,
  normalized_headword TEXT NOT NULL,
  pronunciation TEXT,
  definition_text TEXT NOT NULL,
  rank INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE forms (
  normalized_form TEXT NOT NULL,
  entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  rank INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (normalized_form, entry_id)
);
CREATE INDEX idx_entries_normalized_headword ON entries(normalized_headword, rank, id);
CREATE INDEX idx_forms_normalized_form ON forms(normalized_form, rank, entry_id);
```

`meta` 保存导入器版本、原始 SHA-256、语言、显示名称、创建时间和条目数，以便打开前校验目录与文件的一致性。释义只保存抽取、清洗后的 Unicode 纯文本；最大单条释义、词头和变形数均受上限控制。

### 5.3 文件生命周期

- 原始上传先写入 `data/dictionary-imports/{job_id}.upload`，以独占方式创建；成功或失败后删除。
- 导入器写入同目录的 `{dictionary_id}.sqlite.tmp`，完成 `PRAGMA integrity_check`、条目计数和元数据校验后，以原子 rename 发布为 `{dictionary_id}.sqlite`。
- 主库事务只在最终文件存在且可读后创建目录记录；失败则移除临时产物。
- 删除先在主库事务中移除默认关系和目录记录，再将输出数据库移动到 `data/dictionaries/.trash/{id}.sqlite`，最后删除该临时回收文件。启动时清理遗留 trash 和没有目录记录的过期 tmp/upload，绝不删除存在目录记录的文件。

## 6. Kindle 导入器

新增一个窄范围、可单测的 `kindle_dictionary.py` 适配器，而不是引入 Calibre 全量依赖。它使用经过许可证审查且固定版本的非 DRM Kindle/Mobipocket 解析实现；从 Kindle 字典索引恢复 `<idx:entry>`、`<idx:orth>` 和 `<idx:iform>`，并读取 source/target language 元数据。实现可参考 KindleUnpack 的公开 dictionary-index 处理逻辑，但必须在实现前记录实际采用依赖/代码的许可证、版本和 SHA。

导入规则：

- 只接受扩展名和魔数都匹配的 MOBI/AZW3；最大原始文件 512 MiB，文件名最长 200 Unicode 字符。
- 明确检测并拒绝 DRM/encryption、KFX、未知容器、非字典内容、损坏索引、缺少可用源语言或零条目结果。
- 解析运行在独立受限 worker 进程；主 Server 只负责持久化任务状态。worker 有可配置的 CPU/墙钟时间、内存、条目数、每条词形数、累计释义字节和解压输出上限。超限产生稳定错误码并清理临时文件。
- 规范化使用 Unicode NFC、首尾空白折叠、语言无关的大小写折叠；保留原始词头显示。空字符串、超过 120 个 Unicode code points 的查询、包含控制字符的查询被拒绝。
- 解析器剥离脚本、样式、外部 URL 和所有 HTML 标签，再将块级文本以换行连接，限制最大释义 12 KiB。不能安全抽取的条目跳过，并在完成前检查仍有足够有效条目。
- 同 SHA-256 的已完成导入不再重复构建，返回已存在词典及一个完成任务；同 SHA 的排队/运行任务返回原任务，不启动第二个 worker。

## 7. API 合约

所有变更 API 由全局认证中间件校验 CSRF；管理 API 额外使用 `require_admin`。错误遵循现有 `{error: {code, message}}` 形式，`message` 由客户端以 code 翻译或服务端按现有 locale 机制给出。

### 管理 API

| 方法和路径 | 请求 | 响应 |
| --- | --- | --- |
| `GET /api/admin/dictionaries` | 无 | 已安装词典、默认映射、近期导入任务 |
| `POST /api/admin/dictionaries/imports` | 原始二进制 body；`X-Epub-Browser-Filename` | `202 {job}` 或现有去重任务 |
| `GET /api/admin/dictionaries/imports/{job_id}` | 无 | 单个任务状态 |
| `POST /api/admin/dictionaries/imports/{job_id}/retry` | 无 | 新/重置后的 `202 {job}`，仅失败或 interrupted |
| `PUT /api/admin/dictionaries/{id}` | `{enabled: boolean}` | 更新后的词典 |
| `PUT /api/admin/dictionary-defaults/{source_language}` | `{dictionary_id}` | 更新默认项 |
| `DELETE /api/admin/dictionaries/{id}` | 无 | `204` |

管理员列表绝不返回本地绝对路径、解析堆栈或上传原始内容。`id` 必须是 UUID；source language 使用 BCP-47 的保守规范化并与已导入词典的 source language 精确比较。

### 读者查词 API

`POST /api/books/{book_id}/dictionary/lookup`，body 为 `{ "text": "selected text" }`。不接受客户端声明的语言、词典 ID 或文件路径。流程必须依序完成：

1. `require_principal`；使用 `book_access_denied`/同等机制确认该用户能阅读 book ID。
2. 从受保护内容缓存的 `metadata.json` 取得规范化书籍语言。
3. 查询该语言的启用默认词典；不存在时返回 `dictionary_not_configured`（404）。
4. 对请求文本做长度/控制字符校验和规范化，在该词典只读库按 `forms.normalized_form` 查询，再回退 `entries.normalized_headword`。
5. 按 rank 返回最多三个 `{headword, pronunciation?, definition}`；命中为空返回 `{found: false}`（200）。

成功响应还包含 `{dictionary: {id, display_name, source_language, target_language}, query, entries, found}`。响应使用 `Cache-Control: private, no-store`；请求使用 POST，避免将查询词写入 URL、浏览器历史、反向代理常见访问日志或 Service Worker 缓存。

查询本身不写主数据库，不保存使用者、书名、词语、时间或 IP 的查词历史。普通用户不能列出词典目录，也不能探测不属于其可读书籍的语言配置。

## 8. 服务集成

新增 `DictionaryService(store, server_dir)`：

- 创建并验证 `data/dictionaries`、`data/dictionary-imports` 和 `.trash` 目录，不接受符号链接逃逸。
- 在 Starlette lifespan 中启动一个单并发导入调度器，启动时将运行中任务标记 interrupted，再处理 queued 任务；关闭时停止接收新任务并等待/终止 worker。
- 提供 `submit_import`、`get_job`、`retry_import`、`list_admin`、`set_enabled`、`set_default`、`delete_dictionary` 与 `lookup`。HTTP 层只作认证、JSON/二进制解析和响应映射。
- 每次 lookup 在目录读取和文件打开之间重新验证 `enabled` 与默认映射；文件缺失或完整性失败时返回受控 `dictionary_unavailable`，并记录服务器端错误，不将 SQL/文件细节交给读者。

`server.py` 在通用 `/api/{path:path}` 标注回退路由之前注册所有词典路由。管理员页面继续由 `server_chrome.py` 壳和 `auth.js` 的账户页行为承载；词典管理界面只在 Server 的管理员会话中出现。

## 9. 前端实施边界

- `annotation.js` 负责四项菜单的选择状态、复制、高亮、笔记以及调用一个新的 Server-only `dictionary.js` 小模块；它不解析词典、不持久化 lookup，也不向 SSG 发请求。
- `dictionary.js` 和 `dictionary.css` 是 `SERVER_ONLY_ASSET_PATHS`；只有 Server 章节模板以 asset manifest URL 加载。它从章节页的最小 runtime config 读取 book ID 和启用标记。
- 若查词资产未加载、没有 Server runtime config 或用户在 SSG 页面，选区菜单只显示复制/高亮/笔记，绝不显示一个会失败的“查词”按钮。
- 所有可见字符串添加 en、zh-CN、zh-TW、ko、ja 的键值；扩展现有 i18n 覆盖测试，禁止在首次方 JS/HTML 中遗留硬编码英文提示。

## 10. 验收与测试

### 单元与迁移

- 新库初始化直接得到 schema 14；12、13 版本数据库正确迁移；运行中任务被中断标记；外键、默认项、启用状态、重复 SHA 和删除级联均受约束。
- 导入器覆盖 MOBI 字典、AZW3/KF8 字典、词头/变形词、Unicode 规范化、纯文本清洗、重复导入、超限、DRM、KFX、普通书、损坏容器和零条目。
- 词典 SQLite 创建后通过 integrity check；缺文件、篡改 meta、无效 URI 和临时文件清理不会使服务崩溃。

### Server API 与权限

- 未登录得到认证响应；非管理员不能管理或导入；无 CSRF 的变更被拒绝。
- 无书籍权限时，查词在读取任何元数据/词典前拒绝；可读书只能使用其 metadata 的语言默认词典。
- 没有默认词典、词典停用、词形命中、词头回退、未命中、无效文本、服务文件缺失、导入失败和删除中的词典都返回稳定且不泄密的响应。
- 查询响应带 `private, no-store`，且 StateStore 中不新增任何 lookup 记录。

### 阅读器与部署边界

- JS 测试验证四个入口的互斥行为：复制无写入；高亮只创建标注；笔记仅保存后创建；查词不创建标注，取消与 Esc 清理草稿。
- 验证查词结果使用安全文本插入、能关闭/取消请求、焦点和 aria 行为正确。
- Server 动态章节已加载词典资产并能查词；同一内容缓存不重转书籍即可获得新 UI。
- SSG `AssetPublisher` 输出不含 `dictionary.js` / `dictionary.css`，SSG HTML 不含“查词”、词典 config 或词典 API URL；Server 输出包含受控资产。
- 覆盖五种 locale，并运行现有 i18n coverage、Server、state、asset publisher、SSG/Server 边界和完整测试套件，最后运行 `git diff --check`。

## 11. 发布顺序

1. 先落地状态迁移、词典库构建器和纯 Python 测试。
2. 接入 DictionaryService、受保护管理/查询 API 和生命周期测试。
3. 增加管理员管理面与 Server-only 资产发布边界。
4. 最后改选区菜单、i18n、可访问性与端到端行为。

这保证任何中间提交都不会把“查词”暴露给 SSG，也不会出现点击菜单却没有安全后端的状态。
