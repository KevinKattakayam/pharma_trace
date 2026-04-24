import React from 'react';
import { useVoice } from '../hooks/useVoice';
import { useNavigate } from 'react-router-dom';

export default function VoiceInterface() {
  const { isListening, transcript, supported, startListening, stopListening, speak } = useVoice();
  const navigate = useNavigate();

  React.useEffect(() => {
    if (!transcript) return;
    const lower = transcript.toLowerCase();

    if (lower.includes('verify') || lower.includes('scan') || lower.includes('check medicine')) {
      speak('Opening the scanner. Point your camera at the medicine.');
      navigate('/scan');
      stopListening();
    } else if (lower.includes('interaction') || lower.includes('drug combination')) {
      speak('Opening the interaction checker.');
      navigate('/interactions');
      stopListening();
    } else if (lower.includes('pharmacy') || lower.includes('map') || lower.includes('nearby')) {
      speak('Showing nearby pharmacies on the map.');
      navigate('/map');
      stopListening();
    } else if (lower.includes('report') || lower.includes('suspicious')) {
      speak('Opening the report form.');
      navigate('/report');
      stopListening();
    } else if (lower.includes('home') || lower.includes('go back')) {
      navigate('/');
      stopListening();
    }
  }, [transcript]);

  if (!supported) return null;

  return (
    <button
      className={`voice-btn${isListening ? ' listening' : ''}`}
      onClick={isListening ? stopListening : startListening}
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
  );
}
