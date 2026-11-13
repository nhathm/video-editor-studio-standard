# Cut strategies

The strategy is chosen at S3 (plan) and only executed at S5. `nve ingest` measures the speech ratio and
suggests one (`analysis/ingest.json` → `suggested_strategy`). If it disagrees with the template, say so
at G1 and ask ("video này gần như không có lời, mình đề xuất cắt theo hình").

| id | Vietnamese label | use when | how you choose what to keep |
|---|---|---|---|
| `speech` | theo lời nói | speech ≥ ~60 %: talking head, interview, review | `nve plan draft` keeps runs of words (splits on silence > 0.45 s, fillers count as silence). Then YOU read `storyboard.md`/the transcript and remove false starts (`--`), retakes (keep the last good take), repeated sentences; reorder if the real hook comes late. |
| `visual` | theo hình | little or no speech: product ads (pouring, holding, close-ups), everyday clips | `nve shots <p>` splits sources into shots and writes `analysis/shots_sheet_N.jpg` (3 frames per shot + sharpness/light/motion, flags: blurry, dark, overexposed, static). LOOK at every sheet. Pick the strongest 1.2–3 s moments, order them hook → reveal → benefits → CTA. The draft picks are only a starting point. |
| `beat` | theo nhịp nhạc | music-led montage | (0.2) like visual, cut points on music beats. For now: visual + choose shot lengths in multiples of the beat by ear. |
| `hybrid` | kết hợp | vlog: talking parts + b-roll | speech ranges for talking sources, visual picks for b-roll sources, interleaved in `tracks.video`. |

Photos are sources too (`kind: image`): each range `{"src": "c", "in": 0, "out": 2.5}` shows the photo for
2.5 s (cover-cropped to the frame).
