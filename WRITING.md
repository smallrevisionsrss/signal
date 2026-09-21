# Signal's own writing

Articles live in `signal-articles.json` at the repo root, separate from
`signal-issues-data.json` so the issue builder's invariants are untouched.
`site_build.py` picks them up automatically and publishes them at
`/writing/<slug>/`, with an index at `/writing/`. If the file is absent the
build simply skips the whole section.

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
  "byline": "Signal",
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

## `issue_eligible`

A flag, not a gate. Nothing in the build reads it; it records an editorial
judgement so the reason survives the conversation it was made in.

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
