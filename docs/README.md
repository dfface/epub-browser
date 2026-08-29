# Documentation / 文档中心

This page is the stable entry point for user guides, release notes, and maintainer
documentation. 本页集中列出用户指南、版本说明和维护者文档，避免在主 README 中堆叠
实现细节。

## Start here / 从这里开始

- [English README](../README.md) — project overview, installation, formats, deployment,
  and operations.
- [简体中文 README](readme/README.zh-CN.md) — 项目概览、安装、格式、部署与运维。
- [Localized READMEs](readme/) — other supported documentation languages.

## Guides / 专题指南

- [AI-native reading](ai-native-reading.md) — Server-side AI reading workflows,
  permissions, and privacy boundaries.
- [Third-party AI renderers](third-party-ai-renderers.md) — locally packaged rich-text
  rendering dependencies and network policy.
- [Migration guide for v2](migration-v2.md) — command, identity, and deployment changes
  for upgrades from v1.

## Releases / 版本说明

- [v2.9.1](releases/v2.9.1.md) — reliable OIDC account linking, automatic
  legacy identity-schema repair, and safer configurable logging.
- [v2.9.0](releases/v2.9.0.md) — generic OIDC single sign-on, safe account
  linking and provisioning, and guarded administrator user deletion.
- [All release notes](releases/) — versioned, immutable release documentation.

## Maintainers / 维护者

- [AGENTS.md](../AGENTS.md) — architecture boundaries and required development checks.
- [CONTEXT.md](../CONTEXT.md) — current repository context and long-lived design decisions.
- [`plans/`](plans/) — implementation plans and historical design records; these are not
  the primary user documentation.

When a guide conflicts with current CLI help, the installed CLI help is authoritative.
When implementation work changes a documented contract, update the relevant guide and
localized navigation in the same change.
