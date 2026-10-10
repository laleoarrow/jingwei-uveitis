'use strict';

const $ = (id) => document.getElementById(id);
// These fixed synthetic values never depend on the selected image or modality.
const EXAMPLE = Object.freeze({ score: 1.25, probability: 1 / (1 + Math.exp(-1.25)) });
const state = { sequence: 0, timer: null, pending: false, modality: 'cfp', image: null, result: null };
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));

function releaseImage(image) {
  if (image?.url.startsWith('blob:')) URL.revokeObjectURL(image.url);
}

function closeReport() {
  document.body.classList.remove('report-open');
  $('reportView').classList.add('hidden');
  $('siteContent').classList.remove('hidden');
}

function renderDemo() {
  $('progressState').classList.toggle('hidden', !state.pending);
  $('emptyState').classList.toggle('hidden', state.pending || Boolean(state.result));
  $('resultState').classList.toggle('hidden', !state.result);
  $('resetDemo').disabled = !state.image && !state.pending && !state.result;
  $('generateReport').disabled = !state.result || state.pending;
  document.querySelectorAll('[data-modality]').forEach((button) => {
    const selected = button.dataset.modality === state.modality;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
}

function resetDemo(message = '') {
  state.sequence += 1;
  clearTimeout(state.timer);
  state.timer = null;
  state.pending = false;
  state.result = null;
  releaseImage(state.image);
  state.image = null;
  $('imageInput').value = '';
  $('imagePreview').removeAttribute('src');
  $('imagePreview').classList.add('hidden');
  $('dropPrompt').classList.remove('hidden');
  $('replaceImage').classList.add('hidden');
  $('imageLabel').textContent = 'JPG, PNG or WebP · up to 20 MB';
  $('imageError').textContent = message;
  $('imageError').classList.toggle('hidden', !message);
  $('reportPage').replaceChildren();
  closeReport();
  renderDemo();
}

async function startDemo(image) {
  const sequence = ++state.sequence;
  clearTimeout(state.timer);
  state.timer = null;
  state.pending = true;
  state.result = null;
  if (state.image?.url !== image.url) releaseImage(state.image);
  state.image = image;
  $('imageError').classList.add('hidden');
  $('imagePreview').classList.add('hidden');
  $('dropPrompt').classList.remove('hidden');
  $('replaceImage').classList.add('hidden');
  $('imageLabel').textContent = image.kind === 'sample' ? 'Abstract sample · not a clinical image' : 'Your image · preview only';
  closeReport();
  renderDemo();
  try {
    const decoded = new Image();
    decoded.src = image.url;
    await decoded.decode();
    if (sequence !== state.sequence) return;
    if (!decoded.naturalWidth || !decoded.naturalHeight || decoded.naturalWidth * decoded.naturalHeight > 40000000) throw new Error('Choose an image smaller than 40 megapixels.');
    $('imagePreview').src = image.url;
    $('imagePreview').classList.remove('hidden');
    $('dropPrompt').classList.add('hidden');
    $('replaceImage').classList.remove('hidden');
    // A short presentation delay only. No model, API or image computation runs.
    state.timer = setTimeout(() => {
      if (sequence !== state.sequence) return;
      state.timer = null;
      state.pending = false;
      state.result = { ...EXAMPLE, modality: state.modality, image: { ...image } };
      $('scoreValue').textContent = EXAMPLE.score.toFixed(3);
      $('probabilityValue').textContent = (EXAMPLE.probability * 100).toFixed(1);
      renderDemo();
    }, 900);
  } catch (error) {
    if (sequence !== state.sequence) return;
    resetDemo(error.message?.includes('megapixels') ? error.message : 'This image could not be opened. Choose a JPG, PNG or WebP file.');
  }
}

function selectFile(file) {
  if (!file) return;
  const extension = file.name.split('.').pop().toLowerCase();
  if (!['jpg', 'jpeg', 'png', 'webp'].includes(extension) || file.type && !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    resetDemo('Choose a JPG, PNG or WebP image.');
    return;
  }
  if (!file.size || file.size > 20 * 1024 * 1024) {
    resetDemo(file.size ? 'Choose an image smaller than 20 MB.' : 'This file is empty. Choose another image.');
    return;
  }
  startDemo({ url: URL.createObjectURL(file), kind: 'upload' });
}

function syntheticChart() {
  const left = 35, right = 645, center = 105, scale = (right - left) / 10;
  const x = (score) => left + (score + 5) * scale;
  const path = (mean, width, direction) => {
    const points = Array.from({ length: 151 }, (_, index) => {
      const score = -5 + index / 15;
      const density = Math.exp(-.5 * ((score - mean) / width) ** 2);
      return `L${x(score).toFixed(2)},${(center + direction * 56 * density).toFixed(2)}`;
    });
    return `M${left},${center} ${points.join(' ')} L${right},${center}Z`;
  };
  const ticks = [-4, -2, 0, 2, 4].map((score) => `<line x1="${x(score)}" x2="${x(score)}" y1="177" y2="183" stroke="#aebbae"/><text x="${x(score)}" y="201" text-anchor="middle" font-size="12" fill="#718477">${score}</text>`).join('');
  const marker = x(EXAMPLE.score);
  return `<svg viewBox="0 0 680 235" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Synthetic demonstration distributions. Fixed example RVL Score 1.250, example probability 77.7 percent. Not research data." font-family="Arial, Helvetica, sans-serif">
    <path d="${path(1.4, 1.1, -1)}" fill="#bc625b" fill-opacity=".55" stroke="#bc625b" stroke-width=".8"/>
    <path d="${path(-1.1, 1.15, 1)}" fill="#537fad" fill-opacity=".55" stroke="#537fad" stroke-width=".8"/>
    <line x1="${left}" x2="${right}" y1="${center}" y2="${center}" stroke="#dfe6df"/>
    <line x1="${x(0)}" x2="${x(0)}" y1="45" y2="177" stroke="#a9b6ab" stroke-dasharray="3 4"/>
    <line x1="${marker}" x2="${marker}" y1="44" y2="177" stroke="#35483d" stroke-width="2"/>
    <circle cx="${marker}" cy="${center}" r="3.5" fill="#35483d" stroke="white"/>
    <rect x="${marker - 92}" y="9" width="184" height="26" rx="3" fill="#edf2eb"/>
    <text x="${marker}" y="27" text-anchor="middle" font-size="12" fill="#35483d">Example 1.250 · 77.7%</text>
    <line x1="${left}" x2="${right}" y1="177" y2="177" stroke="#aebbae"/>${ticks}
    <text x="340" y="226" text-anchor="middle" font-size="12" fill="#718477">RVL Score · illustrative scale</text>
  </svg>`;
}

function updatePrintedTime() {
  const footer = $('printedAt');
  if (!footer) return;
  const now = new Date();
  footer.dateTime = now.toISOString();
  footer.textContent = `Printed ${new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset' }).format(now)}`;
}

function openReport() {
  const result = state.result;
  if (!result || state.pending) return;
  const kind = result.image.kind === 'sample' ? 'Abstract sample' : 'Browser upload';
  $('reportPage').innerHTML = `
    <header class="report-header"><span class="brand"><img src="assets/jingwei-wordmark.svg" alt="JingWei"><span lang="zh">精卫</span></span><span>Sample report</span></header>
    <h1 class="report-title">Retinal Vascular Leakage Assessment</h1><p class="report-subtitle">Interface demonstration</p>
    <div class="report-demo-notice"><strong>DEMO · NOT ANALYZED</strong>Illustrative result — not calculated from your image</div>
    <dl class="report-info"><div><dt>Modality</dt><dd>${result.modality.toUpperCase()}</dd></div><div><dt>Image source</dt><dd>${kind}</dd></div><div><dt>Result source</dt><dd>Fixed synthetic example</dd></div></dl>
    <h2>Example assessment</h2><div class="report-assessment"><dl class="report-results"><div><dt>Example RVL Score</dt><dd>${result.score.toFixed(3)}</dd></div><div><dt>Example probability</dt><dd>${(result.probability * 100).toFixed(1)}%</dd></div><div><dt>Example classification</dt><dd class="classification">Positive</dd></div></dl><figure class="report-image"><img src="${escapeHtml(result.image.url)}" alt="Image preview only; not analyzed"><figcaption>Preview only · not analyzed</figcaption></figure></div>
    <h2>Synthetic distributions</h2><div class="chart-legend"><span><i class="positive"></i>RVL positive</span><span><i class="negative"></i>RVL negative</span><span><i class="example"></i>Fixed example</span></div><div class="report-chart">${syntheticChart()}</div><p class="report-chart-caption">Generated curves for this demo · no research or patient data</p>
    <h2>Interpretation</h2><p class="report-interpretation">This sample demonstrates the report layout. The displayed RVL Score, probability and classification are fixed examples and do not describe the image.</p><p class="report-purpose">No image analysis was performed. Not for clinical use.</p>
    <footer class="report-footer"><time id="printedAt"></time><span>Page 1 of 1</span></footer>`;
  updatePrintedTime();
  $('siteContent').classList.add('hidden');
  $('reportView').classList.remove('hidden');
  document.body.classList.add('report-open');
  window.scrollTo({ top: 0, behavior: 'instant' });
  $('printReport').focus({ preventScroll: true });
}

$('useSample').addEventListener('click', () => startDemo({ url: 'assets/sample.svg', kind: 'sample' }));
$('resetDemo').addEventListener('click', () => resetDemo());
$('dropZone').addEventListener('click', () => $('imageInput').click());
$('imageInput').addEventListener('change', (event) => { const file = event.target.files[0]; event.target.value = ''; selectFile(file); });
for (const eventName of ['dragenter', 'dragover']) $('dropZone').addEventListener(eventName, (event) => { event.preventDefault(); $('dropZone').classList.add('drag-over'); });
$('dropZone').addEventListener('dragleave', () => $('dropZone').classList.remove('drag-over'));
$('dropZone').addEventListener('drop', (event) => {
  event.preventDefault();
  $('dropZone').classList.remove('drag-over');
  if (event.dataTransfer.files.length !== 1) { resetDemo('Choose one image at a time.'); return; }
  selectFile(event.dataTransfer.files[0]);
});
for (const eventName of ['dragover', 'drop']) document.addEventListener(eventName, (event) => { if (Array.from(event.dataTransfer?.types || []).includes('Files')) event.preventDefault(); });
document.querySelectorAll('[data-modality]').forEach((button) => button.addEventListener('click', () => {
  if (state.modality === button.dataset.modality) return;
  state.modality = button.dataset.modality;
  if (state.image) startDemo(state.image); else renderDemo();
}));
$('generateReport').addEventListener('click', openReport);
$('backToDemo').addEventListener('click', () => { closeReport(); $('demo').scrollIntoView({ behavior: 'instant' }); $('generateReport').focus({ preventScroll: true }); });
document.querySelectorAll('a[href^="#"]').forEach((link) => link.addEventListener('click', closeReport));
$('printReport').addEventListener('click', async () => {
  const result = state.result;
  $('printReport').disabled = true;
  try {
    await Promise.all(Array.from($('reportPage').querySelectorAll('img'), (image) => image.decode()));
    if (state.result !== result || !document.body.classList.contains('report-open')) return;
    updatePrintedTime();
    window.print();
  } catch {
    window.alert('The preview image could not load. Return to the demo and try again.');
  } finally {
    $('printReport').disabled = false;
  }
});
window.addEventListener('beforeprint', updatePrintedTime);
window.addEventListener('pagehide', (event) => { if (!event.persisted) { clearTimeout(state.timer); releaseImage(state.image); } });
$('demoChart').innerHTML = syntheticChart();
renderDemo();
