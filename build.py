# -*- coding: utf-8 -*-
"""tl128 新站静态生成器。

用法：
    python build.py                # 生成到 public/
    python build.py --draft        # 只生成、不做 URL 校验

内容：content/*.md（JSON front matter + markdown）
产物：public/  index.html、post/*.html、tag/*.html、tag.html、rss.xml、
      search.json、sitemap.xml、assets/*
"""
import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = os.path.dirname(os.path.abspath(__file__))
CONTENT = os.path.join(ROOT, "content")
TEMPLATES = os.path.join(ROOT, "templates")
ASSETS = os.path.join(ROOT, "assets")
PUBLIC = os.path.join(ROOT, "public")
STANZA_FILE = os.path.join(ROOT, "data", "stanzas.json")

IDEO = "\u3000"


# ---------------------------------------------------------------- front matter
def parse_post(path):
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    if not raw.startswith("---\n"):
        raise SystemExit("缺少 front matter: %s" % path)
    end = raw.index("\n---\n", 4)
    meta = json.loads(raw[4:end])
    body = raw[end + 5:].lstrip("\n")
    meta["body"] = body
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
    """给散文的每条正文行补段首两个全角空格（与作者既有风格一致）。"""
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
    """按断点行号在诗里插空行。断点表为空则原样返回。"""
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
    """在 HTML 层补段首缩进：markdown 渲染会把段首的全角空格吃掉。

    只处理以文字开头的 <p>，图片/已有缩进/嵌套标签的段落原样跳过。
    """
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


def plain_summary(meta, html_body):
    text = re.sub(r"<[^>]+>", " ", html_body)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(IDEO, "").strip()
    if meta.get("summary"):
        s = re.sub(r"\s+", " ", meta["summary"]).strip().replace(IDEO, "")
        return s
    return text[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="覆盖 config 里的 baseUrl")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    base = (args.base or cfg["baseUrl"]).rstrip("/")
    out_dir = args.out or PUBLIC
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "post"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "tag"), exist_ok=True)

    breaks = {}
    known_already = set()
    if os.path.exists(STANZA_FILE):
        data = json.load(open(STANZA_FILE, encoding="utf-8"))
        breaks = data.get("breaks", {})
        known_already = set(data.get("already_sectioned", []))

    posts = [parse_post(os.path.join(CONTENT, f)) for f in os.listdir(CONTENT) if f.endswith(".md")]
    for p in posts:
        p["is_poem"] = "诗" in p.get("tags", [])
        body = p["body"]
        if p["is_poem"]:
            if p["title"] in breaks and p["title"] not in known_already:
                body = split_stanzas(body, breaks[p["title"]])
        else:
            body = indent_paragraphs(body)
        html_body = render_html(body)
        if not p["is_poem"]:
            html_body = indent_html(html_body)
        p["html"] = html_body
        p["summary"] = plain_summary(p, p["html"])
        p["words"] = len(re.sub(r"\s", "", re.sub(r"<[^>]+>", "", p["html"])))
        p["minutes"] = max(1, round(p["words"] / 400))
        p["url"] = "%s/post/%s.html" % (base, p["slug"])

    posts.sort(key=lambda x: (x.get("top", 0), x["date"], x["pid"]), reverse=True)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    env.globals.update(base=base, cfg=cfg)
    tpl_index = env.get_template("index.html")
    tpl_post = env.get_template("post.html")
    tpl_tag = env.get_template("tag.html")
    tpl_tags = env.get_template("tags.html")
    tpl_search = env.get_template("search.html")

    per_page = int(cfg.get("perPage", 25))

    # 文章页
    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        html_out = tpl_post.render(post=p, newer=newer, older=older, page="post",
                                   page_title=p["title"])
        open(os.path.join(out_dir, "post", p["slug"] + ".html"), "w", encoding="utf-8").write(html_out)

    # 首页与分页
    pages = [posts[i:i + per_page] for i in range(0, len(posts), per_page)] or [[]]
    for n, chunk in enumerate(pages, 1):
        name = "index.html" if n == 1 else "page%d.html" % n
        html_out = tpl_index.render(posts=chunk, page_no=n, page_count=len(pages), page="index",
                                    page_title=None, total=len(posts))
        open(os.path.join(out_dir, name), "w", encoding="utf-8").write(html_out)

    # 标签
    tag_map = {}
    for p in posts:
        for t in p.get("tags", []):
            tag_map.setdefault(t, []).append(p)
    for t, items in tag_map.items():
        fn = re.sub(r'[\\/:*?"<>|\s]', "_", t)
        html_out = tpl_tag.render(tag=t, posts=items, page="tag", page_title=t, total=len(items))
        open(os.path.join(out_dir, "tag", fn + ".html"), "w", encoding="utf-8").write(html_out)
    tags_sorted = sorted(tag_map.items(), key=lambda kv: -len(kv[1]))
    open(os.path.join(out_dir, "tag.html"), "w", encoding="utf-8").write(
        tpl_tags.render(tags=tags_sorted, page="tags", page_title="标签"))

    # 搜索页
    open(os.path.join(out_dir, "search.html"), "w", encoding="utf-8").write(
        tpl_search.render(page="search", page_title="搜索"))

    # 搜索索引
    index = [{"t": p["title"], "u": p["url"].replace(base, ""), "d": p["date"],
              "g": p.get("tags", []), "s": p["summary"][:100],
              "c": re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", p["html"]))[:600]} for p in posts]
    json.dump(index, open(os.path.join(out_dir, "search.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    # RSS
    tz = timezone(timedelta(hours=int(cfg.get("utcOffset", 8))))
    items = []
    for p in posts[:40]:
        try:
            dt = datetime.strptime(p["date"], "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            dt = datetime(1970, 1, 1, tzinfo=tz)
        items.append(
            "<item><title>%s</title><link>%s</link><guid>%s</guid>"
            "<pubDate>%s</pubDate><description><![CDATA[%s]]></description></item>"
            % (html.escape(p["title"]), p["url"], p["url"], dt.strftime("%a, %d %b %Y %H:%M:%S %z"),
               p["html"][:4000])
        )
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
        "<title>%s</title><link>%s/</link><description>%s</description><language>zh-CN</language>%s"
        "</channel></rss>" % (html.escape(cfg["title"]), base, html.escape(cfg.get("subTitle", "")),
                              "".join(items))
    )
    open(os.path.join(out_dir, "rss.xml"), "w", encoding="utf-8").write(rss)

    # sitemap
    urls = [base + "/"] + [p["url"] for p in posts]
    open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join("<url><loc>%s</loc></url>" % u for u in urls) + "</urlset>")

    # 静态资源
    shutil.copytree(ASSETS, os.path.join(out_dir, "assets"))
    if os.path.exists(os.path.join(ROOT, "static")):
        shutil.copytree(os.path.join(ROOT, "static"), out_dir, dirs_exist_ok=True)

    print("posts: %d" % len(posts))
    print("pages: %d, per page: %d" % (len(pages), per_page))
    print("tags : %d -> %s" % (len(tag_map), ", ".join("%s(%d)" % (t, len(v)) for t, v in tags_sorted)))
    print("out  : %s" % out_dir)


if __name__ == "__main__":
    main()
