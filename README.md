# clipcut

Claude Code skill — AI auto-editor for Thai talking-head clips (ChenLab).

- Cuts dead air / silence, keeps silent highlight moments (`--keep`)
- Thai viral subtitles: per-speaker colors, keyword highlights, correct tone-mark shaping (libass `shaping=complex`)
- Exports 16:9 and/or 9:16 (auto from source orientation)
- Transcription: ElevenLabs scribe_v2 (diarize) → fallback faster-whisper

## Install
```bash
git clone https://github.com/chenlab789/clipcut ~/.claude/skills/clipcut
```
Requires: Python 3, ffmpeg 8.x, `pip install requests pythainlp faster-whisper` (whisper optional), env `ELEVENLABS_API_KEY`.

Usage: `/clipcut <video>` in Claude Code — see [SKILL.md](SKILL.md).

## Fonts
`fonts/` contains Mali, Kanit, Itim from Google Fonts — SIL Open Font License 1.1.
