# Setup

Five steps. No paid services, no API keys beyond a Telegram bot.

## 1. Make it yours

The scoring profile is the only thing you must change. It lives in one place —
the **Score vs Profile** node inside `jobs-radar.workflow.json` (and its source of
truth, `build_workflow.py`).

Everything from `TITLE_LEAD` down to the language penalties is configuration:

| What | Change it to |
|---|---|
| `TITLE_LEAD` / `TITLE_SENIOR` / `TITLE_BASE` | the titles at, above and below your level |
| `TITLE_AI`, `TITLE_PLATFORM`, `TITLE_KW` | the topics you want weighted in the title |
| `KW` | description keywords that map to real evidence on your CV |
| `TITLE_BLOCK` | title shapes to reject outright (junior, engineering, sales…) |
| `EU_WORD`, the Spain bonus, `-hybrid` / `-onsite` penalties | your geography and work-arrangement preferences |
| the language gates | languages you do **not** work in |

Ship the defaults and you will get one particular person's shortlist. That is the
point of changing them.

## 2. Pick your sources

The **Build Source List** node holds ~119 boards grouped by ATS. Add or remove
freely — the fetch step is deliberately non-fatal, so a dead board costs nothing
but a line in the health report. `README.md` explains how to find the id for each
ATS, including Getro's VC-portfolio boards.

## 3. Create a Telegram bot

Talk to `@BotFather`, create a bot, take the token. Send it a message, then read
your chat id from `https://api.telegram.org/bot<TOKEN>/getUpdates`.

## 4. Add the secrets

In the repo: **Settings → Secrets and variables → Actions**, add `TELEGRAM_TOKEN`
and `TELEGRAM_CHAT_ID`. They are never read from the code.

## 5. Run it

```bash
DRY_RUN=1 node radar.mjs          # score and print locally, send nothing
gh workflow run radar.yml -f dry_run=true
```

The scheduled workflow runs every 4 hours and commits `seen.json`, `status.json`
and `STATUS.md` back to the repo, so dedup state and board health are readable
without opening a log.

## Ad-hoc shortlist

`hunt.mjs` runs the same pipeline once and prints a ranked shortlist with URLs,
filtered to roles you can actually take. Seed `DONE_COMPANIES` with companies you
have already applied to or ruled out, and `EU_OK` with the geographies that work
for you.

```bash
node hunt.mjs
```
