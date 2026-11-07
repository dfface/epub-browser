# Server 事件循环阻塞治理方案（阶段 1）

**范围：** 仅治理 Server 模式下 `async` 处理函数在事件循环里直接执行同步代码的问题。**不做 FastAPI 迁移**，不引入 `APIRouter`/`Depends`/Pydantic，不改任何对外行为。

**Tech Stack：** Python 3、Starlette、uvicorn、SQLite（WAL）、`asyncio`/`anyio`、`unittest` + `starlette.testclient`。

**状态：** 阻塞点清单与治理方案已定稿，等待分批实施。

---

## 0. 前提与边界

- 当前 Server 已经是 Starlette + uvicorn（[`runtime.py`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/runtime.py#L489-L533)、[`create_app`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L737-L752)）。本阶段只改“同步调用跑在事件循环上”，不动框架。
- 不修改 `SERVER_OUTPUT_REVISION`、`PDF_OUTPUT_REVISION`、`PDF_METADATA_SCHEMA_VERSION`，不触碰 `content/` 与 `pdf/` 缓存结构。
- 不改 URL、Cookie 属性、缓存头、304/ETag/Range/416、SSE 事件名、`{"code","message"}` 错误体、CSP 计算规则、i18n 文案、SSG 输出。
- 页面模板继续由 `processor.py` / `server_pages.py` 提供，不新增第二套模板。

---

## 1. 线程模型与执行器

新增 `epub_browser/server_concurrency.py`（模块级单例，`atexit` 关闭）：

| 执行器 | 线程数 | 承载 | 理由 |
| --- | --- | --- | --- |
| `db_executor` | 4 | 所有 `StateStore` 同步方法 | SQLite WAL 允许多读单写；4 个线程足以覆盖并发页面的少量 DB 往返，同时避免默认 40 线程各开一个 SQLite 连接导致 fd/写锁争用。单请求内 DB 调用是顺序的，不会自占多线程 |
| `render_executor` | 2 | EPUB/PDF 页面渲染、CSP 计算、`hashlib` 大对象摘要 | CPU 密集；CPython GIL 下增加线程收益有限，2 个线程保证一个慢渲染不会堵住所有页面，同时不挤占 DB 池 |
| `io_executor` | 2 | 上传落盘、词典包安装、大文件复制/探测 | 这些操作耗时长但频率低；独立池避免占满 anyio 默认 limiter 而拖慢普通请求 |
| anyio 默认 limiter（40） | 共享 | 零散、短小的文件读取（如 5 字节魔数探测、单次 `stat`/`read_text`） | 不值得为一次性小 IO 另建池 |

封装：

```python
async def run_db(fn, *args, **kwargs) -> Any
async def run_render(fn, *args, **kwargs) -> Any
async def run_io(fn, *args, **kwargs) -> Any
```

统一使用 `loop.run_in_executor(pool, functools.partial(fn, *args, **kwargs))`，异常原样向上抛，取消语义与 `run_in_threadpool` 一致（客户端断开不会中断已提交的线程工作）。

**原则：** 每个 `async def` 内不得直接调用 `store.*`、`Path.read_text/read_bytes/write_*`、`EPUBProcessor` 渲染、Argon2、词典查询/安装、`sync_bookshelf` 等同步函数；必须经过上面三个入口之一。纯同步且无 `await` 的处理函数可直接改为 `def`，由 Starlette 自动放进默认线程池。

---

## 2. 完整阻塞点清单与治理方式

标记说明：**DB** = `db_executor`；**R** = `render_executor`；**IO** = `io_executor`；**TP** = anyio 默认线程池（`run_in_threadpool`）；**MEM** = 改为内存缓存/纯内存操作，不再阻塞。

### 2.1 中间件与每请求开销（Batch 1）

| # | 位置 | 原来阻塞什么 | 治理 |
| --- | --- | --- | --- |
| M1 | [`auth_middleware` L5144](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L5144) → [`has_administrator`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/state.py#L2698-L2720) | 每请求打开 SQLite、查 `sqlite_master`、`PRAGMA table_info`、查 admin | **MEM**：`SetupStateMonitor` 内存布尔；启动时探测一次；无管理员期间由中间件以 ≤100ms 节流触发一次 `await run_db(store.has_administrator)`；已完成后由后台任务每 5s 校验一次 |
| M2 | [`is_public_unauthenticated_asset` L806-L829](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L806-L829) → [`current_published_assets` L790-L798](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L790-L798) | 每个静态资源请求都读 `assets/asset-manifest.json` 并 JSON 解析 | **MEM**：`AssetManifestCache`，键为 `(st_mtime_ns, st_size)`；未变化时零 IO（仅一次 `os.stat`），重新发布后下一次请求自动重建 |
| M3 | [`auth_middleware` L5192](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L5192) `auth_service.create_session` | 代理认证会话补发 Cookie 时同步写 SQLite | **DB** |
| M4 | [`auth_middleware` L5182](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L5182) `verify_csrf` | HMAC 比较，微秒级 | 保持同步（不属于阻塞） |

**缓存失效规则（关键）**

`SetupStateMonitor`：

- 初始值：`create_app()` 时同步探测一次（只读一次，不在请求路径）。
- `False → True`：`/setup` 成功后处理函数立即 `mark_complete()`，**本进程零窗口**；其他进程（若存在）因 `False` 分支 ≤100ms 重新探测，最多 100ms 收敛。
- `True → False`：管理员删除/角色降级后处理函数立即 `invalidate()`；后台任务每 5s 兜底校验；其他进程最多 5s 收敛。
- 一旦为 `True`，中间件只读内存，不做任何 IO。
- 单实例约束：`runtime.py` 已用目录锁保证同一输出目录只有一个 Server 进程；上述 TTL 仅为多 worker/多实例部署的兜底，不改变单实例语义。

`AssetManifestCache`：

- 每次访问只做 `os.stat`（微秒级），键不变则直接返回缓存对象。
- 资产重新发布会改写 `asset-manifest.json` → `mtime_ns/size` 变化 → 下一次请求重建；多进程共享同一文件系统，各自按 stat 收敛。
- 解析失败时**继续抛出原异常**（`is_public_unauthenticated_asset` 返回 False、`current_asset_url` 回退），与现状一致；不把“解析失败”变成“沿用旧清单”，避免安全语义变化。
- 缓存对象不可变（复用现有 `PublishedAssets`），并发读取安全。

### 2.2 认证 / 账户 / 管理后台（Batch 2）

| # | 位置 | 原来阻塞什么 | 治理 |
| --- | --- | --- | --- |
| A1 | [`setup` L1372-L1440](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L1372-L1440) | `has_administrator` ×2、`complete_setup`（Argon2 + 建管理员 + 建会话） | **MEM** 读缓存；`complete_setup` → **DB**（Argon2/哈希一并在线程内完成），成功后 `mark_complete()` |
| A2 | [`oidc_callback` L1765](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L1765)、[`oidc_associate` L1861](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L1861) | `link/provision/stage/complete` OIDC、`get_oidc_association`、`authenticate_password`、`login_retry_after_seconds` | **DB**；每个分支把同一逻辑段的 DB 调用合并到一次 offload |
| A3 | [`login` L1931-L2037](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L1931-L2037) | `get_oidc_settings`、Argon2 `authenticate_password`、`login_retry_after_seconds`、`replace_session`/`create_session` | **DB**：登录校验 + 限流读取 + 会话写入合并为一个同步函数，一次 offload；HTTP 层仍按原顺序返回 401/423/302 |
| A4 | [`logout` L2039](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2039)、[`session` L2049](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2049)、[`csrf` L2081](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2081) | `revoke_session`、`get_user`、`get_oidc_settings` | **DB** |
| A5 | [`change_password` L2093-L2125](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2093-L2125) | Argon2 校验 + `hash_password` + 撤销会话 | **DB**（哈希 CPU 在线程内完成，一次 offload） |
| A6 | [`list_own_sessions` L2127](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2127)、[`revoke_own_session` L2146](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2146)、PAT 列表/创建/撤销 L2177-L2247 | `session_id_from_token`、`list_sessions`、`list/create/revoke_personal_access_tokens`、`authenticate_password` | **DB** |
| A7 | `admin_*` 处理器 L2248-L3210（用户、书籍、授权、AI 设置/标签/任务、词典、webhook） | 全部 `store.*`；`hash_password`；`_admin_*` 同步辅助函数 | **DB**；每个处理函数把“读-校验-写”合并为一次 offload，减少线程切换 |
| A8 | [`admin_books_upload` L2596-L2635](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L2596-L2635) | `async for chunk: output.write(chunk)` 在事件循环上写磁盘；`open/read/os.replace/unlink` | **IO**：按 1 MB 缓冲批量 `run_io(output.write, buf)`；打开、魔数探测、`os.replace`、清理都走 **IO**；`queue_path` 仍只入队 |
| A9 | [`admin_dictionaries` L3352-L3453](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3352-L3453)、[`admin_dictionary_resources` L3455](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3455) | 词典包安装（解压/索引）、资源附加、删除/重命名 | **IO**（长任务，避免占用 DB/R 池） |

### 2.3 书库 / 页面 / 标注 / 进度 / PDF（Batch 3）

| # | 位置 | 原来阻塞什么 | 治理 |
| --- | --- | --- | --- |
| B1 | [`protected_public_file` L4051-L4233](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4051-L4233) | `store.can_read_book`、`book_by_id`、`get_ai_settings`、`managed_book_metadata`、`get_book_review`；`Path.is_file`；[`ServerPageRenderer`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server_pages.py#L20-L211) 全页渲染；CSP 全文读取 | DB 调用 → **DB**；渲染与 `apply_reader_security_headers` → **R**；静态 `FileResponse` 保持异步（Starlette 已用 `anyio.open_file` 分块读取）。动态页面把已有 `markup` 直接传给 CSP，避免二次读 |
| B2 | [`library_index` L3845-L3868](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3845-L3868) | `get_ai_settings`、`os.path.isfile`、`FileResponse` 的 CSP 全文读取 | `get_ai_settings` → **DB**；`apply_reader_security_headers` → **R** |
| B3 | [`filtered_library_metadata` L3836-L3842](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3836-L3842)、[`kindle_library_page` L3895](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3895) | `visible_books`、`get_bookshelf` | **DB** |
| B4 | [`pdf_document` L3946-L4049](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3946-L4049) | `can_read_book`、`book_by_id` 在循环上；`os.close` | DB → **DB**；`prepare_pdf_delivery_async` 已走 `anyio.to_thread`，保留；`os.close` 保持同步（微秒级） |
| B5 | [`annotations` L4344-L4525](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4344-L4525) | GET/POST/PATCH/DELETE 分支内的全部 `store.*` | **DB**：body 解析留在 `async`，切换后同步逻辑整体 offload |
| B6 | [`sync` L4528-L4543](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4528-L4543) | `sync_bookshelf(...)`（服务端同步算法 + DB + 文件路径） | **DB**（原 `sync_bookshelf` 是同步辅助函数，此前审计只看到 `is_ready`，属漏项） |
| B7 | [`bookshelf` L4570-L4604](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4570-L4604) | `bookshelf_document`（`get_bookshelf` + `json.loads`）、`create/update_bookshelf` | **DB** |
| B8 | [`reading_progress` L4611-L4672](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4611-L4672)、[`recent_reading` L4674](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4674)、[`book_review` L4774](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4774)、[`reading_session_heartbeat` L4809](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4809)、[`reading_session_summary` L4871](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4871)、[`reading_insights` L4882](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4882) | `get/set/delete_reading_progress`、`list_reading_progress`、`get/upsert/delete_book_review`、`record_reading_heartbeat`、`reading_time_for_book`、`reading_insights` | **DB** |
| B9 | [`health` L4235](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4235)、[`ready` L4250](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4250) | `runtime_status.snapshot/is_ready` | 纯内存，保持同步 |

### 2.4 AI / SSE / 词典 / 公共 API（Batch 4）

| # | 位置 | 原来阻塞什么 | 治理 |
| --- | --- | --- | --- |
| C1 | [`ai_status` L3210](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3210)、[`book_effective_metadata` L3219](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3219) | AI 设置、用量、书元数据 | **DB** |
| C2 | [`dictionary_lookup` L3243](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3243)、choices/media/asset L3270-L3309 | `dictionary_service.lookup/list_available/get_media/get_asset`（含压缩包读取与可选脚本执行） | **IO**（长 IO）；`list_available` 这类轻查询走 **DB** |
| C3 | [`ai_reading_request` L3475-L3497](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3475-L3497) | `can_read_book`；`AIReadingService.submit` 内的 `_material_for_request`（读章节 JSON）与 `hashlib` | **DB** + **R**（材料读取与摘要移入线程）；提交仍保持原有入队语义 |
| C4 | [`ai_job` L3503](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3503)、`ai_book_results` L3551、`ai_reading_library` L3601、`ai_result` L3670、`ai_followups` L3776、`ai_book_chat` L3805 | 全部 `store.*` | **DB** |
| C5 | [`ai_events` L3687-L3774](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L3687-L3774) | 前置鉴权查询与生成器内每 0.5s 的 `snapshot()` 同步查库 | 前置查询 → **DB**；生成器内每轮 `snapshot()` → `await run_db(...)`；SSE 帧格式、心跳、事件名不变 |
| C6 | [`AIReadingService._worker_loop` L1170-L1185](file:///Users/handy/Documents/projects/epub-browser/epub_browser/ai_reading.py#L1170-L1185) 及 `_run_queued_job/_followup/_book_chat_turn` L1188-L1256 | 每轮 `claim_next_*`（≤1s 一次）以及任务准备/收尾的全部 `store.*`、`_material_for_request`、`_cache_key` 都在事件循环上 | `claim_*` → **DB**；材料读取 → **R**；摘要 → **R**；其余 `store.*` → **DB**。`_provider_call` 已是 `asyncio.to_thread`，保留 |
| C7 | [`AIReadingService.submit` L951-L1000](file:///Users/handy/Documents/projects/epub-browser/epub_browser/ai_reading.py#L951-L1000)、[`retry_job` L1024](file:///Users/handy/Documents/projects/epub-browser/epub_browser/ai_reading.py#L1024)、[`ask_book` L2284](file:///Users/handy/Documents/projects/epub-browser/epub_browser/ai_reading.py#L2284) | `hashlib.sha256`（大章节）、`can_read_book`、材料读取 | **DB** / **R** |
| C8 | [`public_api.py` L104-L629](file:///Users/handy/Documents/projects/epub-browser/epub_browser/public_api.py#L104-L629) 全部 `async` 处理器 | PAT 鉴权、`visible_books`、章节渲染、进度/标注/评论/管理统计 | 鉴权与 `store.*` → **DB**；`renderer.chapter_content` → **R**；鉴权中间层的 `_context` 同步读取需一并包进 offload |
| C9 | [`webhook_service`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L4973-L4997) | 处理函数只做 `enqueue_*`/状态读写，投递在后台线程 | 仅 `store.*` → **DB** |

### 2.5 排查后确认“不阻塞/无需改”的位置

- Starlette `FileResponse`：`os.stat` 用 `anyio.to_thread`，文件读取用 `anyio.open_file` 分块读取，事件循环不被阻塞。
- [`prepare_pdf_delivery_async`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/pdf_delivery.py#L383-L386)：已走 `anyio.to_thread`。
- [`AIReadingService._provider_call`](file:///Users/handy/Documents/projects/epub-browser/epub_browser/ai_reading.py#L1278-L1309)：已走 `asyncio.to_thread`。
- `progress_broker.subscribe/next`、`runtime_status.snapshot`、`heartbeat_attempts`、`login_retry_after_seconds` 的内存部分：纯内存/微秒级。
- `server_library.py` 转换：`queue.Queue` + 独立线程，不在请求路径。
- `webhook` 投递：后台线程。
- `issue_csrf_token` / `verify_csrf_token`：HMAC，微秒级。
- `os.path.join`、`mimetypes.guess_type`、`os.close`、`Path.exists` 单次 stat：微秒级，不单独 offload。
- SSG 路径（`ssg.py`、`processor.py` 静态输出）不涉及。

---

## 3. 分批落地与验证

### Batch 1：基础设施 + 中间件缓存

**改动：** 新增 `server_concurrency.py`；`create_app()` 初始化 `SetupStateMonitor` / `AssetManifestCache`；`auth_middleware` 去掉每请求 DB；代理会话写入 offload；后台校验任务挂在 [`ai_worker_lifespan` L5120](file:///Users/handy/Documents/projects/epub-browser/epub_browser/server.py#L5120-L5130)。

**验证：**
- `tests/test_server.py`、`tests/test_auth.py`、`tests/test_setup*.py`。
- 新增缓存行为测试：setup 完成后立即不再判定“未初始化”；删除管理员后立即失效；资产清单改写后下一次请求读到新值。

### Batch 2：认证 / 账户 / 管理

**改动：** A1-A9。

**验证：** `tests/test_auth.py`、`tests/test_server.py`（账户/管理段）、`tests/test_pat.py`、`tests/test_oidc.py`、`tests/test_webhooks.py`、`tests/test_dictionary_api.py`；上传限速/409/400 语义逐项回归。

### Batch 3：书库 / 页面 / 标注 / 进度 / PDF

**改动：** B1-B8。

**验证：** `tests/test_server.py`、`tests/test_pdf_server.py`、`tests/test_library_progress.py`、`tests/test_static_asset_delivery.py`、`tests/test_server_cache_boundary.py`；重点比对 304/ETag/Range/416、CSP、`Cache-Control`。

### Batch 4：AI / 公共 API / 词典

**改动：** C1-C9。

**验证：** `tests/test_ai_reading.py`、`tests/test_server.py`（AI 段）、`tests/test_public_api.py`、`tests/test_dictionary_api.py`；SSE 首帧与事件名回归。

### 全阶段通用验证

- 新增 `tests/test_server_concurrency.py`：用 `httpx.AsyncClient(transport=ASGITransport(app))`
  - 让某个 `store` 方法 `sleep(0.3)`，并发请求该接口时，`/api/health` 必须在 100ms 内返回；
  - 让 `ServerPageRenderer.render_chapter` `sleep(0.3)`，并发打开章节页时，`/api/session` 仍可响应；
  - 让上传写盘模拟 0.3s，`/api/health` 不受影响。
- 全部批次后运行：`python -m pytest tests`、`git diff --check`。
- 不改 `SERVER_OUTPUT_REVISION` / PDF 修订；不触发任何重新转换。

---

## 4. 行为兼容面（必须逐项保持）

1. URL 与路径参数转换器（`/api/{path:path}`、`/{path:path}`、`{job_id:path}`）顺序不变。
2. Cookie：名称、`path`、`Secure`、`HttpOnly`、`SameSite`、生命周期。
3. 缓存：`Cache-Control` 各路径策略、304 空响应、ETag/`If-Range`、`Content-Range`、416。
4. 错误：`{"code","message"}`、401/403/404/405/409/416/429、500 的 `X-Request-ID`。
5. 安全：CSP、`X-Content-Type-Options`、PDF `Content-Disposition`。
6. SSE：`text/event-stream`、`X-Accel-Buffering: no`、事件名 `progress/job/followup/chat`、`: heartbeat`。
7. i18n：不新增未翻译文案；运行时插入仍用 `data-i18n*`。
8. SSG：静态输出不引用 `/api/*`、不依赖线程池、不触发任何 Server 逻辑。
9. AI 语义：任务仍持久化在 SQLite，断线可恢复；不改成 WebSocket，不逐 token 写库。

---

## 5. 已知风险与停点

| 风险 | 处理 |
| --- | --- |
| 后台校验任务与 `TestClient` 生命周期 | `create_app()` 先同步探测一次；`TestClient` 未进入上下文时依赖 ≤100ms 的 False 分支兜底 |
| 多进程/多实例下的 `has_administrator` 可见性 | False→True ≤100ms；True→False ≤5s；单目录单进程由 `runtime.py` 目录锁保证 |
| 线程池饱和 | DB/R/IO 三池隔离；禁止长任务进 DB 池；监控 `run_db` 队列长度 |
| 上传分块写盘的内存峰值 | 1 MB 缓冲上限，超出即 flush；保持流式 |
| 把 `asyncio.Event`/`Future` 等 loop 对象带进线程 | 只 offload纯同步函数，禁止在线程内调用 `asyncio.get_running_loop()` |
| `heartbeat_attempts` 等可变字典跨线程 | 仅在事件循环内访问；若未来移入线程，需加 `threading.Lock` |
| 取消/超时语义变化 | 线程任务不可取消，与现状一致；不引入新的超时错误码 |
| 返回对象被线程修改 | offload 函数只返回不可变数据或新建对象 |
| 任何行为差异 | 立即停止并汇报，不擅自调整契约 |

---

## 6. 验收标准

- 并发打开 8 个不同章节页时，`/api/health` p95 < 100ms，且不出现 5xx。
- 登录、同步、标注写入、上传、AI 提交在并发下互不拖慢事件循环。
- 现有测试全绿；`git diff --check` 通过。
- 不产生任何 `content/`、`pdf/` 缓存格式变化，不提高内容修订。
