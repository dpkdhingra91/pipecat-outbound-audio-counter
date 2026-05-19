"""pipecat-outbound-audio-counter — diagnostic processor for TTS silent-failure detection.

Counts outbound TTS audio bytes per bot-speaking turn. Logs per-turn totals.
On a "silent turn" (TTSStartedFrame → TTSStoppedFrame with zero audio bytes
emitted), logs a WARNING. Useful for catching cases where a TTS provider
acknowledges a synthesis request but produces no audio — invisible to the
rest of the pipeline.
"""

import logging
import time
from typing import Optional

from pipecat.frames.frames import (
    Frame,
    OutputAudioRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger(__name__)


class OutboundAudioCounter(FrameProcessor):
    """Diagnostic-only. Counts TTS audio per turn; emits a WARNING on silent turns.

    Position: immediately AFTER `tts`, BEFORE `transport.output()`. From this
    seat the processor sees:
      - downstream:  TTSStartedFrame → TTSAudioRawFrame[...] → TTSStoppedFrame

    Logs:
      - INFO `[audio_out] tts_started session=<id>`
      - INFO `[audio_out] tts_stopped session=<id> frames=N bytes=B dur_s=D`
      - WARNING `[tts_silent_fail] session=<id> consecutive=N` when a turn
        ends with 0 bytes after ≥SILENT_FAIL_THRESHOLD_S of synth duration.

    Grep targets:
      - `[audio_out]` per turn — correlate `bytes=` against `dur_s=`
      - `[tts_silent_fail]` — alert on consecutive silent turns

    Tune SILENT_FAIL_THRESHOLD_S if your TTS provider takes longer to first byte.
    """

    SILENT_FAIL_THRESHOLD_S = 2.0

    def __init__(self, session_id: str = ""):
        super().__init__()
        self._session_id = session_id
        self._audio_bytes = 0
        self._audio_frames = 0
        self._tts_started_at: Optional[float] = None
        self._silent_streak = 0

    @property
    def silent_streak(self) -> int:
        """How many consecutive silent turns. Resets on the first good turn."""
        return self._silent_streak

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, TTSStartedFrame):
                self._audio_bytes = 0
                self._audio_frames = 0
                self._tts_started_at = time.time()
                logger.info("[audio_out] tts_started session=%s", self._session_id)
            elif isinstance(frame, TTSStoppedFrame):
                dur = time.time() - (self._tts_started_at or time.time())
                logger.info(
                    "[audio_out] tts_stopped session=%s frames=%d bytes=%d dur_s=%.2f",
                    self._session_id, self._audio_frames, self._audio_bytes, dur,
                )
                if (
                    self._audio_bytes == 0
                    and dur >= self.SILENT_FAIL_THRESHOLD_S
                ):
                    self._silent_streak += 1
                    logger.warning(
                        "[tts_silent_fail] zero audio bytes after %.1fs synth window "
                        "session=%s consecutive=%d",
                        dur, self._session_id, self._silent_streak,
                    )
                else:
                    self._silent_streak = 0
                self._tts_started_at = None
            elif isinstance(frame, (TTSAudioRawFrame, OutputAudioRawFrame)):
                payload = getattr(frame, "audio", b"") or b""
                self._audio_frames += 1
                self._audio_bytes += len(payload)

        await self.push_frame(frame, direction)


__all__ = ["OutboundAudioCounter"]
__version__ = "0.1.0"
