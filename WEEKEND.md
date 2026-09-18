# Building Signal from another computer

For days away from the studio machine. Nothing needs installing — no git, no
GitHub Desktop, no Python. A browser and a GitHub login is the whole kit.

This works because **you only ever change one file.** `site_build.py` runs in
GitHub Actions, not on your machine, so a new issue is a single edit to
`signal-issues-data.json` and nothing else.

---

## What you need

1. **A browser, signed in to GitHub** as the account that owns
   `smallrevisionsrss/signal`. A laptop or iPad is comfortable; a phone works
   but the upload step is fiddly.
2. **Claude**, on whatever device you have.
3. **The editorial files**, so the harvest is judged against the real doctrine
   rather than a summary of it:
   - `harvest-doctrine.md`
   - `category-definitions.md`
   - `sources-full-list.md`

   These live in `signal-editorial`, which is **private** — so Claude cannot
   read them on its own. Attach all three to the chat at the start. They are in
   your OneDrive under `Signal/signal-editorial/`, reachable from OneDrive on
   the web if the machine has no sync.

You do **not** need `signal-issues-data.json`. The `signal` repo is public and
the file is also served at `https://signal.smallrevisions.com/signal-issues-data.json`,
so Claude can pull the current state itself. Give it that URL.

---

## The run

**1. Open a chat and say:**

> Build today's issue. The current data is at
> https://signal.smallrevisions.com/signal-issues-data.json — pull it and
> append to it. Doctrine attached.

Then attach the three editorial files.

**2. Let it harvest and build.** Same rules as any weekday: twenty five pieces,
four per section, one image per category, the rolling source cap across the six
prior issues, and **never ship an issue short**.

**3. Claude hands back a complete `signal-issues-data.json`** — the whole file
with the new issue prepended, not a fragment. Download it.

**4. Upload it to GitHub.**

   - Go to `github.com/smallrevisionsrss/signal`
   - **Add file → Upload files**
   - Drag in the downloaded `signal-issues-data.json`

     A file of the same name replaces the existing one. Do not use the pencil
     icon to edit in place: the file is ~400 KB and pasting it into the web
     editor is miserable and error-prone.
   - Commit message: `Signal, <Month> <day>`
   - **Commit directly to `main`**

**5. Wait two to three minutes.** Actions builds, runs the sanity checks,
deploys, and pings IndexNow. Watch it under the repo's **Actions** tab.

---

## If the build fails

The workflow fails loudly rather than shipping something broken. Under Actions,
open the red run and read the step that failed.

| What you see | What it means |
|---|---|
| `test -f _site/assets/logo.svg` | `assets/` is missing from the repo. Nothing to do with your issue — someone removed the folder. |
| `BAD JSON-LD` | A headline or byline contains a character that broke the structured data. |
| `FAIL: home page is not server-rendered` | The data file is malformed enough that no articles rendered. Usually invalid JSON. |
| `IndexNow rejected the submission` | Deploy succeeded, only the search-engine ping failed. The issue is live. Ignore it. |

Nothing deploys when the build fails, so a bad push leaves yesterday's issue up
rather than breaking the site. You can fix and re-upload.

---

## What you cannot do without the studio machine

- Edit `.github/workflows/deploy.yml` — GitHub blocks workflow changes from
  some clients. Use the web editor on github.com directly if it must change.
- Update the Squarespace blocks. Those are pastes into smallrevisions.com and
  need a real browser session in Squarespace, which is fine from any computer,
  just not something a weekend issue ever requires.

---

## The one thing to get right

The **rolling source cap** — no publication more than twice across the six
prior issues — is the check most likely to slip when you are working from a
different setup, because it depends on reading the six previous issues rather
than on anything in front of you. Claude pulls those from the live data file,
so it has what it needs, but say so explicitly if an issue feels repetitive.
