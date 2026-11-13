# S2: analysing a reference video (only when the user asks)

0.1 support is manual and cheap:

1. Copy the sample into the project: `projects/<p>/reference/` (photos/files the user drops; URLs come later).
2. `nve new <sample> --name ref-<x>` in a scratch project, `nve ingest`, `nve shots` → contact sheets.
3. Look at the sheets and transcript and write `analysis/style_dna.json` in the main project:
   `{"avg_shot_s", "cuts_per_10s", "hook", "text_style", "caption_style", "colour", "music_energy", "structure": [...]}`.
4. Use it to choose template, strategy, shot lengths, stamp density and fonts in the storyboard; mention
   at G1 which choices came from the reference.

Planned for 0.2: an `analyze_ref` engine (candidate: rea-video) that produces this automatically.
