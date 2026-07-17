import { useState, useCallback, useRef, useEffect } from 'react';

export function useScanner() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState(null);
  const scanIntervalRef = useRef(null);

  const startCamera = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'environment',
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsScanning(true);
    } catch (err) {
      setError('Camera access denied. Please allow camera permissions.');
      setIsScanning(false);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (scanIntervalRef.current) {
      clearInterval(scanIntervalRef.current);
      scanIntervalRef.current = null;
    }
    setIsScanning(false);
  }, []);

  /**
   * Captures video frame, downsamples to max 800px on longest side,
   * and transfers purely as a binary Blob object.
   */
  const captureFrame = useCallback(async () => {
    if (!videoRef.current) return null;
    const v = videoRef.current;
    
    // Calculate downsampled dimensions (max 800px on longest side)
    const MAX_DIM = 800;
    let width = v.videoWidth;
    let height = v.videoHeight;
    if (!width || !height) return null;

    if (width > height && width > MAX_DIM) {
      height = Math.round((height * MAX_DIM) / width);
      width = MAX_DIM;
    } else if (height >= width && height > MAX_DIM) {
      width = Math.round((width * MAX_DIM) / height);
      height = MAX_DIM;
    }

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(v, 0, 0, width, height);

    if (!canvas.toBlob) {
      console.warn("DEPRECATION WARNING: Browser does not support canvas.toBlob. Falling back to base64 string transfer.");
      const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
      return { blob: null, dataUrl };
    }

    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.8));
    return { blob, dataUrl: null };
  }, []);

  useEffect(() => {
    return () => stopCamera();
  }, [stopCamera]);

  return { videoRef, isScanning, error, startCamera, stopCamera, captureFrame };
}
