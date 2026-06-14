"""
Voice Service for vernacular audio transcription and translation.
Uses Groq Whisper API (whisper-large-v3-turbo) and LibreTranslate.
"""
import httpx
from config import get_settings
from services.translation import translate_text

GROQ_AUDIO_API = "https://api.groq.com/openai/v1/audio/transcriptions"

import asyncio
from fastapi import WebSocket
from groq import AsyncGroq
import io

client = AsyncGroq()

async def transcribe_streaming(websocket: WebSocket, language_hint: str = None):
    """
    Accepts audio chunks over WebSocket, streams partial transcripts back.
    Uses Whisper's timestamp_granularities for word-level confidence.
    """
    await websocket.accept()
    audio_buffer = bytearray()
    full_transcript_segments = []

    try:
        while True:
            chunk = await asyncio.wait_for(websocket.receive_bytes(), timeout=10.0)
            if chunk == b"END":
                break
            audio_buffer.extend(chunk)

            # Process every ~3 seconds of audio (48kHz mono = ~144KB)
            if len(audio_buffer) >= 144_000:
                segment_text, detected_lang = await _transcribe_chunk(
                    bytes(audio_buffer), language_hint
                )
                full_transcript_segments.append(segment_text)
                await websocket.send_json({
                    "type": "partial",
                    "text": segment_text,
                    "lang": detected_lang
                })
                audio_buffer = bytearray()  # reset buffer

        # Final chunk
        if audio_buffer:
            segment_text, detected_lang = await _transcribe_chunk(
                bytes(audio_buffer), language_hint
            )
            full_transcript_segments.append(segment_text)

        full_text = " ".join(full_transcript_segments)
        await websocket.send_json({
            "type": "final",
            "text": full_text,
            "lang": detected_lang
        })

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()


async def _transcribe_chunk(audio_bytes: bytes, lang_hint: str = None) -> tuple[str, str]:
    """Transcribe one chunk. Returns (text, detected_language)."""
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "chunk.webm"

    kwargs = {
        "model": "whisper-large-v3-turbo",
        "response_format": "verbose_json",  # gives word timestamps + language
        "temperature": 0.0,  # deterministic for medical terms
    }
    if lang_hint:
        kwargs["language"] = lang_hint  # skip language detection if known

    response = await client.audio.transcriptions.create(
        file=audio_file, **kwargs
    )
    return response.text, response.language
