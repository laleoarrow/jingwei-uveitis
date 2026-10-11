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

function browser() {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: '', checked: false, textContent: '', innerHTML: '', disabled: false,
      classList: { toggle() {}, add() {}, remove() {} },
      removeAttribute() {}, replaceChildren() { this.innerHTML = ''; },
      querySelector() { return element(`${id}:child`); },
      sheet: { cssRules: [{ cssRules: [] }] },
    });
    return elements.get(id);
  };
  const requests = [];
  const images = [], canvases = [];
  class Image {
    constructor() { this.naturalWidth = 1600; this.naturalHeight = 900; images.push(this); }
    decode() { return new Promise((resolve) => { this.finishDecode = resolve; }); }
  }
  const context = vm.createContext({
    document: {
      getElementById: element,
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
    URL: { createObjectURL: () => 'blob:test-image', revokeObjectURL() {} },
    setTimeout: () => 1, clearTimeout() {}, setInterval: () => 1, clearInterval() {},
    fetch(path, options) {
      return new Promise((resolve) => requests.push({
        path, options,
        respond(data, ok = true) { resolve({ ok, status: ok ? 200 : 400, json: async () => data }); },
      }));
    },
  });
  // Skip only automatic page initialization; keep the lifecycle and report functions intact.
  assert.match(source, /\ninitialize\(\);\s*$/);
  const app = vm.runInContext(source.replace(/\ninitialize\(\);\s*$/, '') + `
    readFile = async () => 'data:image/png;base64,AA==';
    showPreview = renderResult = updatePatientDirty = populateSettings = () => {};
    refreshHealth = async () => {};
    ({ state, saveSettings, ensureInterpretation, analyzeFile, renderReport, useSample, invalidatePrediction });
  `, context);
  return { ...app, element, requests, images, canvases };
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
  assert.equal(status().text, 'AI-assisted');
  assert.equal(hiddenBy(status(), printCss), false);
  assert.equal(app.element('printReport').disabled, false);
});

for (const modality of ['cfp', 'oct']) {
  test(`${modality.toUpperCase()} sample uses normal inference and retains its generated-image label`, async () => {
    const app = browser();
    app.state.modality = modality;
    const loading = app.useSample();
    assert.equal(app.element('useSample').disabled, true);
    assert.equal(app.images[0].src, `assets/sample-${modality}-generated.png`);
    app.images[0].finishDecode();
    await tick();
    const canvas = app.canvases[0];
    assert.equal(canvas.width, 1600);
    assert.equal(canvas.height, 900);
    assert.deepEqual(canvas.drawn, [app.images[0], 0, 0]);
    canvas.finishBlob();
    await loading;
    assert.equal(app.element('useSample').disabled, false);
    const prediction = requestsFor(app, '/api/predict')[0];
    const body = JSON.parse(prediction.options.body);
    assert.equal(body.modality, modality);
    assert.equal(body.filename, `AI-generated-${modality.toUpperCase()}-sample.png`);
    prediction.respond({ ...result(), modality });
    await tick();
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
    requestsFor(app, '/api/predict')[1].respond({ ...result(), modality });
    await uploaded;
    assert.equal(app.state.result.snapshot.aiGeneratedSample, false);
    app.renderReport();
    assert.match(app.element('reportPage').innerHTML, /<figcaption>Original<\/figcaption>/);
    assert.doesNotMatch(app.element('reportPage').innerHTML, /AI-generated sample/);
  });
}

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
    assert.match(button.message.textContent, /Paste into Codex/);
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
