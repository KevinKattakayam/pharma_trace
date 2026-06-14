import { useState, useEffect } from 'react';

export default function AudioPlayback({ audioScript, language }) {
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.speechSynthesis) {
      setSupported(false);
    }
  }, []);

  const speak = () => {
    if (!supported) return;
    
    // Stop any ongoing speech first
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(audioScript);
    // Map language to native browser BCP 47 language tag
    utterance.lang = language === "ml" ? "ml-IN" :
                     language === "hi" ? "hi-IN" : 
                     language === "ta" ? "ta-IN" :
                     language === "bn" ? "bn-IN" :
                     "en-IN";
    
    utterance.rate = 0.85;  // slower for elderly patients
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const stop = () => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  if (!supported) {
    return (
      <div style={{ color: '#6b7280', fontSize: '0.875rem', padding: '10px 16px' }}>
        <em>Audio playback not supported on this device.</em>
      </div>
    );
  }

  return (
    <button 
      onClick={speaking ? stop : speak}
      aria-label={speaking ? "Stop audio" : "Listen to summary"}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        padding: '10px 16px',
        borderRadius: '20px',
        border: 'none',
        backgroundColor: speaking ? '#fee2e2' : '#e0f2fe',
        color: speaking ? '#991b1b' : '#0369a1',
        fontWeight: 'bold',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}
    >
      {speaking ? "⏹ Stop" : "🔊 Listen in your language"}
    </button>
  );
}
