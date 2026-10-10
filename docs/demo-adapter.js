'use strict';

// Browser-only adapter for the generated local workbench. No network API exists.
(() => {
  const SCORE = 1.25;
  const PROBABILITY = 1 / (1 + Math.exp(-SCORE));
  const interpretation = 'Illustrative result — not calculated from your image. The score and probability are fixed examples; no image analysis was performed.';
  const settings = Object.freeze({ cfp_weight_path: '', oct_weight_path: '', institution: 'JingWei System', include_heatmap: false, device: 'auto', llm_enabled: false, llm_base_url: '', llm_model: '', llm_api_key_set: false });
  const checkAbort = (signal) => { if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError'); };

  function pause(milliseconds, signal) {
    checkAbort(signal);
    return new Promise((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
      const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, milliseconds);
      signal?.addEventListener('abort', abort, { once: true });
    });
  }

  function canvasImage(image, cropped = false) {
    const canvas = document.createElement('canvas');
    const width = image.naturalWidth, height = image.naturalHeight;
    const scale = Math.min(1, 1280 / Math.max(width, height));
    canvas.width = cropped ? 224 : Math.max(1, Math.round(width * scale));
    canvas.height = cropped ? 224 : Math.max(1, Math.round(height * scale));
    const context = canvas.getContext('2d');
    if (cropped) {
      const side = Math.min(width, height) * 224 / 256;
      context.drawImage(image, (width - side) / 2, (height - side) / 2, side, side, 0, 0, 224, 224);
    } else context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas;
  }

  async function previewImage(encoded, signal) {
    checkAbort(signal);
    if (typeof encoded !== 'string' || encoded.length > 28 * 1024 * 1024) throw new Error('Choose a JPG, PNG or WebP image smaller than 20 MB.');
    const bytes = Uint8Array.from(atob(encoded), (character) => character.charCodeAt(0));
    let type;
    if (bytes[0] === 255 && bytes[1] === 216) type = 'image/jpeg';
    else if (bytes[0] === 137 && String.fromCharCode(...bytes.slice(1, 4)) === 'PNG') type = 'image/png';
    else if (String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP') type = 'image/webp';
    else throw new Error('Choose a JPG, PNG or WebP image. TIFF is available in the local app.');
    const url = URL.createObjectURL(new Blob([bytes], { type }));
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      checkAbort(signal);
      if (!image.naturalWidth || !image.naturalHeight || image.naturalWidth * image.naturalHeight > 40000000) throw new Error('Choose an image smaller than 40 megapixels.');
      return { width: image.naturalWidth, height: image.naturalHeight, preview: canvasImage(image).toDataURL('image/png'), input_preview: canvasImage(image, true).toDataURL('image/png') };
    } finally { URL.revokeObjectURL(url); }
  }

  window.jingweiDemoInterpretation = interpretation;
  window.jingweiDemoApi = async (path, options = {}) => {
    checkAbort(options.signal);
    const route = new URL(path, 'https://demo.invalid');
    if (route.pathname === '/api/settings') {
      if (options.method && options.method !== 'GET') throw new Error('Configure models in the local application.');
      return { ...settings };
    }
    if (route.pathname === '/api/health') return { status: 'demo', device: 'browser', available_devices: [], reference_available: true, models: { cfp: { exists: false, loaded: false, name: 'No model loaded' }, oct: { exists: false, loaded: false, name: 'No model loaded' } } };
    if (route.pathname === '/api/reference') {
      const reference = window.JINGWEI_DEMO_REFERENCES?.[route.searchParams.get('modality')]?.[route.searchParams.get('cohort')];
      if (!reference) throw new Error('Reference distribution unavailable.');
      return JSON.parse(JSON.stringify(reference));
    }
    if (route.pathname === '/api/interpret') return { text: interpretation, source: 'template', fallback: false };
    if (route.pathname === '/api/predict' || route.pathname === '/api/preview') {
      const body = JSON.parse(options.body || '{}');
      const image = await previewImage(body.image_base64, options.signal);
      if (route.pathname === '/api/preview') return image;
      if (!['cfp', 'oct'].includes(body.modality)) throw new Error('Select CFP or OCT.');
      // Presentation delay only; these values never depend on the selected pixels.
      await pause(900, options.signal);
      checkAbort(options.signal);
      return {
        id: `DEMO-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
        modality: body.modality, score: SCORE, probability: PROBABILITY, positive: true,
        timestamp: new Date().toISOString(), elapsed_seconds: 0, threshold: .5,
        image, attribution: { status: 'disabled' },
        model: { name: 'Fixed illustrative example', checkpoint: '', signature: 'demo', device: 'browser', reference_compatible: true },
      };
    }
    throw new Error('This feature is available in the local application.');
  };

  window.jingweiDemoSample = async () => {
    const image = new Image();
    image.src = 'assets/sample.svg';
    await image.decode();
    const blob = await new Promise((resolve) => canvasImage(image).toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('Could not load the sample.');
    return new File([blob], 'abstract-sample.png', { type: 'image/png' });
  };
})();
