# pipecat-outbound-audio-counter

A diagnostic [Pipecat](https://github.com/pipecat-ai/pipecat) `FrameProcessor` that counts outbound TTS audio per turn and warns when a turn ends with zero bytes.

## The bug it catches

Sometimes a TTS provider (Sarvam, Azure, ElevenLabs, …) emits `TTSStartedFrame`, takes ~2 seconds, and then emits `TTSStoppedFrame` — without ever emitting any actual audio frames in between. The pipeline keeps moving. The state machine thinks everything is fine. **The user hears silence.**

This is invisible to most observability — there's no exception, no error frame, no log line. The only signal is "zero audio between Started and Stopped." This processor watches for exactly that.

## What you get in your logs

```
[audio_out] tts_started session=abc
[audio_out] tts_stopped session=abc frames=42 bytes=120000 dur_s=2.1     ← healthy
[audio_out] tts_started session=abc
[audio_out] tts_stopped session=abc frames=0 bytes=0 dur_s=2.3
[tts_silent_fail] zero audio bytes after 2.3s synth window session=abc consecutive=1   ← silent turn
```

Alert on `[tts_silent_fail]` in your log aggregator. Consecutive silent turns suggest a structural TTS degradation; a single one is usually a blip.

## Install

```bash
pip install pipecat-outbound-audio-counter
```

## Wire it up

Position: **immediately after `tts`, before `transport.output()`**.

```python
from pipecat.pipeline.pipeline import Pipeline
from pipecat_outbound_audio_counter import OutboundAudioCounter

audio_counter = OutboundAudioCounter(session_id=meeting_id)

pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    llm,
    tts,
    audio_counter,             # ← here
    transport.output(),
    context_aggregator.assistant(),
])
```

## Tuning

`SILENT_FAIL_THRESHOLD_S = 2.0` — turns shorter than 2 seconds that produce 0 bytes don't trigger the warning (some TTS providers do a quick "no speech needed for this short text" path). Bump it if your TTS has a longer time-to-first-byte.

Override by subclassing:
```python
class CustomCounter(OutboundAudioCounter):
    SILENT_FAIL_THRESHOLD_S = 4.0
```

## Programmatic access

```python
if audio_counter.silent_streak >= 3:
    # tear down this session, three consecutive silent turns is a structural problem
    ...
```

## Related projects

- 🎯 [`pipecat-sarvam-azure-starter`](https://github.com/dpkdhingra91/pipecat-sarvam-azure-starter) — canonical voice pipeline this diagnostic was extracted from.
- 🎙️ [`pipecat-bot-speaking-observer`](https://github.com/dpkdhingra91/pipecat-bot-speaking-observer) — turn-gate orchestration sibling.
- 🛡️ [`pipecat-content-filter-fallback`](https://github.com/dpkdhingra91/pipecat-content-filter-fallback) — RAI false-positive guard sibling.

## License

MIT — see [LICENSE](LICENSE).

---

*Extracted from the production voice stack of [AI Interview Agents](https://www.aiinterviewagents.com) — an AI voice interviewer that runs real two-way spoken interviews and screens candidates at scale.*
