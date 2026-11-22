# -*- coding: utf-8 -*-
"""站内死链检查：解析 public/ 下所有 HTML，把内部链接解析成磁盘路径，逐个验证存在。

用法： python check_links.py [public目录]
"""
import json
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
PUB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "public")
cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
BASE = (sys.argv[2] if len(sys.argv) > 2 else cfg["baseUrl"]).rstrip("/")

LINK_RE = re.compile(r'(?:href|src)="([^"]+)"')


def local_path(url, page_dir):
    """把内部链接解析成磁盘路径；外部链接返回 None。"""
    u = url.split("#", 1)[0].split("?", 1)[0]
    if not u:
        return None
    if re.match(r"^(https?:)?//", u) or u.startswith(("mailto:", "javascript:", "data:")):
        if u.startswith(BASE):
            u = u[len(BASE):]
        else:
            return None
    if u.startswith("/"):
        rel = u
    else:
        rel = os.path.join(page_dir, u).replace("\\", "/")
    decoded = urllib.parse.unquote(rel)
    norm = os.path.normpath(os.path.join(PUB, decoded.lstrip("/")))
    return norm


def main():
    pages = []
    for dirpath, _, files in os.walk(PUB):
        for f in files:
            if f.endswith(".html"):
                pages.append(os.path.join(dirpath, f))
    missing, checked = [], 0
    for page in pages:
        page_dir = os.path.relpath(os.path.dirname(page), PUB).replace("\\", "/")
        if page_dir == ".":
            page_dir = ""
        body = open(page, encoding="utf-8").read()
        for url in set(LINK_RE.findall(body)):
            target = local_path(url, page_dir)
            if target is None:
                continue
            checked += 1
            if not os.path.exists(target):
                missing.append((os.path.relpath(page, PUB), url, os.path.relpath(target, PUB)))

    print("页面: %d，内部链接: %d，失效: %d" % (len(pages), checked, len(missing)))
    for page, url, target in missing[:40]:
        print("  %-40s -> %s\n      缺: %s" % (page, url[:70], target[:80]))
    if len(missing) > 40:
        print("  …还有 %d 条" % (len(missing) - 40))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
