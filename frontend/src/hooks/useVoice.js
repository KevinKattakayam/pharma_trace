import { useRef, useState } from 'react';

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

// Backward compatibility for components expecting the old hook signature
export function useVoice() {
  const { start, stop, isListening } = useVoiceStreaming(
    (text) => console.log("Partial:", text),
    (text) => console.log("Final:", text)
  );
  return {
    isListening,
    supported: true,
    startListening: start,
    stopListening: async () => { stop(); return null; },
    speak: (text) => console.log("Speak stub:", text)
  };
}
