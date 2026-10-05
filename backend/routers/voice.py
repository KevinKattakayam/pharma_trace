"""
Voice API router for vernacular audio transcription.
"""
from fastapi import APIRouter, File, HTTPException, UploadFile, WebSocket
from pydantic import BaseModel

router = APIRouter(prefix="/voice", tags=["voice"])

class TranscriptionResponse(BaseModel):
    transcribed_text: str
    detected_language: str
    english_text: str

@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe an audio file and translate to English if needed."""
    from services.voice import process_audio
    
    file_bytes = await file.read()
    result = await process_audio(file_bytes, file.filename, file.content_type)
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
        
    return TranscriptionResponse(
        transcribed_text=result["transcribed_text"],
        detected_language=result["detected_language"],
        english_text=result["english_text"]
    )

@router.websocket("/stream")
async def voice_stream_endpoint(websocket: WebSocket):
    from services.voice import transcribe_streaming
    lang_hint = websocket.query_params.get("lang")
    await transcribe_streaming(websocket, lang_hint)
