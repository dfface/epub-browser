# AI 阅读 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Server mode 中提供无剧透、可缓存、可追问的自适应 AI 阅读体验。

**Architecture:** 以现有 StateStore 为唯一持久化边界，AIReadingService 用受限 worker 调度兼容 OpenAI 的请求并合并相同工作。Starlette 只暴露固定的 Server API；章节页通过独立的 ES5 控制器渲染经服务端验证的结构化结果。

**Tech Stack:** Python 3.9+、标准库 urllib、SQLite、Starlette、ES5 JavaScript、CSS、Python unittest、Node node:test。

**Spec:** docs/superpowers/specs/2026-08-19-ai-reading-design.md

## Global Constraints

- I18N 现有基线是 v2.0.1；所有新增 UI 必须有完整 aiReading.* EN/zh-CN 键。
- AI 仅在 Server mode 且三项必需环境变量有效时启用；SSG 不包含 AI API 或资源。
- API key、Provider URL、原始 prompt/response、绝对路径不进入浏览器、SQLite 或日志。
- 第 N 章仅使用 0..N 的正文和前文 bridge summary，禁止未来章节、未来 TOC 或未来缓存输入。
- 不运行 E2E；不得修改既有书架、标注、阅读进度、书籍 identity 或 migration 行为。
- 所有不受信任文本（模型、EPUB、问题）均经 JSON/textContent，不写入 innerHTML。

---

### Task 1: 审计 I18N 基线并定义 AI UI 文案

**Files:**
- Modify: epub_browser/assets/i18n.js
- Modify: tests/test_i18n.js
- Modify: tests/test_i18n_coverage.py

**Interfaces:**
- Produces window.EpubBrowserI18n.t('aiReading.<key>') for later UI tasks.
- Adds aiReading to each dictionary with identical non-empty key trees.

- [ ] **Step 1: 写完整的双语键失败断言**

    assert.equal(i18n.t('aiReading.open'), 'AI Reading');
    i18n.setLocale('zh-CN');
    assert.equal(i18n.t('aiReading.open'), 'AI 阅读');
    assert.equal(i18n.t('aiReading.providerUnavailable').includes('AI'), true);

- [ ] **Step 2: 运行并确认新增键尚不存在**

Run: PATH="/usr/bin:$PATH" node --test tests/test_i18n.js

Expected: FAIL with missing aiReading.open.

- [ ] **Step 3: 添加同构键树**

英文至少新增 open、start、quickGrasp、structure、deepDive、evidence、followUp、providerUnavailable、generating、retry、privacyNotice、questionPlaceholder、error.*。中文使用“AI 阅读”“开始帮读本节”“快速掌握”“脉络理解”“深入理解”“原文证据”“继续追问”“此服务器尚未配置 AI 阅读”等等值含义，不翻译 EPUB/模型原文。

- [ ] **Step 4: 运行 I18N 与 coverage 测试**

Run: /usr/bin/python3 -m unittest tests.test_i18n_coverage -v && PATH="/usr/bin:$PATH" node --test tests/test_i18n.js

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/assets/i18n.js tests/test_i18n.js tests/test_i18n_coverage.py
    git commit -m "feat: add AI reading interface copy"

### Task 2: 安全的 Provider 配置与兼容客户端

**Files:**
- Create: epub_browser/ai_config.py
- Create: epub_browser/ai_client.py
- Create: tests/test_ai_config.py
- Create: tests/test_ai_client.py

**Interfaces:**
- Produces AIConfig.from_environ(environ) -> Optional[AIConfig] and public_payload() -> dict.
- Produces OpenAICompatibleClient(config).complete(messages) -> dict.

- [ ] **Step 1: 写配置不泄密和 URL 约束的失败测试**

    config = AIConfig.from_environ({
        'EPUB_BROWSER_AI_BASE_URL': 'https://api.example/v1',
        'EPUB_BROWSER_AI_API_KEY': 'secret',
        'EPUB_BROWSER_AI_MODEL': 'reader-model',
    })
    self.assertEqual(config.public_payload(), {'enabled': True, 'model': 'reader-model'})
    self.assertIsNone(AIConfig.from_environ({}))
    with self.assertRaises(ValueError):
        AIConfig.from_environ({
            'EPUB_BROWSER_AI_BASE_URL': 'http://example.com/v1',
            'EPUB_BROWSER_AI_API_KEY': 'secret',
            'EPUB_BROWSER_AI_MODEL': 'reader-model',
        })

- [ ] **Step 2: 运行并确认模块缺失**

Run: /usr/bin/python3 -m unittest tests.test_ai_config -v

Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: 实现冻结配置和 urllib 客户端**

    @dataclass(frozen=True)
    class AIConfig:
        base_url: str
        api_key: str
        model: str
        timeout_seconds: int = 60
        max_concurrency: int = 2

        def public_payload(self):
            return {'enabled': True, 'model': self.model}

complete() POST JSON 至 base_url.rstrip('/') + '/chat/completions'，使用 Authorization: Bearer；第一次含 response_format json_object，仅在 400 指向该参数时去掉后重试一次。将 transport/HTTP/JSON 错误转换为不含 URL、key 或原始 body 的专用异常。

- [ ] **Step 4: 用假的 opener 验证请求、单次回退和净化错误**

Run: /usr/bin/python3 -m unittest tests.test_ai_config tests.test_ai_client -v

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/ai_config.py epub_browser/ai_client.py tests/test_ai_config.py tests/test_ai_client.py
    git commit -m "feat: add configurable AI provider client"

### Task 3: 章节正文提取、无剧透上下文与结果校验

**Files:**
- Create: epub_browser/ai_reading.py
- Create: tests/test_ai_reading.py

**Interfaces:**
- Produces ChapterTextExtractor(book_dir).chapter(index) -> ChapterSource.
- Produces build_reading_request(source, previous_bridges, locale) -> list[dict].
- Produces validate_reading_result(payload, allowed_sources) -> dict.

- [ ] **Step 1: 写章节范围和 evidence 规则的失败测试**

    result = validate_reading_result(payload, {2: 'Current allowed excerpt'})
    self.assertEqual(result['strategy'], 'technical')
    with self.assertRaises(InvalidAIResult):
        validate_reading_result(future_evidence_payload, {2: 'Current allowed excerpt'})
    with self.assertRaises(InvalidAIResult):
        validate_reading_result(non_substring_payload, {2: 'Current allowed excerpt'})

- [ ] **Step 2: 运行并确认模块缺失**

Run: /usr/bin/python3 -m unittest tests.test_ai_reading -v

Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: 实现提取、prompt 和严格 schema**

用 html.parser.HTMLParser 跳过 script/style/nav，合并空白并在 24,000 字符截断。build_reading_request() 只接受小于当前 index 的 bridge summaries，在 system message 中要求 locale、三种 strategy、三层字段和“禁止未来信息”。校验器仅接受 technical|fiction|general，限制节点/边/证据长度，验证 every edge endpoint、evidence ID 与允许章节/子串。

- [ ] **Step 4: 运行 focused tests**

Run: /usr/bin/python3 -m unittest tests.test_ai_reading -v

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/ai_reading.py tests/test_ai_reading.py
    git commit -m "feat: validate spoiler-safe AI reading results"

### Task 4: SQLite 缓存和用户追问持久化

**Files:**
- Modify: epub_browser/state.py
- Modify: tests/test_state.py

**Interfaces:**
- Produces StateStore.get_ai_result(cache_key), put_ai_result(...), list_ai_bridges(book_id, before_chapter), and add_ai_followup(username, result_id, question, answer).
- Consumes validated result dicts from Task 3 only.

- [ ] **Step 1: 写 schema 升级和缓存键失败测试**

    store.initialize()
    store.put_ai_result(key, validated_result, bridge_summary='Earlier context')
    self.assertEqual(store.get_ai_result(key)['result']['strategy'], 'fiction')
    self.assertEqual(store.list_ai_bridges('book', before_chapter=4), ['Earlier context'])
    self.assertIsNone(store.get_ai_result(key.with_locale('zh-CN')))

- [ ] **Step 2: 运行并确认方法不存在**

Run: /usr/bin/python3 -m unittest tests.test_state -v

Expected: FAIL with AttributeError.

- [ ] **Step 3: 递增 schema 并只新增表与索引**

新增 ai_reading_results 和 ai_reading_followups，对共享结果使用完整 cache-key UNIQUE index；JSON 用 ensure_ascii=False、sort_keys=True、紧凑分隔符保存。读取时验证 JSON object，坏缓存返回未命中而不抛出原文。

- [ ] **Step 4: 运行 StateStore 与既有服务端测试**

Run: /usr/bin/python3 -m unittest tests.test_state tests.test_server -v

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/state.py tests/test_state.py
    git commit -m "feat: cache AI reading results in SQLite"

### Task 5: 有界调度、同键合并与任务状态

**Files:**
- Modify: epub_browser/ai_reading.py
- Modify: tests/test_ai_reading.py

**Interfaces:**
- Produces AIReadingService.request_chapter(...), request_followup(...), get_job(job_id), and shutdown().
- Returns queued, running, complete, or failed；只有 complete 暴露已验证结果。

- [ ] **Step 1: 写同缓存键只调用一次 Provider 的失败测试**

    first = service.request_chapter(request)
    second = service.request_chapter(request)
    self.assertEqual(first.job_id, second.job_id)
    completed = await_job(service, first.job_id)
    self.assertEqual(completed.status, 'complete')
    self.assertEqual(fake_client.calls, 1)

- [ ] **Step 2: 运行确认 service 尚不存在**

Run: /usr/bin/python3 -m unittest tests.test_ai_reading.AIReadingServiceTests -v

Expected: FAIL with AttributeError.

- [ ] **Step 3: 用 ThreadPoolExecutor 实现调度**

使用 max_workers=config.max_concurrency，在锁内按稳定 cache key 存放 in-flight job。worker 在调用 Provider 前再读 SQLite 缓存，完成后只保存经 Task 3 校验的结果；不保留 prompt 或 raw provider JSON。失败状态只保存 ai_provider_failed、ai_timeout、ai_invalid_response 或 ai_queue_full 等稳定 code。

- [ ] **Step 4: 验证并发、超时、缓存命中和 shutdown**

Run: /usr/bin/python3 -m unittest tests.test_ai_reading.AIReadingServiceTests -v

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/ai_reading.py tests/test_ai_reading.py
    git commit -m "feat: schedule deduplicated AI reading jobs"

### Task 6: Server mode API 和 runtime 生命周期

**Files:**
- Modify: epub_browser/server.py
- Modify: epub_browser/runtime.py
- Modify: tests/test_server.py
- Modify: tests/test_runtime.py

**Interfaces:**
- Produces设计文档中的 /api/ai-reading routes；create_app(..., ai_reading_service=None)。
- run_server() 从环境创建服务，关闭时总是调用 shutdown()。

- [ ] **Step 1: 写 availability、202 到终态和错误码失败测试**

    self.assertEqual(client.get('/api/ai-reading/availability').json(), {'enabled': False})
    queued = client.post('/api/ai-reading/books/book/chapters/1').json()
    self.assertEqual(queued['status'], 'queued')
    self.assertEqual(client.get('/api/ai-reading/jobs/' + queued['job_id']).status_code, 200)

- [ ] **Step 2: 运行 API 测试并确认 route 为 404**

Run: /usr/bin/python3 -m unittest tests.test_server tests.test_runtime -v

Expected: FAIL for missing AI route tests.

- [ ] **Step 3: 挂载固定 route 并映射安全错误**

路由必须在通配 /api/{path:path} 之前注册；从 X-Username 取现有用户语义；GET 永不启动任务；POST body 只允许 schema 中的 question。availability 只能返回 {enabled: false} 或 {enabled: true, model}。未配置 POST 返回 503 ai_not_configured。

- [ ] **Step 4: 运行 focused 服务端测试**

Run: /usr/bin/python3 -m unittest tests.test_server tests.test_runtime -v

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/server.py epub_browser/runtime.py tests/test_server.py tests/test_runtime.py
    git commit -m "feat: expose server AI reading API"

### Task 7: Server-only 页面挂载与安全抽屉壳

**Files:**
- Create: epub_browser/assets/ai-reading.js
- Create: epub_browser/assets/ai-reading.css
- Modify: epub_browser/site.py
- Modify: epub_browser/processor.py
- Modify: tests/test_site.py
- Modify: tests/test_generated_reader_surfaces.py

**Interfaces:**
- Produces chapter-page [data-ai-reading] with data-book-id/data-chapter-index.
- Only Server renderer emits AI assets after i18n.js；SSG emits none.

- [ ] **Step 1: 写 Server/SSG 生成面差异失败测试**

    self.assertIn('ai-reading.js', server_chapter_html)
    self.assertIn('data-ai-reading', server_chapter_html)
    self.assertNotIn('ai-reading.js', static_chapter_html)
    self.assertNotIn('data-ai-reading', static_chapter_html)

- [ ] **Step 2: 运行测试并确认 AI shell 缺失**

Run: /usr/bin/python3 -m unittest tests.test_site tests.test_generated_reader_surfaces -v

Expected: FAIL.

- [ ] **Step 3: 生成可访问抽屉**

抽屉使用 button、aria-controls、aria-expanded、dialog focus return 和 data-i18n；资源 URL 必须经 immutable asset publisher。将 book id/chapter index 作为转义过的 data 属性写入，文本节点不拼接模型内容。

- [ ] **Step 4: 运行生成面测试**

Run: /usr/bin/python3 -m unittest tests.test_site tests.test_generated_reader_surfaces -v

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/assets/ai-reading.js epub_browser/assets/ai-reading.css epub_browser/site.py epub_browser/processor.py tests/test_site.py tests/test_generated_reader_surfaces.py
    git commit -m "feat: add server AI reading drawer shell"

### Task 8: 三层阅读结果、脉络图、证据和追问前端

**Files:**
- Modify: epub_browser/assets/ai-reading.js
- Modify: epub_browser/assets/ai-reading.css
- Create: tests/test_ai_reading.js

**Interfaces:**
- Consumes only API payloads validated by Task 3.
- Produces AIReadingController with open, generate, renderResult, focusEvidence, and askFollowup.

- [ ] **Step 1: 写 DOM 测试，禁止 HTML sink**

    controller.renderResult({quick_grasp: {summary: '<img onerror=1>'}});
    assert.equal(panel.querySelector('img'), null);
    assert.equal(panel.textContent.includes('<img onerror=1>'), true);
    assert.equal(panel.querySelectorAll('[data-ai-evidence]').length, 1);

- [ ] **Step 2: 运行并确认控制器不存在**

Run: PATH="/usr/bin:$PATH" node --test tests/test_ai_reading.js

Expected: FAIL.

- [ ] **Step 3: 实现轮询与渲染**

客户端 POST 后每秒 GET job，最多 70 次；离开/关闭时取消定时器。每个文本节点用 textContent，mind map 使用 createElementNS 创建有限 SVG 节点/边，evidence 以书内 fragment 或当前 DOM query 定位。提交 follow-up 时限制输入长度并显示本地化错误/加载状态。

- [ ] **Step 4: 运行 JS 测试**

Run: PATH="/usr/bin:$PATH" node --test tests/test_ai_reading.js tests/test_i18n.js

Expected: PASS.

- [ ] **Step 5: 提交**

    git add epub_browser/assets/ai-reading.js epub_browser/assets/ai-reading.css tests/test_ai_reading.js
    git commit -m "feat: render adaptive AI reading guidance"

### Task 9: 文档和发布前验证

**Files:**
- Modify: README.md
- Modify: docs/releases/v2.0.2.md（仅在功能完成后）
- Modify: epub_browser/version.py（仅在用户确认发布后）

**Interfaces:**
- Documents environment-only Provider setup, privacy boundary, caching and no-spoiler behavior.

- [ ] **Step 1: 写 README 配置示例与故障排查**

    export EPUB_BROWSER_AI_BASE_URL="https://provider.example/v1"
    export EPUB_BROWSER_AI_API_KEY="..."
    export EPUB_BROWSER_AI_MODEL="reader-model"
    epub-browser server ./books --server-dir ./library

说明不应把 key 放进网页、EPUB、命令历史或公开配置；未配置时功能仅显示不可用状态。

- [ ] **Step 2: 运行完整自动化套件（不含 E2E）**

Run: /usr/bin/python3 -m unittest discover -s tests -v && PATH="/usr/bin:$PATH" node --test tests/*.js && git diff --check

Expected: PASS.

- [ ] **Step 3: 审阅验收矩阵**

逐项核对设计中的验收标准，特别验证 cache hit 不调用 Provider、未来 evidence 被拒绝、HTML 不被解释、未配置时不发网络请求。

- [ ] **Step 4: 提交文档**

    git add README.md
    git commit -m "docs: explain server AI reading"

- [ ] **Step 5: 等待用户发布确认后再改版本号、写 Release note、打 tag**

不得把计划完成自动等同于发布；发布版本和 tag 由用户确认后执行。

## 自检

- 需求覆盖：Task 1 覆盖 I18N；Tasks 2–6 覆盖 Provider、提取、调度、SQLite、前文摘要与无剧透；Tasks 7–8 覆盖三类策略、三层结果、脉络图、证据和追问；Task 9 覆盖文档和验证。
- 占位符扫描：本计划没有 TBD/TODO 或“类似前面”的实现指令。
- 接口一致性：Task 2 的 AIConfig 供 Task 5 使用；Task 3 的验证结果是 Task 4/5 唯一可缓存输入；Task 5 的 jobs 是 Task 6/8 的共同协议。

