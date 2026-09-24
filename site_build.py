#!/usr/bin/env python3
"""
Signal static site generator.

Reads signal-issues-data.json and writes a fully server-rendered static site.
Every headline, source and link exists in the served HTML, so AI crawlers
(GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot, PerplexityBot) can read
it. None of them execute JavaScript.

Output:
  index.html                     latest issue
  issues/YYYY-MM-DD/index.html   one permanent URL per issue
  archive/index.html             every issue, newest first
  about/index.html               what Signal is, how it is made
  feed.xml                       RSS 2.0, full issue in each item
  sitemap.xml
  robots.txt                     AI crawlers explicitly allowed
  404.html
  CNAME

Usage:  python3 site_build.py [--out DIR] [--domain HOST] [--data FILE]
"""

import argparse, html, json, os, re, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- config

SITE_NAME = "Signal"
PUBLISHER = "Small Revisions"
SHOP_URL  = "https://www.smallrevisions.com"
# The design studio. Signal and the shop both point here; the studio is
# the only property that was previously a terminus, linking out to the
# shop but never linked to from anywhere. Separate registrable domain,
# so no prefetch and rel=noopener on every link out.
STUDIO_URL = "https://www.mcswain.studio"
# Google Search Console ownership. Keep this: removing it un-verifies
# the property and the sitemap stops being accepted.
GSC_VERIFY = "kFPZfxmZVRVFninZCFa9nUyYcgQ3X1Xb5mG99A4zh3E"
# IndexNow. The key is proved by hosting it as a text file at the site
# root, so the build writes that file and the workflow pings the API
# after each deploy. Self-generated keys are valid per the spec; this
# one is 32 hex characters.
INDEXNOW_KEY = "182a146f131abb081b50fb231b669a70"

# ---------------------------------------------------------------- analytics
# Signal ran with NO analytics of any kind until 19 Sep 2026. Squarespace's
# dashboard covers smallrevisions.com only and cannot see this subdomain at all,
# so the whole findability effort - the server-rendered pages, the sitemap, the
# IndexNow pings, the category surface - was unmeasurable. That is the gap this
# closes. Optimising anything before this was guesswork.
#
# Off until a token is set: an empty ANALYTICS_ID emits nothing at all, so the
# build keeps working unchanged and switches on by itself once the value lands.
# Same no-flag-day shape as asset().
#
# Both providers are COOKIELESS, so no consent banner is needed and nothing
# about the reading experience changes.
#
#   "cloudflare"  ANALYTICS_ID = the beacon token from
#                 Cloudflare dashboard > Web Analytics > Add a site. Free.
#   "plausible"   ANALYTICS_ID = the bare domain, signal.smallrevisions.com
#
# THE ID IS NOT A SECRET. It is a public site identifier that ships inside the
# page source and is readable by every visitor. Committing it to this public
# repo is expected and carries no risk; do not treat it like an API key.
ANALYTICS_PROVIDER = "cloudflare"
ANALYTICS_ID = "0286586b1b3242d19acb5933f9cd79c1"


def analytics_tag():
    if not ANALYTICS_ID:
        return ""
    if ANALYTICS_PROVIDER == "cloudflare":
        # type="module" is what Cloudflare itself issues; module scripts defer by
        # default, so this does not block rendering. Kept identical to their
        # snippet rather than paraphrased, so it cannot drift from what they test.
        return ('<script type="module" '
                'src="https://static.cloudflareinsights.com/beacon.min.js" '
                f'data-cf-beacon=\'{{"token": "{ANALYTICS_ID}"}}\'></script>')
    if ANALYTICS_PROVIDER == "plausible":
        return (f'<script defer data-domain="{ANALYTICS_ID}" '
                'src="https://plausible.io/js/script.js"></script>')
    raise SystemExit(f"unknown ANALYTICS_PROVIDER: {ANALYTICS_PROVIDER!r}")
TAGLINE   = "A daily edit of writing on design, art, sound, collecting, history and film."
DESCRIPTION = (
    "Signal is a daily digest from Small Revisions. Each issue gathers "
    "twenty four pieces of writing from across design, art and culture, sound, "
    "collecting, history and film, chosen for being reported, researched or "
    "first hand rather than circulated from a press release."
)

# live label -> data key. The keys are a legacy layer; the labels are the site.
SECTIONS = [
    ("Design",         "design-arch"),
    ("Arts & Culture", "craft"),
    ("Sound",          "sound-vinyl"),
    ("Collecting",     "collecting"),
    ("Document",       "archives"),
    ("Film",           "photo-film"),
]
KEY_TO_LABEL = {k: lab for lab, k in SECTIONS}

AI_CRAWLERS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User",
    "ClaudeBot", "Claude-SearchBot", "Claude-User",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot-Extended", "meta-externalagent",
    "Bingbot", "Amazonbot", "cohere-ai", "Bytespider", "Diffbot", "Timpibot",
]

# ---------------------------------------------------------------- helpers

def e(s):
    return html.escape(s or "", quote=True)

def parse_label(label):
    """'September 14, 2026' -> datetime"""
    return datetime.strptime(label.strip(), "%B %d, %Y")

def slug(dt):
    return dt.strftime("%Y-%m-%d")

def rfc822(dt):
    return dt.replace(hour=12, tzinfo=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

def issue_articles(issue):
    for lab, key in SECTIONS:
        for a in issue["categories"].get(key, []):
            yield lab, a

def trim(text, n):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:") + "..."

# ---------------------------------------------------------------- styles

CSS = """
/* Tokens and type scale taken verbatim from Small Revisions' own
   .signal-editorial content block, so this site and
   smallrevisions.com/rsssignal are the same publication. */
:root{
  --ink:#111111;
  --ink-soft:#4c4c4c;
  --ink-faint:#8f8f8c;
  --bg:#f9f7f0;
  --rule:#111111;
  --rule-soft:#dedcd6;
  --signal:#ff3b2f;
  --dot:#fa4616;
  --cat:#152035;
  --serif:'Instrument Serif', Georgia, serif;
  --sans:'Instrument Sans','Helvetica Neue',Arial,sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; background:var(--bg); color-scheme:light}
/* Both sites paint the same cream immediately, so a move between
   them never flashes the browser's default white. */
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans);
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
}
a{color:inherit; text-decoration:none}
h1,h2,h3,h4,h5,p{margin:0}
img{display:block; max-width:100%}
[hidden]{display:none !important}
:focus-visible{outline:2px solid var(--signal); outline-offset:3px}
.container{max-width:1440px; margin:0 auto; padding:0 24px}
/* Gutters. box-sizing is border-box, so this padding sits INSIDE the 1440
   cap rather than outside it. On any display wider than 1440 the cap leaves
   its own generous margin and the padding is irrelevant; at exactly 1440 the
   cap binds, the margin is zero, and the 24px padding is the entire gutter.
   That is the MacBook Pro case and it read as cramped: 24px on a laptop
   against 264px on a 1920 monitor. Doubled from 1024px up, which is the
   range where the cap can bind; phones and tablets keep their own smaller
   values below. Costs 48px of content width at the widest, ~16px per column. */
@media (min-width:1024px){ .container{padding:0 48px} }

/* hero ----------------------------------------------------------- */
.signal-hero{border-top:1px solid var(--rule); padding-top:28px; padding-bottom:24px}
.signal-hero-topline{display:flex; align-items:center; justify-content:space-between; margin-bottom:28px}
.signal-eyebrow{
  display:inline-flex; align-items:center; gap:8px;
  font-size:12px; font-weight:700; letter-spacing:.16em;
  text-transform:uppercase; color:var(--ink);
}
.signal-dot{width:8.4px; height:8.4px; border-radius:50%; background:var(--dot); animation:signal-pulse 2.2s ease-in-out infinite}
@keyframes signal-pulse{0%,100%{opacity:1; transform:scale(1)} 50%{opacity:.35; transform:scale(.72)}}
.signal-hero-date{font-size:13px; font-weight:500; color:var(--ink-faint); letter-spacing:.02em}
.signal-hero-date-value{color:var(--ink)}
.signal-hero-paging{display:flex; gap:18px; margin-top:28px; font-size:13px; font-weight:500; color:var(--ink-faint)}
.signal-hero-paging a{border-bottom:1px solid var(--rule-soft); padding-bottom:2px; transition:color .15s ease, border-color .15s ease}
.signal-hero-paging a:hover{border-color:var(--signal)}
.signal-hero-paging a:hover{color:var(--signal)}

.signal-hero-grid{display:grid; grid-template-columns:repeat(3,1fr); column-gap:0; align-items:center}
.signal-hero-text{grid-column:1; padding-right:40px; display:flex; flex-direction:column; gap:20px}
/* Hero with no usable image. The media figure is hidden by the fallback script,
   which would otherwise leave the text stranded in the first of three columns
   with two thirds of the row empty. Let it run the full width instead. */
.signal-hero.noimg .signal-hero-grid{grid-template-columns:1fr}
.signal-hero.noimg .signal-hero-text{grid-column:1; padding-right:0}
.signal-hero.noimg .signal-hero-dek{max-width:72ch}
.signal-hero-headline{
  font-family:var(--serif); font-weight:400;
  font-size:clamp(1.5rem,.64rem + 2.25vw,2.625rem);
  line-height:1.05; letter-spacing:-.01em;
}
.signal-hero-link{transition:opacity .15s ease}
.signal-hero-link:hover{opacity:.6}
.signal-hero-dek{font-size:1.15rem; line-height:1.55; font-weight:400; color:var(--ink-soft); max-width:46ch}
.signal-hero-meta{display:flex; align-items:center; flex-wrap:wrap; gap:20px; margin-top:4px}
.signal-hero-cta{font-size:14px; font-weight:700; letter-spacing:.01em; border-bottom:1px solid var(--ink); padding-bottom:3px; transition:border-color .15s ease, color .15s ease}
.signal-hero-cta:hover{border-color:var(--signal); color:var(--signal)}
.signal-hero-byline{font-size:13px; color:var(--ink-faint); font-weight:500}
.signal-hero-media{position:relative; grid-column:2 / 4; margin:0}
.signal-hero-media img{width:100%; aspect-ratio:4/3; object-fit:cover; background:#111; border:1px solid var(--rule-soft)}
.signal-hero-media figcaption{
  position:absolute; right:14px; bottom:14px; padding:4px 9px;
  font-size:12px; color:#fff; letter-spacing:.02em;
  background:rgba(0,0,0,.45); border-radius:3px;
}

/* editor note ---------------------------------------------------- */
.signal-note{max-width:74ch; margin:24px 0 0; padding:18px 22px; border:1px solid var(--rule-soft)}
.signal-note h2{font-size:12px; font-weight:700; letter-spacing:.16em; text-transform:uppercase; color:var(--ink-faint); margin-bottom:8px}
.signal-note p{font-size:1.05rem; line-height:1.55; color:var(--ink-soft)}

/* feed ----------------------------------------------------------- */
.signal-feed{padding-top:8px; padding-bottom:64px}
.signal-feed-grid{
  display:grid; grid-template-columns:repeat(3,1fr); column-gap:0;
  margin-left:-32px; margin-right:-32px; width:calc(100% + 64px);
  grid-template-areas:
    "h1 h2 h3"
    "l1 l2 l3"
    "h4 h5 h6"
    "l4 l5 l6";
}
.signal-column-header{
  display:flex; align-items:center; gap:9px;
  margin:0 32px 4px; padding-bottom:14px;
  border-bottom:1px solid var(--rule); color:var(--cat);
}
.signal-column-header[data-category="design-arch"]{grid-area:h1}
.signal-column-header[data-category="craft"]{grid-area:h2}
.signal-column-header[data-category="sound-vinyl"]{grid-area:h3}
.signal-column-header[data-category="collecting"]{grid-area:h4; margin-top:32px}
.signal-column-header[data-category="archives"]{grid-area:h5; margin-top:32px}
.signal-column-header[data-category="photo-film"]{grid-area:h6; margin-top:32px}
.signal-cat-icon{width:18.75px; height:18.75px; flex:none; display:block; color:var(--cat)}
.signal-column-title{font-size:13px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--cat)}

.signal-column{position:relative; padding:0 32px}
.signal-column[data-category="design-arch"]{grid-area:l1}
.signal-column[data-category="craft"]{grid-area:l2}
.signal-column[data-category="sound-vinyl"]{grid-area:l3}
.signal-column[data-category="collecting"]{grid-area:l4}
.signal-column[data-category="archives"]{grid-area:l5}
.signal-column[data-category="photo-film"]{grid-area:l6}
.signal-column[data-category="craft"]::before,
.signal-column[data-category="sound-vinyl"]::before,
.signal-column[data-category="archives"]::before,
.signal-column[data-category="photo-film"]::before{
  content:""; position:absolute; top:32px; bottom:0; left:0; width:1px; background:var(--rule-soft);
}

.signal-row{padding:18px 0; border-bottom:1px solid var(--rule-soft)}
.signal-row:last-child{border-bottom:none}
.signal-row-media{display:block; width:100%; aspect-ratio:4/3; margin-bottom:14px}
.signal-row-media img{width:100%; height:100%; object-fit:cover; display:block; background:#111; border:1px solid var(--rule-soft)}
.signal-row-headline{
  font-family:var(--serif); font-weight:400;
  font-size:clamp(1.15rem,.95rem + .7vw,1.4rem); line-height:1.25;
}
.signal-row-headline a{transition:opacity .15s ease}
.signal-row-headline a:hover{opacity:.6}
.signal-external-icon{font-family:var(--sans); font-size:.72em; color:var(--ink-faint); vertical-align:super}
.signal-row-date{display:block; margin-top:8px; font-size:12.5px; font-weight:500; font-family:var(--sans); color:var(--ink-faint)}

/* merged filter view --------------------------------------------- */
.signal-merged{padding-top:8px; padding-bottom:64px}
.signal-merged .signal-column-list{position:relative; display:flex; align-items:flex-start; column-gap:0}
.signal-filter-col{flex:1 1 0; min-width:0}
.signal-filter-col + .signal-filter-col{border-left:1px solid var(--rule-soft)}
.signal-merged .signal-column-list .signal-row{margin-left:32px; margin-right:32px}
.signal-merged-count{font-size:12.5px; font-weight:500; color:var(--ink-faint); margin-left:auto}

/* pagination ------------------------------------------------------ */
/* No rule of its own: the feed above ends on its own hairline and the
   subscribe block below opens with the black one, so a third line
   here just stacked two rules in the same gap. */
.signal-pagination{display:flex; justify-content:space-between; align-items:center; gap:24px; padding:24px 0 48px}
.signal-pagination-link:only-child{margin-left:auto; margin-right:auto}
.signal-hero-date-value a{color:inherit; border-bottom:1px solid transparent; transition:border-color .15s ease, color .15s ease}
.signal-hero-date-value a:hover{color:var(--signal); border-color:var(--signal)}
/* Stacked issues need no divider of their own: .signal-hero already
   opens with a full-width black rule, which is exactly how the
   /rsssignal block separates one issue from the next. Adding a
   second, lighter line here put two rules in the same seam. */
.signal-pagination-link{font-size:13px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; border-bottom:1px solid var(--ink); padding-bottom:3px; transition:border-color .15s ease, color .15s ease}
.signal-pagination-link:hover{border-color:var(--signal); color:var(--signal)}

/* archive + prose ------------------------------------------------- */
.signal-arch{list-style:none; margin:0; padding:0; max-width:900px}
.signal-arch li{border-bottom:1px solid var(--rule-soft)}
.signal-arch a{display:flex; flex-wrap:wrap; gap:6px 20px; align-items:baseline; padding:18px 2px; transition:opacity .15s ease}
.signal-arch a:hover{opacity:.6}
.signal-arch .d{font-family:var(--serif); font-size:1.4rem; min-width:11em}
.signal-arch .h{color:var(--ink-faint); font-size:14px; flex:1 1 280px}

.prose{max-width:68ch; padding-top:28px}
.prose h1{font-family:var(--serif); font-weight:400; font-size:clamp(1.9rem,1.2rem+2vw,2.625rem); line-height:1.05; letter-spacing:-.01em; margin-bottom:12px}
.prose h2{font-family:var(--serif); font-weight:400; font-size:1.5rem; margin:36px 0 10px}
.prose p,.prose li{font-size:1.05rem; line-height:1.6; color:var(--ink-soft); margin-bottom:14px}
.prose strong{color:var(--ink); font-weight:600}
.prose a{color:var(--signal); border-bottom:1px solid var(--signal)}
.prose ul{padding-left:20px; margin-bottom:14px}
.prose-intro{font-size:13px; font-weight:500; color:var(--ink-faint); letter-spacing:.02em; margin-bottom:28px}

/* subscribe ------------------------------------------------------- */
.feedurl{display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin:0 0 20px}
.feedurl code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:14px; background:#fff; border:1px solid var(--rule-soft); padding:9px 12px; overflow-wrap:anywhere}
.feedcopy{font-family:inherit; font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:var(--ink); background:none; border:0; border-bottom:1px solid var(--ink); padding:0 0 3px; cursor:pointer}
.feedcopy:hover{color:var(--signal); border-color:var(--signal)}
.signal-sub{padding:28px 0 0; border-top:1px solid var(--rule);
  display:grid; grid-template-columns:repeat(3,1fr); column-gap:32px; align-items:center}
.signal-sub-text{grid-column:1 / 3}
.signal-sub h2{font-family:var(--serif); font-weight:400; font-size:1.5rem; margin-bottom:8px}
.signal-sub p{color:var(--ink-soft); font-size:1.05rem; line-height:1.55; margin-bottom:18px; max-width:58ch}
/* A cut-out product shot on a transparent ground, so it is never cropped
   and never given the dark backing the editorial images carry. */
.signal-sub-media{grid-column:3; margin:0; justify-self:end; width:100%}
.signal-sub-media img{width:100%; height:auto; display:block; object-fit:contain}
/* Colophon. One line naming who compiles this, set quiet and given no
   rule above it — the two hairlines that used to sit at the foot of an
   issue were both removed on request, and this is not an excuse to put
   one back. It states a fact and links the studio; it does not sell. */
.signal-colophon{padding:26px 0 44px; font-size:13px; line-height:1.5;
  color:var(--ink-faint); letter-spacing:.01em}
.signal-colophon a{color:var(--ink-soft); border-bottom:1px solid var(--rule-soft);
  padding-bottom:1px; transition:color .15s ease, border-color .15s ease}
.signal-colophon a:hover{color:var(--ink); border-color:var(--ink)}

@media (max-width:900px){
  .signal-hero-grid{grid-template-columns:1fr; gap:28px}
  .signal-hero-text{grid-column:1; padding-right:0}
  .signal-hero-media{grid-column:1; order:-1}
  .signal-feed-grid{
    grid-template-columns:1fr; margin-left:0; margin-right:0; width:100%;
    grid-template-areas:"h1" "l1" "h2" "l2" "h3" "l3" "h4" "l4" "h5" "l5" "h6" "l6";
  }
  .signal-column-header{margin-left:0 !important; margin-right:0 !important; margin-top:28px !important}
  .signal-column-header[data-category="design-arch"]{margin-top:0 !important}
  .signal-column{padding:0 !important}
  .signal-column::before{display:none}
  .signal-sub{grid-template-columns:1fr; row-gap:24px}
  .signal-sub-text{grid-column:1}
  .signal-sub-media{grid-column:1; justify-self:start; max-width:360px}
  .signal-merged .signal-column-list{display:block}
  .signal-filter-col + .signal-filter-col{border-left:none}
  .signal-merged .signal-column-list .signal-row{margin-left:0; margin-right:0}
}
@media (max-width:520px){
  .container{padding:0 18px}
  .signal-hero-dek{max-width:none}
  .signal-sub{grid-template-columns:1fr; row-gap:24px}
  .signal-sub-text{grid-column:1}
  .signal-sub-media{grid-column:1; justify-self:start; max-width:320px}
  /* The topline is one line at desktop width; at phone width the
     eyebrow and the standing line stack rather than crowd. */
  .signal-hero-topline{display:block}
  .signal-hero-date{display:block; margin-top:8px}
}
@media (prefers-reduced-motion:reduce){
  .signal-dot{animation:none}
  .signal-hero-link,.signal-row-headline a,.signal-hero-cta,.signal-arch a{transition:none}
}
"""

# ---------------------------------------------------------------- shell

# Assets the site owns. Anything dropped into assets/ beside this script is
# copied to _site/assets/ and served from our own domain.
#
# These used to load from raw.githubusercontent.com (a repo now retired) and the
# shop's Squarespace CDN. Both are gone: the files live in assets/ and are served
# from our own domain.
#
# There was briefly a fallback to those old URLs, so the switchover needed no flag
# day. It is deliberately removed. A fallback is only worth having if the thing it
# falls back TO still works, and once the old repo is archived it does not — it
# would simply trade one broken image for another, quietly. The workflow now runs
# `test -f _site/assets/logo.svg` and `crate.png`, so a missing asset fails the
# deploy outright. Loud beats silent; asset() warns for the local case, where
# there is no CI to catch it.
ASSET_DIR = Path(__file__).resolve().parent / "assets"


def asset(name):
    if not (ASSET_DIR / name).is_file():
        print(f"WARNING: assets/{name} is missing - pages will link a broken image",
              file=sys.stderr)
    return f"/assets/{name}"


LOGO = asset("logo.svg")

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?'
         'family=Instrument+Sans:ital,wght@0,400..700;1,400..700'
         '&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">')

# One line-art glyph per section, echoing the marks beside the column
# headings on smallrevisions.com/rsssignal.
GLYPHS = {
 "design-arch": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V9l8-5 8 5v11"/><path d="M9 20v-6h6v6"/></svg>',
 "craft":       '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 3l4 4L9 19l-5 1 1-5z"/><path d="M14 6l4 4"/></svg>',
 "sound-vinyl": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/></svg>',
 "collecting":  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 8l9-4 9 4-9 4z"/><path d="M3 12l9 4 9-4"/><path d="M3 16l9 4 9-4"/></svg>',
 "archives":    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/></svg>',
 "photo-film":  '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14"/><path d="M7 5v14M17 5v14M3 12h18"/></svg>',
}

ARROW = '<span class="arw" aria-hidden="true">&#8599;</span>'

# ---------------------------------------------------------------- nav
# Ported from Small Revisions' own header code injection so the two
# domains read as one site. CSS is close to verbatim; the markup drops
# the Squarespace-only plumbing and points Shop, cart and logo at
# www.smallrevisions.com with absolute URLs so navigation between the
# two never looks like a boundary.

NAV_CSS = """
/* fixed nav ------------------------------------------------------ */
.mainnav-fixed{position:fixed; top:0; left:0; right:0; z-index:20; background:var(--bg)}
.mainnav-spacer{width:100%}

.mainnav-announce{background:var(--ink); border-bottom:1px solid var(--ink)}
.mainnav-announce-row{position:relative; display:flex; align-items:center; justify-content:center; padding:10px 40px; text-align:center}
.mainnav-announce-text{font-size:13px; color:rgba(249,247,240,.7); margin:0}
.mainnav-announce-text a{font-weight:700; color:var(--bg); border-bottom:1px solid var(--bg); padding-bottom:1px; transition:border-color .15s ease, color .15s ease}
.mainnav-announce-text a:hover{border-color:var(--signal); color:var(--signal)}
.mainnav-announce-close{position:absolute; right:24px; top:50%; transform:translateY(-50%); background:none; border:none; cursor:pointer; padding:4px; font-size:16px; line-height:1; color:rgba(249,247,240,.7); transition:color .15s ease}
.mainnav-announce-close:hover{color:var(--bg)}
.mainnav-announce.is-dismissed{display:none}

.mainnav-inner{display:flex; align-items:center; gap:24px; padding:20px 0}
.mainnav-logo{display:block; flex:none; transition:opacity .15s ease}
.mainnav-logo:hover{opacity:.6}
.mainnav-logo img{display:block; height:63px; width:auto}
.mainnav-bottom-row{display:flex; align-items:center; justify-content:space-between; gap:24px; flex:1; min-width:0}
.mainnav-links{display:flex; align-items:center; flex:1; min-width:0}

.mainnav-toplink{
  background:none; border:none; cursor:pointer; padding:6px 0; margin-right:20px;
  font-size:14px; font-weight:600; letter-spacing:.01em; color:var(--ink);
  border-bottom:2px solid transparent; transition:border-color .15s ease;
  flex:none; white-space:nowrap;
}
.mainnav-toplink.is-open{border-color:var(--dot)}

.mainnav-rollout{
  display:grid; grid-template-columns:0fr; align-items:center; margin-right:0;
  overflow:hidden; opacity:0;
  transition:grid-template-columns .4s cubic-bezier(.4,0,.2,1), margin-right .4s cubic-bezier(.4,0,.2,1), opacity .3s ease;
}
.mainnav-rollout.is-open{grid-template-columns:1fr; margin-right:20px; opacity:1}
.mainnav-rollout-inner{display:flex; align-items:center; gap:20px; min-width:0; overflow:hidden; white-space:nowrap}

.signal-tab{
  background:none; border:none; cursor:pointer; padding:6px 0;
  font-size:14px; font-weight:600; letter-spacing:.01em; color:var(--ink-faint);
  border-bottom:2px solid transparent; transition:color .15s ease, border-color .15s ease;
  white-space:nowrap; flex:none;
}
.signal-tab:hover{color:var(--ink)}
.signal-tab.is-active{color:var(--cat); border-color:var(--dot)}

.mainnav-rollout a{
  font-size:13px; font-weight:600; letter-spacing:.01em; color:var(--ink-faint);
  border-bottom:2px solid transparent; padding-bottom:2px;
  transition:color .15s ease, border-color .15s ease; white-space:nowrap; flex:none;
}
.mainnav-rollout a:hover{color:var(--ink)}
.mainnav-rollout a.is-active{color:var(--cat); border-color:var(--dot)}

.mainnav-actions{display:flex; align-items:center; gap:22px}
.mainnav-search{position:relative; flex:none; width:200px; max-width:100%}
.mainnav-search-input{
  width:100%; border:none; border-bottom:1px solid var(--rule-soft); background:none;
  padding:6px 18px 6px 0; font-size:14px; font-family:inherit; color:var(--ink);
  text-align:right; transition:border-color .15s ease;
}
.mainnav-search-input::placeholder{color:var(--ink-faint)}
.mainnav-search-input::-webkit-search-cancel-button{display:none}
.mainnav-search-input:focus{outline:none; border-color:var(--ink)}

.search-dropdown{
  position:absolute; top:calc(100% + 8px); right:0; width:360px;
  max-width:calc(100vw - 32px); max-height:420px; overflow-y:auto;
  background:var(--bg); border:1px solid var(--rule-soft);
  box-shadow:0 12px 32px rgba(17,17,17,.12); z-index:30; display:none; text-align:left;
}
.search-dropdown.is-open{display:block}
.search-section-label{padding:10px 14px 6px; font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-faint)}
.search-result{display:block; padding:8px 14px; border-top:1px solid var(--rule-soft)}
.search-section-label + .search-result{border-top:none}
.search-result:hover{background:var(--rule-soft)}
.search-result-title{font-size:13.5px; font-weight:600; color:var(--ink); line-height:1.3}
.search-result-meta{font-size:11.5px; color:var(--ink-faint); margin-top:2px}
.search-empty,.search-loading{padding:16px 14px; font-size:13px; color:var(--ink-faint); text-align:center}

.mainnav-icon-btn{display:flex; align-items:center; gap:6px; background:none; border:none; cursor:pointer; padding:0; color:var(--ink); transition:color .15s ease}
.mainnav-icon-btn:hover{color:var(--signal)}
.mainnav-icon{width:19px; height:19px; flex:none; display:block}
.mainnav-icon-btn.cart .mainnav-icon{width:28px; height:28px}
.mainnav-cart-count{font-size:12px; font-weight:600; color:var(--ink)}
.mainnav-icon-btn:hover .mainnav-cart-count{color:var(--signal)}

.mainnav-toggle{display:none; background:none; border:none; cursor:pointer; padding:4px; color:var(--ink)}
.mainnav-toggle .mainnav-icon{width:22px; height:22px}

/* merged filter view --------------------------------------------- */
.merged-feed{padding-top:8px; padding-bottom:64px}
.merged-head{display:flex; flex-wrap:wrap; gap:10px 18px; align-items:baseline; padding-bottom:9px; border-bottom:1px solid var(--rule); margin-bottom:6px}
.merged-head .count{font-size:12.5px; color:var(--ink-faint)}
.merged-grid{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:0 34px}
.merged-grid li{list-style:none; padding:17px 0; border-bottom:1px solid var(--rule-soft)}
.merged-grid ol{list-style:none; margin:0; padding:0}
.merged-issue{font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-faint); margin:0 0 6px}

@media (max-width:1100px){ .merged-grid{grid-template-columns:repeat(2,minmax(0,1fr))} }
@media (max-width:760px){
  .mainnav-announce-row{padding:10px 44px}
  .mainnav-announce-text{font-size:12px}
  .mainnav-logo img{height:51.61px}
  .mainnav-links{display:none}
  .mainnav-toggle{display:block}
  .mainnav-inner{display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 0; position:relative}
  .mainnav-bottom-row{display:contents}
  .mainnav-actions{flex:1; gap:16px; justify-content:flex-end}
  .mainnav-search{flex:1; width:auto; min-width:0}
  .search-dropdown{left:0; right:0; width:auto; max-width:none}
  .merged-grid{grid-template-columns:1fr}
  .mainnav-links.is-open{
    display:flex; flex-direction:column; align-items:stretch;
    position:absolute; top:100%; left:0; right:0; background:var(--bg);
    border-top:1px solid var(--rule-soft); padding:18px 0; gap:0;
    max-height:calc(100vh - 60px); overflow-y:auto; z-index:25;
  }
  .mainnav-links.is-open .mainnav-toplink{padding:10px 0; margin-right:0; font-size:16px; color:var(--ink); border-bottom:none; text-align:left}
  .mainnav-links.is-open .mainnav-rollout{display:flex; flex-direction:column; align-items:flex-start; max-height:0; gap:0; margin-right:0; overflow:hidden; opacity:1; grid-template-columns:none; transition:max-height .4s ease}
  .mainnav-links.is-open .mainnav-rollout.is-open{max-height:420px}
  .mainnav-links.is-open .mainnav-rollout-inner{display:contents}
  .mainnav-links.is-open .signal-tab,
  .mainnav-links.is-open .mainnav-rollout a{padding:8px 0 8px 14px; font-size:14px; border-bottom:none}
}
"""

CART_SVG = ('<svg class="mainnav-icon" viewBox="0 0 144 144" aria-hidden="true" fill="currentColor">'
            '<path d="M91.95,109.3h-40.08c-2.9,0-5.26,2.36-5.26,5.26v4.9h50.61v-4.9c0-2.9-2.36-5.26-5.26-5.26Z"/>'
            '<path d="M121.54,25.07H22.28c-3.18,0-5.75,2.89-5.75,6.44v81.5c0,3.56,2.58,6.44,5.75,6.44h21.04v-4.9c0-4.71,3.83-8.54,8.54-8.54h40.08c4.71,0,8.54,3.83,8.54,8.54v4.9h21.04c3.18,0,5.75-2.89,5.75-6.44V31.51c0-3.56-2.58-6.44-5.75-6.44ZM62.54,62.6l9.37-9.37,9.37,9.37-9.37,9.37-9.37-9.37ZM67.81,75.01l-9.37,9.37-9.37-9.37,9.37-9.37,9.37,9.37ZM85.38,65.64l9.37,9.37-9.37,9.37-9.37-9.37,9.37-9.37ZM89.49,62.6l9.37-9.37,9.37,9.37-9.37,9.37-9.37-9.37ZM85.38,59.55l-9.37-9.37h18.74l-9.37,9.37ZM55.91,34.02c0-1.24,1.21-2.25,2.7-2.25h26.59c1.49,0,2.7,1.01,2.7,2.25v7.54c0,1.24-1.21,2.25-2.7,2.25h-26.59c-1.49,0-2.7-1.01-2.7-2.25v-7.54ZM67.81,50.18l-9.37,9.37-9.37-9.37h18.74ZM54.34,62.6l-9.37,9.37-9.37-9.37,9.37-9.37,9.37,9.37ZM31.77,50.18h9.37l-9.37,9.37v-9.37ZM31.77,65.64l9.37,9.37-9.37,9.37v-18.74ZM31.77,99.84v-9.37l9.37,9.37h-9.37ZM44.97,96.8l-9.37-9.37,9.37-9.37,9.37,9.37-9.37,9.37ZM49.07,99.84l9.37-9.37,9.37,9.37h-18.74ZM62.54,87.43l9.37-9.37,9.37,9.37-9.37,9.37-9.37-9.37ZM76.01,99.84l9.37-9.37,9.37,9.37h-18.74ZM98.86,96.8l-9.37-9.37,9.37-9.37,9.37,9.37-9.37,9.37ZM111.93,99.84h-9.37l9.37-9.37v9.37ZM111.93,84.38l-9.37-9.37,9.37-9.37v18.74ZM111.93,59.55l-9.37-9.37h9.37v9.37Z"/></svg>')

BURGER_SVG = ('<svg class="mainnav-icon" viewBox="0 0 72 72" aria-hidden="true">'
              '<line x1="10" y1="22" x2="62" y2="22" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>'
              '<line x1="10" y1="36" x2="62" y2="36" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>'
              '<line x1="10" y1="50" x2="62" y2="50" stroke="currentColor" stroke-width="5" stroke-linecap="round"/></svg>')


def nav_html(domain):
    tabs = "".join(
        f'<button type="button" class="signal-tab" data-filter="{k}" role="tab" aria-selected="false">{e(lab)}</button>'
        for lab, k in [("All", "all")] + SECTIONS)
    shop = "".join(
        f'<a href="{SHOP_URL}{href}"{cls}>{lab}</a>'
        for lab, href, cls in [("All", "/all", ' class="is-active"'), ("Books", "/all/books", ""),
                               ("Records", "/all/records", ""), ("Accessories", "/all/accessories", "")])
    return f"""<div class="mainnav-fixed" id="mainnav-fixed">
<div class="mainnav-announce" id="mainnav-announce"><div class="container">
<div class="mainnav-announce-row">
<p class="mainnav-announce-text">A curated selection of design, art &amp; culture. <a href="{SHOP_URL}/all">Order now</a></p>
<button type="button" class="mainnav-announce-close" id="mainnav-announce-close" aria-label="Dismiss announcement">&times;</button>
</div></div></div>
<div class="mainnav-row"><div class="container"><div class="mainnav-inner">
<a class="mainnav-logo" href="{SHOP_URL}"><img src="{LOGO}" alt="{e(PUBLISHER)}" width="154" height="63"></a>
<div class="mainnav-bottom-row">
<nav class="mainnav-links" id="mainnav-links" aria-label="Main">
<a class="mainnav-toplink" href="{SHOP_URL}/all" data-group="shop">Shop</a>
<button type="button" class="mainnav-toplink" data-group="scroll" aria-expanded="false">Signal</button>
<div class="mainnav-rollout" id="scroll-rollout" role="tablist" aria-label="Filter stories by section">
<div class="mainnav-rollout-inner">{tabs}</div>
</div>
</nav>
<div class="mainnav-actions">
<div class="mainnav-search">
<input type="search" class="mainnav-search-input" id="search-input" placeholder="Search" aria-label="Search" autocomplete="off">
<div class="search-dropdown" id="search-dropdown" role="listbox" aria-label="Search results"></div>
</div>
<a class="mainnav-icon-btn cart" href="{SHOP_URL}/cart" aria-label="Cart, 0 items">{CART_SVG}<span class="mainnav-cart-count">0</span></a>
<button type="button" class="mainnav-toggle" id="mainnav-toggle" aria-label="Open menu" aria-expanded="false">{BURGER_SVG}</button>
</div>
</div>
</div></div></div>
</div>
<div class="mainnav-spacer" id="mainnav-spacer" aria-hidden="true"></div>"""


NAV_JS = """
<script>
(function(){
  var announce = document.getElementById('mainnav-announce');
  var bar = document.getElementById('mainnav-fixed');
  var spacer = document.getElementById('mainnav-spacer');
  var toplink = document.querySelector('.mainnav-toplink[data-group="scroll"]');
  var rollout = document.getElementById('scroll-rollout');
  var links = document.getElementById('mainnav-links');
  var toggle = document.getElementById('mainnav-toggle');
  var input = document.getElementById('search-input');
  var dropdown = document.getElementById('search-dropdown');
  var mergedWrap = document.getElementById('merged-wrap');
  var mergedGrid = document.getElementById('merged-grid');
  var mergedHead = document.getElementById('merged-head');
  var LABELS = __LABELS__;
  var ICONS = __ICONS__;

  function reserve(){ if(bar && spacer) spacer.style.height = bar.offsetHeight + 'px'; }
  function alignClose(){
    var close = document.getElementById('mainnav-announce-close');
    var cart = document.querySelector('.mainnav-icon-btn.cart');
    var row = close ? close.closest('.mainnav-announce-row') : null;
    if(!close || !cart || !row) return;
    var r = row.getBoundingClientRect(), c = cart.getBoundingClientRect();
    close.style.right = (r.right - (c.left + c.width/2) - close.offsetWidth/2) + 'px';
  }
  function layout(){ reserve(); alignClose(); }

  /* Filtering runs on top of server-rendered HTML, never instead of
     it. Crawlers get the full issue; this only rearranges it. */
  var DATA = null;
  function loadData(cb){
    if(DATA){ cb(DATA); return; }
    fetch('/signal-issues-data.json').then(function(r){ return r.json(); })
      .then(function(d){ DATA = d; cb(d); }).catch(function(){ cb([]); });
  }

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }

  function showIssue(v){
    /* Class names track the .signal-editorial content block, so the
       filter has to hide the same elements the block styles. */
    /* A listing page stacks seven issues, so this has to hide all of
       them, not just the first. querySelector would leave six behind. */
    ['.signal-issue', '.signal-hero', '.signal-feed', '.signal-pagination'].forEach(function(sel){
      document.querySelectorAll(sel).forEach(function(el){ el.hidden = !v; });
    });
  }

  /* Ported from the /rsssignal content block so the filtered view is the
     same view: images included, heroes folded in, and the three columns
     balanced by image count rather than sliced in thirds. */
  var MONTH_ABBR = {January:'Jan',February:'Feb',March:'Mar',April:'Apr',May:'May',June:'Jun',
                    July:'Jul',August:'Aug',September:'Sep',October:'Oct',November:'Nov',December:'Dec'};
  function shortDate(dateLabel){
    var m = /^(\w+) (\d+),/.exec(dateLabel || '');
    if(!m) return dateLabel || '';
    return (MONTH_ABBR[m[1]] || m[1]) + ' ' + m[2];
  }
  function sourceFromByline(byline){
    var parts = (byline || '').split('\u00b7');
    return parts.length > 1 ? parts[parts.length - 1].trim() : (byline || '');
  }
  function heroToRow(issue){
    return {headline: issue.hero.headline, url: issue.hero.url, image: issue.hero.image,
            source: sourceFromByline(issue.hero.byline), date: shortDate(issue.dateLabel)};
  }
  /* A hero whose category matches the filter belongs in the results too;
     leaving it out silently dropped one piece per issue. */
  function buildAllFilteredRows(issues, key){
    var rows = [];
    issues.forEach(function(issue){
      if(issue.hero && issue.hero.category === key) rows.push(heroToRow(issue));
      ((issue.categories && issue.categories[key]) || []).forEach(function(a){ rows.push(a); });
    });
    return rows;
  }
  /* Images drive column height, so balance on image count first and row
     count second. A flat slice into thirds leaves ragged columns. */
  function distributeIntoColumns(rows, count){
    var cols = [], imageCounts = [], rowCounts = [];
    for(var c = 0; c < count; c++){ cols.push([]); imageCounts.push(0); rowCounts.push(0); }
    rows.forEach(function(item){
      var best = 0;
      for(var c = 1; c < count; c++){
        if(imageCounts[c] < imageCounts[best] ||
           (imageCounts[c] === imageCounts[best] && rowCounts[c] < rowCounts[best])) best = c;
      }
      cols[best].push(item);
      rowCounts[best]++;
      if(item.image) imageCounts[best]++;
    });
    return cols;
  }
  function renderRowHTML(item){
    var imageHTML = item.image ?
      '<a class="signal-row-media" href="' + esc(item.url) + '" tabindex="-1" aria-hidden="true">' +
      '<img src="' + esc(item.image) + '" alt="" loading="lazy"></a>' : '';
    return '<div class="signal-row' + (item.image ? ' has-media' : '') + '">' + imageHTML +
      '<h5 class="signal-row-headline"><a href="' + esc(item.url) + '" target="_blank" rel="noopener">' +
      esc(item.headline) + ' <span class="signal-external-icon" aria-hidden="true">\u2197\ufe0e</span></a></h5>' +
      '<time class="signal-row-date">' + esc(item.source) +
      (item.date ? ' \u00b7 ' + esc(item.date) : '') + '</time></div>';
  }

  function renderMerged(key){
    if(!mergedWrap) return;
    loadData(function(issues){
      var rows = buildAllFilteredRows(issues, key);
      var colsHTML = distributeIntoColumns(rows, 3).map(function(colRows){
        return '<div class="signal-filter-col">' + colRows.map(renderRowHTML).join('') + '</div>';
      }).join('');
      mergedHead.innerHTML = (ICONS[key] || '') +
        '<h4 class="signal-column-title">' + esc(LABELS[key] || '') + '</h4>' +
        '<span class="signal-merged-count">' + rows.length +
        ' pieces across ' + issues.length + ' issues</span>';
      mergedGrid.className = 'signal-column-list';
      mergedGrid.innerHTML = colsHTML;
      mergedWrap.hidden = false;
      window.scrollTo(0, 0);
    });
  }

  function setFilter(key){
    document.querySelectorAll('.signal-tab').forEach(function(t){
      var on = t.getAttribute('data-filter') === key;
      t.classList.toggle('is-active', on);
      t.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    if(key === 'all'){
      showIssue(true);
      if(mergedWrap){ mergedWrap.hidden = true; mergedGrid.innerHTML = ''; }
    } else {
      showIssue(false);
      renderMerged(key);
    }
  }

  function openRollout(){
    rollout.classList.add('is-open');
    toplink.classList.add('is-open');
    toplink.setAttribute('aria-expanded', 'true');
    setFilter('all');
    layout();
  }
  function closeRollout(){
    rollout.classList.remove('is-open');
    toplink.classList.remove('is-open');
    toplink.setAttribute('aria-expanded', 'false');
    document.querySelectorAll('.signal-tab').forEach(function(t){
      t.classList.remove('is-active'); t.setAttribute('aria-selected','false');
    });
    showIssue(true);
    if(mergedWrap){ mergedWrap.hidden = true; mergedGrid.innerHTML = ''; }
    layout();
  }

  if(toplink && rollout){
    toplink.addEventListener('click', function(){
      if(window.location.pathname !== '/'){ window.location.href = '/?open=scroll'; return; }
      rollout.classList.contains('is-open') ? closeRollout() : openRollout();
    });
    document.querySelectorAll('.signal-tab').forEach(function(t){
      t.addEventListener('click', function(){ setFilter(t.getAttribute('data-filter')); });
    });
    /* The filter bar opens on arrival, on All, so the six sections are
       visible without a click. Listing pages only: an issue page has no
       merged container, so a tab clicked there would hide the issue and
       have nowhere to render, leaving the page blank. There the toplink
       keeps sending you home with ?open=scroll instead. */
    if(mergedWrap){
      openRollout();
    }
    if(new URLSearchParams(window.location.search).get('open') === 'scroll'){
      if(!rollout.classList.contains('is-open')) openRollout();
      history.replaceState(null, document.title, window.location.pathname);
    }
  }

  var close = document.getElementById('mainnav-announce-close');
  if(close && announce){
    close.addEventListener('click', function(){ announce.classList.add('is-dismissed'); layout(); });
  }
  if(toggle && links){
    toggle.addEventListener('click', function(){
      var open = links.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      layout();
    });
  }

  /* Search covers Signal only. The shop lives on another origin and
     its JSON endpoint refuses cross-origin reads, so shop results
     would silently return nothing rather than fail loudly. */
  var idx = null, debounce = null;
  function buildIndex(issues){
    var list = [];
    issues.forEach(function(iss){
      if(iss.hero) list.push({t: iss.hero.headline, m: iss.hero.byline, u: iss.hero.url});
      Object.keys(iss.categories || {}).forEach(function(k){
        iss.categories[k].forEach(function(a){ list.push({t: a.headline, m: a.source, u: a.url}); });
      });
    });
    return list;
  }
  function runSearch(q){
    q = q.trim();
    if(!q){ dropdown.classList.remove('is-open'); dropdown.innerHTML=''; return; }
    dropdown.innerHTML = '<div class="search-loading">Searching&hellip;</div>';
    dropdown.classList.add('is-open');
    loadData(function(issues){
      if(input.value.trim() !== q) return;
      if(!idx) idx = buildIndex(issues);
      var ql = q.toLowerCase(), out = [];
      for(var i = 0; i < idx.length && out.length < 10; i++){
        if(idx[i].t && idx[i].t.toLowerCase().indexOf(ql) !== -1) out.push(idx[i]);
      }
      if(!out.length){
        dropdown.innerHTML = '<div class="search-empty">No results for &ldquo;' + esc(q) + '&rdquo;</div>';
        return;
      }
      dropdown.innerHTML = '<div class="search-section-label">Signal</div>' + out.map(function(r){
        return '<a class="search-result" href="' + esc(r.u) + '" target="_blank" rel="noopener">' +
          '<div class="search-result-title">' + esc(r.t) + '</div>' +
          (r.m ? '<div class="search-result-meta">' + esc(r.m) + '</div>' : '') + '</a>';
      }).join('');
    });
  }
  if(input && dropdown){
    input.addEventListener('input', function(){
      clearTimeout(debounce);
      var q = input.value;
      debounce = setTimeout(function(){ runSearch(q); }, 180);
    });
    input.addEventListener('keydown', function(ev){
      if(ev.key === 'Escape'){ dropdown.classList.remove('is-open'); return; }
      if(ev.key !== 'Enter') return;
      ev.preventDefault();
      var first = dropdown.querySelector('.search-result');
      if(first) first.click();
    });
    document.addEventListener('click', function(ev){
      if(!ev.target.closest || !ev.target.closest('.mainnav-search')){
        dropdown.classList.remove('is-open');
      }
    });
  }

  layout();
  window.addEventListener('resize', layout);
  if(document.fonts && document.fonts.ready) document.fonts.ready.then(layout);
})();
</script>
"""


# Publisher images are hotlinked and some hosts refuse cross-origin
# requests. Drop a refused figure rather than show a broken box.
# Progressive enhancement only: every headline, source and link is
# already in the served HTML.
# Chrome prefetches on hover, so by the time the click lands the next
# document is already in memory and swaps in without a loading frame.
# signal.smallrevisions.com and www.smallrevisions.com share one
# registrable domain, which is what makes the cross-origin rule legal.
SPECULATION = """<script type="speculationrules">
{"prefetch":[
 {"where":{"href_matches":"/*"},"eagerness":"moderate"},
 {"where":{"href_matches":"https://www.smallrevisions.com/*"},"eagerness":"moderate"}
]}
</script>"""


IMG_FALLBACK_JS = """
<script>
function signalDropImage(i){
  var f = i.closest('figure') || i;
  f.style.display = 'none';
  // .signal-hero, not .hero. This selector was wrong from the start, so the
  // hero never reflowed when its image failed; it just left a hole where the
  // picture should be. Same stale-class bug as the old showIssue().
  var hero = i.closest('.signal-hero');
  if (hero) { hero.classList.add('noimg'); }
}
document.querySelectorAll('img').forEach(function(i){
  i.addEventListener('error', function(){ signalDropImage(i); });
  if (i.complete && i.naturalWidth === 0) { signalDropImage(i); }
});
</script>
"""



def nav_js():
    labels = {"all": "All"}
    labels.update({k: lab for lab, k in SECTIONS})
    return (NAV_JS.replace("__LABELS__", json.dumps(labels, ensure_ascii=False))
                  .replace("__ICONS__", json.dumps(ICONS, ensure_ascii=False)))

# ---------------------------------------------------------------- footer
# Ported from squarespace-block-signal-footer.html. Same silhouette:
# one compact row (logo, links, newsletter, social) over a thin black
# copyright band, mirroring the nav's main row over its announcement
# strip. Logo sized to 63px/51.61px so it reads as the nav's bookend.

FOOTER_CSS = """
.signal-footer{
  background:var(--bg); color:var(--ink);
  border-top:1px solid var(--rule-soft);
  margin-top:64px;
}
.signal-footer-row{padding:35px 0; display:flex; align-items:center; flex-wrap:wrap; gap:16px 24px}
.signal-footer-logo{display:block; flex:none; transition:opacity .15s ease}
.signal-footer-logo:hover{opacity:.6}
.signal-footer-logo img{display:block; height:63px; width:auto}

.signal-footer-links{display:flex; flex-wrap:wrap; align-items:center; gap:20px; flex:1; min-width:0}
.signal-footer-links a{font-size:14px; font-weight:600; letter-spacing:.01em; color:var(--ink); white-space:nowrap}
.signal-footer-links a:not(.signal-footer-jump){color:var(--ink-faint); transition:color .15s ease}
.signal-footer-links a:not(.signal-footer-jump):hover{color:var(--ink)}

.signal-footer-newsletter{
  display:flex; align-items:center; border-bottom:1px solid var(--rule-soft);
  flex:none; width:180px; transition:border-color .15s ease;
}
.signal-footer-newsletter:hover{border-color:var(--ink)}
.signal-footer-newsletter .go{
  flex:none; padding:4px 10px 4px 0; font-size:12px; font-weight:700;
  letter-spacing:.03em; text-transform:uppercase; color:var(--ink);
  transition:color .15s ease;
}
.signal-footer-newsletter:hover .go{color:var(--signal)}
.signal-footer-newsletter .field{flex:1; min-width:0; padding:4px 0; font-size:13px; color:var(--ink-faint); text-align:right}

.signal-footer-social{display:flex; flex:none; gap:10px}
.signal-footer-social a{
  display:flex; align-items:center; justify-content:center;
  width:26px; height:26px; border:1px solid var(--rule-soft); border-radius:50%;
  color:var(--ink-faint); transition:color .15s ease, border-color .15s ease;
}
.signal-footer-social a:hover{color:var(--ink); border-color:var(--ink)}
.signal-footer-social svg{width:12px; height:12px; display:block}

.signal-footer-bottom-bar{background:var(--ink)}
.signal-footer-bottom{padding:10px 0; display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:8px 16px}
.signal-footer-copy{font-size:11px; color:rgba(249,247,240,.7); letter-spacing:.02em}

@media (max-width:760px){
  .signal-footer-row{padding:28px 0; align-items:flex-start}
  .signal-footer-logo img{height:51.61px}
  .signal-footer-links{order:3; width:100%}
  .signal-footer-newsletter{width:auto; flex:1 1 160px}
}
@media (prefers-reduced-motion:reduce){
  .signal-footer-logo,.signal-footer-newsletter,.signal-footer-links a,.signal-footer-social a{transition:none}
}
"""

IG_SVG = ('<svg viewBox="0 0 72 72" fill="none" aria-hidden="true">'
          '<rect x="10" y="10" width="52" height="52" rx="14" stroke="currentColor" stroke-width="5"/>'
          '<circle cx="36" cy="36" r="13" stroke="currentColor" stroke-width="5"/>'
          '<circle cx="50" cy="22" r="3.5" fill="currentColor"/></svg>')

FB_SVG = ('<svg viewBox="0 0 72 72" fill="none" aria-hidden="true">'
          '<path d="M54 6h-9a15 15 0 0 0-15 15v9H21v12h9v24h12V42h9l3-12H42V21a3 3 0 0 1 3-3h9z" '
          'stroke="currentColor" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/></svg>')


def footer_html(domain):
    year = datetime.now().year
    return f"""<footer class="signal-footer">
<div class="container">
<div class="signal-footer-row">
<a class="signal-footer-logo" href="{SHOP_URL}"><img src="{LOGO}" alt="{e(PUBLISHER)}" width="154" height="63"></a>
<nav class="signal-footer-links" aria-label="Footer">
<a href="{SHOP_URL}/all" class="signal-footer-jump">Shop</a>
<a href="#" class="signal-footer-jump" data-jump="scroll">Signal</a>
<!-- No .signal-footer-jump class. That class is what the CSS below uses to
     mean "top-level, stays black"; it belongs to Shop and Signal only.
     Studio is a quiet link and takes the faint treatment like Archive,
     About, Contact and Terms. Dropping the class is safe: the only script
     that reads it is scoped to [data-jump="scroll"], which is Signal. -->
<a href="{STUDIO_URL}" rel="noopener">Studio</a>
<a href="/archive/">Archive</a>
<a href="/about/">About</a>
<a href="{SHOP_URL}/contact">Contact</a>
<a href="{SHOP_URL}/shipping-returns">Terms</a>
</nav>
<a class="signal-footer-newsletter" href="{SHOP_URL}/#newsletter">
<span class="go">Go</span><span class="field">Join / Email</span>
</a>
<div class="signal-footer-social">
<a href="https://www.instagram.com/smallrevisions/" target="_blank" rel="noopener" aria-label="Instagram">{IG_SVG}</a>
<a href="https://www.facebook.com/p/Small-Revisions-61550887410561/" target="_blank" rel="noopener" aria-label="Facebook">{FB_SVG}</a>
</div>
</div>
</div>
<div class="signal-footer-bottom-bar"><div class="container">
<div class="signal-footer-bottom">
<div class="signal-footer-copy">&copy; {year} {e(PUBLISHER)}. All rights reserved.</div>
</div>
</div></div>
</footer>"""


FOOTER_JS = """
<script>
document.querySelectorAll('.signal-footer-jump[data-jump="scroll"]').forEach(function(link){
  link.addEventListener('click', function(ev){
    ev.preventDefault();
    var btn = document.querySelector('.mainnav-toplink[data-group="scroll"]');
    if(!btn) return;
    if(!document.getElementById('scroll-rollout').classList.contains('is-open')) btn.click();
    btn.scrollIntoView({behavior:'smooth', block:'center'});
  });
});
</script>
"""


def page(*, title, desc, canonical, body, domain, jsonld=None,
         og_image=None, og_type="website", prev_url=None, next_url=None,
         nav_current=None):
    base = f"https://{domain}"
    head = [
        '<!doctype html>', '<html lang="en">', '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<meta name="google-site-verification" content="{GSC_VERIFY}">',
        f'<title>{e(title)}</title>',
        f'<meta name="description" content="{e(desc)}">',
        f'<link rel="canonical" href="{e(canonical)}">',
        '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">',
        '<meta name="theme-color" content="#f9f7f0">',
        # The shop is a different origin on the same site. Opening the
        # connection early removes the DNS, TCP and TLS wait from the click.
        f'<link rel="preconnect" href="{SHOP_URL}">',
        f'<link rel="dns-prefetch" href="{SHOP_URL}">',
        f'<meta property="og:site_name" content="{e(SITE_NAME)}">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{e(canonical)}">',
        f'<meta property="og:type" content="{og_type}">',
        '<meta name="twitter:card" content="' + ("summary_large_image" if og_image else "summary") + '">',
        f'<meta name="twitter:title" content="{e(title)}">',
        f'<meta name="twitter:description" content="{e(desc)}">',
    ]
    if og_image:
        head += [f'<meta property="og:image" content="{e(og_image)}">',
                 f'<meta name="twitter:image" content="{e(og_image)}">']
    if prev_url: head.append(f'<link rel="prev" href="{e(prev_url)}">')
    if next_url: head.append(f'<link rel="next" href="{e(next_url)}">')
    head += [
        f'<link rel="alternate" type="application/rss+xml" title="{e(SITE_NAME)}" href="{base}/feed.xml">',
        FONTS,
        SPECULATION,
        f'<style>{CSS}{NAV_CSS}{FOOTER_CSS}{ARTICLE_CSS}</style>',
    ]
    if jsonld:
        head.append('<script type="application/ld+json">'
                    + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
                    + '</script>')
    head.append('</head><body>')

    def nav(href, label, key, sub=False):
        cur = ' aria-current="page"' if nav_current == key else ""
        cls = ' class="navsub"' if sub else ""
        return f'<a href="{href}"{cls}{cur}>{label}</a>'

    mast = nav_html(domain)

    # Colophon removed 24 Sep 2026 at the editor's request. It read "Signal is
    # compiled each morning by McSwain, a design studio in New York" and sat on
    # every page. STUDIO_URL is still used by the footer, so the studio is still
    # linked from the site; this was the per-page line, not the only one.
    colophon = ''
    foot = (footer_html(domain) + IMG_FALLBACK_JS + nav_js() + FOOTER_JS
            + analytics_tag() + "</body></html>")

    return ("\n".join(head) + mast
            + '<main class="container">' + body + colophon + "</main>" + foot)

# ---------------------------------------------------------------- blocks
# Markup mirrors the Signal content block's own structure and class
# names, so the two pages share one stylesheet in all but name.

ICONS = {
 "design-arch": '<svg class="signal-cat-icon" viewBox="0 0 72 72" aria-hidden="true"><polyline points="16.83 7.99 22.34 33.06 55.17 33.06" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><polyline points="55.17 64.01 55.17 39.57 22.21 39.57 16.83 64.01" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
 "craft": '<svg class="signal-cat-icon" viewBox="0 0 72 72" aria-hidden="true"><path d="M14 58L38 34" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><rect x="34" y="10" width="28" height="16" rx="3" transform="rotate(45 48 18)" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/></svg>',
 "sound-vinyl": '<svg class="signal-cat-icon" viewBox="0 0 72 72" aria-hidden="true"><g><circle cx="35.91" cy="36.34" r="26.75" fill="none" stroke="currentColor" stroke-width="5" stroke-miterlimit="10"/><path d="M46.49,20.65c5.03,3.4,8.34,9.16,8.34,15.69" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><path d="M25.33,52.02c-5.03-3.4-8.34-9.16-8.34-15.69" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g><path d="M35.91,26.73c-5.3,0-9.61,4.3-9.61,9.61s4.3,9.61,9.61,9.61,9.61-4.3,9.61-9.61-4.3-9.61-9.61-9.61ZM35.91,38.02c-.93,0-1.68-.75-1.68-1.68s.75-1.68,1.68-1.68,1.68.75,1.68,1.68-.75,1.68-1.68,1.68Z" fill="currentColor"/></svg>',
 "collecting": '<svg class="signal-cat-icon" viewBox="0 0 72 72" aria-hidden="true"><polygon points="36,9 61,23 36,37 11,23" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/><polyline points="11,23 11,49 36,63 36,37" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/><polyline points="61,23 61,49 36,63" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/></svg>',
 "archives": '<svg class="signal-cat-icon" viewBox="0 0 72 72" aria-hidden="true"><polyline points="9,27 36,11 63,27" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/><line x1="7" y1="59" x2="65" y2="59" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><line x1="17" y1="31" x2="17" y2="53" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><line x1="31" y1="31" x2="31" y2="53" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><line x1="43" y1="31" x2="43" y2="53" stroke="currentColor" stroke-width="5" stroke-linecap="round"/><line x1="57" y1="31" x2="57" y2="53" stroke="currentColor" stroke-width="5" stroke-linecap="round"/></svg>',
 "photo-film": '<svg class="signal-cat-icon" viewBox="0 0 72 72" aria-hidden="true"><rect x="9" y="24" width="54" height="34" rx="4" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/><rect x="27" y="14" width="18" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round"/><circle cx="36" cy="41" r="11" fill="none" stroke="currentColor" stroke-width="5"/></svg>',
}

ARROW = '<span class="signal-external-icon" aria-hidden="true">↗︎</span>'


SITE_HOST = "signal.smallrevisions.com"   # set from --domain in build()


def is_own(url):
    """A link to a page on this site, i.e. one of Signal's own pieces."""
    u = url or ""
    return u.startswith("/") or u.startswith(f"https://{SITE_HOST}/")


def row_html(a, internal=False):
    internal = internal or is_own(a.get("url"))
    media = (f'<a class="signal-row-media" href="{e(a["url"])}" tabindex="-1" aria-hidden="true">'
             f'<img src="{e(a["image"])}" alt="" loading="lazy"></a>') if a.get("image") else ""
    date = f' &middot; {e(a["date"])}' if a.get("date") else ""
    return (f'<div class="signal-row">{media}'
            f'<h5 class="signal-row-headline"><a href="{e(a["url"])}"'
            + ('>' + e(a["headline"]) if internal else
               f' target="_blank" rel="noopener">{e(a["headline"])} {ARROW}')
            + '</a></h5>'
            f'<time class="signal-row-date">{e(a["source"])}{date}</time></div>')


def hero_block(issue, paging="", issue_url=None):
    h = issue["hero"]
    media = ""
    if h.get("image"):
        cap = f'<figcaption>{e(h["caption"])}</figcaption>' if h.get("caption") else ""
        media = (f'<figure class="signal-hero-media"><img src="{e(h["image"])}" '
                 f'alt="{e(h.get("caption") or h["headline"])}">{cap}</figure>')
    pag = f'<span class="signal-hero-paging">{paging}</span>' if paging else ""
    note = ""
    if issue.get("note"):
        note = (f'<div class="signal-note"><h2>From the editor</h2>'
                f'<p>{e(issue["note"])}</p></div>')
    # On a listing page the date is the way into that issue's permanent
    # page, which is how a crawler reaches all 48 of them from the home
    # page. It inherits its colour, so it reads as the same plain text.
    datemark = (f'<a href="{e(issue_url)}">{e(issue["dateLabel"])}</a>'
                if issue_url else e(issue["dateLabel"]))
    # Signal's own piece as hero opens here, not in a new tab.
    ext = "" if is_own(h.get("url")) else ' target="_blank" rel="noopener"'
    arrow = "" if is_own(h.get("url")) else ' <span aria-hidden="true">↗︎</span>'
    return f"""<section class="signal-hero">
<div class="signal-hero-topline">
<span class="signal-eyebrow"><span class="signal-dot" aria-hidden="true"></span>Signal</span>
<span class="signal-hero-date">A Running Record of Findings from the Internet / <span class="signal-hero-date-value">{datemark}</span></span>
</div>
<div class="signal-hero-grid">
<div class="signal-hero-text">
<h2 class="signal-hero-headline"><a class="signal-hero-link" href="{e(h['url'])}"{ext}>{e(h['headline'])}</a></h2>
<p class="signal-hero-dek">{e(h.get('dek',''))}</p>
<div class="signal-hero-meta">
<a class="signal-hero-cta" href="{e(h['url'])}"{ext}>Read the story{arrow}</a>
<span class="signal-hero-byline">{e(h.get('byline',''))}</span>
</div>
</div>
{media}
</div>{note}{pag}</section>"""


def sections_block(issue):
    heads, cols = [], []
    for label, key in SECTIONS:
        heads.append(f'<div class="signal-column-header" data-category="{key}">{ICONS.get(key,"")}'
                     f'<h4 class="signal-column-title">{e(label)}</h4></div>')
        rows = "".join(row_html(a) for a in issue["categories"].get(key, []))
        cols.append(f'<div class="signal-column" data-category="{key}">'
                    f'<div class="signal-column-list">{rows}</div></div>')
    return ('<section class="signal-feed"><div class="signal-feed-grid">'
            + "".join(heads) + "".join(cols) + "</div></section>")


SUB_IMAGE = asset("crate.png")


def subscribe_block(domain):
    return f"""<div class="signal-sub">
<div class="signal-sub-text">
<h2>Follow Signal</h2>
<p>Findings across Design, Arts &amp; Culture, Sound, Collecting, Document &amp; Film, gathered each morning. Picked up wherever they were left.</p>
<a class="signal-pagination-link" href="/subscribe/">Subscribe by RSS</a>
</div>
<figure class="signal-sub-media"><img src="{SUB_IMAGE}" alt="Small Revisions crate in primary colors" width="1000" height="671" loading="lazy"></figure>
</div>"""

def issue_jsonld(issue, dt, url, domain):
    arts = list(issue_articles(issue))
    h = issue["hero"]
    items = [{
        "@type": "ListItem", "position": 1,
        "url": h["url"], "name": h["headline"],
    }]
    for i, (lab, a) in enumerate(arts, start=2):
        items.append({"@type": "ListItem", "position": i, "url": a["url"], "name": a["headline"]})
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": url + "#article",
                "headline": f"Signal, {issue['dateLabel']}",
                "description": trim(h.get("dek", ""), 300),
                "datePublished": dt.strftime("%Y-%m-%d"),
                "dateModified": dt.strftime("%Y-%m-%d"),
                "url": url,
                "isAccessibleForFree": True,
                "image": h.get("image", ""),
                "author":    {"@type": "Organization", "name": PUBLISHER, "url": SHOP_URL},
                "publisher": {"@type": "Organization", "name": PUBLISHER, "url": SHOP_URL},
                "isPartOf": {"@type": "Periodical", "name": SITE_NAME,
                             "url": f"https://{domain}/"},
            },
            {
                "@type": "ItemList", "@id": url + "#list",
                "name": f"Signal, {issue['dateLabel']}",
                "numberOfItems": len(items),
                "itemListOrder": "https://schema.org/ItemListUnordered",
                "itemListElement": items,
            },
        ],
    }

def render_issue(issue, dt, *, domain, prev=None, nxt=None, as_index=False):
    url = f"https://{domain}/issues/{slug(dt)}/"
    h = issue["hero"]
    n = 1 + sum(len(v) for v in issue["categories"].values())
    srcs = {h.get("byline", "").split("·")[-1].strip()} | {a["source"] for _, a in issue_articles(issue)}
    desc = trim(f"Signal for {issue['dateLabel']}. {n} pieces from {len(srcs)} publications, "
                f"led by {h['headline']}.", 300)

    paging = []
    if nxt: paging.append(f'<a href="/issues/{slug(nxt)}/" rel="next">Newer issue</a>')
    if prev: paging.append(f'<a href="/issues/{slug(prev)}/" rel="prev">Older issue</a>')
    paging.append('<a href="/archive/">All issues</a>')
    pag = "".join(paging)

    merged = ('<div id="merged-wrap" hidden><section class="signal-merged">'
              '<div class="signal-column-header" id="merged-head"></div>'
              '<div id="merged-grid"></div></section></div>') if as_index else ""
    body = hero_block(issue, paging=pag) + sections_block(issue) + merged + subscribe_block(domain)

    return page(
        title=(f"Signal · {issue['dateLabel']}" if not as_index
               else f"Signal, a daily edit from Small Revisions"),
        desc=desc if not as_index else DESCRIPTION,
        canonical=url if not as_index else f"https://{domain}/",
        body=body, domain=domain, og_type="article",
        og_image=h.get("image"),
        jsonld=issue_jsonld(issue, dt, url, domain),
        prev_url=(f"https://{domain}/issues/{slug(prev)}/" if prev else None),
        next_url=(f"https://{domain}/issues/{slug(nxt)}/" if nxt else None),
        nav_current="today",
    )

PER_PAGE = 7  # matches /rsssignal, which always shows the seven newest


def page_path(n):
    """Page 1 is the site root; every later page lives at /page/N/."""
    return "/" if n == 1 else f"/page/{n}/"


def listing_jsonld(chunk, domain, page_no, total_pages):
    """A listing page is a CollectionPage wrapping an ItemList that points
    at each issue's own permanent URL. The Article markup for an issue
    stays on that permanent page, so nothing is claimed twice."""
    base = f"https://{domain}"
    items = [{
        "@type": "ListItem",
        "position": i,
        "url": f"{base}/issues/{slug(dt)}/",
        "name": f"Signal, {issue['dateLabel']}",
    } for i, (issue, dt) in enumerate(chunk, start=1)]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": base + page_path(page_no),
                "url": base + page_path(page_no),
                "name": SITE_NAME if page_no == 1 else f"{SITE_NAME}, page {page_no}",
                "isPartOf": {"@type": "WebSite", "@id": base + "/#website"},
                "publisher": {"@type": "Organization", "name": PUBLISHER, "url": SHOP_URL},
                "mainEntity": {
                    "@type": "ItemList",
                    "numberOfItems": len(items),
                    "itemListOrder": "https://schema.org/ItemListOrderDescending",
                    "itemListElement": items,
                },
            },
            {
                "@type": "WebSite",
                "@id": base + "/#website",
                "url": base + "/",
                "name": SITE_NAME,
                "description": DESCRIPTION,
                "publisher": {"@type": "Organization", "name": PUBLISHER, "url": SHOP_URL},
            },
        ],
    }


def render_listing(pairs, page_no, domain):
    """One page of the scroll: seven issues stacked newest first, exactly
    as /rsssignal does it, then Newer and Older links. Every issue is
    rendered in full server side, so a crawler that never runs a line of
    JavaScript still reads all seven."""
    base = f"https://{domain}"
    total_pages = max(1, -(-len(pairs) // PER_PAGE))
    page_no = min(max(1, page_no), total_pages)
    start = (page_no - 1) * PER_PAGE
    chunk = pairs[start:start + PER_PAGE]

    blocks = []
    for issue, dt in chunk:
        iso = slug(dt)
        blocks.append(
            f'<article class="signal-issue" id="issue-{iso}">'
            + hero_block(issue, issue_url=f"/issues/{iso}/")
            + sections_block(issue)
            + "</article>")

    links = []
    if page_no > 1:
        links.append(f'<a class="signal-pagination-link" rel="prev" '
                     f'href="{page_path(page_no - 1)}">&larr; Newer</a>')
    if page_no < total_pages:
        links.append(f'<a class="signal-pagination-link" rel="next" '
                     f'href="{page_path(page_no + 1)}">Older &rarr;</a>')
    pagination = f'<div class="signal-pagination">{"".join(links)}</div>' if links else ""

    # The filter view replaces the stack in place, so its container has to
    # exist on every listing page, not only the first.
    merged = ('<div id="merged-wrap" hidden><section class="signal-merged">'
              '<div class="signal-column-header" id="merged-head"></div>'
              '<div id="merged-grid"></div></section></div>')

    newest, oldest = chunk[0][0]["dateLabel"], chunk[-1][0]["dateLabel"]
    if page_no == 1:
        title = f"{SITE_NAME}, a daily edit from {PUBLISHER}"
        desc = DESCRIPTION
    else:
        title = f"{SITE_NAME}, page {page_no} of {total_pages}"
        desc = trim(f"Issues of Signal from {oldest} to {newest}. "
                    f"{len(chunk)} daily editions, each carrying twenty five pieces "
                    f"on design, art, sound, collecting, history and film.", 300)

    return page(
        title=title, desc=desc,
        canonical=base + page_path(page_no),
        body="".join(blocks) + merged + pagination + subscribe_block(domain),
        domain=domain,
        jsonld=listing_jsonld(chunk, domain, page_no, total_pages),
        og_image=chunk[0][0]["hero"].get("image"),
        prev_url=(base + page_path(page_no - 1)) if page_no > 1 else None,
        next_url=(base + page_path(page_no + 1)) if page_no < total_pages else None,
        nav_current="today",
    )


def render_archive(pairs, domain):
    rows = []
    for issue, dt in pairs:
        rows.append(f'<li><a href="/issues/{slug(dt)}/"><span class="d">{e(issue["dateLabel"])}</span>'
                    f'<span class="h">{e(trim(issue["hero"]["headline"], 90))}</span></a></li>')
    total = sum(1 + sum(len(v) for v in i["categories"].values()) for i, _ in pairs)
    body = (f'<div class="prose"><h1>Archive</h1>'
            f'<p class="prose-intro">{len(pairs)} issues, {total} pieces, newest first.</p></div>'
            f'<ul class="signal-arch">{"".join(rows)}</ul>')
    return page(title="Signal archive, every issue",
                desc=f"Every issue of Signal. {len(pairs)} daily editions, {total} pieces of writing "
                     f"on design, art, sound, collecting, history and film.",
                canonical=f"https://{domain}/archive/", body=body, domain=domain,
                nav_current="archive", og_image=pairs[0][0]["hero"].get("image"),
                jsonld={"@context": "https://schema.org", "@type": "CollectionPage",
                        "name": "Signal archive", "url": f"https://{domain}/archive/"})

def render_about(pairs, domain):
    total = sum(1 + sum(len(v) for v in i["categories"].values()) for i, _ in pairs)
    srcs = set()
    for i, _ in pairs:
        srcs.add(i["hero"].get("byline", "").split("·")[-1].strip())
        for _, a in issue_articles(i):
            srcs.add(a["source"])
    body = f"""<div class="prose">
<h1>About Signal</h1>
<p>Signal is a daily edit of writing on design, art and culture, sound, collecting,
history and film, published by <a href="{SHOP_URL}">Small Revisions</a>, an independent
publishing label and retailer in New York City.</p>
<p>Every issue carries twenty four pieces, four in each of six sections, plus one lead
article. To date there are {len(pairs)} issues and {total} pieces drawn from
{len(srcs)} publications.</p>

<h2>What gets in</h2>
<p>One question decides it: could another outlet have written this from the same press
release? If the answer is yes, it is circulated and a reader who follows the field has
already met it. What Signal looks for is the opposite, writing that required somebody to
go somewhere, interview someone, handle the object, read the archive, or remember
something first hand.</p>
<p>That rules out most of what fills a feed: exhibition and product announcements,
reworded press releases, brand collaborations, roundups of other people's roundups,
trend pieces, wire copy. It rules in reported pieces, interviews with a real transcript,
process and technique writing, institutions writing about their own collections,
obituaries carrying first hand memory, close readings of one object or one record or one
building, corrections to accepted accounts, and writing translated from another language.</p>

<h2>How recency is judged</h2>
<p>Not by a fixed window. A site posting five times a day always has something from this
morning, and a museum journal publishing twice a month almost never does, so a flat rule
selects for publishing frequency and reads like quality. Instead each source is measured
against its own cadence: for a daily publication Signal takes the last three days, for a
monthly one the current piece. The principle is to take whatever is currently that
publisher's newest work. Anything pegged to an event keeps the tight window regardless.</p>
<p>One article per issue may run at any age if it is still true, marked <em>evergreen</em>.</p>

<h2>The sections</h2>
<p>An article's section is decided by what it is about and what the writer actually did,
never by which publication ran it. <strong>Design</strong> covers product, graphic,
architecture and interiors, one each. <strong>Arts &amp; Culture</strong> covers art,
photography, fashion and subculture. <strong>Sound</strong> is anything music related,
from live performance and composers to instruments, producers, sound installation and
film scores. <strong>Collecting</strong> is any collected thing, however unlikely.
<strong>Document</strong> is the recorded past examined by someone who went and looked.
<strong>Film</strong> is moving image.</p>

<h2>Rules that never bend</h2>
<ul>
<li>Every date is confirmed on the article's own page, never an index or a search result.</li>
<li>No link ever runs twice, anywhere in the archive.</li>
<li>No publication appears twice in one issue, or more than twice across six issues.</li>
<li>Links go to the real, unaltered source. Signal takes no affiliate revenue and accepts
no payment for placement.</li>
</ul>

<h2>Reading it</h2>
<p>A new issue every day at <a href="https://{domain}/">{domain}</a>. The
<a href="https://{domain}/feed.xml">RSS feed</a> carries each issue in full.</p>
</div>"""
    return page(title="About Signal, how it is edited",
                desc="How Signal is edited: the circulation test, cadence-tiered recency, "
                     "the six sections, and the rules that never bend.",
                canonical=f"https://{domain}/about/", body=body, domain=domain,
                nav_current="about", og_image=pairs[0][0]["hero"].get("image"),
                jsonld={"@context": "https://schema.org", "@type": "AboutPage",
                        "name": "About Signal", "url": f"https://{domain}/about/",
                        "publisher": {"@type": "Organization", "name": PUBLISHER, "url": SHOP_URL}})

# ---------------------------------------------------------------- feeds

def render_subscribe(pairs, domain):
    """A readable page in front of the feed.

    Pointing the button straight at feed.xml showed a wall of XML, because
    no browser ships a feed reader any more. The usual dodge, an XSL
    stylesheet on the feed, is not worth building: Chrome removes XSLT in
    version 158 on 17 November 2026, so it would break within weeks.
    Chrome's own guidance is this shape instead, an HTML page for people
    and a <link rel="alternate"> in the head for readers, which every page
    here already carries."""
    base = f"https://{domain}"
    recent = "".join(
        f'<li><a href="/issues/{slug(dt)}/"><span class="d">{e(i["dateLabel"])}</span>'
        f'<span class="h">{e(trim(i["hero"]["headline"], 80))}</span></a></li>'
        for i, dt in pairs[:5])
    body = f"""<div class="prose">
<h1>Subscribe</h1>
<p>Signal publishes one issue a morning and the feed carries each one whole, so nothing
is held back for the site. Paste this address into any reader.</p>
<div class="feedurl">
<code id="feedurl">{base}/feed.xml</code>
<button type="button" class="feedcopy" id="feedcopy">Copy</button>
</div>
<p>If you do not keep a reader, <a href="{base}/feed.xml">the feed itself is here</a>.
It will look like code in a browser, which is what a feed is: a file written for
software to read rather than a person.</p>
<h2>The last five issues</h2>
</div>
<ul class="signal-arch">{recent}</ul>
<div class="prose"><p><a href="/archive/">All {len(pairs)} issues</a> &middot;
<a href="/about/">What gets in, and why</a></p></div>
<script>
(function(){{
  var b = document.getElementById('feedcopy'), u = document.getElementById('feedurl');
  if(!b || !u || !navigator.clipboard) {{ if(b) b.hidden = true; return; }}
  b.addEventListener('click', function(){{
    navigator.clipboard.writeText(u.textContent.trim()).then(function(){{
      var was = b.textContent; b.textContent = 'Copied';
      setTimeout(function(){{ b.textContent = was; }}, 1600);
    }});
  }});
}})();
</script>"""
    return page(title="Subscribe to Signal",
                desc=f"Signal publishes one issue every morning, carried whole in the feed. "
                     f"{len(pairs)} issues so far.",
                canonical=f"{base}/subscribe/", body=body, domain=domain,
                nav_current="subscribe", og_image=pairs[0][0]["hero"].get("image"),
                jsonld={"@context": "https://schema.org", "@type": "WebPage",
                        "name": "Subscribe to Signal", "url": f"{base}/subscribe/"})


def render_feed(pairs, domain, limit=30):
    base = f"https://{domain}"
    items = []
    for issue, dt in pairs[:limit]:
        url = f"{base}/issues/{slug(dt)}/"
        parts = [f"<p><strong>{html.escape(issue['hero']['headline'])}</strong><br>"
                 f"{html.escape(issue['hero'].get('byline',''))}</p>",
                 f"<p>{html.escape(issue['hero'].get('dek',''))}</p>"]
        for label, key in SECTIONS:
            arts = issue["categories"].get(key, [])
            if not arts:
                continue
            parts.append(f"<h3>{html.escape(label)}</h3><ul>")
            for a in arts:
                parts.append(f'<li><a href="{html.escape(a["url"])}">{html.escape(a["headline"])}</a>'
                             f' &mdash; {html.escape(a["source"])}</li>')
            parts.append("</ul>")
        n = 1 + sum(len(v) for v in issue["categories"].values())
        items.append(f"""  <item>
    <title>Signal, {html.escape(issue['dateLabel'])}</title>
    <link>{url}</link>
    <guid isPermaLink="true">{url}</guid>
    <pubDate>{rfc822(dt)}</pubDate>
    <description><![CDATA[{''.join(parts)}]]></description>
  </item>""")
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{html.escape(SITE_NAME)}</title>
  <link>{base}/</link>
  <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml"/>
  <description>{html.escape(TAGLINE)}</description>
  <language>en</language>
  <lastBuildDate>{now}</lastBuildDate>
  <generator>signal site_build.py</generator>
{chr(10).join(items)}
</channel>
</rss>
"""

def render_sitemap(pairs, domain, arts=()):
    base = f"https://{domain}"
    total_pages = max(1, -(-len(pairs) // PER_PAGE))
    urls = [(f"{base}/", pairs[0][1], "daily", "1.0"),
            (f"{base}/archive/", pairs[0][1], "daily", "0.7"),
            (f"{base}/about/", pairs[0][1], "monthly", "0.6"),
            (f"{base}/subscribe/", pairs[0][1], "monthly", "0.5")]
    # Later pages of the scroll, each one a real URL a crawler can walk.
    urls += [(f"{base}/page/{n}/", pairs[(n - 1) * PER_PAGE][1], "weekly", "0.6")
             for n in range(2, total_pages + 1)]
    urls += [(f"{base}/issues/{slug(dt)}/", dt, "yearly", "0.8") for _, dt in pairs]
    if arts:
        urls.append((f"{base}/writing/", arts[0]["_dt"], "weekly", "0.7"))
        urls += [(f"{base}/writing/{a['slug']}/", a["_dt"], "monthly", "0.8") for a in arts]
    rows = "".join(
        f"<url><loc>{u}</loc><lastmod>{dt.strftime('%Y-%m-%d')}</lastmod>"
        f"<changefreq>{cf}</changefreq><priority>{pr}</priority></url>\n"
        for u, dt, cf, pr in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + rows + "</urlset>\n")

def render_robots(domain):
    allows = "\n\n".join(f"User-agent: {b}\nAllow: /" for b in AI_CRAWLERS)
    return f"""# Signal, published by Small Revisions.
# Read freely. Cite the original publication where one is linked.

User-agent: *
Allow: /

{allows}

Sitemap: https://{domain}/sitemap.xml
"""

def render_404(domain):
    body = ('<div class="prose"><h1>Not here</h1>'
            '<p>That page does not exist. Signal publishes one issue a day; '
            'the <a href="/archive/">archive</a> has all of them, and '
            '<a href="/">today\'s issue</a> is on the front.</p></div>')
    return page(title="Not found", desc="Page not found.",
                canonical=f"https://{domain}/", body=body, domain=domain)

# ---------------------------------------------------------------- main

# ------------------------------------------------------------- articles
# Signal's own writing, kept in its own data file so the issue builder's
# invariants are untouched. An article is just a URL to the rest of the
# system, so dedup, source uniqueness and the rolling cap keep working
# unchanged if one is ever cited in an issue. Whether a given piece has
# earned that is an editorial question, not a build one: the flag
# `issue_eligible` records the answer and nothing here overrides it.

ARTICLES_FILE = Path(__file__).resolve().parent / "signal-articles.json"

ARTICLE_CSS = """
/* Header restyled 24 Sep 2026 to match the issue pages: the rule sits directly
   under the nav, and beneath it the dotted Signal eyebrow on the left with the
   dateline hard right, exactly as .signal-hero/.signal-hero-topline do it. The
   eyebrow and dot classes are the site's own, reused rather than duplicated. */
.signal-article{padding:0 0 72px}
/* The rule lives on the TOPLINE, not on .signal-article. The article is the
   left column of a 68ch grid, so a rule on it stopped short of the page; the
   topline is lifted out of the grid and sits straight in .container, which is
   how .signal-hero does it on the issue pages. Same full bleed, date hard
   right against the container edge. */
.signal-article-topline{display:flex; align-items:center; justify-content:space-between;
  gap:20px; border-top:1px solid var(--rule); padding-top:28px; margin-bottom:36px}
.signal-article-dateline{font-family:var(--sans); font-size:13px; font-weight:500;
  color:var(--ink-faint); letter-spacing:.02em; text-align:right}
.signal-article-dateline b{font-weight:500; color:var(--ink)}
@media (max-width:640px){.signal-article-topline{flex-direction:column;
  align-items:flex-start; gap:10px} .signal-article-dateline{text-align:left}}
/* The site's column system is repeat(3,1fr) - see .signal-hero-grid and
   .signal-feed-grid. This grid used to be minmax(0,68ch) + 1fr, a fixed text
   measure that never grew, so the article stayed the same width on a 1440px
   screen as on a 1024px one while the rail swallowed the difference. Now it is
   the same three fluid columns as everything else, the article spanning two of
   them and the rail taking the third. The gutter is padding on the article
   rather than a grid gap, which is how .signal-hero-text does it. */
.signal-article-grid{display:grid; grid-template-columns:repeat(3,1fr);
  column-gap:0; align-items:start}
.signal-article-grid > .signal-article{grid-column:1 / span 2; padding-right:40px}
.signal-article-grid > .signal-article-rail{grid-column:3}
@media (max-width:1023px){
  .signal-article-grid{grid-template-columns:1fr; row-gap:48px}
  .signal-article-grid > .signal-article{grid-column:1; padding-right:0}
  .signal-article-grid > .signal-article-rail{grid-column:1}
}
.signal-article-eyebrow{font-family:var(--sans);font-size:13px;font-weight:700;
  letter-spacing:.1em;text-transform:uppercase;color:var(--cat);margin:48px 0 18px}
.signal-article-hed{font-family:var(--serif);font-weight:400;
  font-size:clamp(1.9rem,1.2rem + 2vw,2.625rem);line-height:1.12;letter-spacing:-.01em;
  color:var(--ink);max-width:20ch;margin:0 0 20px}
.signal-article-standfirst{font-family:var(--sans);font-size:1.15rem;line-height:1.55;
  color:var(--ink-soft);max-width:46ch;margin:0 0 30px}
/* The standalone byline line is gone: the byline moved into the topline
   dateline on 24 Sep 2026, so it now reads "By Signal / 20 September" up beside
   the eyebrow rather than sitting on its own between standfirst and hero. */
.signal-article-figure{margin:0 0 40px}
.signal-article-figure img{width:100%;aspect-ratio:4/3;object-fit:cover;display:block}
.signal-article-body p{font-family:var(--sans);font-size:1.0625rem;line-height:1.66;
  color:var(--ink);max-width:68ch;margin:0 0 1.3em}
.signal-article-pull{font-family:var(--serif);font-size:1.55rem;line-height:1.26;
  color:var(--ink);max-width:30ch;margin:2.2em 0;padding-top:20px;
  border-top:2px solid var(--signal)}
.signal-article-rail{position:sticky;top:28px}
/* Hairline under the rail heading only. .signal-column-title is shared with the
   issue pages' category headings and with Sources/Further, so this is scoped to
   the rail rather than added to the token; the others were not asked for and a
   rule under every one of them would restripe the issue pages. --rule-soft is
   the lighter of the two rule tokens (#dedcd6 against #111111). */
.signal-article-rail .signal-column-title{display:block;
  border-bottom:1px solid var(--rule-soft); padding-bottom:12px; margin:0 0 4px}
.signal-article-sources{margin:56px 0 0;padding-top:24px;border-top:1px solid var(--rule)}
/* Inside the rail these are stacked blocks, not a coda to a long article, so
   they drop the heavy top rule and the 56px gap. The hairline under each
   heading comes from the .signal-article-rail .signal-column-title rule. */
.signal-article-rail .signal-article-sources{margin:0 0 36px; padding-top:0; border-top:0}
.signal-article-rail .signal-article-sources:last-child{margin-bottom:0}
.signal-article-note{font-family:var(--sans);font-size:13px;line-height:1.6;
  color:var(--ink-faint);max-width:68ch;margin:40px 0 0;padding-top:18px;
  border-top:1px solid var(--rule-soft)}
.signal-writing-list{margin:40px 0 0}
.signal-fig{margin:0 0 40px}
.signal-fig--full{grid-column:1 / -1}
.signal-fig img{width:100%;display:block;background:var(--rule-soft)}
.signal-fig--crop img{aspect-ratio:4/3;object-fit:cover}
.signal-fig--wide img{aspect-ratio:16/9;object-fit:cover}
.signal-figcap{font-family:var(--sans);font-size:12.5px;line-height:1.5;
  color:var(--ink-faint);margin:10px 0 0;max-width:68ch}
.signal-figcap b{font-weight:500;color:var(--ink-soft)}
.signal-figcap a{color:var(--ink-faint);text-decoration:underline;
  text-underline-offset:2px;text-decoration-thickness:.5px}
.signal-figcap a:hover{color:var(--ink)}
.signal-figcap .sep{color:var(--rule-soft);padding:0 .45em}
.signal-plate{aspect-ratio:4/3;background:var(--cat);color:#f4f2ec;
  display:flex;flex-direction:column;justify-content:flex-end;
  padding:clamp(20px,4vw,44px);position:relative;overflow:hidden}
.signal-plate::before{content:"";position:absolute;top:clamp(20px,4vw,44px);
  left:clamp(20px,4vw,44px);width:34px;height:3px;background:var(--signal)}
.signal-plate-line{font-family:var(--serif);font-weight:400;
  font-size:clamp(1.35rem,.7rem + 2.1vw,2.5rem);line-height:1.1;
  letter-spacing:-.01em;margin:0}
.signal-plate-meta{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:clamp(10px,.5rem + .35vw,12px);letter-spacing:.13em;
  text-transform:uppercase;color:#a9b2c4;margin:18px 0 0;line-height:1.9}
"""


def load_articles():
    if not ARTICLES_FILE.is_file():
        return []
    arts = json.load(open(ARTICLES_FILE, encoding="utf-8"))
    bad = []
    for a in arts:
        a["_dt"] = datetime.strptime(a["date"], "%Y-%m-%d").date()
        s = a.get("slug", "?")

        # Every article carries a hero. A piece with no opening image reads as
        # a draft next to the rest of the site, so this fails the build rather
        # than shipping one.
        h = a.get("hero")
        if not h:
            bad.append(f"{s}: no hero")
        elif h.get("kind") == "plate":
            if not h.get("lines"):
                bad.append(f"{s}: plate hero has no lines")
        elif not h.get("src"):
            bad.append(f"{s}: hero has no src")

        figs = [f for f in a.get("body", []) if f.get("type") == "figure"]
        for f in ([h] if h else []) + figs:
            if f.get("kind") == "plate":
                continue
            src = f.get("src", "")
            if "?" in src:
                bad.append(f"{s}: image carries a query string: {src}")
            if not f.get("alt"):
                bad.append(f"{s}: image has no alt text: {src}")
            # Somebody else's picture needs attribution. Our own does not.
            if not src.startswith("/assets/") and not f.get("credit"):
                bad.append(f"{s}: third party image with no credit: {src}")
    if bad:
        raise SystemExit("FAILED, article data is not publishable:\n  - "
                         + "\n  - ".join(bad))
    return sorted(arts, key=lambda a: a["_dt"], reverse=True)


def article_rail(article, pairs, limit=5, wrap=True):
    """Rows from the archive in the same section, so a piece visibly sits on
    the material it came out of. This is the one thing a Signal article can
    do that a post on any other site cannot."""
    cat = article.get("category")
    seen, rows = set(), []
    for issue, dt in pairs:
        for a in issue.get("categories", {}).get(cat, []):
            if a["url"] in seen:
                continue
            seen.add(a["url"])
            rows.append({k: v for k, v in a.items() if k != "image"})
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    if not rows:
        return ""
    inner = (f'<div class="signal-article-sources">'
             f'<h2 class="signal-column-title">From the archive</h2>'
             '<div class="signal-column-list">'
             + "".join(row_html(r) for r in rows) + '</div></div>')
    # wrap=False when the caller supplies the <aside> itself, because the rail
    # now holds Sources and Further above these rows.
    return ('<aside class="signal-article-rail">' + inner + '</aside>') if wrap else inner



def credit_line(f):
    """Caption, credit and provenance for one image. Credit is not optional
    decoration: an article that shows somebody else's picture says whose it
    is and, where there is one, links the place it came from."""
    bits = []
    if f.get("caption"):
        bits.append(e(f["caption"]))
    if f.get("credit"):
        c = e(f["credit"])
        if f.get("credit_url"):
            c = f'<a href="{e(f["credit_url"])}" target="_blank" rel="noopener">{c}</a>'
        bits.append(f"<b>{c}</b>")
    if f.get("source_url"):
        label = e(f.get("source_label") or "Source")
        bits.append(f'<a href="{e(f["source_url"])}" target="_blank" rel="noopener">{label}</a>')
    if not bits:
        return ""
    return ('<figcaption class="signal-figcap">'
            + '<span class="sep">&middot;</span>'.join(bits) + "</figcaption>")


def figure_html(f, *, full=False):
    """An image block. `fit` is crop (4:3, the site default), wide (16:9) or
    native. Images for Signal's own writing should be self hosted under
    /assets/writing/ rather than hotlinked: a hotlinked picture is one
    publisher's cache rule away from a blank space, which is exactly how the
    19 September hero broke."""
    fit = f.get("fit", "crop")
    cls = "signal-fig" + (" signal-fig--full" if full else "")
    cls += {"crop": " signal-fig--crop", "wide": " signal-fig--wide"}.get(fit, "")
    if f.get("kind") == "plate":
        inner = ('<div class="signal-plate">'
                 + "".join(f'<p class="signal-plate-line">{e(l)}</p>'
                           for l in f.get("lines", []))
                 + (f'<p class="signal-plate-meta">'
                    + "<br>".join(e(m) for m in f.get("meta", [])) + "</p>"
                    if f.get("meta") else "")
                 + "</div>")
    else:
        inner = (f'<img src="{e(f["src"])}" alt="{e(f.get("alt", ""))}" loading="lazy">')
    return f'<figure class="{cls}">{inner}{credit_line(f)}</figure>'

def article_url(a, domain):
    return f"https://{domain}/writing/{a['slug']}/"


def render_article(a, pairs, domain):
    dt = a["_dt"]
    nice = dt.strftime("%B %-d, %Y") if os.name != "nt" else dt.strftime("%B %d, %Y")
    hero = a.get("hero")
    blocks = []
    for b in a.get("body", []):
        if b["type"] == "pull":
            blocks.append(f'<p class="signal-article-pull">{e(b["text"])}</p>')
        elif b["type"] == "figure":
            blocks.append(figure_html(b))
        else:
            blocks.append(f'<p>{e(b["text"])}</p>')

    def cite(items, heading, note=None):
        if not items:
            return ""
        rows = "".join(row_html({"headline": i["title"], "source": i.get("publisher", ""),
                                 "url": i["url"]}) for i in items)
        n = f'<p class="signal-article-note">{e(note)}</p>' if note else ""
        return (f'<div class="signal-article-sources">'
                f'<h2 class="signal-column-title">{heading}</h2>'
                f'<div class="signal-column-list">{rows}</div>{n}</div>')

    note = ""
    if a.get("editorial_note"):
        note = f'<p class="signal-article-note">{e(a["editorial_note"])}</p>'

    topline = ('<div class="signal-article-topline">'
               '<span class="signal-eyebrow"><span class="signal-dot" aria-hidden="true">'
               f'</span>{e(a.get("eyebrow", "Signal"))}</span>'
               f'<span class="signal-article-dateline">By {e(a["byline"])} / '
               f'<b>{e(nice)}</b></span>'
               '</div>')

    left = ('<article class="signal-article">'
            f'<h1 class="signal-article-hed">{e(a["title"])}</h1>'
            f'<p class="signal-article-standfirst">{e(a["standfirst"])}</p>'
            + figure_html(hero)
            + '<div class="signal-article-body">' + "".join(blocks) + '</div>'
            + note + '</article>')

    # Sources and Further moved into the rail on 24 Sep 2026. They are apparatus
    # rather than argument, and they were pushing the end of the piece a long way
    # down the page while the third column sat empty beside it. The rail now
    # carries all three blocks; the archive rows stay last because they are the
    # one thing here no other site could assemble.
    rail = ('<aside class="signal-article-rail">'
            + cite(a.get("sources"), "Sources")
            + cite(a.get("further"), "Further", a.get("further_note"))
            + article_rail(a, pairs, wrap=False)
            + '</aside>')

    body = (topline + '<div class="signal-article-grid">' + left + rail + '</div>')

    url = article_url(a, domain)
    ld = {"@context": "https://schema.org", "@type": "Article",
          "headline": a["title"], "description": a["standfirst"],
          "datePublished": a["date"], "dateModified": a["date"],
          "mainEntityOfPage": {"@type": "WebPage", "@id": url},
          "author": {"@type": "Organization", "name": a["byline"],
                     "url": f"https://{domain}/"},
          "publisher": {"@type": "Organization", "name": "Small Revisions",
                        "url": SHOP_URL},
          "isAccessibleForFree": True}
    hero_src = hero.get("src") if hero.get("kind") != "plate" else None
    # og:image and JSON-LD need an absolute URL; self-hosted heroes are site-relative.
    if hero_src and hero_src.startswith("/"):
        hero_src = f"https://{domain}{hero_src}"
    if hero_src:
        ld["image"] = hero_src

    return page(title=f'{a["title"]} \u00b7 Signal', desc=a["standfirst"],
                canonical=url, body=body, domain=domain, jsonld=ld,
                og_image=hero_src, og_type="article")


def render_writing_index(arts, domain):
    if not arts:
        rows = '<p class="signal-article-note">Nothing here yet.</p>'
    else:
        rows = "".join(
            row_html({"headline": a["title"], "source": a["byline"],
                      "date": a["_dt"].strftime("%b %-d") if os.name != "nt"
                              else a["_dt"].strftime("%b %d"),
                      "url": f"/writing/{a['slug']}/"}, internal=True) for a in arts)
    body = ('<article class="signal-article">'
            '<div class="signal-article-topline">'
            '<span class="signal-eyebrow"><span class="signal-dot" aria-hidden="true">'
            '</span>Signal</span>'
            '<span class="signal-article-dateline">Occasional Pieces Written Here</span>'
            '</div>'
            '<h1 class="signal-article-hed">Writing</h1>'
            '<p class="signal-article-standfirst">Occasional pieces written here '
            'rather than found elsewhere. Everything else on this site is a link '
            'to somebody else\u2019s work.</p>'
            f'<div class="signal-writing-list"><div class="signal-column-list">{rows}</div></div>'
            '</article>')
    return page(title="Writing \u00b7 Signal",
                desc="Occasional pieces written by Signal rather than gathered from elsewhere.",
                canonical=f"https://{domain}/writing/", body=body, domain=domain,
                jsonld={"@context": "https://schema.org", "@type": "CollectionPage",
                        "name": "Signal Writing",
                        "url": f"https://{domain}/writing/"})


def check_signal_pieces(pairs, arts):
    """The limits WRITING.md sets on Signal's own pieces, enforced so they
    cannot drift. A Signal piece is any hero or row whose url is one of our
    /writing/ pages, or whose source is "Signal". The build fails if:
      - it points at no article, or at one not marked issue_eligible;
      - an issue carries more than one;
      - a Signal hero comes within 30 days of the previous Signal hero.
    Without these the paper slowly becomes about itself."""
    by_slug = {a["slug"]: a for a in arts}
    bad, heroes = [], []
    for issue, dt in pairs:
        label = issue.get("dateLabel", str(dt))
        items = [("hero", issue.get("hero") or {})]
        items += [(k, r) for k, rows in issue.get("categories", {}).items() for r in rows]
        mine = []
        for where, it in items:
            url = it.get("url", "")
            src = (it.get("source") or "").strip()
            if not (is_own(url) and "/writing/" in url) and src != "Signal":
                continue
            m = re.search(r"/writing/([^/?#]+)/?", url)
            art = by_slug.get(m.group(1)) if m else None
            if not art:
                bad.append(f"{label}: Signal piece in {where} links to no article: {url or '(no url)'}")
            elif not art.get("issue_eligible"):
                bad.append(f"{label}: '{art['slug']}' is in {where} but not marked issue_eligible")
            mine.append(where)
            if where == "hero":
                heroes.append((dt, label))
        if len(mine) > 1:
            bad.append(f"{label}: {len(mine)} Signal pieces ({', '.join(mine)}); the limit is one per issue")
    heroes.sort()
    for (d1, l1), (d2, l2) in zip(heroes, heroes[1:]):
        if (d2 - d1).days < 30:
            bad.append(f"{l2}: Signal hero only {(d2 - d1).days} days after {l1}; the limit is once a month")
    if bad:
        raise SystemExit("FAILED, Signal's own pieces break the issue limits:\n  - "
                         + "\n  - ".join(bad))


def issue_slugs(pairs):
    """Every article slug an issue actually carries.

    Publication rule, set 24 Sep 2026: a Signal piece goes live only once an
    issue carries it. Writing one is not publishing it. Until an issue runs the
    row, the page does not exist — no /writing/<slug>/, no row on /writing/,
    nothing in the sitemap or the feed — so nothing can be found by a crawler,
    a share or a guessed URL before the paper has actually run it.

    Same detection as check_signal_pieces: a row is ours if its url is one of
    our /writing/ pages, or its source is "Signal".
    """
    out = set()
    for issue, _dt in pairs:
        items = [issue.get("hero") or {}]
        items += [r for rows in issue.get("categories", {}).values() for r in rows]
        for it in items:
            url = it.get("url", "")
            if not (is_own(url) and "/writing/" in url) and (it.get("source") or "").strip() != "Signal":
                continue
            m = re.search(r"/writing/([^/?#]+)/?", url)
            if m:
                out.add(m.group(1))
    return out


def build(data_file, out_dir, domain):
    global SITE_HOST
    SITE_HOST = domain
    data = json.load(open(data_file))
    pairs = sorted(((i, parse_label(i["dateLabel"])) for i in data),
                   key=lambda p: p[1], reverse=True)
    # Checked before anything is written, so a bad issue never half-builds.
    # load_articles() validates every article in the file, published or not, so
    # a piece still waiting for a slot cannot quietly rot; issue_slugs() then
    # decides which of them the site is allowed to publish.
    all_arts = load_articles()
    check_signal_pieces(pairs, all_arts)
    live = issue_slugs(pairs)
    arts = [a for a in all_arts if a["slug"] in live]
    held = [a["slug"] for a in all_arts if a["slug"] not in live]

    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    (out / "issues").mkdir(parents=True)

    for n, (issue, dt) in enumerate(pairs):
        prev = pairs[n + 1][1] if n + 1 < len(pairs) else None
        nxt  = pairs[n - 1][1] if n > 0 else None
        d = out / "issues" / slug(dt)
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(
            render_issue(issue, dt, domain=domain, prev=prev, nxt=nxt), encoding="utf-8")

    total_pages = max(1, -(-len(pairs) // PER_PAGE))
    for n in range(1, total_pages + 1):
        html = render_listing(pairs, n, domain)
        if n == 1:
            (out / "index.html").write_text(html, encoding="utf-8")
        else:
            d = out / "page" / str(n)
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(html, encoding="utf-8")

    if arts:
        (out / "writing").mkdir(exist_ok=True)
        (out / "writing" / "index.html").write_text(
            render_writing_index(arts, domain), encoding="utf-8")
        for a in arts:
            d = out / "writing" / a["slug"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "index.html").write_text(
                render_article(a, pairs, domain), encoding="utf-8")

    for sub, content in (("archive",   render_archive(pairs, domain)),
                         ("about",     render_about(pairs, domain)),
                         ("subscribe", render_subscribe(pairs, domain))):
        (out / sub).mkdir(exist_ok=True)
        (out / sub / "index.html").write_text(content, encoding="utf-8")

    (out / "feed.xml").write_text(render_feed(pairs, domain), encoding="utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(pairs, domain, arts), encoding="utf-8")
    (out / "robots.txt").write_text(render_robots(domain), encoding="utf-8")
    (out / "404.html").write_text(render_404(domain), encoding="utf-8")
    shutil.copyfile(data_file, out / "signal-issues-data.json")
    (out / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")

    # What a new issue actually changes: the home page, the new issue's own
    # page, the issue that just lost the "newest" slot, the archive, the
    # subscribe page's recent list, and every listing page, because the
    # whole run shifts by one. Written for the workflow to post to IndexNow.
    changed = [f"https://{domain}/", f"https://{domain}/archive/",
               f"https://{domain}/subscribe/", f"https://{domain}/feed.xml"]
    changed += [f"https://{domain}/page/{n}/" for n in range(2, total_pages + 1)]
    changed += [f"https://{domain}/issues/{slug(dt)}/" for _, dt in pairs[:2]]
    if arts:
        changed.append(f"https://{domain}/writing/")
        changed += [f"https://{domain}/writing/{a['slug']}/" for a in arts[:3]]
    # Written as the exact POST body, so the workflow only has to send it.
    # The key is public by design in IndexNow, hosted at the root as proof.
    (out / "indexnow.json").write_text(json.dumps({
        "host": domain,
        "key": INDEXNOW_KEY,
        "keyLocation": f"https://{domain}/{INDEXNOW_KEY}.txt",
        "urlList": changed,
    }, indent=2), encoding="utf-8")

    (out / "CNAME").write_text(domain + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    # Ship whatever the repo owns. Dotfiles are skipped so .gitkeep can hold
    # the folder in git without being published.
    if ASSET_DIR.is_dir():
        shutil.copytree(ASSET_DIR, out / "assets", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".*"))
        served = sorted(p.name for p in (out / "assets").iterdir() if p.is_file())
        print("self-hosted assets:", ", ".join(served) if served else "(none)")
    else:
        print("self-hosted assets: NONE - assets/ is missing entirely; "
              "every page will link broken images", file=sys.stderr)

    total = sum(1 + sum(len(v) for v in i["categories"].values()) for i, _ in pairs)
    files = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"built {len(pairs)} issues over {total_pages} pages of {PER_PAGE}, "
          f"{total} pieces, {files} files -> {out}")
    print(f"newest: {pairs[0][0]['dateLabel']}   oldest: {pairs[-1][0]['dateLabel']}")
    # Said out loud every build, because a piece can sit written and unpublished
    # for weeks and the only thing that would otherwise show it is its absence.
    if arts:
        print("writing, live: " + ", ".join(a["slug"] for a in arts))
    if held:
        print("writing, held back until an issue carries them: " + ", ".join(held))
    return pairs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",   default="/root/signal/signal-issues-data.json")
    ap.add_argument("--out",    default="/root/signal/signal-site-build")
    ap.add_argument("--domain", default="signal.smallrevisions.com")
    a = ap.parse_args()
    build(a.data, a.out, a.domain)
