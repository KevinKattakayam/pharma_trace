import { useRef, useState, useCallback } from 'react';

export function useVoiceStreaming(onPartial, onFinal) {
  const wsRef = useRef(null);
  const recorderRef = useRef(null);
  const [isListening, setIsListening] = useState(false);
  const reconnectAttempts = useRef(0);
  const MAX_RECONNECTS = 3;

  const start = async (langHint = "") => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      connectWebSocket(stream, langHint);
    } catch (error) {
      console.error("Voice streaming failed to start:", error);
      throw error;
    }
  };

  const connectWebSocket = (stream, langHint) => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.VITE_API_URL ? new URL(process.env.VITE_API_URL).host : window.location.host;
    const wsUrl = `${protocol}//${host}/api/v1/voice/stream?lang=${langHint}`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "partial" && onPartial) onPartial(msg.text, msg.lang);
      if (msg.type === "final" && onFinal) onFinal(msg.text, msg.lang);
    };

    ws.onopen = () => {
      reconnectAttempts.current = 0;
      setIsListening(true);
      
      let recorder = recorderRef.current;
      if (!recorder || recorder.state === 'inactive') {
        recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
        recorderRef.current = recorder;
        recorder.start(3000); // chunk every 3s
      }

      // EXPLICIT REASSIGNMENT: guarantee the recorder writes to the *new* socket.
      recorder.ondataavailable = (e) => {
        if (wsRef.current?.readyState === WebSocket.OPEN && e.data.size > 0) {
          e.data.arrayBuffer().then(buf => wsRef.current.send(buf));
        }
      };
    };

    ws.onclose = () => {
      if (isListening && reconnectAttempts.current < MAX_RECONNECTS) {
        reconnectAttempts.current += 1;
        console.warn(`WebSocket closed. Reconnecting... Attempt ${reconnectAttempts.current}`);
        setTimeout(() => connectWebSocket(stream, langHint), Math.pow(2, reconnectAttempts.current) * 1000);
      } else {
        stop();
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      // Let onclose handle reconnects
    };
  };

  const stop = () => {
    setIsListening(false);
    reconnectAttempts.current = MAX_RECONNECTS; // prevent reconnects
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
      recorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(new TextEncoder().encode("END"));
      // Give it a brief moment to send END before closing
      setTimeout(() => wsRef.current.close(), 500);
    } else if (wsRef.current) {
      wsRef.current.close();
    }
  };

  return { start, stop, isListening };
}

// Full voice hook with actual microphone recording and TTS playback
export function useVoice() {
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);
  const [isListening, setIsListening] = useState(false);
  const [supported] = useState(() => !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia));

  const startListening = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      
      const recorder = new MediaRecorder(stream, { 
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus') 
          ? 'audio/webm;codecs=opus' 
          : 'audio/webm' 
      });
      recorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start();
      setIsListening(true);
    } catch (err) {
      console.error("Microphone access failed:", err);
      setIsListening(false);
    }
  }, []);

  const stopListening = useCallback(async () => {
    return new Promise((resolve) => {
      if (!recorderRef.current || recorderRef.current.state === 'inactive') {
        setIsListening(false);
        resolve(null);
        return;
      }

      recorderRef.current.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        chunksRef.current = [];
        
        // Stop all mic tracks
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
          streamRef.current = null;
        }
        
        setIsListening(false);
        resolve(blob.size > 0 ? blob : null);
      };

      recorderRef.current.stop();
    });
  }, []);

  const speak = useCallback((text) => {
    if ('speechSynthesis' in window) {
      // Cancel any ongoing speech
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.9;
      utterance.pitch = 1;
      window.speechSynthesis.speak(utterance);
    }
  }, []);

  return {
    isListening,
    supported,
    startListening,
    stopListening,
    speak,
  };
}
