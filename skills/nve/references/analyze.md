# S2: taking the style of a sample video

When the user shows a sample video and wants theirs "in this style", learn its **design language** (fonts,
colours, text treatments, motion, pace, music mood) and apply it to the user's own footage and words. Never
copy the sample's footage, music, words or scene order.

If `<install>/pro/skills/reference-style.md` exists, follow it instead (it has tools for this). Otherwise do
it by hand, and never tell the user about tools this install does not have:

1. Ask for the video file (send the file; do not try to download links).
2. `nve new <sample> --name "ref <x>"` (a scratch project), `nve ingest`, `nve shots` → contact sheets.
3. Look at the sheets: for each kind of text, the font look (condensed / geometric / serif…), weight, case,
   size, colours, outline / glow / box, position, how it enters; the palette, cut pace, framing and light, and
   whether there is music and how many sound effects.
4. Tell the user in 2–3 plain lines what you took from it, then set the user's storyboard `style` (fonts from
   the pack, palette, caption props, look), speed and music to match, and plan the overlays in that style.
5. Delete the scratch project folder (`projects/<ref project>`) when done: the sample is not kept.
