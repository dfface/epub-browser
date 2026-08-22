# 本地 AI 富文本渲染器

AI 阅读随应用发布以下本地静态资源；阅读或对话页面不会为公式或图形加载第三方 CDN：

- KaTeX 0.16.47（MIT），用于受限 `math` fenced block。
- Mermaid 11.12.0（MIT），用于受限 `mermaid` fenced block。

资源位于 `epub_browser/assets/vendor/`，其上游许可证分别随 npm 包发布。
渲染器以严格安全模式运行：不接受模型生成的 HTML、脚本、外部链接或 Mermaid
`click` / `link` 指令；不能安全渲染时保留原始文本。
