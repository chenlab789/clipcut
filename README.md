# clipcut — v1.1

Claude Code skill — AI auto-editor for Thai talking-head clips (ChenLab).

- Cuts dead air / silence, keeps silent highlight moments (`--keep`)
- Thai viral subtitles: per-speaker colors, keyword highlights, correct tone-mark shaping (libass `shaping=complex`)
- Exports 16:9 and/or 9:16 (auto from source orientation)
- Transcription: ElevenLabs scribe_v2 (diarize) → fallback faster-whisper
- **ClipCut app**: desktop icon → drop a raw clip → pick a preset → `autopilot.py` (Claude Code headless `claude -p`) fixes the transcript, picks subtitle style + music, cuts dead air, plans SFX / emoji / pixel-art b-roll / zooms → opens the editor for review. Install the icon with `python scripts/install_shortcut.py`.
- **Editor** (`scripts/editor/server.py`): local timeline app (Chrome `--app` window) with live canvas preview — layers for subtitles, b-roll images, sticker emoji, SFX and zoom/shake/flash. Claude drafts effects into `edit.json`, you see them appear and tweak by drag & drop; both sides sync live. `render_edit.py` renders the same plan with ffmpeg.

- **Smart zoom**: camera crops to follow whoever is speaking (YuNet face tracking + mouth motion), punch-ins on vocal emphasis, AI-vision zoom onto objects held up / pointed at, slow drift zooms on static stretches.
- **GIF / meme**: local GIF library picked by AI per sentence — sticker overlays, full-screen meme cutaways (the clip pauses, everything after shifts automatically) and freeze-frame captions, each paired with synthesized meme SFX.
- **Pixel-art characters follow the speaker** (creator vs. co-host sprites).
- **Motion Explainer** mode: Remotion-rendered paper-collage scenes with AI-drawn pixel icons.
- **Multi-clip**: drop several clips, arrange them yourself (story) or let it build a funny-scene compilation — AI trims each scene to the funny part and orders them (or shuffle).
- **Demo-aware dead-air cut**: silent stretches where something is being shown (typing, unboxing) are detected from motion + AI vision and kept, sped up (×2–4 with a badge) or jump-cut instead of removed.
- **Tray icon + start at login** (Windows), lean `claude -p` calls (~5k tokens overhead instead of ~30k) with per-job usage logged.
- **Mobile**: optional access from your own phone via `tailscale serve` (tailnet only) behind a PIN, with a compact editor at `/m`.

## Install
```bash
git clone https://github.com/chenlab789/clipcut ~/.claude/skills/clipcut
```
Requires: Python 3, ffmpeg 8.x, `pip install requests pythainlp faster-whisper pillow numpy opencv-python pystray` (whisper optional), env `ELEVENLABS_API_KEY`.

Usage: `/clipcut <video>` in Claude Code — see [SKILL.md](SKILL.md).

## Fonts
`fonts/` contains Mali, Kanit, Itim from Google Fonts — SIL Open Font License 1.1.

## Sound effects
`assets/sfx/` — synthesized in `scripts/build_sfx.py` (whoosh, boom, riser, ding, pop, boing, tada, buzzer, record_scratch, shutter) plus a curated set from [Kenney](https://kenney.nl) Impact / Interface / Digital Audio packs — CC0 1.0.

Pixel-art sprites in `assets/pixel/` come from the companion [animclip](https://github.com/chenlab789/animclip) skill. Brand logos are fetched as favicons at runtime and pixelated locally (not redistributed).

Background music (`scripts/fetch_music.py`): Kevin MacLeod (incompetech.com), CC BY 4.0 — credit required in the video description; downloaded on demand, not stored in the repo.

GIF library (`scripts/gif_lib.py build`) is downloaded from GIPHY into `assets/gif/` with your own `GIPHY_API_KEY` and is **not** included in this repo — the clips belong to their owners. Drop your own GIFs into `assets/gif/_mine/` and run `gif_lib.py mine` to add them.

Face detection model `assets/models/yunet.onnx` — OpenCV Zoo (YuNet), Apache-2.0.

Emoji stickers are rendered locally from the system's Segoe UI Emoji font and are not redistributed (Windows only for now).
