#!/usr/bin/env python3
"""Turn a built /features/ page into one standalone HTML file.

The page as built pulls its pictures from /assets/, which only resolves on the
live site. Opening the built file straight off disk gives you the layout with
every picture broken, which is exactly the part worth checking before it ships.

So: read the built page, replace every src="/assets/..." with a data URI of the
file on disk, drop the Cloudflare beacon, and write one file that can be double
clicked, mailed, or dropped on a phone and still look like the real thing.

    python3 site_build.py
    python3 make_article_preview.py --all        # or: eigengrau
"""

import argparse, base64, mimetypes, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = ROOT / "signal-site-build"


def data_uri(path: pathlib.Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def inline(slug: str, site: pathlib.Path, out_dir: pathlib.Path) -> pathlib.Path:
    src = site / "features" / slug / "index.html"
    if not src.is_file():
        sys.exit(f"not built: {src}\n"
                 f"Run site_build.py first. Note that an article only builds once an "
                 f"issue carries it; until then there is no page to preview.")
    page = src.read_text(encoding="utf-8")
    missing = []

    def swap(m):
        rel = m.group(1)
        f = site / rel.lstrip("/")
        if not f.is_file():
            missing.append(rel)
            return m.group(0)
        return f'src="{data_uri(f)}"'

    page = re.sub(r'src="(/assets/[^"]+)"', swap, page)
    # The analytics beacon is the site's business, not the preview's, and it
    # makes a file opened from disk reach out to the network for no reason.
    page = re.sub(r'<script[^>]*cloudflareinsights[^>]*>.*?</script>', '',
                  page, flags=re.S)

    out = out_dir / f"{slug}-preview.html"
    out.write_text(page, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"{slug}: {kb:,.0f} KB -> {out}" + (f"   MISSING {missing}" if missing else ""))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--site", default=str(SITE), help="the site_build.py output directory")
    ap.add_argument("--out", default=str(ROOT))
    a = ap.parse_args()

    site = pathlib.Path(a.site)
    writing = site / "features"
    slugs = a.slugs
    if a.all:
        if not writing.is_dir():
            sys.exit(f"no {writing}: no article is live yet. An article is published "
                     f"only once an issue carries it - see WRITING.md.")
        slugs = sorted(p.name for p in writing.iterdir() if p.is_dir())
    if not slugs:
        sys.exit("name a slug, or pass --all")
    for s in slugs:
        inline(s, site, pathlib.Path(a.out))


if __name__ == "__main__":
    main()
