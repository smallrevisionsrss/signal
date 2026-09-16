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
[hidden]{display:none !important}
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
  padding:6px 0; font-size:14px; font-family:inherit; color:var(--ink);
  text-align:right; transition:border-color .15s ease;
}
.mainnav-search-input::placeholder{color:var(--ink-faint)}
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
    return f"""<div class="mainnav-fixed" id="mainnav-fixed">
<div class="mainnav-announce" id="mainnav-announce"><div class="container">
<div class="mainnav-announce-row">
<p class="mainnav-announce-text">A curated selection of design, art &amp; culture. <a href="{SHOP_URL}/all">Order now</a></p>
<button type="button" class="mainnav-announce-close" id="mainnav-announce-close" aria-label="Dismiss announcement">&times;</button>
</div></div></div>
<div class="mainnav-row"><div class="container"><div class="mainnav-inner">
<a class="mainnav-logo" href="/"><img src="{LOGO}" alt="{e(PUBLISHER)}" width="220" height="63"></a>
<div class="mainnav-bottom-row">
<nav class="mainnav-links" id="mainnav-links" aria-label="Main">
<a class="mainnav-toplink" href="{SHOP_URL}/all">Shop</a>
<button type="button" class="mainnav-toplink" data-group="scroll" aria-expanded="false">RSS / Signal</button>
<div class="mainnav-rollout" id="scroll-rollout" role="tablist" aria-label="Filter stories by section">
<div class="mainnav-rollout-inner">{tabs}</div>
</div>
<a class="mainnav-toplink" href="/archive/">Archive</a>
<a class="mainnav-toplink" href="/about/">About</a>
</nav>
<div class="mainnav-actions">
<div class="mainnav-search">
<input type="search" class="mainnav-search-input" id="search-input" placeholder="Search" aria-label="Search" autocomplete="off">
<div class="search-dropdown" id="search-dropdown" role="listbox" aria-label="Search results"></div>
</div>
<a class="mainnav-icon-btn cart" href="{SHOP_URL}/cart" aria-label="Cart">{CART_SVG}<span class="mainnav-cart-count">0</span></a>
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
    var hero = document.querySelector('.hero');
    var cols = document.querySelector('.cols');
    var line = document.querySelector('.issueline');
    if(hero) hero.hidden = !v;
    if(cols) cols.hidden = !v;
    if(line) line.hidden = !v;
  }

  function renderMerged(key){
    if(!mergedWrap) return;
    loadData(function(issues){
      var rows = [];
      issues.forEach(function(iss){
        (iss.categories && iss.categories[key] || []).forEach(function(a){
          rows.push({issue: iss.dateLabel, a: a});
        });
      });
      var per = Math.ceil(rows.length / 3) || 1;
      var html = '';
      for(var c = 0; c < 3; c++){
        html += '<ol>';
        rows.slice(c*per, (c+1)*per).forEach(function(r){
          var a = r.a;
          html += '<li><p class="merged-issue">' + esc(r.issue) + '</p>' +
            '<h3><a href="' + esc(a.url) + '" rel="noopener">' + esc(a.headline) +
            '<span class="arw" aria-hidden="true">&#8599;</span></a></h3>' +
            '<p class="meta"><span class="src">' + esc(a.source) + '</span>' +
            (a.date ? '<span>&middot;</span><span>' + esc(a.date) + '</span>' : '') + '</p></li>';
        });
        html += '</ol>';
      }
      mergedHead.innerHTML = '<span class="label">' + esc(LABELS[key] || '') + '</span>' +
        '<span class="count">' + rows.length + ' pieces across ' + issues.length + ' issues</span>';
      mergedGrid.className = 'merged-grid items';
      mergedGrid.innerHTML = html;
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
    if(new URLSearchParams(window.location.search).get('open') === 'scroll'){
      openRollout();
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



def nav_js():
    labels = {"all": "All"}
    labels.update({k: lab for lab, k in SECTIONS})
    return NAV_JS.replace("__LABELS__", json.dumps(labels, ensure_ascii=False))

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
<a class="signal-footer-logo" href="/"><img src="{LOGO}" alt="{e(PUBLISHER)}" width="220" height="63"></a>
<nav class="signal-footer-links" aria-label="Footer">
<a href="{SHOP_URL}/all" class="signal-footer-jump">Shop</a>
<a href="#" class="signal-footer-jump" data-jump="scroll">RSS / Signal</a>
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
        f'<style>{CSS}{NAV_CSS}{FOOTER_CSS}</style>',
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

    mast = nav_html(domain) + issueline

    foot = footer_html(domain) + IMG_FALLBACK_JS + nav_js() + FOOTER_JS + "</body></html>"

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

    merged = ('<div id="merged-wrap" hidden><section class="merged-feed">'
              '<div class="merged-head" id="merged-head"></div>'
              '<div class="merged-grid" id="merged-grid"></div></section></div>') if as_index else ""
    body = note + hero_block(issue) + sections_block(issue) + merged + subscribe_block(domain)

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
    shutil.copyfile(data_file, out / "signal-issues-data.json")
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
