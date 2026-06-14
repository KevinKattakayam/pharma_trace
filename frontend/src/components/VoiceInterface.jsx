import React, { useState } from 'react';
import { useVoice } from '../hooks/useVoice';
import { useNavigate } from 'react-router-dom';

export default function VoiceInterface() {
  const { isListening, supported, startListening, stopListening, speak } = useVoice();
  const navigate = useNavigate();
  const [detectedLang, setDetectedLang] = useState('');

  const handleStop = async () => {
    const audioBlob = await stopListening();
    if (!audioBlob) return;

    // Send to backend
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');

    try {
      setDetectedLang('Processing audio...');
      const response = await fetch('/api/v1/voice/transcribe', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      
      const engText = data.english_text.toLowerCase();
      
      let displayMessage = `Detected: ${data.detected_language} - ${data.transcribed_text}`;
      setDetectedLang(displayMessage);

      let reply = "";
      if (engText.includes('verify') || engText.includes('scan') || engText.includes('check medicine')) {
        reply = 'Opening the scanner. Point your camera at the medicine.';
        navigate('/scan');
      } else if (engText.includes('interaction') || engText.includes('drug combination')) {
        reply = 'Opening the interaction checker.';
        navigate('/interactions');
      } else if (engText.includes('pharmacy') || engText.includes('map') || engText.includes('nearby')) {
        reply = 'Showing nearby pharmacies on the map.';
        navigate('/map');
      } else if (engText.includes('report') || engText.includes('suspicious')) {
        reply = 'Opening the report form.';
        navigate('/report');
      } else if (engText.includes('home') || engText.includes('go back')) {
        reply = 'Going to home page.';
        navigate('/');
      } else {
         reply = `Command not recognized: ${engText}`;
      }
      
      // If it wasn't English, try to translate the reply back to the user's language
      if (data.detected_language !== 'en' && data.detected_language !== 'english' && reply) {
        try {
          const transRes = await fetch(`/api/v1/translate?text=${encodeURIComponent(reply)}&target=${data.detected_language}&source=en`, { method: 'POST' });
          const transData = await transRes.json();
          reply = transData.translated || reply;
        } catch(e) { /* ignore translation error */ }
      }
      
      if (reply) {
        speak(reply);
      }
      
      // Clear message after 5 seconds
      setTimeout(() => setDetectedLang(''), 5000);
      
    } catch (err) {
      console.error(err);
      setDetectedLang('Error processing audio');
      setTimeout(() => setDetectedLang(''), 3000);
    }
  };

  if (!supported) return null;

  return (
    <div style={{ position: 'fixed', bottom: '20px', right: '20px', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '10px', zIndex: 1000 }}>
      {detectedLang && (
        <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-2)', boxShadow: 'var(--shadow-sm)', padding: '8px 12px', borderRadius: '8px', fontSize: '12px', color: 'var(--text-1)', fontWeight: 600 }}>
          {detectedLang}
        </div>
      )}
      <button
        className={`voice-btn${isListening ? ' listening' : ''}`}
        onClick={isListening ? handleStop : startListening}
        title={isListening ? 'Stop listening' : 'Voice command'}
        id="btn-voice-interface"
        aria-label="Voice command"
      >
        {isListening ? (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
          </svg>
        ) : (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
            <line x1="8" y1="23" x2="16" y2="23" />
          </svg>
        )}
      </button>
    </div>
  );
}
