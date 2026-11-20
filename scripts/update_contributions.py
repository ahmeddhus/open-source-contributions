#!/usr/bin/env python3
"""Add newly merged open-source PRs to a README.

Finds PRs authored by GH_USER that were merged into repositories the user
doesn't own, and inserts any whose URL isn't already in the README.
Hand-written entries are never touched or reordered.

Usage:
  python scripts/update_contributions.py --mode profile    # ahmeddhus/ahmeddhus
  python scripts/update_contributions.py --mode portfolio  # open-source-contributions
  add --dry-run to print the result instead of writing it.

Env: GITHUB_TOKEN (optional locally, set automatically in Actions), GH_USER.
Skip a PR or a whole repo by listing its URL or owner/repo in
.github/contributions-ignore (one per line, # for comments).
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com"
USER = os.environ.get("GH_USER", "ahmeddhus")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
IGNORE_FILE = ".github/contributions-ignore"

PROFILE_HEADING = "### 🔓 Open Source Contributions"
PORTFOLIO_HEADING = "## 🛠️ Open Source Contributions"


def api(path, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "contributions-readme-updater",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def merged_prs():
    q = f"is:pr is:merged author:{USER} -user:{USER} is:public"
    items, page = [], 1
    while True:
        data = api("/search/issues", {"q": q, "per_page": 100, "page": page})
        items += data["items"]
        if len(items) >= data["total_count"] or not data["items"]:
            break
        page += 1
    prs = []
    for it in items:
        owner, repo = it["repository_url"].split("/")[-2:]
        prs.append({
            "owner": owner,
            "repo": repo,
            "number": it["number"],
            "url": it["html_url"],
            # drop a trailing "(#39)" that squash merges add
            "title": re.sub(r"\s*\(#\d+\)\s*$", "", it["title"]).strip(),
            "merged": (it.get("pull_request") or {}).get("merged_at") or it["closed_at"],
        })
    prs.sort(key=lambda p: p["merged"])  # oldest first
    return prs


def load_ignores():
    if not os.path.exists(IGNORE_FILE):
        return set()
    with open(IGNORE_FILE) as f:
        return {l.strip().lower().rstrip("/") for l in f
                if l.strip() and not l.lstrip().startswith("#")}


def repo_pattern(owner, repo):
    return re.compile(rf"github\.com/{re.escape(owner)}/{re.escape(repo)}(?![\w.-])", re.I)


def update_profile(text, new):
    lines = text.split("\n")
    i = lines.index(PROFILE_HEADING) + 1
    while i < len(lines) and not lines[i].startswith("- "):
        i += 1
    # newest goes first, so insert oldest-first at the same spot
    for pr in new:
        lines.insert(i, f"- [{pr['repo']} #{pr['number']}]({pr['url']}) - {pr['title']}")
    return "\n".join(lines)


def update_portfolio(text, new):
    lines = text.split("\n")
    for pr in new:
        pat = repo_pattern(pr["owner"], pr["repo"])
        bullet = [f"- ✅ **[PR #{pr['number']}]({pr['url']})**  ", f"  {pr['title']}"]
        start = section_end = None
        top = lines.index(PORTFOLIO_HEADING)
        # sections run from a "### " line to the next "---" / "## " / "### "
        j = top + 1
        while j < len(lines) and not lines[j].startswith("## "):
            if lines[j].startswith("### "):
                k = j + 1
                while k < len(lines) and not (lines[k].strip() == "---"
                                              or lines[k].startswith("## ")
                                              or lines[k].startswith("### ")):
                    k += 1
                # match by GitHub links in the section, or a heading like
                # "### 🗓️ [repo_name](https://pub.dev/packages/repo_name)"
                if pat.search("\n".join(lines[j:k])) or re.search(
                        rf"(?<![\w.-]){re.escape(pr['repo'])}(?![\w.-])", lines[j], re.I):
                    start, section_end = j, k
                    break
                j = k
            else:
                j += 1
        if start is not None:
            last = section_end - 1
            while lines[last].strip() == "":
                last -= 1
            lines[last + 1:last + 1] = bullet
        else:
            info = api(f"/repos/{pr['owner']}/{pr['repo']}")
            desc = (info.get("description") or "").strip()
            block = [f"### 📦 [{pr['repo']}](https://github.com/{pr['owner']}/{pr['repo']})", ""]
            if desc:
                block += [f"> {desc}", ""]
            block += bullet + ["", "---", ""]
            ins = top + 1
            while ins < len(lines) and lines[ins].strip() == "":
                ins += 1
            lines[ins:ins] = block
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["profile", "portfolio"], required=True)
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.readme, encoding="utf-8") as f:
        text = f.read()
    ignores = load_ignores()
    known = text.lower()
    new = [p for p in merged_prs()
           if p["url"].lower() not in known
           and p["url"].lower() not in ignores
           and f"{p['owner']}/{p['repo']}".lower() not in ignores]

    if not new:
        print("No new merged PRs.")
        return
    for p in new:
        print(f"Adding {p['owner']}/{p['repo']}#{p['number']}: {p['title']}")
    out = (update_profile if args.mode == "profile" else update_portfolio)(text, new)
    if args.dry_run:
        sys.stdout.write(out)
    else:
        with open(args.readme, "w", encoding="utf-8") as f:
            f.write(out)


if __name__ == "__main__":
    main()
