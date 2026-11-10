'use strict';

const $ = id => document.getElementById(id);
const state = { token: '', images: [], index: -1, image: null, busy: false, closed: false,
  folder: 'images', revision: 0, exportedRevision: 0, sourceUrl: null, cropUrl: null, rect: null,
  view: { zoom: 1, center: [0, 0] }, moveMode: false, spaceDown: false, pointer: null };
const supported = new Set(['jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff', 'gif', 'webp']);
const current = () => state.images[state.index];
const keptCount = () => state.images.filter(item => item.kept).length;
const unexported = () => state.revision !== state.exportedRevision;

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'X-Clip-Token': state.token, ...options.headers } });
  if (!response.ok) {
    let message = `The request could not be completed (${response.status}).`;
    let metadata = null;
    try { metadata = await response.json(); message = metadata.error || message; } catch (_) { /* Non-JSON service failure. */ }
    const error = new Error(message);
    error.apiMetadata = metadata;
    throw error;
  }
  return response;
}

function jsonPost(path, data) {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

function status(message, error = false) {
  $('status').textContent = message;
  $('status').closest('.status-line').classList.toggle('error', error);
}

function controls() {
  const item = current();
  const blocked = state.busy || !state.token || state.closed;
  for (const id of ['chooseFolder', 'chooseImages', 'quitButton', 'apiSettingsButton']) $(id).disabled = blocked;
  $('exportButton').disabled = blocked || !keptCount();
  $('previousButton').disabled = blocked || state.index <= 0;
  $('nextButton').disabled = blocked || state.index < 0 || state.index >= state.images.length - 1;
  $('resetButton').disabled = blocked || !item?.points.length;
  $('keepButton').disabled = blocked || !state.image || item?.points.length !== 2 || radius(item.points) <= 0;
  $('keepButtonLabel').textContent = item && state.index < state.images.length - 1 ? 'Keep crop & next' : 'Keep crop';
  const noImage = blocked || !state.image;
  for (const id of ['autoPlaceButton', 'fitButton', 'moveButton']) $(id).disabled = noImage;
  $('zoomInButton').disabled = noImage || state.view.zoom >= 8;
  $('zoomOutButton').disabled = noImage || state.view.zoom <= 1;
  $('apiKey').disabled = blocked;
  $('apiBaseUrl').disabled = blocked;
  $('apiModel').disabled = blocked;
  $('zoomLevel').textContent = `${Number(state.view.zoom.toFixed(2))}×`;
  $('moveButton').setAttribute('aria-pressed', String(state.moveMode));
  $('sourceCanvas').classList.toggle('moving', state.moveMode || state.spaceDown);
  $('sourceCanvas').classList.toggle('dragging', !!state.pointer && state.pointer.kind !== 'place');
  $('sourceStage').classList.toggle('busy', state.busy);
  $('exportCount').textContent = keptCount();
  $('queueSummary').textContent = state.images.length ? `${state.images.length} image${state.images.length === 1 ? '' : 's'} · ${keptCount()} kept` : 'No images selected';
  $('imagePosition').textContent = item ? `${state.index + 1} / ${state.images.length}` : '—';
  $('firstStep').classList.toggle('active', !!item && !item.points.length);
  $('firstStep').classList.toggle('done', !!item?.points.length);
  $('secondStep').classList.toggle('active', item?.points.length === 1);
  $('secondStep').classList.toggle('done', item?.points.length === 2);
  $('firstStatus').textContent = item?.points.length ? (item.suggested ? 'Suggested' : 'Selected') : 'Select first';
  $('secondStatus').textContent = item?.points.length === 2 ? (item.suggested ? 'Suggested' : 'Selected') : 'Crop centre';
}

async function run(action) {
  if (state.busy || state.closed) return;
  state.busy = true;
  controls();
  try { await action(); } catch (error) { status(error.message, true); }
  finally { state.busy = false; controls(); }
}

function releaseUrl(key) {
  if (state[key]) URL.revokeObjectURL(state[key]);
  state[key] = null;
}

async function loadImage(blob, key) {
  releaseUrl(key);
  state[key] = URL.createObjectURL(blob);
  const image = new Image();
  image.src = state[key];
  await image.decode();
  return image;
}

async function importFiles(fileList, folderMode) {
  const files = Array.from(fileList).filter(file => {
    const path = file.webkitRelativePath || file.name;
    return !file.name.startsWith('.') && supported.has(file.name.split('.').pop().toLowerCase()) &&
      (!folderMode || path.split('/').length === 2);
  }).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
  if (!files.length) { status('No supported images were found. Choose images from the top level of a folder.', true); return; }
  if (unexported() && !window.confirm('Some kept crops have not been exported. Replace this image set and discard those crops?')) return;
  await run(async () => {
    const folder = folderMode ? files[0].webkitRelativePath.split('/')[0] : 'images';
    await jsonPost('/api/reset', { folder });
    Object.assign(state, { images: [], index: -1, image: null, folder, revision: 0, exportedRevision: 0 });
    releaseUrl('sourceUrl'); releaseUrl('cropUrl');
    $('importNotice').classList.add('hidden');
    render();
    const errors = [];
    for (let i = 0; i < files.length; i++) {
      status(`Opening image ${i + 1} of ${files.length}…`);
      try {
        const response = await api(`/api/images?name=${encodeURIComponent(files[i].name)}`, { method: 'POST', body: files[i] });
        state.images.push({ ...await response.json(), points: [], kept: false, savedPoints: null });
      } catch (error) { errors.push(`${files[i].name}: ${error.message}`); }
    }
    if (errors.length) {
      $('importNotice').textContent = `${errors.length} image${errors.length === 1 ? '' : 's'} could not be opened. ${errors.join(' · ')}`;
      $('importNotice').classList.remove('hidden');
    }
    if (state.images.length) await showImage(0);
    else status('No images could be opened. Please choose another image set.', true);
  });
}

async function showImage(index) {
  state.index = index;
  state.image = null;
  state.pointer = null;
  state.rect = null;
  state.view = { zoom: 1, center: [current().width / 2, current().height / 2] };
  releaseUrl('cropUrl');
  render();
  const item = current();
  status(`Opening ${item.name}…`);
  try {
    const response = await api(`/api/images/${item.id}/source`);
    state.image = await loadImage(await response.blob(), 'sourceUrl');
    render();
    pointPrompt();
  } catch (error) { render(); throw error; }
}

function pointPrompt() {
  const item = current();
  if (!item) return;
  if (hasUnkeptChanges(item)) status('Unkept changes. Export still uses the last kept crop.');
  else if (!item.points.length) status('Click the optic disc.');
  else if (item.points.length === 1) status('Click the macular centre.');
  else if (!radius(item.points)) status('The two landmarks must be at different positions. Drag either point to adjust.', true);
  else status(item.kept && samePoints(item.points, item.savedPoints) ? 'Crop kept.' : 'Drag either point to adjust, then keep the crop.');
}

const radius = points => points?.length === 2 ? 1.5 * Math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1]) : 0;
const samePoints = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const hasUnkeptChanges = item => !!item?.kept && !samePoints(item.points, item.savedPoints);
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

function cropBounds(item) {
  const r = radius(item.points);
  const [x, y] = item.points[1];
  const left = Math.max(0, Math.floor(x - r));
  const top = Math.max(0, Math.floor(y - r));
  const right = Math.min(item.width, Math.ceil(x + r));
  const bottom = Math.min(item.height, Math.ceil(y + r));
  return { left, top, width: right - left, height: bottom - top, x, y, r };
}

function render() {
  const item = current();
  const hasImage = !!state.image;
  $('sourceEmpty').classList.toggle('hidden', hasImage);
  $('sourceCanvas').classList.toggle('hidden', !hasImage);
  $('sourceStage').classList.toggle('loaded', hasImage);
  $('filename').textContent = item?.name || 'No image selected';
  $('filename').title = item?.name || '';
  $('dimensions').textContent = item ? `${item.width} × ${item.height} px` : '';
  $('savedPreview').classList.add('hidden');
  if (hasImage) drawSource();
  drawPreview();
  drawApiUsage();
  controls();
}

function drawApiUsage() {
  const request = current()?.lastApi;
  const summary = $('apiUsageSummary'), detail = $('apiUsageDetail');
  $('apiUsage').title = '';
  if (!request) { summary.textContent = 'No API request yet'; detail.textContent = 'Input — · Output —'; return; }
  const seconds = request.pending ? (performance.now() - request.startedAt) / 1000 : request.elapsed_seconds;
  const time = Number.isFinite(seconds) ? `${seconds.toFixed(1)} s` : '—';
  if (request.pending) {
    summary.textContent = `${time} · Locating points…`;
    detail.textContent = 'Token usage pending';
    return;
  }
  const count = value => Number.isInteger(value) && value >= 0 ? value.toLocaleString('en-US') : '—';
  const usage = request.usage;
  summary.textContent = `${time} · Total ${count(usage?.total_tokens)} tokens`;
  detail.textContent = usage ? `Input ${count(usage.input_tokens)} · Output ${count(usage.output_tokens)}` : 'Token usage unavailable';
  $('apiUsage').title = [request.model, usage && `Cached input ${count(usage.cached_input_tokens)} · Reasoning ${count(usage.reasoning_tokens)}`].filter(Boolean).join('\n');
}

function apiMetadata(data, model, elapsed) {
  return { model: data?.model || model, elapsed_seconds: Number.isFinite(data?.elapsed_seconds) ? data.elapsed_seconds : elapsed, usage: data?.usage || null };
}

function badgePosition(point, rect = state.rect) {
  return [
    Math.min(rect.x + rect.width - 13, Math.max(rect.x + 13, rect.x + point[0] * rect.scale + 17)),
    Math.min(rect.y + rect.height - 13, Math.max(rect.y + 13, rect.y + point[1] * rect.scale - 16))
  ];
}

function drawSource() {
  const canvas = $('sourceCanvas');
  const box = canvas.getBoundingClientRect();
  if (!box.width || !box.height) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(box.width * dpr); canvas.height = Math.round(box.height * dpr);
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const item = current();
  const scale = Math.min((box.width - 32) / item.width, (box.height - 32) / item.height) * state.view.zoom;
  const width = item.width * scale, height = item.height * scale;
  const halfWidth = Math.min(item.width / 2, (box.width / 2 - 16) / scale);
  const halfHeight = Math.min(item.height / 2, (box.height / 2 - 16) / scale);
  state.view.center[0] = clamp(state.view.center[0], halfWidth, item.width - halfWidth);
  state.view.center[1] = clamp(state.view.center[1], halfHeight, item.height - halfHeight);
  const x = box.width / 2 - state.view.center[0] * scale;
  const y = box.height / 2 - state.view.center[1] * scale;
  state.rect = { x, y, width, height, scale };
  ctx.drawImage(state.image, x, y, width, height);
  ctx.save(); ctx.beginPath(); ctx.rect(x, y, width, height); ctx.clip();
  if (item.points.length === 2) {
    const [cx, cy] = item.points[1];
    ctx.beginPath(); ctx.arc(x + cx * scale, y + cy * scale, radius(item.points) * scale, 0, Math.PI * 2);
    ctx.strokeStyle = '#A9CFD0'; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x + item.points[0][0] * scale, y + item.points[0][1] * scale);
    ctx.lineTo(x + cx * scale, y + cy * scale); ctx.setLineDash([3, 4]);
    ctx.strokeStyle = '#ffffffa6'; ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
  }
  item.points.forEach(([px, py], index) => {
    const cx = x + px * scale, cy = y + py * scale;
    ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2); ctx.fillStyle = index ? '#A9CFD0' : '#ffffff'; ctx.fill();
    ctx.strokeStyle = '#006D5B'; ctx.lineWidth = 1.5; ctx.stroke();
    const [labelX, labelY] = badgePosition([px, py]);
    ctx.beginPath(); ctx.arc(labelX, labelY, 10, 0, Math.PI * 2); ctx.fillStyle = '#006D5Be8'; ctx.fill();
    ctx.font = '500 11px -apple-system, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#fff'; ctx.fillText(String(index + 1), labelX, labelY);
  });
  ctx.restore();
}

function drawPreview() {
  const item = current();
  const ready = !!state.image && item?.points.length === 2 && radius(item.points) > 0;
  $('previewEmpty').classList.toggle('hidden', ready);
  $('previewCanvas').classList.toggle('hidden', !ready);
  $('previewStage').classList.toggle('has-crop', ready);
  $('cropState').textContent = hasUnkeptChanges(item) ? 'Unkept changes' : ready ? (item.kept ? 'Kept' : 'Preview') : 'Awaiting points';
  if (!ready) return;
  const bounds = cropBounds(item);
  const canvas = $('previewCanvas');
  const scale = Math.min(900 / bounds.width, 900 / bounds.height, 1);
  canvas.width = Math.max(1, Math.round(bounds.width * scale));
  canvas.height = Math.max(1, Math.round(bounds.height * scale));
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.scale(scale, scale);
  ctx.beginPath(); ctx.arc(bounds.x - bounds.left, bounds.y - bounds.top, bounds.r, 0, Math.PI * 2); ctx.clip();
  ctx.drawImage(state.image, -bounds.left, -bounds.top, item.width, item.height);
}

function canvasPosition(event) {
  const box = $('sourceCanvas').getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
}

function imagePosition(position) {
  return [(position[0] - state.rect.x) / state.rect.scale, (position[1] - state.rect.y) / state.rect.scale];
}

function pointsChanged() {
  current().suggested = false;
  releaseUrl('cropUrl'); render(); pointPrompt();
}

function pointerDown(event) {
  if (event.button !== 0 || state.busy || !state.image || !state.rect || state.closed || state.pointer) return;
  event.preventDefault();
  $('sourceCanvas').focus({ preventScroll: true });
  const position = canvasPosition(event);
  const item = current();
  let index = item.points.findIndex(point => {
    const [x, y] = badgePosition(point);
    return Math.hypot(position[0] - x, position[1] - y) <= 12;
  });
  if (index < 0) index = item.points.findIndex(([x, y]) => Math.hypot(position[0] - state.rect.x - x * state.rect.scale, position[1] - state.rect.y - y * state.rect.scale) <= 15);
  const kind = state.moveMode || state.spaceDown ? 'pan' : index >= 0 ? 'point' : 'place';
  state.pointer = { id: event.pointerId, kind, index, start: position, point: index >= 0 ? [...item.points[index]] : null, center: [...state.view.center], moved: false };
  $('sourceCanvas').setPointerCapture(event.pointerId);
  controls();
}

function pointerMove(event) {
  const pointer = state.pointer;
  if (state.busy || state.closed || !pointer || pointer.id !== event.pointerId) return;
  const position = canvasPosition(event);
  const dx = position[0] - pointer.start[0], dy = position[1] - pointer.start[1];
  if (Math.hypot(dx, dy) > 3) pointer.moved = true;
  if (!pointer.moved) return;
  if (pointer.kind === 'point') {
    const item = current();
    const [x, y] = [pointer.point[0] + dx / state.rect.scale, pointer.point[1] + dy / state.rect.scale];
    item.points[pointer.index] = [clamp(x, 0, item.width - 1), clamp(y, 0, item.height - 1)];
    pointsChanged();
  } else if (pointer.kind === 'pan') {
    state.view.center = [pointer.center[0] - dx / state.rect.scale, pointer.center[1] - dy / state.rect.scale];
    drawSource();
  }
}

function pointerUp(event) {
  const pointer = state.pointer;
  if (!pointer || pointer.id !== event.pointerId) return;
  if (!state.busy && !state.closed && event.type === 'pointerup' && pointer.kind === 'place' && !pointer.moved) {
    const item = current();
    const [x, y] = imagePosition(canvasPosition(event));
    if (item.points.length < 2 && x >= 0 && y >= 0 && x < item.width && y < item.height) {
      item.points.push([x, y]);
      pointsChanged();
    } else if (item.points.length === 2) pointPrompt();
  }
  state.pointer = null;
  if ($('sourceCanvas').hasPointerCapture(event.pointerId)) $('sourceCanvas').releasePointerCapture(event.pointerId);
  controls();
}

function zoomImage(factor, anchor) {
  if (state.busy || state.closed || !state.image || !state.rect || state.pointer) return;
  const box = $('sourceCanvas').getBoundingClientRect();
  anchor ||= [box.width / 2, box.height / 2];
  const point = imagePosition(anchor);
  const zoom = clamp(state.view.zoom * factor, 1, 8);
  const scale = state.rect.scale * zoom / state.view.zoom;
  state.view = { zoom, center: [point[0] - (anchor[0] - box.width / 2) / scale, point[1] - (anchor[1] - box.height / 2) / scale] };
  drawSource(); controls();
}

function fitImage() {
  if (state.busy || state.closed || !state.image) return;
  state.view = { zoom: 1, center: [current().width / 2, current().height / 2] };
  drawSource(); controls();
}

async function autoPlacePoints() {
  if ($('autoPlaceButton').disabled) return;
  const apiKey = $('apiKey').value.trim();
  const baseUrl = $('apiBaseUrl').value.trim() || 'https://api.openai.com/v1';
  const model = $('apiModel').value.trim() || 'gpt-6-sol';
  if (!apiKey) {
    openApiSettings();
    status('Add your API key to auto-place the two points.');
    return;
  }
  await run(async () => {
    const item = current();
    const startedAt = performance.now();
    item.lastApi = { model, pending: true, startedAt };
    drawApiUsage();
    const timer = setInterval(drawApiUsage, 100);
    status('Locating the optic disc and macular centre…');
    $('autoPlaceButton').setAttribute('aria-busy', 'true');
    try {
      const response = await jsonPost(`/api/images/${item.id}/landmarks`, { api_key: apiKey, base_url: baseUrl, model });
      const points = await response.json();
      item.lastApi = apiMetadata(points, model, (performance.now() - startedAt) / 1000);
      item.points = [points.first, points.center];
      item.suggested = true;
      releaseUrl('cropUrl'); render();
      if (hasUnkeptChanges(item)) pointPrompt();
      else status('Suggested points are ready. Drag either point to adjust.');
    } catch (error) {
      item.lastApi = apiMetadata(error.apiMetadata, model, (performance.now() - startedAt) / 1000);
      throw error;
    } finally {
      clearInterval(timer);
      $('autoPlaceButton').setAttribute('aria-busy', 'false');
      drawApiUsage();
    }
  });
}

function openApiSettings() {
  state.spaceDown = false;
  $('apiSettings').showModal();
  $('apiKey').focus();
  controls();
}

function resetPoints() {
  if (state.busy || !current() || state.closed) return;
  const pointer = state.pointer;
  state.pointer = null;
  if (pointer && $('sourceCanvas').hasPointerCapture(pointer.id)) $('sourceCanvas').releasePointerCapture(pointer.id);
  current().points = [];
  pointsChanged();
}

async function keepCrop() {
  if ($('keepButton').disabled) return;
  await run(async () => {
    const item = current();
    const points = item.points.map(point => [...point]);
    status('Keeping crop at original resolution…');
    await jsonPost(`/api/images/${item.id}/crop`, { first: points[0], center: points[1] });
    item.kept = true; item.savedPoints = points; state.revision++;
    if (state.index < state.images.length - 1) {
      await showImage(state.index + 1);
      status(`Crop kept. ${current().points.length ? 'Review the next photograph.' : 'Click the optic disc on the next photograph.'}`);
    } else {
      const response = await api(`/api/images/${item.id}/crop`);
      const image = await loadImage(await response.blob(), 'cropUrl');
      $('savedPreview').src = image.src;
      $('previewCanvas').classList.add('hidden'); $('savedPreview').classList.remove('hidden');
      $('cropState').textContent = 'Kept';
      status(`${keptCount()} of ${state.images.length} crops kept. Export your crops, or go back to review other images.`);
    }
  });
}

async function exportCrops() {
  if ($('exportButton').disabled) return;
  let destination;
  try {
    if (typeof window.showSaveFilePicker === 'function') {
      destination = window.showSaveFilePicker({ suggestedName: `${state.folder}_clip.zip`, types: [{ description: 'ZIP archive', accept: { 'application/zip': ['.zip'] } }] });
    }
  } catch (error) { status(error.message, true); return; }
  await run(async () => {
    let file;
    try { if (destination) file = await destination; }
    catch (error) {
      if (error.name === 'AbortError') { status('Export cancelled. Your crops are still kept.'); return; }
      throw error;
    }
    status('Preparing your crop download…');
    const response = await api('/api/export');
    const blob = await response.blob();
    if (file) {
      const writable = await file.createWritable();
      try { await writable.write(blob); await writable.close(); }
      catch (error) { try { await writable.abort(); } catch (_) { /* The stream may already be closed. */ } throw error; }
      state.exportedRevision = state.revision;
      status(`ZIP saved with ${keptCount()} crop${keptCount() === 1 ? '' : 's'}.`);
      return;
    }
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = `${state.folder}_clip.zip`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    status('ZIP download started. Check it is saved before closing.');
  });
}

$('chooseFolder').addEventListener('click', () => $('folderInput').click());
$('chooseImages').addEventListener('click', () => $('imageInput').click());
for (const [id, folderMode] of [['folderInput', true], ['imageInput', false]]) {
  $(id).addEventListener('change', async event => {
    const files = Array.from(event.target.files); event.target.value = '';
    if (files.length) await importFiles(files, folderMode);
  });
}
$('sourceCanvas').addEventListener('pointerdown', pointerDown);
$('sourceCanvas').addEventListener('pointermove', pointerMove);
$('sourceCanvas').addEventListener('pointerup', pointerUp);
$('sourceCanvas').addEventListener('pointercancel', pointerUp);
$('sourceCanvas').addEventListener('wheel', event => {
  if (!state.image || state.busy || state.closed) return;
  event.preventDefault();
  zoomImage(Math.exp(-event.deltaY * (event.deltaMode === 1 ? .025 : .002)), canvasPosition(event));
}, { passive: false });
$('zoomInButton').addEventListener('click', () => zoomImage(1.25));
$('zoomOutButton').addEventListener('click', () => zoomImage(1 / 1.25));
$('fitButton').addEventListener('click', fitImage);
$('moveButton').addEventListener('click', () => { state.moveMode = !state.moveMode; controls(); });
$('autoPlaceButton').addEventListener('click', autoPlacePoints);
$('apiSettingsButton').addEventListener('click', openApiSettings);
$('closeApiSettings').addEventListener('click', () => $('apiSettings').close());
$('apiSettings').addEventListener('close', () => $('apiSettingsButton').focus());
$('resetButton').addEventListener('click', resetPoints);
$('previousButton').addEventListener('click', () => run(() => showImage(state.index - 1)));
$('nextButton').addEventListener('click', () => run(() => showImage(state.index + 1)));
$('keepButton').addEventListener('click', keepCrop);
$('exportButton').addEventListener('click', exportCrops);
$('quitButton').addEventListener('click', async () => {
  if (unexported() && !window.confirm('Some kept crops have not been exported. Quit and discard them?')) return;
  await run(async () => {
    try { await jsonPost('/api/shutdown', {}); }
    finally {
      state.closed = true; state.exportedRevision = state.revision;
      $('apiKey').value = '';
      releaseUrl('sourceUrl'); releaseUrl('cropUrl');
      Object.assign(state, { images: [], index: -1, image: null, pointer: null, rect: null, spaceDown: false, moveMode: false });
      render();
    }
    status('This tab is closed. You can close it.');
  });
});
document.addEventListener('keydown', event => {
  if ($('apiSettings').open) return;
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.target.matches('input, textarea, select, button, [contenteditable="true"]')) return;
  if (event.code === 'Space' && state.image && !state.busy && !state.closed) {
    event.preventDefault(); state.spaceDown = true; controls(); return;
  }
  const actions = { Enter: 'keepButton', ArrowLeft: 'previousButton', ArrowRight: 'nextButton', Backspace: 'resetButton' };
  const id = actions[event.key];
  if (id) { event.preventDefault(); if (!state.pointer && !$(id).disabled) $(id).click(); }
});
document.addEventListener('keyup', event => { if (event.code === 'Space') { state.spaceDown = false; controls(); } });
window.addEventListener('blur', () => { state.spaceDown = false; state.pointer = null; controls(); });
window.addEventListener('beforeunload', event => { if ((unexported() || state.busy) && !state.closed) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('pagehide', () => {
  $('apiKey').value = '';
  if (state.token && !state.closed) {
    fetch('/api/close-session', { method: 'POST', headers: { 'X-Clip-Token': state.token, 'Content-Type': 'application/json' }, body: '{}', keepalive: true }).catch(() => {});
  }
});
window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
new ResizeObserver(() => { if (state.image) drawSource(); }).observe($('sourceStage'));
(async () => {
  try {
    const response = await fetch('/api/config');
    if (!response.ok) throw new Error('The local tool is unavailable. Restart CFP Crop and reopen its page.');
    state.token = (await response.json()).token;
    status('Choose a folder or select images to begin.');
  } catch (error) { status(error.message, true); }
  controls();
})();
