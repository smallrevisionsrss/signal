# Signal's own writing

Articles live in `signal-articles.json` at the repo root, separate from
`signal-issues-data.json` so the issue builder's invariants are untouched.
`site_build.py` picks them up automatically and publishes them at
`/writing/<slug>/`, with an index at `/writing/`. If the file is absent the
build simply skips the whole section.

---

## The page

Settled 24 September 2026 on the Death piece, and it is the template for every
self-written article from here. Nothing about it is per-article; the layout
comes out of `site_build.py` and every piece in `signal-articles.json` gets it.

It uses the site's own three-column grid, `repeat(3, 1fr)`, the same one behind
`.signal-hero-grid` and `.signal-feed-grid`. So the article column and the
picture above it hold **two columns of three** at any screen width, lining up
exactly with the issue pages rather than sitting at some measure of their own.

From the top:

| | |
|---|---|
| **Nav** | Signal wordmark with the red dot, the section underneath, date on the right |
| **Rule** | Full bleed, tight under the nav — the same first rule the issues have |
| **Topline** | Eyebrow and dateline, lifted out of the grid so the rule runs the full width |
| **Headline, standfirst, hero, body** | Columns 1–2, 40px of air on the right |
| **Rail** | Column 3: **Sources**, then **Further**, then **From the archive** |

The rail order matters and was arrived at by moving it: citations sit level with
the top of the piece where they can be read while reading, and the archive rows
sit under them rather than above. Only the rail's column titles carry the
hairline (`--rule-soft`), so the article column stays clean.

Byline is **Small Revisions**, not Signal. No colophon, no "written from
secondary sources" note, no rights boilerplate — those came off on 24 September
and should not come back; anything that needs saying about provenance goes in
`_image_provenance` on the article, which is a record for us, not for the page.

### Checking one before it ships

The built page pulls its pictures from `/assets/`, which only resolves on the
live site, so opening the built file off disk shows the layout with every
picture broken. `make_article_preview.py` inlines them as data URIs and drops
the analytics beacon, giving one file that can be opened anywhere:

```
python3 site_build.py
python3 make_article_preview.py --all        # or: eigengrau
```

---

## Images

**Every article must carry a hero. The build fails without one**, the same way
it fails on a missing asset or bad JSON-LD, rather than shipping a page that
reads as a draft.

Five rules are enforced at build time. Each one raises and stops the build:

| Rule | Why |
|---|---|
| Every article has a `hero` | A piece with no opening image does not look like the rest of the site |
| Every image has `alt` | Accessibility, and it is the only description a screen reader gets |
| No query strings in `src` | Signed and resized proxy URLs expire; the picture goes blank later |
| Any image not under `/assets/` has a `credit` | If it is somebody else's picture, say whose |
| A plate hero has `lines` | An empty plate is a black box |

### Self host what you can

Put article images in `assets/writing/` and reference them as
`/assets/writing/<file>`. Hotlinking is how the 19 September hero broke: the
publisher's host refused a cross origin request and the page showed a gap.
Images under `/assets/` are also exempt from the credit rule, because they are
ours.

### Hero, as a photograph

```json
"hero": {
  "kind": "image",
  "src": "/assets/writing/tryangle-45.jpg",
  "alt": "A seven inch single on the Tryangle label, sleeveless, on a table",
  "caption": "The original pressing, photographed in a collector's kitchen.",
  "credit": "Name of photographer",
  "credit_url": "https://example.com/their-site",
  "source_url": "https://example.com/where-it-came-from",
  "source_label": "Via the Hackney family archive",
  "fit": "crop"
}
```

`fit` is `crop` (4:3, the site default and what every issue image uses), `wide`
(16:9) or `native` (whatever shape the file is). Use `crop` unless there is a
reason not to: it matches the rest of the site.

`caption`, `credit`, `credit_url`, `source_url` and `source_label` are all
optional except `credit`, which is required for anything not self hosted. They
render as one small line under the picture: caption, then the credit in a
slightly stronger grey and linked if `credit_url` is given, then the source
link. Anything omitted is skipped cleanly.

### Hero, as a typographic plate

For a piece whose subject cannot be shown, because the imagery is in copyright
or does not exist. It renders in Signal's own type, on the navy from the
category labels, with the red rule from the masthead.

```json
"hero": {
  "kind": "plate",
  "lines": ["Politicians in My Eyes", "b/w Keep on Knocking"],
  "meta": ["Death · Tryangle Records · Detroit",
           "Self released · Edition of five hundred"],
  "alt": "A typographic plate reading ...",
  "caption": "Signal holds no rights to any photograph of the record.",
  "credit": "Signal"
}
```

**One cost to know about:** a plate cannot be an `og:image`, so the page shares
as a small social card rather than a large one. A real photograph is worth
having for that reason alone.

### Images inside the article

A `figure` block anywhere in `body`, taking exactly the same fields as an image
hero:

```json
{ "type": "figure",
  "src": "/assets/writing/united-sound.jpg",
  "alt": "The control room at United Sound Systems",
  "caption": "United Sound Systems, Detroit.",
  "credit": "Name", "credit_url": "https://…",
  "fit": "wide" }
```

There is no limit on how many. A plate works inline too: give the block
`"kind": "plate"` and `lines`.

---

## The rest of the schema

```json
{
  "slug": "url-segment",
  "title": "…",
  "standfirst": "Two sentences. Renders at 46ch under the headline.",
  "eyebrow": "Signal",
  "category": "sound-vinyl",
  "date": "2026-09-20",
  "byline": "Small Revisions",
  "hero": { … },
  "issue_eligible": false,
  "editorial_note": "Shown in small type at the foot of the page.",
  "body": [ {"type": "p", "text": "…"},
            {"type": "pull", "text": "…"},
            {"type": "figure", …} ],
  "sources": [ {"title": "…", "publisher": "…", "url": "…"} ],
  "further":  [ … ],
  "further_note": "…"
}
```

`category` must be one of the six section keys — `design-arch`, `craft`,
`sound-vinyl`, `collecting`, `archives`, `photo-film` — because it drives the
**From the archive** rail, which pulls five real rows from the issue data in the
same section. That rail is the thing no other site can copy, so the category
should be the one the piece genuinely belongs to.

`sources` and `further` render as Signal rows, so citations look like the paper.

---

## Publication: an issue is what puts a piece live

**Set 24 September 2026. Writing a piece is not publishing it.** A Signal
article goes live only once an issue carries it as a row or as the hero.

`build()` enforces this. It loads and validates every article in the file, then
publishes only the slugs some issue actually references:

- carried by an issue → `/writing/<slug>/` is built, it gets a row on
  `/writing/`, and it enters the sitemap
- not carried → **no page at all.** Not unlinked, not `noindex`: absent. There
  is nothing for a crawler to find, nothing for a guessed URL to hit, and
  nothing to share early by accident

Every build says which is which, so a piece cannot sit forgotten:

```
writing, live: eigengrau
writing, held back until an issue carries them: death-politicians-in-my-eyes
```

Two ways to put a piece in an issue, and the build detects both: give the row
`"url": "/writing/<slug>/"`, or set `"source": "Signal"`. A row pointing at a
slug that does not exist fails the build, so a typo cannot quietly publish
nothing.

This replaces `.gitignore` as the mechanism. Keeping `signal-articles.json` out
of the repo hides everything at once, including a piece that is ready; the gate
is per-article and survives the file being committed.

---

## `issue_eligible`

A flag, not a gate — the gate is the issue itself, above. This records the
editorial judgement so the reason survives the conversation it was made in, and
`check_signal_pieces()` fails the build if an issue carries a piece that was
never marked eligible.

An article is eligible for an issue slot only if it would pass the same tests
Signal applies to everybody else. In practice that means the **circulation
test**: could another outlet have written this from the same press release, or
from the same Wikipedia page? A piece assembled from secondary sources fails,
and running it anyway means Signal publishing in its own paper something it
would reject from any other masthead.

When a piece is eligible, it enters an issue as an ordinary row with the source
`Signal`, so dedup, source uniqueness and the rolling cap all keep working
unchanged. Two further limits, which nothing enforces and which matter:

- **No more than one Signal piece per issue.**
- **Never the hero more than once a month.**

Without them the paper slowly becomes about itself, which is the exact thing the
rolling cap exists to prevent for every other publication on the list.
