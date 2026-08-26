# Server 本地词典与百科查阅 Implementation Plan

**Goal:** 在 Server 阅读页提供本地 StarDict/MDict 查词和在线 Wikimedia 百科；选区菜单为复制、高亮、笔记、查词、百科五项，SSG 保持前三项。

**Architecture:** 本地格式适配器把合法安装包转换为独立只读 SQLite 词典；主 StateStore 只保存目录和默认映射。词典查询和百科查询使用两个独立、受 ACL 保护的 POST API。百科通过受限的 Wikimedia 服务端客户端获取摘要。前端统一管理选择草稿，分别呈现本地释义和百科摘要。

## Constraints

- 不支持 Kindle 文件、DRM 或商业词典；不增加 GPL 依赖。
- 词典运行时文件不进入 EPUB 内容缓存；不提高 `SERVER_OUTPUT_REVISION`，无需重转 EPUB。
- 词典 API 与资产仅 Server 可用；SSG 不引用 `/api/*`。
- 本地查词不联网、不保存历史；百科不持久化查询或结果。
- Visible strings are translated in en, zh-CN, zh-TW, ko and ja.

## Tasks

### 1. Restore the no-Kindle baseline

- [x] Revert schema 14 and remove the Mobi parser draft.
- [x] Supersede obsolete Kindle design/plan documents.
- [ ] Run focused StateStore regression tests.

### 2. Build the local dictionary foundation

- [ ] Add StateStore schema for dictionary metadata and per-language defaults only.
- [ ] Define adapter interface and bounded normalized entry model.
- [ ] Implement and test StarDict parsing (`.ifo/.idx/.dict[.dz]/.syn`).
- [ ] Implement and test MDict reading (`.mdx`, safely ignore optional `.mdd` resources) using a permissively licensed or project-native reader.
- [ ] Build isolated read-only SQLite files; test atomic publication, lookup, cleanup, disable/delete and no lookup history.

### 3. Add protected Server services

- [ ] Add admin install/list/enable/default/delete APIs, authentication and CSRF coverage.
- [ ] Add reader local-dictionary lookup API with ACL before metadata/lookup and `private, no-store`.
- [ ] Add fixed-host Wikimedia summary client, timeout/concurrency/Retry-After handling, attribution and no persistent cache.
- [ ] Add reader encyclopedia lookup API with the same ACL and privacy headers.

### 4. Deliver the five-action reader UI

- [ ] Publish dictionary JavaScript/CSS only in Server mode and pass no runtime data into content cache.
- [ ] Refactor annotation selection into Copy, Highlight, Note, Dictionary and Encyclopedia actions.
- [ ] Implement accessible, cancellable local-definition and encyclopedia dialogs with safe text rendering.
- [ ] Add all translations and UI boundary tests; validate SSG remains three actions.

### 5. Verify

- [ ] Run StateStore, parser/service, Server/auth, asset and SSG/Server integration tests.
- [ ] Perform UI/UX accessibility review: keyboard flow, visible focus, 44px targets, contrast, 375px layout, loading/error states and reduced motion.
- [ ] Run complete test suite and `git diff --check`.
