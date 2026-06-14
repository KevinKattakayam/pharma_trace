// worker code to be loaded via blob URL
const workerCode = `
self.onmessage = function(e) {
  const { imgData, width, height } = e.data;
  const data = imgData.data;

  // Convert to Grayscale and apply Threshold (Binarize)
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const v = 0.2126 * r + 0.7152 * g + 0.0722 * b;

    const threshold = 128;
    const color = v >= threshold ? 255 : 0;

    data[i] = color;     // r
    data[i + 1] = color; // g
    data[i + 2] = color; // b
    // alpha remains same
  }

  self.postMessage({ imgData }, [imgData.data.buffer]);
};
`;

const blob = new Blob([workerCode], { type: 'application/javascript' });
const workerUrl = URL.createObjectURL(blob);
let worker;

export async function preprocessForOCR(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      let width = img.width;
      let height = img.height;

      // Upscale 2x if the image is relatively small (under ~1000px width)
      if (width < 1000) {
        width *= 2;
        height *= 2;
      }

      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, width, height);

      const imageData = ctx.getImageData(0, 0, width, height);

      if (!worker) {
        worker = new Worker(workerUrl);
      }

      worker.onmessage = (e) => {
        ctx.putImageData(e.data.imgData, 0, 0);
        resolve(canvas.toDataURL('image/jpeg', 0.9));
      };
      
      worker.onerror = (err) => {
        console.error('Worker error:', err);
        resolve(dataUrl); // Fallback to original image if worker fails
      };

      // Transfer the buffer to the worker for zero-copy performance
      worker.postMessage(
        { imgData: imageData, width, height }, 
        [imageData.data.buffer]
      );
    };
    img.onerror = reject;
    img.src = dataUrl;
  });
}
