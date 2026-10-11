'use strict';

const $ = (id) => document.getElementById(id);
const DEFAULTS = {
  cfp_weight_path: '',
  oct_weight_path: '',
  institution: 'JingWei System',
  include_heatmap: false,
  device: 'auto', llm_enabled: false, llm_base_url: '', llm_model: '', llm_api_key_set: false,
};
const state = {
  modality: 'cfp', settings: null, health: null, result: null, reference: null,
  referenceError: '', referencePending: false, predictionPending: false,
  predictionSequence: 0, referenceSequence: 0, predictionController: null,
  predictionTimer: null, predictionStartedAt: null,
  previewUrl: null, originalPreview: null, previewMode: 'original', view: 'workspace',
  settingsRevision: 0, settingsPending: false, clearLlmApiKey: false,
  interpretationSequence: 0, interpretationController: null, interpretationPending: false,
  interpretationResult: null, reportPrintPrepared: false,
};
const cohortLabel = (cohort, fallback = '') => ({
  internal_test: 'UC-FAH-CQMU', prospective: 'UC-FAH-CQMU · Temporal validation', shanghai: 'EENT-FDU',
  zhengzhou: 'FAH-ZZU', jilin: 'OC-JLU2H', proton: 'PROTON',
}[cohort] || fallback || cohort);
const eyeLabel = (eye) => ({ OD: 'Right (OD)', OS: 'Left (OS)' }[eye] || eye);
const number = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const count = (value) => Number.isFinite(value) ? value.toLocaleString('en-US') : '—';
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const localDate = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error(`Unexpected server response (${response.status}).`); }
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map((e) => e.msg || 'Invalid parameter').join('; ') : 'Request failed';
    throw new Error(detail);
  }
  return data;
}

function setNotice(id, message, isError = false) {
  $(id).textContent = message;
  $(id).classList.toggle('hidden', !message);
  $(id).classList.toggle('error-notice', isError);
}

function patientInformation() {
  return {
    id: $('patientId').value.trim(), name: $('patientName').value.trim(), eye: $('eye').value,
    date: $('examDate').value, physician: $('physician').value.trim(),
  };
}

function setView(view) {
  if (view === 'report' && !state.result) return;
  state.view = view;
  for (const name of ['workspace', 'settings', 'report']) $(`${name}View`).classList.toggle('hidden', name !== view);
  document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view || view === 'report' && button.dataset.view === 'workspace'));
  if (view === 'report') renderReport();
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function renderHealth() {
  const health = state.health;
  $('connectionText').textContent = health ? 'Connected' : 'Disconnected';
  $('connectionDot').classList.toggle('bad', !health);
  for (const modality of ['cfp', 'oct']) {
    const model = health?.models?.[modality];
    const label = $(`${modality}WeightState`);
    const unconfigured = state.settings?.[`${modality}_weight_path`] === '';
    label.textContent = model ? model.exists ? 'Model ready' : unconfigured ? 'Not configured' : 'Weights not found' : 'Disconnected';
    label.className = `weight-state ${model?.exists ? 'present' : unconfigured ? '' : 'missing'}`;
  }
  const model = health?.models?.[state.modality];
  $('activeModelStatus').textContent = model ? model.exists ? 'Model ready' : 'Weights not found' : 'Disconnected';
  $('modelDot').className = `status-dot ${model?.exists ? '' : 'bad'}`;
  renderDeviceStatus();
  if (health?.reference_available === false) setNotice('serviceNotice', 'Reference distribution unavailable.');
}

function renderDeviceStatus() {
  const available = state.health?.available_devices;
  const confirmed = Array.isArray(available);
  const hasMps = confirmed && available.includes('mps');
  $('device').querySelector('option[value="mps"]').disabled = !hasMps;
  if (!confirmed) {
    $('deviceStatus').textContent = 'Device availability unknown';
    return;
  }
  const selected = $('device').value;
  const effective = selected === 'auto' ? hasMps ? 'mps' : 'cpu' : selected;
  const name = effective === 'mps' ? 'Apple MPS' : 'CPU';
  $('deviceStatus').textContent = available.includes(effective)
    ? selected === (state.settings?.device || DEFAULTS.device) ? `Using ${name}` : `On save: ${name}`
    : `${name} unavailable`;
}

async function refreshHealth() {
  try {
    state.health = await api('/api/health');
    renderHealth();
    if (state.health.reference_available !== false) setNotice('serviceNotice', '');
  } catch (error) {
    state.health = null;
    renderHealth();
    setNotice('serviceNotice', 'JingWei service unavailable. Start the application and retry.', true);
  }
}

function populateSettings() {
  const settings = state.settings || DEFAULTS;
  $('cfpWeightPath').value = settings.cfp_weight_path || '';
  $('octWeightPath').value = settings.oct_weight_path || '';
  $('institution').value = settings.institution || '';
  $('includeHeatmap').checked = Boolean(settings.include_heatmap);
  $('device').value = settings.device || 'auto';
  renderDeviceStatus();
  $('llmEnabled').checked = Boolean(settings.llm_enabled);
  $('llmBaseUrl').value = settings.llm_base_url || '';
  $('llmModel').value = settings.llm_model || '';
  $('llmApiKey').value = '';
  state.clearLlmApiKey = false;
  renderLlmSettings();
}

async function saveSettings(event) {
  event.preventDefault();
  state.settingsPending = true;
  cancelInterpretation();
  ensureInterpretation();
  const button = $('saveSettings');
  button.disabled = true;
  button.textContent = 'Saving…';
  setNotice('settingsMessage', '');
  try {
    const settings = {
      cfp_weight_path: $('cfpWeightPath').value.trim(), oct_weight_path: $('octWeightPath').value.trim(),
      institution: $('institution').value.trim(), device: $('device').value,
      include_heatmap: $('includeHeatmap').checked,
      llm_enabled: $('llmEnabled').checked, llm_base_url: $('llmBaseUrl').value.trim(),
      llm_model: $('llmModel').value.trim(),
    };
    if ($('llmApiKey').value.trim()) settings.llm_api_key = $('llmApiKey').value.trim();
    if (state.clearLlmApiKey) settings.llm_clear_api_key = true;
    state.settings = await api('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings) });
    state.settingsRevision += 1;
    populateSettings();
    setNotice('settingsMessage', 'Saved for the next analysis.');
    await refreshHealth();
  } catch (error) {
    setNotice('settingsMessage', error.message || 'Could not save. Please retry.', true);
  } finally {
    state.settingsPending = false;
    button.disabled = false;
    button.textContent = 'Save changes';
  }
}

function renderLlmSettings() {
  const enabled = $('llmEnabled').checked;
  $('llmFields').classList.toggle('hidden', !enabled);
  for (const id of ['llmBaseUrl', 'llmModel']) {
    $(id).disabled = !enabled;
    $(id).required = enabled;
  }
  $('llmApiKey').disabled = !enabled;
  $('llmApiKey').placeholder = state.clearLlmApiKey ? 'Removed when you save' : state.settings?.llm_api_key_set ? 'Configured · leave blank to keep' : 'API key';
  $('clearLlmKey').disabled = !enabled || state.clearLlmApiKey || (!state.settings?.llm_api_key_set && !$('llmApiKey').value);
}

function presetInterpretation(result) {
  const percentage = result.probability * 100;
  const positive = result.probability >= .5;
  const displayed = number(percentage, 1);
  const approximate = [0, 50, 100].includes(Number(displayed)) && Number(displayed) !== percentage;
  const text = `Predicted RVL probability is ${approximate ? 'approximately ' : ''}${displayed}%, ${percentage === 50 ? 'at' : positive ? 'above' : 'below'} the 50% classification threshold. The model favors an RVL-${positive ? 'positive' : 'negative'} result.`;
  return { text, source: 'template', fallback: true };
}

function cancelInterpretation() {
  state.interpretationSequence += 1;
  state.interpretationController?.abort();
  state.interpretationController = null;
  state.interpretationPending = false;
  state.interpretationResult = null;
}

async function ensureInterpretation() {
  const result = state.result;
  if (!result) return;
  if (state.interpretationPending && state.interpretationResult === result) return;
  cancelInterpretation();
  if (result.interpretation) return;
  // Settings changes apply to new analyses. Never regenerate an old result with a new LLM configuration.
  if (state.settingsPending || result.interpretationSettingsRevision !== state.settingsRevision) {
    result.interpretation = presetInterpretation(result);
    if (state.view === 'report') renderReport();
    return;
  }
  const sequence = state.interpretationSequence;
  const controller = new AbortController();
  state.interpretationController = controller;
  state.interpretationPending = true;
  state.interpretationResult = result;
  if (state.view === 'report') renderReport();
  const timeout = setTimeout(() => controller.abort(), 16000);
  try {
    const response = await api('/api/interpret', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ modality: result.modality, score: result.score, probability: result.probability }),
    });
    if (sequence !== state.interpretationSequence || state.result !== result) return;
    if (typeof response.text !== 'string' || !response.text.trim() || !['template', 'llm'].includes(response.source)) throw new Error('Invalid interpretation response');
    result.interpretation = { text: response.text.trim(), source: response.source, fallback: Boolean(response.fallback) };
  } catch {
    if (sequence !== state.interpretationSequence || state.result !== result) return;
    result.interpretation = presetInterpretation(result);
  } finally {
    clearTimeout(timeout);
    if (sequence === state.interpretationSequence) {
      state.interpretationController = null;
      state.interpretationPending = false;
      if (state.view === 'report') renderReport();
    }
  }
}

function clearPreview() {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  state.originalPreview = null;
  state.previewMode = 'original';
  $('imagePreview').removeAttribute('src');
  $('imagePreview').classList.add('hidden');
  $('dropContent').classList.remove('hidden');
  $('replaceImage').classList.add('hidden');
  $('previewControls').classList.add('hidden');
  $('dropContent').querySelector('strong').textContent = 'Drop an image';
  $('previewNote').textContent = '';
  $('previewNote').classList.add('hidden');
  $('imageFilename').textContent = '';
  $('imageDimensions').textContent = '';
}

function stopPredictionTimer() {
  clearInterval(state.predictionTimer);
  state.predictionTimer = null;
  state.predictionStartedAt = null;
  $('predictionElapsed').textContent = '';
}

function updatePredictionElapsed(sequence) {
  if (sequence !== state.predictionSequence || !state.predictionPending || state.predictionStartedAt === null) return;
  $('predictionElapsed').textContent = `${((performance.now() - state.predictionStartedAt) / 1000).toFixed(2)} s elapsed`;
}

function invalidatePrediction(clearImage = true) {
  cancelInterpretation();
  stopPredictionTimer();
  state.predictionSequence += 1;
  state.predictionController?.abort();
  state.predictionController = null;
  state.predictionPending = false;
  state.result = null;
  $('imageInput').value = '';
  $('applyPatient').classList.add('hidden');
  $('reportPage').replaceChildren();
  setNotice('predictionError', '');
  if (clearImage) clearPreview();
  renderResult();
}

function newCase() {
  invalidatePrediction();
  for (const field of ['patientId', 'patientName', 'eye', 'physician']) $(field).value = '';
  $('examDate').value = localDate();
  setView('workspace');
}

function changeModality(modality) {
  if (state.modality === modality) return;
  state.modality = modality;
  invalidatePrediction();
  document.querySelectorAll('[data-modality]').forEach((button) => {
    const selected = button.dataset.modality === modality;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  renderHealth();
  loadReference();
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Unable to read this image. Choose another file.'));
    reader.readAsDataURL(file);
  });
}

function showPreview(mode) {
  state.previewMode = mode;
  const preview = mode === 'input' ? state.result?.image?.input_preview : state.originalPreview;
  if (preview) {
    $('imagePreview').src = preview;
    $('imagePreview').classList.remove('hidden');
    $('dropContent').classList.add('hidden');
    $('replaceImage').classList.remove('hidden');
  }
  document.querySelectorAll('[data-preview]').forEach((button) => {
    button.classList.toggle('selected', button.dataset.preview === mode);
    button.setAttribute('aria-pressed', String(button.dataset.preview === mode));
  });
  $('previewNote').textContent = mode === 'input' ? '224 × 224 · Center crop' : '';
  $('previewNote').classList.toggle('hidden', mode !== 'input');
}

async function useSample() {
  const sequence = state.predictionSequence;
  const modality = state.modality;
  const button = $('useSample');
  button.disabled = true;
  try {
    const image = new Image();
    image.src = `assets/sample-${modality}-generated.png`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    canvas.getContext('2d').drawImage(image, 0, 0);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('Could not load the sample.');
    const file = new File([blob], `AI-generated-${modality.toUpperCase()}-sample.png`, { type: 'image/png' });
    file.jingweiGeneratedSample = true;
    if (sequence === state.predictionSequence) analyzeFile(file);
  } catch {
    if (sequence === state.predictionSequence) setNotice('predictionError', 'The sample could not load. Choose an image or try again.', true);
  } finally { button.disabled = false; }
}

async function analyzeFile(file) {
  if (!file) return;
  const extension = file.name.split('.').pop().toLowerCase();
  const isTiff = ['tif', 'tiff'].includes(extension) || file.type?.toLowerCase() === 'image/tiff';
  if (!isTiff && !['jpg', 'jpeg', 'png', 'webp'].includes(extension)) {
    invalidatePrediction();
    setNotice('predictionError', 'Choose a JPG, PNG, TIFF or WEBP image.', true);
    renderResult();
    return;
  }
  if (file.size > 20 * 1024 * 1024 || !file.size) {
    invalidatePrediction();
    setNotice('predictionError', file.size ? 'Image exceeds 20 MB. Choose a smaller file.' : 'This file is empty. Choose another image.', true);
    renderResult();
    return;
  }
  invalidatePrediction();
  const sequence = state.predictionSequence;
  const modality = state.modality;
  const snapshot = { patient: patientInformation(), institution: state.settings?.institution || '', filename: file.name, modality, aiGeneratedSample: file.jingweiGeneratedSample === true };
  const interpretationSettingsRevision = state.settingsRevision;
  state.predictionPending = true;
  state.predictionStartedAt = performance.now();
  $('predictionPhase').textContent = 'Preparing image…';
  updatePredictionElapsed(sequence);
  state.predictionTimer = setInterval(() => updatePredictionElapsed(sequence), 100);
  state.predictionController = new AbortController();
  const controller = state.predictionController;
  if (isTiff) {
    $('dropContent').querySelector('strong').textContent = 'Reading image…';
  } else {
    state.previewUrl = URL.createObjectURL(file);
    state.originalPreview = state.previewUrl;
    showPreview('original');
  }
  $('imageFilename').textContent = file.name;
  renderResult();
  try {
    const dataUrl = await readFile(file);
    if (sequence !== state.predictionSequence) return;
    const imageBase64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
    if (isTiff) {
      // Decode TIFF independently so its preview does not wait for model inference.
      api('/api/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ image_base64: imageBase64 }),
      }).then((image) => {
        if (sequence !== state.predictionSequence || controller.signal.aborted || state.result) return;
        if (!image.preview?.startsWith('data:image/png;base64,')) return;
        state.originalPreview = image.preview;
        showPreview('original');
        $('imageDimensions').textContent = image.width && image.height ? `${image.width} × ${image.height}` : '';
      }).catch(() => { /* Prediction can still provide the final preview. */ });
    }
    $('predictionPhase').textContent = 'Analyzing image…';
    const prediction = await api('/api/predict', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ modality, filename: file.name, image_base64: imageBase64 }),
    });
    if (sequence !== state.predictionSequence) return;
    if (prediction.modality !== modality || !Number.isFinite(prediction.score) || !Number.isFinite(prediction.probability) || prediction.probability < 0 || prediction.probability > 1) throw new Error('Invalid model response. No report was generated.');
    const analysisElapsedSeconds = (performance.now() - state.predictionStartedAt) / 1000;
    state.result = { ...prediction, snapshot, interpretationSettingsRevision, interpretation: null, analysisElapsedSeconds };
    ensureInterpretation();
    if (prediction.image?.preview?.startsWith('data:image/')) state.originalPreview = prediction.image.preview;
    showPreview('original');
    $('imageDimensions').textContent = prediction.image?.width && prediction.image?.height ? `${prediction.image.width} × ${prediction.image.height}` : '';
    $('previewControls').classList.toggle('hidden', !prediction.image?.input_preview?.startsWith('data:image/'));
    updatePatientDirty();
    refreshHealth();
  } catch (error) {
    if (sequence !== state.predictionSequence || error.name === 'AbortError') return;
    setNotice('predictionError', error.message || 'Analysis failed. Check the image and model settings.', true);
  } finally {
    controller.abort();
    if (sequence === state.predictionSequence) {
      stopPredictionTimer();
      state.predictionPending = false;
      state.predictionController = null;
      renderResult();
    }
  }
}

function predictionLabel(result) {
  return result.positive ? 'Predicted RVL: positive' : 'Predicted RVL: negative';
}

function renderResult() {
  const result = state.result;
  const pending = state.predictionPending;
  const hasError = !$('predictionError').classList.contains('hidden');
  const showAnalysisTime = !pending && Number.isFinite(result?.analysisElapsedSeconds);
  $('resultStatus').textContent = hasError ? 'Analysis failed' : showAnalysisTime ? `Analysis time · ${result.analysisElapsedSeconds.toFixed(2)} s` : '';
  $('resultStatus').className = `result-status ${hasError ? 'error' : showAnalysisTime ? '' : 'hidden'}`;
  $('predictionWaiting').classList.toggle('hidden', !pending);
  $('assessmentValues').classList.toggle('hidden', pending || hasError);
  $('scoreValue').textContent = result ? number(result.score, 3) : '—';
  $('probabilityValue').innerHTML = `${result ? number(result.probability * 100, 1) : '—'}<span class="metric-unit">%</span>`;
  $('probabilityBar').style.width = `${result ? result.probability * 100 : 0}%`;
  $('interpretationTitle').textContent = result ? predictionLabel(result) : '';
  $('interpretation').classList.toggle('hidden', !result);
  $('interpretation').classList.toggle('positive-result', Boolean(result?.positive));
  $('openReport').disabled = !result || pending;
  $('individualLegend').classList.toggle('hidden', !result);
  renderDistribution();
}

function updatePatientDirty() {
  const result = state.result;
  const dirty = result && JSON.stringify(patientInformation()) !== JSON.stringify(result.snapshot.patient);
  $('applyPatient').classList.toggle('hidden', !dirty);
}

async function loadReference() {
  const sequence = ++state.referenceSequence;
  const modality = state.modality;
  const cohort = $('cohort').value;
  state.reference = null;
  state.referenceError = '';
  state.referencePending = true;
  renderDistribution();
  try {
    const reference = await api(`/api/reference?modality=${encodeURIComponent(modality)}&cohort=${encodeURIComponent(cohort)}`);
    if (sequence !== state.referenceSequence) return;
    if (reference.modality !== modality || reference.cohort !== cohort || !Array.isArray(reference.groups)) throw new Error('Invalid reference data.');
    state.reference = reference;
  } catch (error) {
    if (sequence !== state.referenceSequence) return;
    state.referenceError = error.message || 'Reference distribution unavailable';
  } finally {
    if (sequence === state.referenceSequence) {
      state.referencePending = false;
      renderDistribution();
      if (state.view === 'report') renderReport();
    }
  }
}

function scoreTicks(min, max) {
  const raw = (max - min) / 6;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const ticks = [];
  for (let tick = Math.ceil(min / step) * step; tick <= max + step * 1e-7; tick += step) ticks.push(Math.abs(tick) < step * 1e-7 ? 0 : tick);
  return ticks.map((value) => ({ value, label: value.toLocaleString('en-US', { maximumFractionDigits: Math.max(0, -Math.floor(Math.log10(step)) + 1) }) }));
}

function distributionSvg(reference, result) {
  if (result?.model?.reference_compatible === false) return `<div class="chart-empty">No matching reference for these weights</div>`;
  if (!reference || !reference.groups.some((group) => group.n > 0 && Array.isArray(group.x) && group.x.length)) return `<div class="chart-empty">No reference distribution for this cohort</div>`;
  const width = 680, left = 24, right = 20, plotWidth = width - left - right;
  let min = Number(reference.range?.[0]), max = Number(reference.range?.[1]);
  if (!Number.isFinite(min) || !Number.isFinite(max) || min >= max) {
    const values = reference.groups.flatMap((group) => group.x || []).filter(Number.isFinite);
    min = Math.min(...values); max = Math.max(...values);
  }
  if (result) { min = Math.min(min, result.score); max = Math.max(max, result.score); }
  min = Math.min(min, 0); max = Math.max(max, 0);
  if (min === max) { min -= 1; max += 1; }
  const padding = (max - min) * .055;
  min -= padding; max += padding;
  const x = (value) => left + (value - min) / (max - min) * plotWidth;
  const baseline = 139, topAxis = 49, axis = 205, halfHeight = 49;
  const f = (value) => Number(value).toFixed(2);
  let content = '';
  for (const tick of scoreTicks(min, max)) {
    content += `<line x1="${f(x(tick.value))}" x2="${f(x(tick.value))}" y1="88" y2="${axis}" stroke="#e8ebef" stroke-width=".7"/><line x1="${f(x(tick.value))}" x2="${f(x(tick.value))}" y1="${axis}" y2="${axis + 5}" stroke="#aab2bd" stroke-width=".7"/><text x="${f(x(tick.value))}" y="${axis + 24}" text-anchor="middle" fill="#67717e" font-size="14">${escapeHtml(tick.label)}</text>`;
  }
  content += `<line x1="${left}" x2="${width - right}" y1="${axis}" y2="${axis}" stroke="#aab2bd" stroke-width=".7"/><line x1="${left}" x2="${width - right}" y1="${baseline}" y2="${baseline}" stroke="#dce1e8" stroke-width=".7"/><line x1="${left}" x2="${width - right}" y1="${topAxis}" y2="${topAxis}" stroke="#e5e9ee" stroke-width=".7"/>`;
  const probabilityCandidates = [.5, .01, .99, .1, .9, .001, .999];
  const selected = [];
  for (const probability of probabilityCandidates) {
    const score = Math.log(probability / (1 - probability));
    const position = x(score);
    if (position >= left + 24 && position <= width - right - 24 && selected.every((item) => Math.abs(item.position - position) >= 72)) selected.push({ probability, position });
  }
  for (const tick of selected.sort((a, b) => a.position - b.position)) {
    const label = `${(tick.probability * 100).toLocaleString('en-US', { maximumFractionDigits: 1 })}%`;
    content += `<line x1="${f(tick.position)}" x2="${f(tick.position)}" y1="${topAxis - 5}" y2="${topAxis}" stroke="#b5bdc8" stroke-width=".7"/><text x="${f(tick.position)}" y="${topAxis - 11}" text-anchor="middle" fill="#67717e" font-size="14">${label}</text>`;
  }
  content += `<text x="${left + plotWidth / 2}" y="17" text-anchor="middle" font-size="15" fill="#67717e">Predicted probability</text>`;
  for (const label of [1, 0]) {
    const group = reference.groups.find((item) => Number(item.label) === label);
    const positive = label === 1;
    const color = positive ? '#C75450' : '#2868B2';
    const sign = positive ? -1 : 1;
    if (!group || !group.n || !group.x?.length) {
      content += `<text x="${left + plotWidth / 2}" y="${baseline + sign * 35}" text-anchor="middle" fill="#67717e" font-size="14">${positive ? 'No positive reference images' : 'No negative reference images'}</text>`;
      continue;
    }
    const points = group.x.map((value, index) => [x(value), baseline + sign * halfHeight * Math.max(0, Math.min(1, Number(group.density[index]) || 0))]);
    if (points.length === 1) {
      content += `<line x1="${f(points[0][0])}" x2="${f(points[0][0])}" y1="${baseline}" y2="${f(points[0][1])}" stroke="${color}" stroke-width="2"><title>RVL ${positive ? 'positive' : 'negative'}: n=${count(group.n)}, score ${number(group.median)}</title></line>`;
      continue;
    }
    const path = `M${f(points[0][0])},${baseline} ` + points.map(([px, py]) => `L${f(px)},${f(py)}`).join(' ') + ` L${f(points.at(-1)[0])},${baseline}Z`;
    content += `<path d="${path}" fill="${color}" fill-opacity=".62" stroke="${color}" stroke-opacity=".9" stroke-width="1"><title>RVL ${positive ? 'positive' : 'negative'}: n=${count(group.n)}, median ${number(group.median)}, IQR ${number(group.q1)}–${number(group.q3)}</title></path>`;
  }
  content += `<line x1="${f(x(0))}" x2="${f(x(0))}" y1="88" y2="${axis}" stroke="#9aa4b1" stroke-width="1" stroke-dasharray="3 4"/>`;
  if (result) {
    const position = x(result.score);
    const tagWidth = 174, tagX = Math.max(left, Math.min(width - right - tagWidth, position - tagWidth / 2));
    content += `<line x1="${f(position)}" x2="${f(position)}" y1="88" y2="${axis}" stroke="#252a34" stroke-width="3"/><circle cx="${f(position)}" cy="${baseline}" r="4.5" fill="#252a34" stroke="white" stroke-width="1.6"/><rect x="${f(tagX)}" y="57" width="${tagWidth}" height="27" rx="3" fill="#eff1f4"/><text x="${f(tagX + tagWidth / 2)}" y="76" text-anchor="middle" font-size="15" fill="#252a34">${number(result.score, 3)} · ${number(result.probability * 100, 1)}%</text>`;
  }
  content += `<text x="${left + plotWidth / 2}" y="252" text-anchor="middle" font-size="15" fill="#67717e">RVL Score</text>`;
  return `<svg viewBox="0 0 ${width} 260" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escapeHtml(`${cohortLabel(reference.cohort, reference.cohort_label)} RVL score reference distribution${result ? `, Score ${number(result.score, 3)}, probability ${number(result.probability * 100, 1)}%` : ''}`)}" font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif">${content}</svg>`;
}

function renderDistribution() {
  const reference = state.reference;
  const incompatible = state.result?.model?.reference_compatible === false;
  document.querySelector('.chart-legend').classList.toggle('hidden', incompatible);
  if (incompatible) $('distributionChart').innerHTML = `<div class="chart-empty">No matching reference for these weights</div>`;
  else if (state.referencePending) $('distributionChart').innerHTML = `<div class="chart-empty">Loading reference…</div>`;
  else if (state.referenceError) $('distributionChart').innerHTML = `<div class="chart-empty">${escapeHtml(state.referenceError)}<br><button class="text-button" id="retryReference" type="button">Retry</button></div>`;
  else $('distributionChart').innerHTML = distributionSvg(reference, state.result);
  $('retryReference')?.addEventListener('click', loadReference);
}

function renderReport() {
  state.reportPrintPrepared = false;
  const result = state.result;
  if (!result) { $('reportPage').innerHTML = `<div class="report-empty">A report is available after analysis.</div>`; return; }
  const { snapshot } = result;
  const reference = state.reference;
  const patient = snapshot.patient;
  const e = escapeHtml;
  const datum = (label, value) => `<div><dt>${label}</dt><dd>${e(value || '—')}</dd></div>`;
  const referenceTitle = cohortLabel(reference?.cohort || $('cohort').value, reference?.cohort_label);
  const compatible = result.model?.reference_compatible !== false;
  const pngImage = (value) => typeof value === 'string' && value.startsWith('data:image/png;base64,') ? value : null;
  const reportImage = pngImage(result.image?.input_preview);
  const includeAttribution = ['ready', 'unavailable'].includes(result.attribution?.status);
  const attribution = result.attribution?.status === 'ready' ? result.attribution : null;
  const imageLegend = !includeAttribution ? '' : attribution && !attribution.empty
    ? `<div class="report-heatmap-key" role="img" aria-label="Relative contribution toward a higher RVL Score, from low to high"><span>Low</span><span class="report-heatmap-scale" aria-hidden="true"></span><span>High</span><span class="report-heatmap-key-label">Relative attribution</span></div>`
    : `<p class="report-image-note">${attribution ? 'No positive contribution displayed' : 'Heatmap unavailable'}</p>`;
  const imagePanel = (label, source, unavailable) => `<figure class="report-image"><div class="report-image-frame">${source ? `<img src="${e(source)}" alt="${e(label)} of the analyzed field">` : `<span class="report-image-placeholder">${unavailable}</span>`}</div><figcaption>${label}</figcaption></figure>`;
  const chart = !compatible ? `<div class="chart-empty">No matching reference for these weights</div>` : state.referencePending ? `<div class="chart-empty">Loading reference…</div>` : state.referenceError ? `<div class="chart-empty">Reference distribution unavailable</div>` : distributionSvg(reference, result).replace('fill="#eff1f4"', 'fill="#252a34"').replace('font-size="15" fill="#252a34"', 'font-size="15" fill="#ffffff"');
  const institution = (snapshot.institution || '').trim();
  const showInstitution = institution && institution.toLowerCase() !== 'jingwei system';
  const interpretation = result.interpretation || presetInterpretation(result);
  const interpretationPending = state.interpretationPending && state.interpretationResult === result;
  const interpretationStatus = interpretationPending ? 'Preparing interpretation…' : interpretation.source === 'llm' ? 'AI-assisted' : '';
  const printedAt = new Date();
  const reportDate = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    second: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset',
  });
  const printedLabel = `Printed ${reportDate.format(printedAt)}`;
  $('reportPrintMetadata').textContent = `@page { @bottom-left { content: ${JSON.stringify(printedLabel)}; } }`;
  const pageRule = $('reportPrintMetadata').sheet.cssRules[0];
  $('reportPage').classList.toggle('print-margin-boxes', Array.from(pageRule.cssRules || []).some((rule) => rule.cssText.startsWith('@bottom-left')));
  $('printReport').disabled = (compatible && state.referencePending) || interpretationPending;
  $('reportPage').innerHTML = `
    <header class="report-header"><div class="report-brand-group"><span class="report-brand-label"><img class="brand-wordmark" src="/jingwei-wordmark.svg?v=20261010" alt="JingWei"> <small class="report-brand-companion">精卫</small></span>${showInstitution ? `<span class="report-institution">${e(institution)}</span>` : ''}</div><span class="report-header-meta">Clinical report</span></header>
    <div class="report-title-block"><h1 class="report-title">Retinal Vascular Leakage Assessment</h1><p class="report-subtitle">Assisted assessment report</p></div>
    <div class="report-metadata"><span>Report ID: <span class="report-id">${e(result.id)}</span></span><span>Analyzed: <time datetime="${e(result.timestamp)}">${e(reportDate.format(new Date(result.timestamp)))}</time></span></div>
    <dl class="report-patient">${datum('Patient name', patient.name)}${datum('Patient ID', patient.id)}${datum('Exam date', patient.date)}${datum('Eye', eyeLabel(patient.eye))}${datum('Referring clinician', patient.physician)}${datum('Modality', result.modality.toUpperCase())}</dl>
    <h2 class="report-section-title report-section-primary">Assessment results</h2>
    <div class="report-measurements${includeAttribution ? '' : ' report-measurements-with-image'}"><dl class="report-result-fields"><div><dt>RVL Score</dt><dd>${number(result.score, 3)}</dd></div><div><dt>Predicted probability</dt><dd>${number(result.probability * 100, 1)}<span>%</span></dd></div><div><dt>RVL prediction</dt><dd><strong class="report-prediction-value">${result.positive ? 'Positive' : 'Negative'}</strong></dd></div></dl>${includeAttribution ? '' : imagePanel(snapshot.aiGeneratedSample ? 'AI-generated sample' : 'Original', reportImage, 'Analyzed image unavailable')}</div>
    ${includeAttribution ? `<h2 class="report-section-title">Contributing regions</h2><div class="report-images">${imagePanel(snapshot.aiGeneratedSample ? 'AI-generated sample' : 'Original', reportImage, 'Analyzed image unavailable')}${imagePanel('Heatmap', pngImage(attribution?.heatmap), 'Heatmap unavailable')}${imagePanel('Overlay', pngImage(attribution?.overlay), 'Overlay unavailable')}</div>${imageLegend}` : ''}
    <h2 class="report-section-title">Reference distribution</h2>
    <div class="report-distribution"><div class="report-chart-legend ${compatible ? '' : 'hidden'}"><span><i class="legend-dot positive"></i>RVL positive</span><span><i class="legend-dot negative"></i>RVL negative</span><span><i class="legend-individual"></i>This image</span></div>${chart}${compatible ? `<div class="report-reference-note">FFA reference · ${e(referenceTitle)}</div>` : ''}</div>
    <section class="report-interpretation"><h2 class="report-section-title">Interpretation${interpretationStatus ? `<span class="report-interpretation-status${interpretationPending ? ' report-interpretation-pending' : ''}">${e(interpretationStatus)}</span>` : ''}</h2><p class="report-interpretation-text">${e(interpretation.text)}</p></section>
    <div class="report-signature"><span>Reviewed by <i class="signature-line"></i></span><span>Review date <i class="signature-line"></i></span></div>
    <footer class="report-footer"><time datetime="${printedAt.toISOString()}">${e(printedLabel)}</time><span class="report-preview-page">Page 1 of 1</span></footer>`;
}

function installPreviewControls() {
  let controls = $('previewControls');
  if (!controls) {
    controls = document.createElement('div');
    controls.id = 'previewControls';
    controls.className = 'preview-controls hidden';
    controls.innerHTML = `<div class="preview-tabs" role="group" aria-label="Image preview"><button type="button" class="selected" data-preview="original" aria-pressed="true">Original</button><button type="button" data-preview="input" aria-pressed="false">Model input</button></div>`;
    $('dropZone').insertAdjacentElement('afterend', controls);
  }
  let note = $('previewNote');
  if (!note) {
    note = document.createElement('p');
    note.id = 'previewNote';
    $('imageFilename').parentElement.insertAdjacentElement('afterend', note);
  }
  note.className = 'preview-note hidden';
  note.textContent = '';
  document.querySelectorAll('[data-preview]').forEach((button) => button.addEventListener('click', () => showPreview(button.dataset.preview)));
}


async function initialize() {
  installPreviewControls();
  $('examDate').value = localDate();
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
  document.querySelector('.brand').addEventListener('click', (event) => { event.preventDefault(); setView('workspace'); });
  document.querySelectorAll('[data-modality]').forEach((button) => button.addEventListener('click', () => changeModality(button.dataset.modality)));
  $('settingsForm').addEventListener('submit', saveSettings);
  $('device').addEventListener('change', renderDeviceStatus);
  $('llmEnabled').addEventListener('change', renderLlmSettings);
  $('llmApiKey').addEventListener('input', () => { if ($('llmApiKey').value) state.clearLlmApiKey = false; renderLlmSettings(); });
  $('clearLlmKey').addEventListener('click', () => { $('llmApiKey').value = ''; $('llmEnabled').checked = false; state.clearLlmApiKey = true; renderLlmSettings(); });
  $('newCase').addEventListener('click', newCase);
  $('useSample').addEventListener('click', useSample);
  $('cohort').addEventListener('change', loadReference);
  $('dropZone').addEventListener('click', () => $('imageInput').click());
  $('imageInput').addEventListener('change', (event) => analyzeFile(event.target.files[0]));
  $('imagePreview').addEventListener('error', () => { $('imagePreview').classList.add('hidden'); $('dropContent').classList.remove('hidden'); if (state.predictionPending) $('dropContent').querySelector('strong').textContent = 'Reading image…'; });
  $('imagePreview').addEventListener('load', () => { $('imagePreview').classList.remove('hidden'); $('dropContent').classList.add('hidden'); });
  for (const name of ['dragenter', 'dragover']) $('dropZone').addEventListener(name, (event) => { event.preventDefault(); $('dropZone').classList.add('drag-over'); });
  $('dropZone').addEventListener('dragleave', () => $('dropZone').classList.remove('drag-over'));
  $('dropZone').addEventListener('drop', (event) => {
    event.preventDefault(); $('dropZone').classList.remove('drag-over');
    const files = event.dataTransfer.files;
    if (files.length !== 1) { invalidatePrediction(); setNotice('predictionError', 'Upload one image at a time.', true); renderResult(); return; }
    analyzeFile(files[0]);
  });
  // Prevent a dropped medical image outside the upload zone from navigating away from the local application.
  document.addEventListener('dragover', (event) => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
  document.addEventListener('drop', (event) => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
  $('openReport').addEventListener('click', () => setView('report'));
  $('backWorkspace').addEventListener('click', () => setView('workspace'));
  $('printReport').addEventListener('click', async () => {
    const result = state.result;
    renderReport();
    if ($('printReport').disabled) return;
    // Licensed local faces are optional in the public source distribution.
    await Promise.allSettled([
      '300 10pt "Helvetica Neue LT Std Light"', '700 11pt "Helvetica Neue LT Std Bold"',
      '700 11pt "Helvetica Neue LT Std Bold Condensed"',
    ].map((font) => document.fonts.load(font)));
    await document.fonts.ready;
    if (state.result !== result || state.view !== 'report') return;
    renderReport();
    if ($('printReport').disabled) return;
    const images = Array.from($('reportPage').querySelectorAll('img'));
    try {
      await Promise.all(images.map((image) => image.decode()));
    } catch {
      if (state.result === result && images.every((image) => image.isConnected)) window.alert('Report images could not load. Refresh the page and try again.');
      return;
    }
    if (state.result !== result || state.view !== 'report' || $('printReport').disabled || images.some((image) => !image.isConnected)) return;
    state.reportPrintPrepared = true;
    window.print();
  });
  window.addEventListener('beforeprint', () => { if (!state.reportPrintPrepared) renderReport(); });
  window.addEventListener('afterprint', () => { state.reportPrintPrepared = false; });
  for (const field of ['patientId', 'patientName', 'eye', 'examDate', 'physician']) $(field).addEventListener('input', updatePatientDirty);
  $('applyPatient').addEventListener('click', () => { if (!state.result) return; state.result.snapshot.patient = patientInformation(); updatePatientDirty(); });
  populateSettings();
  renderResult();
  await Promise.allSettled([
    api('/api/settings').then((settings) => { state.settings = settings; populateSettings(); renderHealth(); }).catch(() => setNotice('serviceNotice', 'Could not load settings. Start the service and refresh.', true)),
    refreshHealth(), loadReference(),
  ]);
}

initialize();
