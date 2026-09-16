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
/* Tokens taken verbatim from Small Revisions' own .signal-editorial
   block so this site and smallrevisions.com/rsssignal are the same
   publication rather than cousins. */
:root{
  --bg:#f9f7f0;
  --ink:#111111;
  --ink-soft:#4c4c4c;
  --ink-faint:#8f8f8c;
  --rule:#111111;
  --rule-soft:#dedcd6;
  --signal:#ff3b2f;
  --dot:#fa4616;
  --cat:#152035;
  --serif:'Instrument Serif', Georgia, 'Times New Roman', serif;
  --sans:'Instrument Sans','Helvetica Neue',Arial,sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.55;
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
}
a{color:inherit; text-decoration:none}
img{max-width:100%}
:focus-visible{outline:2px solid var(--signal); outline-offset:3px}
.container{max-width:1440px; margin:0 auto; padding:0 24px}

.label{font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase}

/* announcement bar ----------------------------------------------- */
.announce{background:var(--ink); border-bottom:1px solid var(--ink)}
.announce .row{display:flex; align-items:center; justify-content:center; padding:10px 40px; text-align:center}
.announce p{font-size:13px; color:rgba(249,247,240,.7); margin:0}
.announce a{font-weight:700; color:var(--bg); border-bottom:1px solid var(--bg); padding-bottom:1px}
.announce a:hover{color:var(--signal); border-color:var(--signal)}

/* masthead ------------------------------------------------------- */
.mastrow .inner{display:flex; align-items:center; gap:24px; padding:20px 0}
.logo{display:block; flex:none; transition:opacity .15s ease}
.logo:hover{opacity:.6}
.logo img{display:block; height:63px; width:auto}
.navwrap{display:flex; align-items:center; justify-content:space-between; gap:24px; flex:1; min-width:0}
.nav{display:flex; align-items:center; gap:20px; min-width:0}
.nav a{
  font-size:14px; font-weight:600; letter-spacing:.01em; color:var(--ink);
  padding:6px 0; border-bottom:2px solid transparent; white-space:nowrap;
  transition:color .15s ease, border-color .15s ease;
}
.nav a.navsub{font-size:13px; color:var(--ink-faint)}
.nav a.navsub:hover{color:var(--ink)}
.nav a[aria-current]{border-color:var(--dot)}
.nav a.navsub[aria-current]{color:var(--cat); border-color:var(--dot)}
.actions{display:flex; align-items:center; gap:22px; flex:none}
.actions a{font-size:13px; font-weight:600; color:var(--ink-faint)}
.actions a:hover{color:var(--signal)}

/* issue line ----------------------------------------------------- */
.issueline{padding:30px 0 26px}
.issueline .inner{display:flex; flex-wrap:wrap; gap:10px 24px; align-items:baseline}
.mark{display:flex; align-items:center; gap:8px}
.dot{width:8px; height:8px; border-radius:50%; background:var(--dot); display:block; flex:none}
.issueline .right{margin-left:auto; font-size:13px; color:var(--ink-faint)}
.issueline .right b{font-weight:600; color:var(--ink)}
.issueline .paging{display:flex; gap:18px; font-size:13px}
.issueline .paging a{color:var(--ink-faint)}
.issueline .paging a:hover{color:var(--signal)}

/* editor note ---------------------------------------------------- */
.note{max-width:74ch; margin:0 0 40px; padding:18px 22px; border:1px solid var(--rule-soft)}
.note h2{margin:0 0 7px; color:var(--ink-faint)}
.note p{margin:0; font-size:15.5px; color:var(--ink-soft)}

/* hero ----------------------------------------------------------- */
.hero{display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.85fr); gap:36px; align-items:start; padding-bottom:52px}
.hero.noimg{grid-template-columns:1fr}
.hero .kicker{color:var(--ink-faint); margin:0 0 16px}
.hero h1{
  font-family:var(--serif); font-weight:400;
  font-size:clamp(2rem,1.3rem+2.3vw,2.9rem); line-height:1.1;
  letter-spacing:-.01em; margin:0 0 20px;
}
.hero h1 a:hover{color:var(--signal)}
.hero .dek{font-size:16px; line-height:1.62; color:var(--ink-soft); margin:0 0 22px}
.hero .read{display:inline-block; font-size:13.5px; font-weight:700; border-bottom:1.5px solid var(--ink); padding-bottom:2px}
.hero .read:hover{color:var(--signal); border-bottom-color:var(--signal)}
.hero .byline{font-size:12.5px; color:var(--ink-faint); margin:0}
.hero .foot{display:flex; flex-wrap:wrap; gap:8px 18px; align-items:baseline}
.hero figure{margin:0; position:relative}
.hero figure img{width:100%; height:auto; display:block; border:1px solid var(--rule-soft)}
.hero figcaption{position:absolute; right:14px; bottom:14px; background:rgba(17,17,17,.8); color:var(--bg); font-size:11.5px; padding:5px 9px}

/* columns -------------------------------------------------------- */
.cols{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:46px 34px}
.colhead{display:flex; align-items:center; gap:8px; padding-bottom:9px; border-bottom:1px solid var(--rule)}
.colhead svg{width:15px; height:15px; flex:none; stroke:var(--ink); fill:none; stroke-width:1.25; stroke-linecap:round; stroke-linejoin:round}
ol.items{list-style:none; margin:0; padding:0}
ol.items li{padding:18px 0; border-bottom:1px solid var(--rule-soft)}
ol.items li:last-child{border-bottom:0}
.items figure{margin:0 0 14px}
.items img{width:100%; height:auto; display:block; border:1px solid var(--rule-soft)}
.items h3{font-family:var(--serif); font-weight:400; font-size:1.2rem; line-height:1.25; margin:0 0 8px}
.items h3 a:hover{color:var(--signal)}
.arw{font-size:.68em; vertical-align:.34em; color:var(--ink-faint); margin-left:.2em}
.items h3 a:hover .arw{color:var(--signal)}
.items .meta{font-size:12.5px; color:var(--ink-faint); margin:0; display:flex; flex-wrap:wrap; gap:6px; align-items:center}
.items .meta .src{color:var(--ink-soft)}
.ever{font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--signal); border:1px solid var(--signal); padding:1px 5px}

/* archive -------------------------------------------------------- */
.arch{list-style:none; margin:0; padding:0; max-width:900px}
.arch li{border-bottom:1px solid var(--rule-soft)}
.arch a{display:flex; flex-wrap:wrap; gap:6px 20px; align-items:baseline; padding:16px 2px}
.arch .d{font-family:var(--serif); font-size:1.2rem; min-width:11em}
.arch .h{color:var(--ink-faint); font-size:14px; flex:1 1 280px}
.arch a:hover .d{color:var(--signal)}

/* prose ---------------------------------------------------------- */
.prose{max-width:68ch}
.prose h1{font-family:var(--serif); font-weight:400; font-size:2.4rem; line-height:1.12; letter-spacing:-.01em; margin:0 0 10px}
.prose h2{font-family:var(--serif); font-weight:400; font-size:1.5rem; margin:36px 0 10px}
.prose p,.prose li{font-size:16px; line-height:1.62; color:var(--ink-soft)}
.prose strong{color:var(--ink); font-weight:600}
.prose a{color:var(--signal); border-bottom:1px solid var(--signal)}
.prose ul{padding-left:20px}

/* subscribe + footer --------------------------------------------- */
.sub{margin:56px 0 0; padding-top:28px; border-top:1px solid var(--rule)}
.sub h2{font-family:var(--serif); font-weight:400; font-size:1.5rem; margin:0 0 7px}
.sub p{color:var(--ink-soft); font-size:14.5px; margin:0 0 16px; max-width:58ch}
.btn{display:inline-block; border:1px solid var(--ink); color:var(--ink); padding:9px 17px; font-size:12px; font-weight:700; letter-spacing:.06em; text-transform:uppercase}
.btn:hover{background:var(--ink); color:var(--bg)}
footer{margin-top:64px; border-top:1px solid var(--rule-soft); padding:20px 0 64px; color:var(--ink-faint); font-size:12.5px}
footer .inner{display:flex; flex-wrap:wrap; gap:8px 22px; align-items:baseline}
footer a:hover{color:var(--ink)}

@media (max-width:1100px){
  .cols{grid-template-columns:repeat(2,minmax(0,1fr))}
  .hero{grid-template-columns:1fr; gap:24px}
  .hero figure{order:-1}
}
@media (max-width:760px){
  .announce .row{padding:10px 24px}
  .announce p{font-size:12px}
  .logo img{height:51.61px}
  .mastrow .inner{flex-wrap:wrap; gap:14px}
  .navwrap{flex-wrap:wrap}
  .nav{flex-wrap:wrap; gap:14px}
  .cols{grid-template-columns:1fr; gap:36px}
  .issueline .right{margin-left:0; width:100%}
}
"""

# ---------------------------------------------------------------- shell

LOGO = ("https://raw.githubusercontent.com/smallrevisionsrss/srrss/"
        "refs/heads/main/Small%20Revisions%20-%20Dymo%20Label%20-%20Knockout%20-%20Black.svg")

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

# Publisher images are hotlinked and some hosts refuse cross-origin
# requests. Drop a refused figure rather than show a broken box.
# Progressive enhancement only: every headline, source and link is
# already in the served HTML.
IMG_FALLBACK_JS = """
<script>
function signalDropImage(i){
  var f = i.closest('figure') || i;
  f.style.display = 'none';
  var hero = i.closest('.hero');
  if (hero) { hero.classList.add('noimg'); }
}
document.querySelectorAll('img').forEach(function(i){
  i.addEventListener('error', function(){ signalDropImage(i); });
  if (i.complete && i.naturalWidth === 0) { signalDropImage(i); }
});
</script>
"""


def page(*, title, desc, canonical, body, domain, jsonld=None,
         og_image=None, og_type="website", prev_url=None, next_url=None,
         nav_current=None, issueline=""):
    base = f"https://{domain}"
    head = [
        '<!doctype html>', '<html lang="en">', '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f'<title>{e(title)}</title>',
        f'<meta name="description" content="{e(desc)}">',
        f'<link rel="canonical" href="{e(canonical)}">',
        '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">',
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
        f'<style>{CSS}</style>',
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

    mast = f"""<div class="announce"><div class="container"><div class="row">
<p>A curated selection of design, art &amp; culture. <a href="{SHOP_URL}/all">Order now</a></p>
</div></div></div>
<header class="mastrow"><div class="container"><div class="inner">
<a class="logo" href="/"><img src="{LOGO}" alt="{e(PUBLISHER)}" width="220" height="63"></a>
<div class="navwrap">
<nav class="nav" aria-label="Main">
{nav(SHOP_URL + '/all', 'Shop', 'shop')}{nav('/', 'RSS / Signal', 'today')}{nav('/archive/', 'Archive', 'archive', True)}{nav('/about/', 'About', 'about', True)}
</nav>
<div class="actions"><a href="/feed.xml">RSS</a></div>
</div>
</div></div></header>
{issueline}"""

    foot = f"""<footer><div class="container"><div class="inner">
<span>{e(SITE_NAME)}, published by <a href="{SHOP_URL}">{e(PUBLISHER)}</a>.</span>
<span><a href="/feed.xml">RSS feed</a></span>
<span><a href="/archive/">Archive</a></span>
<span><a href="/about/">About</a></span>
</div></div></footer>""" + IMG_FALLBACK_JS + "</body></html>"

    return ("\n".join(head) + mast
            + '<main class="container">' + body + "</main>" + foot)

# ---------------------------------------------------------------- blocks

def issue_line(issue, *, paging="", running=True):
    right = (f'<div class="right">A Running Record of Findings from the Internet '
             f'/ <b>{e(issue["dateLabel"])}</b></div>') if running else ""
    return (f'<div class="issueline"><div class="container"><div class="inner">'
            f'<span class="mark"><span class="dot"></span>'
            f'<span class="label">RSS / Signal</span></span>'
            f'{right}{paging}</div></div></div>')

def hero_block(issue):
    h = issue["hero"]
    lab = KEY_TO_LABEL.get(h.get("category"), "")
    img = ""
    if h.get("image"):
        cap = f'<figcaption>{e(h["caption"])}</figcaption>' if h.get("caption") else ""
        img = (f'<figure><a href="{e(h["url"])}" rel="noopener"><img src="{e(h["image"])}" '
               f'alt="{e(h.get("caption") or h["headline"])}" loading="eager"></a>{cap}</figure>')
    return f"""<div class="hero"><div>
<h1><a href="{e(h['url'])}" rel="noopener">{e(h['headline'])}</a></h1>
<p class="dek">{e(h.get('dek',''))}</p>
<div class="foot">
<a class="read" href="{e(h['url'])}" rel="noopener">Read the story {ARROW}</a>
<p class="byline">{e(h.get('byline',''))}</p>
</div>
</div>{img}</div>"""

def sections_block(issue):
    out = ['<div class="cols">']
    for label, key in SECTIONS:
        arts = issue["categories"].get(key, [])
        if not arts:
            continue
        out.append(f'<section><div class="colhead">{GLYPHS.get(key,"")}'
                   f'<span class="label">{e(label)}</span></div><ol class="items">')
        for a in arts:
            img = (f'<figure><a href="{e(a["url"])}" rel="noopener"><img src="{e(a["image"])}" '
                   f'alt="{e(a["headline"])}" loading="lazy"></a></figure>') if a.get("image") else ""
            ever = '<span class="ever">Evergreen</span>' if a.get("evergreen") else ""
            date = f'<span>&middot;</span><span>{e(a["date"])}</span>' if a.get("date") else ""
            out.append(
                f'<li>{img}<h3><a href="{e(a["url"])}" rel="noopener">{e(a["headline"])}'
                f'{ARROW}</a></h3>'
                f'<p class="meta"><span class="src">{e(a["source"])}</span>{date}{ever}</p></li>')
        out.append("</ol></section>")
    out.append("</div>")
    return "".join(out)

def subscribe_block(domain):
    return f"""<div class="sub">
<h2>Follow Signal</h2>
<p>A new issue every day. The feed carries each issue in full, so nothing is held back for the site.</p>
<a class="btn" href="https://{domain}/feed.xml">Subscribe by RSS</a>
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
    if nxt: paging.append(f'<a href="/issues/{slug(nxt)}/" rel="next">Next issue</a>')
    if prev: paging.append(f'<a href="/issues/{slug(prev)}/" rel="prev">Previous issue</a>')
    if as_index: paging.append('<a href="/archive/">All issues</a>')
    pag = f'<div class="paging">{"".join(paging)}</div>' if paging else ""

    note = ""
    if issue.get("note"):
        note = f'<div class="note"><h2>From the editor</h2><p>{e(issue["note"])}</p></div>'

    body = note + hero_block(issue) + sections_block(issue) + subscribe_block(domain)

    return page(
        title=(f"Signal &middot; {issue['dateLabel']}" if not as_index
               else f"Signal, a daily edit from Small Revisions"),
        desc=desc if not as_index else DESCRIPTION,
        canonical=url if not as_index else f"https://{domain}/",
        body=body, domain=domain, og_type="article",
        og_image=h.get("image"),
        jsonld=issue_jsonld(issue, dt, url, domain),
        prev_url=(f"https://{domain}/issues/{slug(prev)}/" if prev else None),
        next_url=(f"https://{domain}/issues/{slug(nxt)}/" if nxt else None),
        nav_current="today",
        issueline=issue_line(issue, paging=pag),
    )

def render_archive(pairs, domain):
    rows = []
    for issue, dt in pairs:
        rows.append(f'<li><a href="/issues/{slug(dt)}/"><span class="d">{e(issue["dateLabel"])}</span>'
                    f'<span class="h">{e(trim(issue["hero"]["headline"], 90))}</span></a></li>')
    total = sum(1 + sum(len(v) for v in i["categories"].values()) for i, _ in pairs)
    body = (f'<div class="prose"><h1>Archive</h1>'
            f'<p>{len(pairs)} issues, {total} pieces, newest first.</p></div>'
            f'<ul class="arch">{"".join(rows)}</ul>')
    return page(title="Signal archive, every issue",
                desc=f"Every issue of Signal. {len(pairs)} daily editions, {total} pieces of writing "
                     f"on design, art, sound, collecting, history and film.",
                canonical=f"https://{domain}/archive/", body=body, domain=domain,
                nav_current="archive",
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
                nav_current="about",
                jsonld={"@context": "https://schema.org", "@type": "AboutPage",
                        "name": "About Signal", "url": f"https://{domain}/about/",
                        "publisher": {"@type": "Organization", "name": PUBLISHER, "url": SHOP_URL}})

# ---------------------------------------------------------------- feeds

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

def render_sitemap(pairs, domain):
    base = f"https://{domain}"
    urls = [(f"{base}/", pairs[0][1], "daily", "1.0"),
            (f"{base}/archive/", pairs[0][1], "daily", "0.7"),
            (f"{base}/about/", pairs[0][1], "monthly", "0.6")]
    urls += [(f"{base}/issues/{slug(dt)}/", dt, "yearly", "0.8") for _, dt in pairs]
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

def build(data_file, out_dir, domain):
    data = json.load(open(data_file))
    pairs = sorted(((i, parse_label(i["dateLabel"])) for i in data),
                   key=lambda p: p[1], reverse=True)

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

    top, topdt = pairs[0]
    (out / "index.html").write_text(
        render_issue(top, topdt, domain=domain,
                     prev=pairs[1][1] if len(pairs) > 1 else None, as_index=True),
        encoding="utf-8")

    for sub, content in (("archive", render_archive(pairs, domain)),
                         ("about",   render_about(pairs, domain))):
        (out / sub).mkdir(exist_ok=True)
        (out / sub / "index.html").write_text(content, encoding="utf-8")

    (out / "feed.xml").write_text(render_feed(pairs, domain), encoding="utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(pairs, domain), encoding="utf-8")
    (out / "robots.txt").write_text(render_robots(domain), encoding="utf-8")
    (out / "404.html").write_text(render_404(domain), encoding="utf-8")
    (out / "CNAME").write_text(domain + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    total = sum(1 + sum(len(v) for v in i["categories"].values()) for i, _ in pairs)
    files = sum(1 for _ in out.rglob("*") if _.is_file())
    print(f"built {len(pairs)} issues, {total} pieces, {files} files -> {out}")
    print(f"newest: {pairs[0][0]['dateLabel']}   oldest: {pairs[-1][0]['dateLabel']}")
    return pairs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",   default="/root/signal/signal-issues-data.json")
    ap.add_argument("--out",    default="/root/signal/signal-site-build")
    ap.add_argument("--domain", default="signal.smallrevisions.com")
    a = ap.parse_args()
    build(a.data, a.out, a.domain)
