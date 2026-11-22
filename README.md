# tl128 · 特零128小站

纯静态博客。**没有 issue、没有数据库、没有一次性批量 API 调用**——更新就是改文件、本地构建、一次 `git push`。

## 结构

```
content/     每篇文章一个 .md（文件头是 JSON front matter）
templates/   页面模板（Jinja2）
assets/      style.css / app.js
data/        诗的分节断点表
build.py     生成器：content → docs/
docs/        构建产物（GitHub Pages 直接托管这个目录）
```

## 日常更新

```bash
# 1. 改内容：在 content/ 里新建或编辑 .md
#    front matter 示例
#    ---
#    {"title":"标题","date":"2026-11-23","tags":["杂文"],"slug":"my-post","pid":"P900","top":0,"words":0,"summary":""}
#    ---

# 2. 构建
python build.py

# 3. 发布（一次 push，约 0.5 MB 增量）
git add -A && git commit -m "post: 标题" && git push
```

## 排版规则（构建时自动处理）

- **散文**：每条正文行首自动补两个全角空格（跳过标题/引用/列表/代码）。
- **诗**（标签含「诗」）：按 `data/stanzas.json` 的断点自动插空行分节；已分节的作品不重复处理。

## 安全约定

- 只用 `git push` 更新，不走 REST 批量写、不建 issue。
- 单次 push 即完成发布；CI 不是必需的（如需可加触发式工作流，禁用 cron 刷提交）。
- 任何必须调用 API 的场合：每次 ≤5 个写请求、间隔 ≥90 秒、遇到 403 立即停止。
