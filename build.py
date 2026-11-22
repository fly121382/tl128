# -*- coding: utf-8 -*-
"""tl128 静态站生成器。

用法：
    python build.py                       # 生成到 public/
    python build.py --base <url> --out <dir>

结构：content/*.md（JSON front matter + markdown）→ public/
产物：首页/分页、文章页（含目录/相关文章）、标签页、标签 RSS、归档页、
      站内搜索索引、全站 RSS、sitemap。
"""
import argparse
import glob
import html
import json
import os
import re
import shutil
import urllib.parse
from datetime import datetime, timedelta, timezone

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
TEMPLATES = os.path.join(ROOT, "templates")
ASSETS = os.path.join(ROOT, "assets")
PUBLIC = os.path.join(ROOT, "public")
STANZA_FILE = os.path.join(ROOT, "data", "stanzas.json")

IDEO = "\u3000"
NOVEL_TAGS = {"短篇", "中篇", "长篇", "连载章节"}


# ---------------------------------------------------------------- front matter
def parse_post(path):
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    if not raw.startswith("---\n"):
        raise SystemExit("缺少 front matter: %s" % path)
    end = raw.index("\n---\n", 4)
    meta = json.loads(raw[4:end])
    meta["body"] = raw[end + 5:].lstrip("\n")
    return meta


# ---------------------------------------------------------------- typography
def is_structural(line):
    s = line.strip()
    return (
        not s
        or s.startswith("#")
        or s.startswith(">")
        or s.startswith("```")
        or s.startswith("|")
        or s.startswith("<")
        or re.match(r"^([-*+]|\d+[.)])\s", s) is not None
        or re.match(r"^(-{3,}|\*{3,}|_{3,})$", s) is not None
    )


def indent_paragraphs(body):
    out, in_code = [], False
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code or is_structural(line) or line.startswith(IDEO):
            out.append(line)
        else:
            out.append(IDEO * 2 + line)
    return "\n".join(out)


def split_stanzas(body, breaks):
    lines = [l for l in body.split("\n") if l.strip()]
    if not breaks:
        return "\n\n".join(lines)
    out, cur, bset = [], [], set(breaks)
    for i, l in enumerate(lines, 1):
        cur.append(l)
        if i in bset:
            out.append("\n".join(cur))
            cur = []
    if cur:
        out.append("\n".join(cur))
    return "\n\n".join(out)


def indent_html(html_text):
    def repl(m):
        inner = m.group(1)
        if inner.startswith(IDEO) or inner.startswith("<"):
            return m.group(0)
        return "<p>" + IDEO * 2 + inner + "</p>"

    return re.sub(r"<p>(.*?)</p>", repl, html_text, flags=re.S)


# ---------------------------------------------------------------- rendering
def make_md():
    return md.Markdown(extensions=["nl2br", "fenced_code", "tables", "sane_lists"],
                       output_format="html5")


def render_html(body_md):
    return make_md().convert(body_md)


def add_headings(html_text):
    """给标题加 id 并返回目录条目。"""
    entries = []

    def repl(m):
        level, inner = int(m.group(1)), m.group(2)
        text = re.sub(r"<[^>]+>", "", inner).strip()
        if not text:
            return m.group(0)
        hid = "h%d" % (len(entries) + 1)
        entries.append({"level": level, "text": text, "id": hid})
        return '<h%d id="%s">%s</h%d>' % (level, hid, inner, level)

    html_text = re.sub(r"<h([1-6])>(.*?)</h\1>", repl, html_text, flags=re.S)
    return html_text, entries


def plain_summary(meta, html_body):
    if meta.get("summary"):
        return re.sub(r"\s+", " ", meta["summary"]).replace(IDEO, "").strip()
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_body)).strip()
    return text.replace(IDEO, "").strip()[:120]


# ---------------------------------------------------------------- rss
def build_rss(cfg, base, items, title=None, link=None):
    tz = timezone(timedelta(hours=int(cfg.get("utcOffset", 8))))
    out = []
    for p in items[:40]:
        try:
            dt = datetime.strptime(p["date"], "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            dt = datetime(1970, 1, 1, tzinfo=tz)
        out.append(
            "<item><title>%s</title><link>%s</link><guid>%s</guid>"
            "<pubDate>%s</pubDate><description><![CDATA[%s]]></description></item>"
            % (html.escape(p["title"]), p["url"], p["url"],
               dt.strftime("%a, %d %b %Y %H:%M:%S %z"), p["html"][:4000]))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        "<title>%s</title><link>%s</link><description>%s</description>"
        "<language>zh-CN</language>%s</channel></rss>"
        % (html.escape(title or cfg["title"]), link or (base + "/"),
           html.escape(cfg.get("subTitle", "")), "".join(out))
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    base = (args.base or cfg["baseUrl"]).rstrip("/")
    out_dir = args.out or PUBLIC
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "post"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "tag"), exist_ok=True)

    breaks, known_already = {}, set()
    if os.path.exists(STANZA_FILE):
        data = json.load(open(STANZA_FILE, encoding="utf-8"))
        breaks = data.get("breaks", {})
        known_already = set(data.get("already_sectioned", []))

    posts = [parse_post(f) for f in glob.glob(os.path.join(CONTENT, "*.md"))]

    # ---- 派生标签
    topic_map = {}
    tagmap_path = os.path.join(ROOT, "data", "tagmap.json")
    if os.path.exists(tagmap_path):
        topic_map = json.load(open(tagmap_path, encoding="utf-8"))
    FORM_TAGS = {"诗", "小说", "短篇", "中篇", "长篇", "杂文",
                 "半成品", "大纲", "商业创作", "连载章节"}
    for p in posts:
        tags = list(p.get("tags") or [])
        if NOVEL_TAGS & set(tags) and "小说" not in tags:
            tags.append("小说")
        if "用力漫评" in p["title"] and "用力漫评" not in tags:
            tags.append("用力漫评")
        for t in topic_map.get(p["pid"], []):
            if t not in tags:
                tags.append(t)
        # 题材标签排前面，文体标签排后面（列表里一眼看到「写的是什么」）
        tags = [t for t in tags if t not in FORM_TAGS] + [t for t in tags if t in FORM_TAGS]
        p["tags"] = tags

    # ---- 正文渲染 + 目录 + 摘要
    for p in posts:
        p["is_poem"] = "诗" in p["tags"]
        body = p["body"]
        if p["is_poem"]:
            if p["title"] in breaks and p["title"] not in known_already:
                body = split_stanzas(body, breaks[p["title"]])
        else:
            body = indent_paragraphs(body)
        html_body = render_html(body)
        if not p["is_poem"]:
            html_body = indent_html(html_body)
        html_body, toc = add_headings(html_body)
        p["html"] = html_body
        p["toc"] = toc
        p["summary"] = plain_summary(p, html_body)
        p["words"] = len(re.sub(r"\s", "", re.sub(r"<[^>]+>", "", html_body)))
        p["minutes"] = max(1, round(p["words"] / 400))
        # slug 可能是百分号编码（从旧站 postUrl 继承来的）：文件名要用解码后的，
        # 链接要用编码后的，否则浏览器解码后找不到文件 → 404。
        p["slug_file"] = urllib.parse.unquote(p["slug"])
        bad = re.search(r'[:/\\*?"<>|]', p["slug_file"])
        if bad:
            p["slug_file"] = re.sub(r'[:/\\*?"<>|]', "-", p["slug_file"])
        p["url"] = "%s/post/%s.html" % (base, urllib.parse.quote(p["slug_file"]))

    posts.sort(key=lambda x: (x.get("top", 0), x["date"], x["pid"]), reverse=True)

    # ---- 新文标记
    today = datetime.now().date()
    try:
        new_days = int(cfg.get("newDays", 7))
    except ValueError:
        new_days = 7
    for p in posts:
        try:
            p["new"] = (today - datetime.strptime(p["date"], "%Y-%m-%d").date()).days <= new_days
        except ValueError:
            p["new"] = False

    # ---- 相关文章
    for p in posts:
        ptag = set(p["tags"])
        scored = []
        for q in posts:
            if q is p:
                continue
            overlap = len(ptag & set(q["tags"]))
            if overlap:
                scored.append((overlap, q["date"], q))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        p["related"] = [q for _, _, q in scored[:3]]

    # ---- 首页配置
    by_title = {p["title"]: p for p in posts}
    featured = []
    for f in cfg.get("featured", []):
        post = by_title.get(f.get("title", ""))
        if post:
            featured.append({"post": post, "blurb": f.get("blurb", "")})
    recs = []
    for tag, titles in (cfg.get("recommend") or {}).items():
        items = [by_title[t] for t in titles if t in by_title]
        if items:
            recs.append({"tag": tag, "posts": items})

    # ---- 友链
    friends = []
    friends_path = os.path.join(ROOT, "data", "friends.json")
    if os.path.exists(friends_path):
        friends = json.load(open(friends_path, encoding="utf-8"))

    env = Environment(loader=FileSystemLoader(TEMPLATES),
                      autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.globals.update(base=base, cfg=cfg, tag_colors=cfg.get("tagColors", {}))
    tpl_index = env.get_template("index.html")
    tpl_post = env.get_template("post.html")
    tpl_tag = env.get_template("tag.html")
    tpl_tags = env.get_template("tags.html")
    tpl_search = env.get_template("search.html")
    tpl_archive = env.get_template("archive.html")
    tpl_friends = env.get_template("friends.html")

    per_page = int(cfg.get("perPage", 25))

    # ---- 文章页
    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        html_out = tpl_post.render(post=p, newer=newer, older=older, page="post",
                                   page_title=p["title"],
                                   show_toc=len(p["toc"]) >= 3 and p["words"] > 1500)
        open(os.path.join(out_dir, "post", p["slug_file"] + ".html"), "w", encoding="utf-8").write(html_out)

    # ---- 首页分页
    pages = [posts[i:i + per_page] for i in range(0, len(posts), per_page)] or [[]]
    for n, chunk in enumerate(pages, 1):
        name = "index.html" if n == 1 else "page%d.html" % n
        html_out = tpl_index.render(posts=chunk, page_no=n, page_count=len(pages), page="index",
                                    page_title=None, total=len(posts),
                                    featured=featured if n == 1 else [],
                                    recs=recs if n == 1 else [])
        open(os.path.join(out_dir, name), "w", encoding="utf-8").write(html_out)

    # ---- 标签页 + 标签 RSS
    tag_map = {}
    for p in posts:
        for t in p["tags"]:
            tag_map.setdefault(t, []).append(p)
    for t, items in tag_map.items():
        fn = re.sub(r'[\\/:*?"<>|\s]', "_", t)
        open(os.path.join(out_dir, "tag", fn + ".html"), "w", encoding="utf-8").write(
            tpl_tag.render(tag=t, posts=items, page="tag", page_title=t, total=len(items)))
        os.makedirs(os.path.join(out_dir, "tag", fn), exist_ok=True)
        open(os.path.join(out_dir, "tag", fn, "rss.xml"), "w", encoding="utf-8").write(
            build_rss(cfg, base, items, title="%s · %s" % (cfg["title"], t),
                      link="%s/tag/%s.html" % (base, t)))
    tags_sorted = sorted(tag_map.items(), key=lambda kv: -len(kv[1]))
    open(os.path.join(out_dir, "tag.html"), "w", encoding="utf-8").write(
        tpl_tags.render(tags=tags_sorted, page="tags", page_title="标签"))

    # ---- 归档页
    years = {}
    for p in posts:
        years.setdefault(p["date"][:4], []).append(p)
    archive = [(y, years[y]) for y in sorted(years, reverse=True)]
    open(os.path.join(out_dir, "archive.html"), "w", encoding="utf-8").write(
        tpl_archive.render(archive=archive, page="archive", page_title="归档", total=len(posts)))

    # ---- 友链页
    if friends:
        open(os.path.join(out_dir, "friends.html"), "w", encoding="utf-8").write(
            tpl_friends.render(friends=friends, page="friends", page_title="友链"))

    # ---- 搜索页 / 索引
    open(os.path.join(out_dir, "search.html"), "w", encoding="utf-8").write(
        tpl_search.render(page="search", page_title="搜索"))
    index = [{"t": p["title"], "u": p["url"].replace(base, ""), "d": p["date"],
              "g": p["tags"], "s": p["summary"][:100],
              "c": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", p["html"]))[:600]} for p in posts]
    json.dump(index, open(os.path.join(out_dir, "search.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    # ---- 全站 RSS / sitemap
    open(os.path.join(out_dir, "rss.xml"), "w", encoding="utf-8").write(
        build_rss(cfg, base, posts))
    urls = [base + "/", base + "/archive.html", base + "/tag.html", base + "/search.html"]
    if friends:
        urls.append(base + "/friends.html")
    urls += [p["url"] for p in posts]
    urls += ["%s/tag/%s.html" % (base, t) for t in tag_map]
    open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join("<url><loc>%s</loc></url>" % html.escape(u) for u in urls) + "</urlset>")

    # ---- 静态资源
    shutil.copytree(ASSETS, os.path.join(out_dir, "assets"))
    if os.path.exists(os.path.join(ROOT, "static")):
        shutil.copytree(os.path.join(ROOT, "static"), out_dir, dirs_exist_ok=True)

    print("posts: %d（新增标记 %d）" % (len(posts), sum(1 for p in posts if p["new"])))
    print("pages: %d, per page: %d" % (len(pages), per_page))
    print("tags : %d -> %s" % (len(tag_map), ", ".join("%s(%d)" % (t, len(v)) for t, v in tags_sorted)))
    print("toc  : %d 篇带目录" % sum(1 for p in posts if len(p["toc"]) >= 3 and p["words"] > 1500))
    print("out  : %s" % out_dir)


if __name__ == "__main__":
    main()
