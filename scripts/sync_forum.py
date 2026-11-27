import json
import re
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

SITE_URL = "https://forum.a1lab.tech"
MAIN_SITE_URL = "https://a1lab.tech"
API_BASE = f"{SITE_URL}/api/v3/post/list"
INDEXNOW_KEY = "a3071ef3c90e4c4f8dc77102aba3d500"

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "how", "to", "in", "of", "for", "on", "with", "at", "by", "from",
    "and", "or", "can", "you", "your", "i", "we", "it", "this", "that",
    "what", "when", "where", "why", "which", "who", "as", "into", "about"
}

def make_canonical_slug(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    chosen = filtered if len(filtered) >= 2 else words
    slug = "-".join(chosen)[:80].strip("-")
    return slug or "post"

def fetch_all_posts(max_pages: int = 10) -> list[dict]:
    all_posts = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        url = f"{API_BASE}?sort=New&limit=50&page={page}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "A1Lab-KnowledgeBase-Sync/2.0 (+https://forum.a1lab.tech)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        batch = payload.get("posts", [])
        if not batch:
            break

        for item in batch:
            post = item.get("post", {})
            pid = post.get("id")
            if not pid or pid in seen_ids:
                continue
            if post.get("removed") or post.get("deleted"):
                continue
            seen_ids.add(pid)
            all_posts.append(item)

        if len(batch) < 50:
            break

    return all_posts

def extract_clean_teaser(body: str, max_len: int = 190) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "```", "---", "|", ">", "!", "- ", "* ")):
            continue
        # Strip inline markdown formatting for crisp plain-text summary
        clean = re.sub(r"`([^`]+)`", r"\1", line)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)
        clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) < 35:
            continue
        if len(clean) <= max_len:
            return clean
        cut = clean[:max_len]
        last_period = cut.rfind(". ")
        if last_period > 80:
            return cut[: last_period + 1]
        return cut.rsplit(" ", 1)[0].rstrip(" ,;:") + "..."
    return ""

def submit_to_indexnow(urls: list[str]) -> None:
    if not INDEXNOW_KEY or not urls:
        return
    try:
        payload = json.dumps({
            "host": "forum.a1lab.tech",
            "key": INDEXNOW_KEY,
            "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
            "urlList": urls[:100],
        }).encode("utf-8")

        req = urllib.request.Request(
            "[https://api.indexnow.org/indexnow](https://api.indexnow.org/indexnow)",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"IndexNow ping status: {resp.status} ({len(urls[:100])} URLs submitted)")
    except Exception as e:
        print(f"IndexNow ping skipped: {e}")

def main() -> None:
    items = fetch_all_posts()
    by_community: dict[str, list[dict]] = {}
    recent_posts: list[dict] = []

    for item in items:
        post = item.get("post", {})
        comm = item.get("community", {})
        counts = item.get("counts", {})

        pid = post["id"]
        title = (post.get("name") or "").strip()
        body = (post.get("body") or "").strip()
        cname = (comm.get("title") or comm.get("name") or "General").strip()
        cslug = (comm.get("name") or "general").strip()

        slug = make_canonical_slug(title)
        canonical_url = f"{SITE_URL}/post/{pid}/{slug}"
        teaser = extract_clean_teaser(body)
        published = (post.get("published") or "")[:10]
        comments_count = counts.get("comments", 0)

        entry = {
            "id": pid,
            "title": title,
            "url": canonical_url,
            "teaser": teaser,
            "published": published,
            "community": cname,
            "community_url": f"{SITE_URL}/c/{cslug}",
            "comments": comments_count,
        }
        by_community.setdefault(cname, []).append(entry)
        recent_posts.append(entry)

    total_posts = len(recent_posts)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# 🚀 A1Lab Developer Knowledge Base — Live Q&A & Engineering Index",
        "",
        f"An automatically synchronized technical index of actionable programming solutions, code examples, and developer discussions published on **[A1Lab Developer Forum]({SITE_URL})** (part of the **[A1Lab Ecosystem]({MAIN_SITE_URL})**).",
        "",
        f"[![Explore Forum](https://img.shields.io/badge/A1Lab_Forum-forum.a1lab.tech-04AA6D?style=flat-square)]({SITE_URL}) "
        f"[![Courses & Tools](https://img.shields.io/badge/Main_Platform-a1lab.tech-111827?style=flat-square)]({MAIN_SITE_URL}) "
        f"[![Indexed Guides](https://img.shields.io/badge/Indexed_Guides-{total_posts}-0A66C2?style=flat-square)]({SITE_URL})",
        "",
        f"> **Auto-Synced Every 6 Hours** | Last Updated: `{now_utc}` | Full runnable code & discussions: [{SITE_URL}]({SITE_URL})",
        "",
        "---",
        "",
        "## 📌 Table of Contents",
        "",
        "- [🆕 Latest Published Technical Guides](#-latest-published-technical-guides)",
    ]

    for cname in sorted(by_community.keys()):
        anchor = re.sub(r"[^a-z0-9]+", "-", cname.lower()).strip("-")
        lines.append(f"- [📂 {cname} ({len(by_community[cname])})](#-{anchor})")

    lines.extend([
        "",
        "---",
        "",
        "## 🆕 Latest Published Technical Guides",
        "",
    ])

    for p in recent_posts[:10]:
        lines.append(f"- **[{p['title']}]({p['url']})** — *{p['community']}* (`{p['published']}`)")

    lines.extend(["", "---", ""])

    for cname in sorted(by_community.keys()):
        c_entries = by_community[cname]
        c_url = c_entries[0]["community_url"]
        lines.append(f"## 📂 {cname}")
        lines.append("")
        lines.append(f"Browse all discussions in **[{cname} on A1Lab Forum]({c_url})**:")
        lines.append("")
        for p in c_entries:
            lines.append(f"- **[{p['title']}]({p['url']})** *({p['published']})*")
            if p["teaser"]:
                lines.append(f"  > {p['teaser']}")
        lines.append("")

    Path("README.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    # Also generate a clean machine-readable llms.txt mirror for GEO / AI crawlers
    llms_lines = [
        "# A1Lab Developer Forum — Curated Technical Knowledge Index",
        f"> Canonical Source: {SITE_URL}",
        f"> Ecosystem Platform: {MAIN_SITE_URL}",
        "",
        "## Canonical Q&A Threads",
        "",
    ]
    for p in recent_posts:
        desc = f": {p['teaser']}" if p["teaser"] else ""
        llms_lines.append(f"- [{p['title']}]({p['url']}){desc}")

    Path("llms.txt").write_text("\n".join(llms_lines).strip() + "\n", encoding="utf-8")
    print(f"Successfully synced {total_posts} posts across {len(by_community)} communities.")

    submit_to_indexnow([p["url"] for p in recent_posts])

if __name__ == "__main__":
    main()
