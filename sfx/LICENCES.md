# SFX Palette — Licence Record

Every file in this directory is either (a) synthesized in-house (original, no
encumbrance), or (b) a real recording whose licence was verified on its
Wikimedia Commons file page via the Commons API (`extmetadata`) before
download. Only CC0 / CC-BY / Public-domain sources are used. CC BY-SA
candidates were found and **excluded** (e.g. "Sound of rain" by Effib,
CC BY-SA 3.0; "Canon T50 shutter noise", CC BY-SA 3.0).

All files: WAV, 48 kHz. One-shots are mono; ambience beds keep the source's
stereo image where the source was stereo. Ambience downloads are 15 s
excerpts (in/out points noted), loudness-normalised to −24 LUFS beds with
0.4 s edge fades.

## Synthesized in-house — original, no encumbrance

Generated with ffmpeg (`aevalsrc` chirps / filtered noise / envelopes).
Author for all rows in this section: Julie project (in-house synthesis).
Source URL: n/a — original synthesis, 2026-11-16. Licence: original work,
no encumbrance.

| Filename | Title |
|---|---|
| boom.wav | Boom (pre-existing in repo; resampled 44.1→48 kHz) |
| click.wav | Click (pre-existing in repo) |
| ding.wav | Ding (pre-existing in repo; resampled 44.1→48 kHz) |
| hit.wav | Hit (pre-existing in repo; resampled 44.1→48 kHz) |
| pop.wav | Pop (pre-existing in repo; resampled 44.1→48 kHz) |
| riser.wav | Riser (pre-existing in repo; resampled 44.1→48 kHz) |
| typing.wav | Typing tick (pre-existing in repo) |
| whoosh.wav | Whoosh (pre-existing in repo) |
| tr_whoosh_fast.wav | Fast whoosh (band-passed pink noise, 0.35 s) |
| tr_swoosh_soft.wav | Soft swoosh (low-passed pink noise, 0.8 s) |
| tr_whoosh_deep.wav | Deep whoosh (brown noise, low-passed, 0.9 s) |
| tr_riser_reverse.wav | Reverse riser (chirp 300→2600 Hz, 1.4 s) |
| hit_impact.wav | Impact (chirp drop 150→40 Hz + noise thump) |
| hit_braam_lite.wav | Braam-lite (detuned 55/58.3 Hz harmonic stack, 1.6 s) |
| hit_sub_drop.wav | Sub drop (chirp 95→28 Hz, 0.9 s) |
| ui_shutter.wav | Camera shutter (two gated noise clicks) |
| ui_click_double.wav | UI double click (two 1800 Hz ticks) |
| fol_paper_swish.wav | Paper swish (band-passed pink noise) |
| fol_page_turn.wav | Page turn (two-stage noise swish) |
| fol_footsteps.wav | Footsteps ×4 (sine thumps + noise scuff) |
| fol_door_close.wav | Door close (swing swish + thud) |
| fol_keys_jingle.wav | Keys jingle (4.2/5.3/6.1 kHz ping cluster) |
| punc_notification.wav | Notification chime (E6→A6 two-tone) |
| punc_scratch_lite.wav | Record scratch-lite (wobbled chirp burst) |
| punc_tape_stop.wav | Tape stop (chirp 440→55 Hz decay) |
| punc_error_buzz.wav | Error buzz (160 Hz square, double blip) |
| amb_room_tone.wav | Room tone bed (low-passed pink noise, 10 s) |

## Downloaded — verified licences (Wikimedia Commons)

| Filename | Title | Author | Source URL | Licence |
|---|---|---|---|---|
| amb_rain.wav | Rain drops (excerpt 0:10–0:25 of source) | Gravity Sound | https://commons.wikimedia.org/wiki/File:Rain_drops_(Gravity_Sound).wav | CC BY 4.0 |
| amb_wind.wav | Wind in forest (excerpt 0:08–0:23 of source) | Gravity Sound | https://commons.wikimedia.org/wiki/File:Wind_in_forest_(Gravity_Sound).wav | CC BY 4.0 |
| amb_forest_birds.wav | Birds Perungalathur Reserved Forest (excerpt 0:15–0:30 of source) | Mk170101 | https://commons.wikimedia.org/wiki/File:Birds_Perungalathur_Reserved_Forest.wav | CC BY 4.0 |
| amb_city_street.wav | Sunday in the city street noise1 (excerpt 0:20–0:35 of source) | cori | https://commons.wikimedia.org/wiki/File:Sunday_in_the_city_street_noise1.ogg | Public domain |
| amb_crowd_murmur.wav | 1 minute at the alexa mall in berlin (excerpt 0:10–0:25 of source) | thore | https://commons.wikimedia.org/wiki/File:1_minute_at_the_alexa_mall_in_berlin.ogg | Public domain |

CC BY 4.0 files: attribution above satisfies the licence for this internal
palette; keep this file with the audio wherever the palette ships.

## Sources attempted but not used

- **Kenney.nl** (CC0 audio packs) — direct page/zip fetches from this machine
  returned HTTP 403 (bot protection). Blocked; no Kenney files used.
- **Freesound** — full-quality downloads require an account login; skipped
  per instructions. No Freesound files used.
- **OpenGameArt** — not needed; the palette was completed from Commons +
  synthesis.
