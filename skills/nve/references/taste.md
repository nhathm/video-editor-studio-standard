# Taste log (every correction is taste)

The user's corrections are kept as rules in `<workspace>/taste.json`, so the next video starts the way they
like it. Taste is a prior: `storyboard.json` always wins, but say so when you break a rule on purpose.

## Read it before planning (S3)

`nve taste prompt --template <id>` lists the active rules: `you said` = the user's own words, `skill rule` =
learned by you. `nve plan draft` already fills the `set` values and SFX bans into the new storyboard (its
`notes` say which). Plan the rest with them; skip style questions the taste already answers.

`nve plan refresh` and `nve preview` return `taste_warnings`: fix each one in the storyboard, or tell the user
in one line why it stays (e.g. they asked for more stamps this time).

## Record every correction

When the user corrects an edit decision ("chữ nhỏ quá", "nhiều stamp quá", "tiếng ting sến", "nhạc to"),
fix the video **and** record it, in their words, in their language:

```bash
nve taste add "<what they said>" [--set style.caption.size=0.07] [--max stamps_per_min=5]
              [--ban-sfx ting] [--ban-bgm acoustic-01] [--template core:talking-head] [--project <p>]
```

- `--set` (repeatable): a default for `output.*` or `style.*` (JSON value), e.g. `output.speed=1.0`,
  `style.look="none"`, `style.skin=false`, `style.caption.size=0.07`, `style.palette.accent="#FF5A5F"`.
- `--max` / `--min` (repeatable) on a metric measured from the storyboard: `duration`, `speed`,
  `stamps_per_min`, `cards_per_min`, `overlays_per_min`, `emoji_per_min`, `sfx_per_min` (block sounds
  included), `bgm_volume`, `caption_words_max`. `nve taste metrics <p>` shows the current values.
- `--ban-sfx` / `--ban-bgm`: never these sounds/tracks (names from `nve assets list`). Banned SFX go into
  `style.ban_sfx`, so block default sounds skip them too.
- `--template`: only when the remark is about that kind of video ("for product ads, no captions").
- `--from skill`: a rule you learned yourself (not the user's words). Only the user's own feedback is `user`.
- A remark with no machine part is still worth recording: it shows up in `taste prompt`.

Confirm to the user in one short line that you'll remember it. One-off wishes for this video only
("this time without music") are not taste: just change the storyboard.

## Manage

`nve taste list [--all]`, `nve taste forget <id>` (the user changed their mind), `nve taste restore <id>`.
When a new remark contradicts an old rule, forget the old one and add the new one.

## Cloud (claude.ai)

The sandbox starts empty in every thread, so the taste lives only in this chat. When the user has rules and
the video is delivered, give them `nve taste export` as a short block to paste at the start of their next
chat (or into their claude.ai project instructions). When a chat starts with such a block, write it to a file
and run `nve taste import <file>` before planning.
