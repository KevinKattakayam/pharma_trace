import React, { useMemo } from 'react';

export default function ConfidenceGauge({ value = 0, size = 110, strokeWidth = 8 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  
  const status = value >= 90 ? 'safe' : value >= 70 ? 'info' : value >= 40 ? 'warn' : 'danger';
  const color = `var(--${status})`;

  return (
    <div className="confidence-gauge anim-scale" style={{ width: size, height: size, position: 'relative' }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}
      >
        {/* Track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--bg-tertiary)"
          strokeWidth={strokeWidth}
          strokeOpacity="0.5"
        />
        {/* Glow Layer */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ 
            opacity: 0.3,
            filter: 'blur(8px)',
            transition: 'stroke-dashoffset 1.5s var(--spring), stroke 0.5s ease'
          }}
        />
        {/* Main Fill */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ 
            transition: 'stroke-dashoffset 1.3s var(--spring), stroke 0.5s ease'
          }}
        />
      </svg>
      
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        gap: '2px'
      }}>
        <div style={{ 
          fontSize: '1.5rem', fontWeight: 900, color: 'var(--text-1)', 
          lineHeight: 1, fontFamily: 'var(--mono)', letterSpacing: '-0.05em' 
        }}>
          {Math.round(value)}
        </div>
        <div style={{ 
          fontSize: '0.5rem', fontWeight: 800, color: 'var(--text-3)', 
          textTransform: 'uppercase', letterSpacing: '0.1em' 
        }}>
          Trust %
        </div>
      </div>
    </div>
  );
}

