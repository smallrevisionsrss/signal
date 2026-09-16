# Signal, new rails

The static site that makes Signal readable by AI crawlers, search engines and
feed readers. Nothing here changes how you edit issues. You keep publishing to
`signal-issues-data.json` exactly as now; this turns that file into a real
website every time you push it.

**Why:** no AI crawler executes JavaScript. The current `/rsssignal` page builds
itself client side from the JSON, so GPTBot, OAI-SearchBot, ClaudeBot,
Claude-SearchBot and PerplexityBot all see an empty shell. This build puts every
headline, source and link into the served HTML.

---

## What gets built

From one command, `python3 site_build.py`:

| Output | What it is |
|---|---|
| `index.html` | Today's issue, complete, server rendered |
| `issues/2026-09-14/` | One permanent URL per issue. 45 of them today |
| `archive/` | Every issue, newest first |
| `about/` | How Signal is edited. Written to be quotable |
| `feed.xml` | RSS 2.0, each issue carried in full |
| `sitemap.xml` | All 48 URLs with lastmod dates |
| `robots.txt` | Every AI crawler explicitly allowed |
| `404.html`, `CNAME`, `.nojekyll` | Housekeeping |

Each issue page also carries `Article` and `ItemList` JSON-LD, per-issue
`og:` tags using that issue's hero image, a canonical URL, and `rel="prev"` /
`rel="next"` so crawlers can walk the whole archive from any entry point.

---

## Setup, once

### 1. Make the repository

Create a GitHub repo, for example `smallrevisions/signal`, and put in it:

```
signal-issues-data.json
site_build.py
.github/workflows/deploy.yml      <- this is deploy.yml, renamed into that path
```

Push to `main`.

### 2. Turn on Pages

Repo → **Settings → Pages → Build and deployment → Source: GitHub Actions**.

The workflow runs on any push that touches the JSON or the generator. It builds,
runs sanity checks, and deploys. If the home page ever comes out without at least
twenty outbound links in its raw HTML, the build **fails rather than deploys**,
which is the guard against silently shipping an empty shell again.

### 3. Point the subdomain at it

At your DNS provider, add one record:

```
Type: CNAME
Name: signal
Value: <your-github-username>.github.io
```

Then in **Settings → Pages → Custom domain**, enter `signal.smallrevisions.com`
and tick **Enforce HTTPS** once the certificate is issued. That takes a few
minutes to an hour.

The `CNAME` file is written by the build, so the domain survives every deploy.

### 4. Squarespace housekeeping

- **Settings → Crawlers**: confirm "Block known artificial intelligence crawlers"
  is **off**. You cannot edit robots.txt on Squarespace, so this toggle is the
  only lever you have there.
- **Settings → Advanced → URL Mappings**: once the new site is live, send the old
  page across so the two do not compete for the same content:
  ```
  /rsssignal -> https://signal.smallrevisions.com/ 301
  ```
  Or, if you want to keep the page on the shop, replace its contents with a short
  description and a link. Either is fine. Two full copies of the same issues on
  two hostnames is the one thing to avoid.

---

## Publishing, daily

Nothing changes in how you build an issue. Afterwards:

```bash
git add signal-issues-data.json
git commit -m "Signal, September 15"
git push
```

Two to three minutes later the issue is live, in the feed, and in the sitemap.

To see it before you push:

```bash
python3 site_build.py --out _site
cd _site && python3 -m http.server 8000
# open http://localhost:8000
```

---

## The editorial note

The generator supports an optional `"note"` field on any issue:

```json
{
  "dateLabel": "September 15, 2026",
  "note": "Three separate pieces this week on institutions being honest about what their collections cannot show...",
  "hero": { ... }
}
```

If present it renders directly under the date, above the hero, and it is the
first substantial prose on the page. Roughly 44% of LLM citations come from the
first 30% of a page's content, so this is the most valuable 100 words on the
site. It is also the only original writing Signal currently has. Without it an
assistant has nothing of yours to quote and will cite Bachtrack or Rylands Blog
instead.

Optional, so an issue without one still builds.

---

## Verifying it worked

**The crawler test.** Open the live site, press Ctrl-U or Cmd-Option-U for
view-source, and search for any headline. View-source is the raw HTML, which is
what crawlers get. Do not use Inspect Element; that shows the rendered DOM and
will tell you everything is fine even when it is not.

**Then, in order:**

1. `signal.smallrevisions.com/robots.txt` and `/sitemap.xml` both load.
2. Submit the sitemap in Google Search Console. This is how the archive gets
   discovered quickly rather than over months.
3. Paste the feed URL into any reader to confirm it parses.
4. In three to four weeks, `site:signal.smallrevisions.com` should return issue
   pages. Today `site:smallrevisions.com` returns no `/rsssignal` at all.

---

## Known gaps, in priority order

1. **Images are hotlinked from publishers.** Roughly half sit on self-hosted
   WordPress installs, which commonly refuse cross-origin requests, which is why
   Quill & Pad came up blank. The build hides a refused image rather than showing
   a broken box, and the hero collapses to one column, so nothing looks broken.
   The real fix is to download each issue's images at build time and serve them
   locally. That also fixes the X cards. Worth doing early.
2. **The `/rsssignal` og:image is still a 254x255 favicon.** The new site uses
   each issue's own hero image, so this only affects the Squarespace page.
3. **No source reference pages yet.** The 300-plus outlet list in
   `sources-full-list.md` is the most citable asset you own and nothing on the
   site exposes it. "Where to find serious writing about film scores" is a
   question people ask assistants in plain language.
4. **No email.** RSS first, as agreed. Revisit once there is sixty days of data.
