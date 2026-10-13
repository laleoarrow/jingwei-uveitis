'use strict';

// Exercise the browser source with controlled requests; no service or credentials are used.
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { Blob, File } = require('node:buffer');
const { test } = require('node:test');
const vm = require('node:vm');

const source = readFileSync(join(__dirname, 'static/app.js'), 'utf8');
const styles = readFileSync(join(__dirname, 'static/styles.css'), 'utf8');
const tick = () => new Promise((resolve) => setImmediate(resolve));
const submit = { preventDefault() {} };

function browser(demo = false, liveHealth = false) {
  const elements = new Map();
  const element = (id) => {
    if (demo && id === 'includeHeatmap') return null;
    if (!elements.has(id)) elements.set(id, {
      value: '', checked: false, textContent: '', innerHTML: '', disabled: false,
      classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
      style: {}, addEventListener() {},
      removeAttribute() {}, replaceChildren() { this.innerHTML = ''; },
      querySelector() { return element(`${id}:child`); },
      sheet: { cssRules: [{ cssRules: [] }] },
    });
    return elements.get(id);
  };
  const requests = [];
  const timeouts = new Map(), intervals = new Map();
  let timerId = 0;
  const images = [], canvases = [];
  class Image {
    constructor() { this.naturalWidth = 1600; this.naturalHeight = 900; images.push(this); }
    decode() { return new Promise((resolve) => { this.finishDecode = resolve; }); }
  }
  const context = vm.createContext({
    document: {
      getElementById: element,
      querySelectorAll: () => [],
      querySelector: element,
      createElement(tag) {
        assert.equal(tag, 'canvas');
        const canvas = {
          getContext: () => ({ drawImage: (...args) => { canvas.drawn = args; } }),
          toBlob(callback, type) { this.finishBlob = () => callback(new Blob(['sample'], { type })); },
        };
        canvases.push(canvas);
        return canvas;
      },
    }, AbortController, performance, Image, File,
    window: {
      scrollTo() {},
      jingweiDemoInterpretation: 'Illustrative result — not calculated from your image.',
      jingweiDemoApi(path, options) {
        return new Promise((resolve) => requests.push({ path, options, respond: resolve }));
      },
    },
    URL: { createObjectURL: () => 'blob:test-image', revokeObjectURL() {} },
    setTimeout(handler, delay) { timeouts.set(++timerId, { handler, delay }); return timerId; },
    clearTimeout(id) { timeouts.delete(id); },
    setInterval(handler, delay) { intervals.set(++timerId, { handler, delay }); return timerId; },
    clearInterval(id) { intervals.delete(id); },
    fetch(path, options) {
      return new Promise((resolve, reject) => {
        requests.push({ path, options, fail: reject,
          respond(data, ok = true) { resolve({ ok, status: ok ? 200 : 400, json: async () => data }); },
        });
        if (path === '/api/health') options.signal?.addEventListener('abort', () => {
          const error = new Error('Request aborted'); error.name = 'AbortError'; reject(error);
        });
      });
    },
  });
  // Skip only automatic page initialization; keep the lifecycle and report functions intact.
  assert.match(source, /\ninitialize\(\);\s*$/);
  const browserSource = demo
    ? readFileSync(join(__dirname, 'docs/app.js'), 'utf8').split('\nconst jingweiInstallPrompt = ')[0]
    : source.replace(/\ninitialize\(\);\s*$/, '');
  const app = vm.runInContext(browserSource + `
    const actualRenderResult = renderResult;
    readFile = async () => 'data:image/png;base64,AA==';
    showPreview = renderResult = updatePatientDirty = populateSettings = () => {};
    ${liveHealth ? '' : 'refreshHealth = async () => {};'}
    ({ state, saveSettings: typeof saveSettings === 'function' ? saveSettings : null,
       ensureInterpretation, analyzeFile, renderReport, useSample, invalidatePrediction,
       refreshHealth, renderHealth, setView,
       renderResult: actualRenderResult,
       startHealthPolling: typeof startHealthPolling === 'function' ? startHealthPolling : null });
  `, context);
  return { ...app, element, requests, images, canvases, timeouts, intervals };
}

function result(revision = 0) {
  return {
    id: 'test-result', timestamp: '2026-01-01T00:00:00Z', modality: 'cfp',
    score: 1, probability: .7, positive: true,
    snapshot: { patient: {}, institution: '', modality: 'cfp' },
    model: { reference_compatible: false }, interpretation: null,
    interpretationSettingsRevision: revision,
  };
}

const analyze = (app) => app.analyzeFile({ name: 'fixture.png', size: 1, type: 'image/png' });
const requestsFor = (app, path) => app.requests.filter((request) => request.path === path);
const finishSave = (app, succeeds) => requestsFor(app, '/api/settings').at(-1)
  .respond(succeeds ? { llm_model: 'next-model' } : { detail: 'Save rejected' }, succeeds);

const healthy = () => ({
  status: 'ok', device: 'mps', available_devices: ['cpu', 'mps'], reference_available: true,
  models: { cfp: { exists: true, loaded: false }, oct: { exists: true, loaded: true } },
  environment: { status: 'available', missing: [] },
  activity: { phase: 'idle', modality: null, elapsed_seconds: 0 },
});

test('health displays dependency, model and live activity states without claiming unloaded weights are ready', () => {
  const app = browser(false, true);
  app.element('device').value = 'auto';
  app.state.health = healthy();
  app.renderHealth();
  assert.equal(app.element('serviceState').textContent, 'Online');
  assert.equal(app.element('environmentState').textContent, 'Dependencies found');
  assert.equal(app.element('activityState').textContent, 'Ready');
  assert.equal(app.element('cfpWeightState').textContent, 'Weights found');
  assert.equal(app.element('octWeightState').textContent, 'Model loaded');
  for (const [phase, expected] of [['analyzing', 'Analyzing OCT'], ['heatmap', 'Generating OCT heatmap'], ['refining', 'Refining OCT heatmap']]) {
    app.state.health.activity = { phase, modality: 'oct', elapsed_seconds: 127.8 };
    app.renderHealth();
    assert.equal(app.element('activityState').textContent, `${expected} · 127 s`);
  }
  app.state.health.environment = { status: 'missing', missing: ['captum', 'torch'] };
  app.state.health.status = 'degraded';
  app.state.health.activity.phase = 'idle';
  app.renderHealth();
  assert.equal(app.element('environmentState').textContent, 'Missing: captum, torch');
  assert.equal(app.element('activityState').textContent, 'Needs setup');
});

test('health polling is bounded, does not overlap, clears offline state and recovers without cancelling inference', async () => {
  const app = browser(false, true);
  app.startHealthPolling();
  app.startHealthPolling();
  assert.equal(app.intervals.size, 1);
  const poll = [...app.intervals.values()][0];
  assert.equal(poll.delay, 5000);
  const first = app.refreshHealth();
  await app.refreshHealth();
  await poll.handler();
  assert.equal(requestsFor(app, '/api/health').length, 1);
  requestsFor(app, '/api/health')[0].respond(healthy());
  await first;
  const previousCheck = app.state.healthCheckedAt;
  const predictionController = app.state.predictionController = new AbortController();
  app.state.predictionPending = true;
  const timedOut = poll.handler();
  const timeout = [...app.timeouts.values()][0];
  assert.equal(timeout.delay, 4000);
  timeout.handler();
  await timedOut;
  assert.equal(app.state.health, null);
  assert.equal(app.state.healthPending, false);
  assert.notEqual(app.state.healthCheckedAt, previousCheck);
  assert.match(app.element('healthCheckedAt').textContent, /^Last checked /);
  assert.equal(app.element('serviceState').textContent, 'Offline');
  assert.equal(app.element('environmentState').textContent, 'Unavailable');
  assert.equal(app.element('activityState').textContent, 'Unavailable');
  assert.equal(app.element('octWeightState').textContent, 'Unavailable');
  assert.equal(app.element('deviceStatus').textContent, 'Device availability unknown');
  assert.equal(app.state.predictionPending, true);
  assert.equal(predictionController.signal.aborted, false);
  const recovering = poll.handler();
  requestsFor(app, '/api/health')[2].respond(healthy());
  await recovering;
  assert.equal(app.element('serviceState').textContent, 'Online');
  assert.equal(app.element('activityState').textContent, 'Ready');
  assert.equal(app.element('serviceNotice').textContent, '');
});

test('entering Settings checks service immediately and does not duplicate an in-flight check', async () => {
  const app = browser(false, true);
  app.setView('settings');
  app.setView('settings');
  assert.equal(requestsFor(app, '/api/health').length, 1);
  requestsFor(app, '/api/health')[0].respond(healthy());
  await tick();
  assert.equal(app.element('serviceState').textContent, 'Online');
});

test('a lost prediction connection stops its timer and offers a reconnection message', async () => {
  const app = browser();
  const analyzing = analyze(app);
  await tick();
  requestsFor(app, '/api/predict')[0].fail(new TypeError('Failed to fetch'));
  await analyzing;
  assert.equal(app.state.predictionPending, false);
  assert.equal(app.state.predictionTimer, null);
  assert.equal(app.intervals.size, 0);
  assert.equal(app.element('predictionError').textContent, 'Service connection lost. Reconnect to JingWei and try again.');
});

test('static demo has no live service card or health polling', () => {
  const app = browser(true);
  assert.equal(app.startHealthPolling, null);
  assert.equal(app.intervals.size, 0);
  assert.doesNotMatch(readFileSync(join(__dirname, 'docs/app.js'), 'utf8'), /startHealthPolling|setInterval\(refreshHealth/);
  const html = readFileSync(join(__dirname, 'docs/index.html'), 'utf8');
  assert.doesNotMatch(html, /id="serviceState"/);
  assert.match(html, /No image analysis is performed/);
});

for (const succeeds of [true, false]) {
  test(`save ${succeeds ? 'success' : 'failure'} cancels old interpretation and ignores its late response`, async () => {
    const app = browser();
    const old = app.state.result = result();
    const interpreting = app.ensureInterpretation();
    const oldRequest = requestsFor(app, '/api/interpret')[0];
    const saving = app.saveSettings(submit);
    assert.equal(app.state.settingsPending, true);
    assert.equal(oldRequest.options.signal.aborted, true);
    assert.equal(old.interpretation.source, 'template');
    assert.equal(app.state.interpretationPending, false);
    finishSave(app, succeeds);
    await saving;
    assert.equal(app.state.settingsPending, false);
    assert.equal(app.state.settingsRevision, succeeds ? 1 : 0);
    assert.equal(app.element('saveSettings').disabled, false);
    const current = app.state.result = result(app.state.settingsRevision);
    const nextInterpretation = app.ensureInterpretation();
    const nextRequest = requestsFor(app, '/api/interpret')[1];
    oldRequest.respond({ text: 'Stale interpretation', source: 'llm' });
    await interpreting;
    assert.equal(old.interpretation.source, 'template');
    assert.equal(current.interpretation, null);
    assert.equal(app.state.interpretationPending, true);
    assert.equal(nextRequest.options.signal.aborted, false);
    nextRequest.respond({ text: 'Current interpretation', source: 'llm' });
    await nextInterpretation;
    assert.equal(current.interpretation.text, 'Current interpretation');
    assert.equal(app.state.interpretationPending, false);
  });

  test(`completed interpretation survives a ${succeeds ? 'successful' : 'failed'} save`, async () => {
    const app = browser();
    const completed = { text: 'Existing interpretation', source: 'llm' };
    app.state.result = { ...result(), interpretation: completed };
    const saving = app.saveSettings(submit);
    finishSave(app, succeeds);
    await saving;
    assert.equal(app.state.result.interpretation, completed);
    assert.equal(requestsFor(app, '/api/interpret').length, 0);
  });

  for (const startDuringSave of [false, true]) {
    test(`analysis started ${startDuringSave ? 'during' : 'before'} a delayed ${succeeds ? 'successful' : 'failed'} save uses the preset`, async () => {
      const app = browser();
      let analyzing;
      if (!startDuringSave) analyzing = analyze(app);
      const saving = app.saveSettings(submit);
      if (startDuringSave) analyzing = analyze(app);
      await tick();
      requestsFor(app, '/api/predict')[0].respond(result());
      await analyzing;
      assert.equal(app.state.settingsPending, true);
      assert.equal(app.state.result.interpretation.source, 'template');
      assert.equal(requestsFor(app, '/api/interpret').length, 0);
      finishSave(app, succeeds);
      await saving;
      await app.ensureInterpretation();
      assert.equal(app.state.result.interpretation.source, 'template');
      assert.equal(requestsFor(app, '/api/interpret').length, 0);
    });
  }
}

for (const startDuringSave of [false, true]) {
  test(`analysis started ${startDuringSave ? 'during' : 'before'} saving cannot use the newly saved configuration`, async () => {
    const app = browser();
    let analyzing;
    if (!startDuringSave) analyzing = analyze(app);
    const saving = app.saveSettings(submit);
    if (startDuringSave) analyzing = analyze(app);
    await tick();
    finishSave(app, true);
    await saving;
    requestsFor(app, '/api/predict')[0].respond(result());
    await analyzing;
    assert.equal(app.state.result.interpretationSettingsRevision, 0);
    assert.equal(app.state.settingsRevision, 1);
    assert.equal(app.state.result.interpretation.source, 'template');
    assert.equal(requestsFor(app, '/api/interpret').length, 0);
  });
}

test('pending report status is hidden only in print; settled AI attribution stays visible', async () => {
  const app = browser();
  app.state.result = result();
  app.state.view = 'report';
  const interpreting = app.ensureInterpretation();
  // Native beforeprint calls this renderer even while the print button is disabled.
  app.renderReport();
  const status = () => {
    const match = app.element('reportPage').innerHTML.match(/<span class="(report-interpretation-status[^"]*)">([^<]*)<\/span>/);
    return { classes: match[1].split(' '), text: match[2] };
  };
  const [screenCss, printCss] = styles.split('@media print {');
  const hiddenBy = (badge, css) => [...css.matchAll(/\.([\w-]+)\s*\{\s*display:\s*none\s*!important\s*;\s*\}/g)]
    .some((rule) => badge.classes.includes(rule[1]));
  assert.equal(status().text, 'Preparing interpretation…');
  assert.equal(hiddenBy(status(), screenCss), false);
  assert.equal(hiddenBy(status(), printCss), true);
  assert.equal(app.element('printReport').disabled, true);
  assert.match(app.element('reportPage').innerHTML, /Predicted RVL probability is 70\.0%/);
  requestsFor(app, '/api/interpret')[0].respond({ text: 'Finished interpretation', source: 'llm' });
  await interpreting;
  assert.equal(status().text, 'AI-assisted interpretation');
  assert.equal(hiddenBy(status(), printCss), false);
  assert.equal(app.element('printReport').disabled, false);
});

test('signed pixel IG report labels both directions with a relative scale and unchanged original image', () => {
  const app = browser();
  app.state.originalPreview = 'data:image/png;base64,UPLOAD';
  app.state.result = {
    ...result(), image: { input_preview: 'data:image/png;base64,MODEL_INPUT' },
    attribution: {
      method: 'integrated_gradients', target: 'rvl_positive_margin', display: 'signed',
      baseline: 'blur', status: 'ready', empty: false,
      heatmap: 'data:image/png;base64,HEATMAP', overlay: 'data:image/png;base64,OVERLAY',
      input_preview: 'data:image/png;base64,BLURRED_REFERENCE',
    },
  };
  app.renderReport();
  const report = app.element('reportPage').innerHTML;
  assert.match(report, /<h2 class="report-section-title">Contributing regions<\/h2>/);
  assert.match(report, /src="data:image\/png;base64,MODEL_INPUT" alt="Model input of the analyzed field"/);
  assert.doesNotMatch(report, /base64,UPLOAD|base64,BLURRED_REFERENCE/);
  assert.match(report, /src="data:image\/png;base64,HEATMAP" alt="Heatmap of the analyzed field"/);
  assert.match(report, /src="data:image\/png;base64,OVERLAY" alt="Overlay of the analyzed field"/);
  assert.match(report, /<span>−1<\/span><span class="report-heatmap-scale" aria-hidden="true">0<\/span><span>\+1<\/span>/);
  assert.match(report, /Red shows contributions that increase the RVL Score; blue shows contributions that decrease it/);
  assert.match(report, /zero is transparent in the overlay/);
  assert.match(report, /Relative scale for this image, not raw attribution units/);
  assert.match(report, /model attribution, not lesion location/);
  assert.doesNotMatch(report, /Only positive contributions|<span>Low<\/span>|<span>High<\/span>/);
  assert.match(styles, /linear-gradient\(to right, #0000ff 0%, #ffffff 50%, #ff0000 100%\)/);
});

test('negative-only IG remains visible for an RVL-negative result', () => {
  const app = browser();
  app.state.result = {
    ...result(), score: -1, probability: .3, positive: false,
    attribution: {
      status: 'ready', empty: false, method: 'integrated_gradients', display: 'signed',
      pixel_map: [[-2, -1], [-3, -4]],
      heatmap: 'data:image/png;base64,NEGATIVE', overlay: 'data:image/png;base64,NEGATIVE_OVERLAY',
    },
  };
  app.renderReport();
  const report = app.element('reportPage').innerHTML;
  assert.match(report, /src="data:image\/png;base64,NEGATIVE"/);
  assert.match(report, /src="data:image\/png;base64,NEGATIVE_OVERLAY"/);
  assert.match(report, /report-heatmap-key/);
  assert.doesNotMatch(report, /No attribution|No positive|Heatmap unavailable|Overlay unavailable/);
});

test('zero IG is described without implying that only positive values are considered', () => {
  const app = browser();
  app.state.result = {
    ...result(), attribution: { status: 'ready', empty: true, method: 'integrated_gradients', display: 'signed' },
  };
  app.renderReport();
  const report = app.element('reportPage').innerHTML;
  assert.match(report, /No visible contributions in this heatmap\./);
  assert.doesNotMatch(report, /report-heatmap-key|No positive|positive IG attribution/);
});

for (const status of ['disabled', 'unavailable']) {
  test(`${status} IG output does not display stale maps or a color scale`, () => {
    const app = browser();
    app.state.result = {
      ...result(), image: { input_preview: 'data:image/png;base64,ORIGINAL' },
      attribution: { status, heatmap: 'data:image/png;base64,STALE', overlay: 'data:image/png;base64,STALE' },
    };
    app.renderReport();
    const report = app.element('reportPage').innerHTML;
    assert.match(report, /src="data:image\/png;base64,ORIGINAL"/);
    assert.doesNotMatch(report, /base64,STALE|report-heatmap-key/);
    if (status === 'unavailable') assert.match(report, /Heatmap unavailable/);
    else assert.doesNotMatch(report, /Contributing regions|<figcaption>Heatmap|<figcaption>Overlay/);
  });
}

for (const enabled of [true, false]) {
  test(`upload uses the heatmap checkbox (${enabled}) at analysis start without saving settings`, async () => {
    const app = browser();
    app.state.settings = { include_heatmap: !enabled };
    app.element('includeHeatmap').checked = enabled;
    const analyzing = analyze(app);
    app.element('includeHeatmap').checked = !enabled;
    await tick();
    const request = requestsFor(app, '/api/predict')[0];
    assert.equal(JSON.parse(request.options.body).include_heatmap, enabled);
    assert.equal(app.element('predictionPhase').textContent,
      enabled ? 'Analyzing image and generating heatmap…' : 'Analyzing image…');
    assert.equal(requestsFor(app, '/api/settings').length, 0);
    assert.equal(app.state.settings.include_heatmap, !enabled);
    request.respond(result());
    await analyzing;
  });
}

for (const modality of ['cfp', 'oct']) {
  test(`${modality.toUpperCase()} sample uses normal inference and retains its generated-image label`, async () => {
    const app = browser();
    app.state.modality = modality;
    app.state.settings = { include_heatmap: false };
    app.element('includeHeatmap').checked = true;
    const loading = app.useSample();
    app.element('includeHeatmap').checked = false;
    assert.equal(app.element('useSample').disabled, true);
    await app.useSample();
    assert.equal(app.images.length, 1);
    assert.equal(app.images[0].src, `assets/sample-${modality}-generated.png`);
    app.images[0].finishDecode();
    await tick();
    const canvas = app.canvases[0];
    assert.equal(canvas.width, 1600);
    assert.equal(canvas.height, 900);
    assert.deepEqual(canvas.drawn, [app.images[0], 0, 0]);
    canvas.finishBlob();
    await tick();
    assert.equal(app.element('useSample').disabled, true);
    assert.equal(app.state.predictionPending, true);
    await app.useSample();
    assert.equal(app.images.length, 1);
    assert.equal(requestsFor(app, '/api/predict').length, 1);
    const prediction = requestsFor(app, '/api/predict')[0];
    const body = JSON.parse(prediction.options.body);
    assert.equal(body.modality, modality);
    assert.equal(body.include_heatmap, true);
    assert.equal(requestsFor(app, '/api/settings').length, 0);
    assert.equal(body.filename, `AI-generated-${modality.toUpperCase()}-sample.png`);
    prediction.respond({ ...result(), modality });
    await loading;
    assert.equal(app.element('useSample').disabled, false);
    assert.equal(app.state.result.snapshot.aiGeneratedSample, true);
    assert.equal(app.state.result.score, 1);
    assert.equal(app.state.result.probability, .7);
    for (const attribution of [{ status: 'disabled' }, { status: 'unavailable' }]) {
      app.state.result.attribution = attribution;
      app.renderReport();
      assert.match(app.element('reportPage').innerHTML, /<figcaption>AI-generated sample<\/figcaption>/);
    }
    requestsFor(app, '/api/interpret')[0].respond({ text: 'Sample assessment', source: 'template' });
    await tick();
    const uploaded = analyze(app);
    await tick();
    assert.equal(JSON.parse(requestsFor(app, '/api/predict')[1].options.body).include_heatmap, false);
    requestsFor(app, '/api/predict')[1].respond({ ...result(), modality });
    await uploaded;
    assert.equal(app.state.result.snapshot.aiGeneratedSample, false);
    app.renderReport();
    assert.match(app.element('reportPage').innerHTML, /<figcaption>Model input<\/figcaption>/);
    assert.doesNotMatch(app.element('reportPage').innerHTML, /AI-generated sample/);
  });
}

test('sample button is restored when a pending prediction fails', async () => {
  const app = browser();
  const loading = app.useSample();
  app.images[0].finishDecode();
  await tick();
  app.canvases[0].finishBlob();
  await tick();
  assert.equal(app.element('useSample').disabled, true);
  requestsFor(app, '/api/predict')[0].respond({ detail: 'Model unavailable' }, false);
  await loading;
  assert.equal(app.element('useSample').disabled, false);
  assert.equal(app.state.predictionPending, false);
  assert.equal(app.element('predictionError').textContent, 'Model unavailable');
  assert.equal(app.state.result, null);
});

test('an upload disables sample requests until prediction finishes', async () => {
  const app = browser();
  const uploading = analyze(app);
  await tick();
  app.renderResult();
  assert.equal(app.element('useSample').disabled, true);
  await app.useSample();
  assert.equal(app.images.length, 0);
  assert.equal(requestsFor(app, '/api/predict').length, 1);
  requestsFor(app, '/api/predict')[0].respond(result());
  await uploading;
  app.renderResult();
  assert.equal(app.element('useSample').disabled, false);
});

test('an upload can replace a pending sample and its late response cannot replace the upload', async () => {
  const app = browser();
  const loading = app.useSample();
  app.images[0].finishDecode();
  await tick();
  app.canvases[0].finishBlob();
  await tick();
  const sample = requestsFor(app, '/api/predict')[0];
  const uploading = analyze(app);
  await tick();
  assert.equal(sample.options.signal.aborted, true);
  requestsFor(app, '/api/predict')[1].respond({ ...result(), id: 'new-upload' });
  await uploading;
  sample.respond({ ...result(), id: 'old-sample' });
  await loading;
  assert.equal(app.state.result.id, 'new-upload');
  assert.equal(app.state.result.snapshot.aiGeneratedSample, false);
  assert.equal(app.element('useSample').disabled, false);
});

test('a replaced sample finishing cannot enable the button during a newer upload', async () => {
  const app = browser();
  const loading = app.useSample();
  app.images[0].finishDecode();
  await tick();
  app.canvases[0].finishBlob();
  await tick();
  const sample = requestsFor(app, '/api/predict')[0];
  const uploading = analyze(app);
  await tick();
  sample.respond(result());
  await loading;
  assert.equal(app.state.predictionPending, true);
  assert.equal(app.element('useSample').disabled, true);
  await app.useSample();
  assert.equal(requestsFor(app, '/api/predict').length, 2);
  requestsFor(app, '/api/predict')[1].respond(result());
  await uploading;
  app.renderResult();
  assert.equal(app.element('useSample').disabled, false);
});

for (const phase of ['decoding', 'encoding']) {
  test(`sample finishing ${phase} after a new prediction sequence cannot replace the current case`, async () => {
    const app = browser();
    const loading = app.useSample();
    if (phase === 'encoding') {
      app.images[0].finishDecode();
      await tick();
    }
    app.invalidatePrediction();
    const current = app.state.result = result();
    if (phase === 'decoding') {
      app.images[0].finishDecode();
      await tick();
    }
    app.canvases[0]?.finishBlob();
    await loading;
    assert.equal(app.state.result, current);
    assert.equal(requestsFor(app, '/api/predict').length, 0);
    assert.equal(app.element('useSample').disabled, false);
    assert.equal(app.element('predictionError').textContent, '');
  });
}

for (const modality of ['cfp', 'oct']) {
  test(`generated ${modality.toUpperCase()} demo sample and upload work without heatmap settings`, async () => {
    assert.doesNotMatch(readFileSync(join(__dirname, 'docs/index.html'), 'utf8'), /id="includeHeatmap"/);
    const app = browser(true);
    app.state.modality = modality;
    assert.equal(app.element('includeHeatmap'), null);
    const loading = app.useSample();
    app.images[0].finishDecode();
    await tick();
    app.canvases[0].finishBlob();
    await tick();
    const sample = requestsFor(app, '/api/predict')[0];
    assert.equal(JSON.parse(sample.options.body).include_heatmap, false);
    sample.respond({ ...result(), modality, attribution: { status: 'disabled' } });
    await loading;
    assert.equal(app.state.result.snapshot.aiGeneratedSample, true);
    app.renderReport();
    assert.match(app.element('reportPage').innerHTML, /Illustrative result — not calculated from your image/);
    assert.doesNotMatch(app.element('reportPage').innerHTML, /Contributing regions/);
    const uploading = analyze(app);
    await tick();
    const upload = requestsFor(app, '/api/predict')[1];
    assert.equal(JSON.parse(upload.options.body).include_heatmap, false);
    upload.respond({ ...result(), modality, attribution: { status: 'disabled' } });
    await uploading;
    assert.equal(app.state.result.snapshot.aiGeneratedSample, false);
    assert.equal(requestsFor(app, '/api/settings').length, 0);
  });
}

function demoInstallButtons(clipboard) {
  const demoSource = readFileSync(join(__dirname, 'docs/app.js'), 'utf8');
  const handlers = demoSource.slice(demoSource.indexOf('const jingweiInstallPrompt = '), demoSource.indexOf('const demoEntryDialog = '));
  const buttons = Array.from({ length: 3 }, () => {
    const message = { textContent: '' }, manualCopy = { hidden: true };
    const feedback = { hidden: true, querySelector: (tag) => tag === 'span' ? message : manualCopy };
    const button = {
      disabled: false, textContent: 'Install with LLM', feedback, message, manualCopy,
      closest: () => ({ querySelector: () => feedback }),
      addEventListener: (event, handler) => { assert.equal(event, 'click'); button.click = handler; },
    };
    return button;
  });
  const timers = new Map();
  let nextTimer = 0;
  vm.runInNewContext(handlers, {
    document: { querySelectorAll: () => buttons }, navigator: { clipboard },
    setTimeout: (handler) => { timers.set(++nextTimer, handler); return nextTimer; },
    clearTimeout: (id) => timers.delete(id),
  });
  return { buttons, timers };
}

test('all demo installation buttons copy the complete README prompt and show confirmation', async () => {
  const copied = [];
  const { buttons, timers } = demoInstallButtons({ writeText: async (text) => copied.push(text) });
  const readme = readFileSync(join(__dirname, 'README.md'), 'utf8');
  const expected = readme.split('### Install with LLM\n')[1].match(/```text\n([\s\S]*?)\n```/)[1];
  for (const button of buttons) {
    await button.click();
    assert.equal(button.textContent, 'Copied');
    assert.equal(button.disabled, false);
    assert.equal(button.feedback.hidden, false);
    assert.equal(button.manualCopy.hidden, true);
    assert.equal(button.message.textContent, 'Paste into your preferred AI assistant to install JingWei.');
  }
  assert.deepEqual(copied, Array(3).fill(expected));
  for (const reset of timers.values()) reset();
  assert.ok(buttons.every((button) => button.textContent === 'Install with LLM'));
});

test('clipboard rejection exposes manual copy and a successful retry clears the failure', async () => {
  let blocked = true;
  const { buttons } = demoInstallButtons({ writeText: async () => { if (blocked) throw new Error('Permission denied'); } });
  const button = buttons[0];
  await button.click();
  assert.equal(button.textContent, 'Install with LLM');
  assert.equal(button.disabled, false);
  assert.equal(button.feedback.hidden, false);
  assert.equal(button.manualCopy.hidden, false);
  assert.match(button.message.textContent, /Could not copy/);
  blocked = false;
  await button.click();
  assert.equal(button.textContent, 'Copied');
  assert.equal(button.manualCopy.hidden, true);
});

test('browsers without clipboard access offer manual copy rather than false success', async () => {
  const { buttons } = demoInstallButtons(undefined);
  await buttons[0].click();
  assert.equal(buttons[0].textContent, 'Install with LLM');
  assert.equal(buttons[0].manualCopy.hidden, false);
  assert.equal(buttons[0].disabled, false);
});
