// Isolated browser regression: no API key, external API calls or patient images.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const path = require('node:path');

async function installSavePicker(page) {
  await page.addInitScript(() => {
    window.__saveEvents = [];
    window.__saveMode = 'abort';
    window.__testSavePicker = options => {
      window.__saveEvents.push('picker');
      window.__suggestedName = options.suggestedName;
      if (window.__saveMode === 'abort') return Promise.reject(new DOMException('Cancelled', 'AbortError'));
      return Promise.resolve({ createWritable: async () => ({
        write: async blob => {
          window.__saveEvents.push('write');
          window.__savedZip = Array.from(new Uint8Array(await blob.arrayBuffer()));
        },
        close: async () => {
          window.__saveEvents.push('close-start');
          if (window.__saveMode === 'close-error') throw new Error('The ZIP could not be saved.');
          if (window.__saveMode === 'hold') await new Promise(resolve => { window.__finishSave = resolve; });
          window.__saveEvents.push('close-complete');
        },
        abort: async () => { window.__saveEvents.push('abort'); },
      }) });
    };
    window.showSaveFilePicker = window.__testSavePicker;
    const originalFetch = window.fetch;
    window.fetch = function (input, options) {
      if (input === '/api/export') window.__saveEvents.push('export-fetch');
      return originalFetch.call(this, input, options);
    };
  });
}

function zipNames(bytes) {
  const buffer = Buffer.from(bytes);
  const end = buffer.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  assert.ok(end >= 0, 'Export must contain a ZIP directory.');
  const names = [];
  let offset = buffer.readUInt32LE(end + 16);
  for (let index = 0; index < buffer.readUInt16LE(end + 10); index++) {
    assert.equal(buffer.readUInt32LE(offset), 0x02014b50);
    const length = buffer.readUInt16LE(offset + 28);
    names.push(buffer.toString('utf8', offset + 46, offset + 46 + length));
    offset += 46 + length + buffer.readUInt16LE(offset + 30) + buffer.readUInt16LE(offset + 32);
  }
  return names;
}

(async () => {
  const server = spawn(process.env.CFP_PYTHON || 'python', ['app.py', '--no-browser'], {
    cwd: path.resolve(__dirname, '..'), stdio: ['ignore', 'pipe', 'pipe'],
  });
  let browser;
  try {
    const base = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Local server did not start.')), 15000);
      server.stdout.on('data', chunk => {
        const url = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
        if (url) { clearTimeout(timer); resolve(url[0]); }
      });
      server.once('error', reject);
      server.once('exit', code => { clearTimeout(timer); reject(new Error(`Server exited: ${code}`)); });
    });
    browser = await chromium.launch({ headless: true,
      ...(process.env.CFP_BROWSER ? { executablePath: process.env.CFP_BROWSER } : {}) });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
    const page = await context.newPage();
    await installSavePicker(page);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const ready = (target = page) => target.waitForFunction(() => !!state.token && !state.busy);
    const points = () => page.evaluate(() => current().points);
    async function screenPoint(point, target = page) {
      return target.evaluate(([x, y]) => {
        const box = document.getElementById('sourceCanvas').getBoundingClientRect();
        return { x: box.x + state.rect.x + x * state.rect.scale,
          y: box.y + state.rect.y + y * state.rect.scale };
      }, point);
    }
    async function screenBadge(index) {
      return page.evaluate(index => {
        const [x, y] = badgePosition(current().points[index]);
        const box = document.getElementById('sourceCanvas').getBoundingClientRect();
        return { x: box.x + x, y: box.y + y };
      }, index);
    }
    async function drag(start, dx, dy, target = page) {
      await target.mouse.move(start.x, start.y); await target.mouse.down();
      await target.mouse.move(start.x + dx, start.y + dy, { steps: 4 }); await target.mouse.up();
    }
    function near(actual, expected, tolerance = 1) {
      assert.ok(Math.abs(actual - expected) < tolerance, `${actual} != ${expected}`);
    }
    const layout = () => page.evaluate(() => Object.fromEntries(
      ['sourceStage', 'previewStage', 'keepButton', 'keepButtonLabel', 'autoPlaceButton', 'apiUsage', 'exportButton'].map(id => {
        const box = document.getElementById(id).getBoundingClientRect();
        return [id, [box.x + scrollX, box.y + scrollY, box.width, box.height]];
      })));
    function unchangedLayout(actual, expected) {
      for (const id of Object.keys(expected)) actual[id].forEach((value, index) => near(value, expected[id][index], .1));
    }

    await page.goto(base); await ready();
    const fixture = await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = 512; canvas.height = 384;
      const context = canvas.getContext('2d');
      context.fillStyle = '#ba5b2f'; context.fillRect(0, 0, 512, 384);
      context.fillStyle = '#ffdc8b'; context.fillRect(300, 160, 40, 40);
      return canvas.toDataURL('image/png').split(',')[1];
    });
    const chooserEvent = page.waitForEvent('filechooser');
    await page.locator('#chooseImages').click();
    await (await chooserEvent).setFiles({ name: 'fixture.png', mimeType: 'image/png',
      buffer: Buffer.from(fixture, 'base64') });
    await page.waitForFunction(() => !!state.image && !state.busy);
    assert.deepEqual(await page.evaluate(() => [state.image.naturalWidth, state.image.naturalHeight]), [512, 384]);
    assert.equal(await page.locator('#keepButtonLabel').innerText(), 'Keep crop');
    assert.equal(await page.locator('#apiUsageSummary').innerText(), 'No API request yet');
    assert.equal(await page.locator('#apiUsageDetail').innerText(), 'Input — · Output —');

    const idleLayout = await layout();
    await page.locator('#apiSettingsButton').click();
    assert.equal(await page.locator('#apiSettings').isVisible(), true);
    unchangedLayout(await layout(), idleLayout);
    assert.equal(await page.locator('#apiModel').inputValue(), 'gpt-6-sol');
    assert.equal(await page.locator('#apiBaseUrl').inputValue(), 'https://api.openai.com/v1');
    await page.locator('#apiBaseUrl').fill('https://vision.example.test/v1');
    await page.locator('#apiKey').fill('test-key-not-a-secret');
    await page.locator('#closeApiSettings').click();
    unchangedLayout(await layout(), idleLayout);
    let calls = 0;
    let releaseSuggestion, requestReceived;
    const suggestionPending = new Promise(resolve => { releaseSuggestion = resolve; });
    const requested = new Promise(resolve => { requestReceived = resolve; });
    await page.route('**/api/images/*/landmarks', async route => {
      calls++;
      const body = route.request().postDataJSON();
      assert.equal(body.api_key, 'test-key-not-a-secret');
      assert.equal(body.model, 'gpt-6-sol');
      assert.equal(body.base_url, 'https://vision.example.test/v1');
      requestReceived();
      await suggestionPending;
      await route.fulfill({ json: { first: [320, 180], center: [220, 195], model: body.model,
        elapsed_seconds: 9.2, usage: { input_tokens: 1234, output_tokens: 456,
          total_tokens: 1690, cached_input_tokens: 100, reasoning_tokens: 300 } } });
    });
    assert.equal(calls, 0);
    await page.locator('#autoPlaceButton').click(); await requested;
    assert.equal(await page.evaluate(() => state.busy), true);
    unchangedLayout(await layout(), idleLayout);
    releaseSuggestion(); await ready();
    assert.equal(calls, 1);
    assert.deepEqual(await points(), [[320, 180], [220, 195]]);
    assert.equal(await page.locator('#exportButton').isDisabled(), true);
    assert.equal(await page.locator('#keepButton').isEnabled(), true);
    assert.equal(await page.evaluate(() => localStorage.length + sessionStorage.length), 0);
    assert.match(await page.locator('#apiUsageSummary').innerText(), /9\.2 s.*1,690/);
    assert.match(await page.locator('#apiUsageDetail').innerText(), /1,234.*456/);
    unchangedLayout(await layout(), idleLayout);

    // API input editing must not trigger canvas keyboard shortcuts.
    await page.locator('#apiSettingsButton').click();
    await page.locator('#apiModel').focus(); await page.keyboard.press('Backspace');
    assert.equal((await points()).length, 2);
    await page.locator('#apiModel').fill('gpt-6-sol');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#apiSettings').isVisible(), false);
    unchangedLayout(await layout(), idleLayout);
    const initial = await points();
    await page.locator('#zoomInButton').click();
    await page.locator('#zoomInButton').click();
    assert.ok(await page.evaluate(() => state.view.zoom > 1));
    assert.deepEqual(await points(), initial);

    const first = await screenPoint(initial[0]);
    const scale = await page.evaluate(() => state.rect.scale);
    await page.mouse.move(first.x, first.y); await page.mouse.down();
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(() => state.busy || current().kept), false);
    await page.mouse.move(first.x + 25, first.y + 12, { steps: 4 }); await page.mouse.up();
    let adjusted = await points();
    assert.equal(adjusted.length, 2);
    near(adjusted[0][0], initial[0][0] + 25 / scale);
    near(adjusted[0][1], initial[0][1] + 12 / scale);
    assert.deepEqual(adjusted[1], initial[1]);

    // Both explicit Move and Space must pan even when the drag begins on a point.
    await page.locator('#moveButton').click();
    const box = await page.locator('#sourceCanvas').boundingBox();
    const oldRect = await page.evaluate(() => state.rect);
    await drag(await screenPoint(adjusted[0]), 30, 20);
    assert.deepEqual(await points(), adjusted);
    assert.notEqual(await page.evaluate(() => state.rect.x), oldRect.x);
    await page.locator('#moveButton').click();
    await page.locator('#sourceCanvas').focus();
    const beforeSpace = await page.evaluate(() => state.rect);
    await page.keyboard.down('Space');
    await drag(await screenPoint(adjusted[1]), -20, -12);
    await page.keyboard.up('Space');
    assert.deepEqual(await points(), adjusted);
    assert.notEqual(await page.evaluate(() => state.rect.x), beforeSpace.x);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    const zoomBefore = await page.evaluate(() => state.view.zoom);
    await page.mouse.wheel(0, -120);
    await page.waitForFunction(value => state.view.zoom > value, zoomBefore);
    assert.deepEqual(await points(), adjusted);
    await page.locator('#fitButton').click();
    assert.equal(await page.evaluate(() => state.view.zoom), 1);
    assert.deepEqual(await points(), adjusted);

    // Drag the visible numbered badges; the point must move only by the drag delta.
    for (const index of [0, 1]) {
      const before = await points();
      const badge = await screenBadge(index);
      const badgeScale = await page.evaluate(() => state.rect.scale);
      await page.mouse.move(badge.x, badge.y); await page.mouse.down();
      await page.mouse.move(badge.x + 4, badge.y + 2);
      const firstMove = await points();
      near(firstMove[index][0], before[index][0] + 4 / badgeScale);
      near(firstMove[index][1], before[index][1] + 2 / badgeScale);
      await page.mouse.move(badge.x + 16, badge.y + 9); await page.mouse.up();
      adjusted = await points();
      near(adjusted[index][0], before[index][0] + 16 / badgeScale);
      near(adjusted[index][1], before[index][1] + 9 / badgeScale);
      assert.deepEqual(adjusted[1 - index], before[1 - index]);
    }

    // The badge is clamped near image edges and must remain a valid drag target.
    await page.locator('#resetButton').click();
    const edge = await screenPoint([510, 1]);
    await page.mouse.click(edge.x, edge.y);
    const edgePoint = (await points())[0];
    const edgeScale = await page.evaluate(() => state.rect.scale);
    await drag(await screenBadge(0), -18, 15);
    near((await points())[0][0], edgePoint[0] - 18 / edgeScale);
    near((await points())[0][1], edgePoint[1] + 15 / edgeScale);
    await page.locator('#resetButton').click();
    for (const point of adjusted) {
      const position = await screenPoint(point); await page.mouse.click(position.x, position.y);
    }
    adjusted = await points();

    // A second input can press Reset while the first pointer is dragging point 2.
    const resetDrag = await screenPoint(adjusted[1]);
    await page.mouse.move(resetDrag.x, resetDrag.y); await page.mouse.down();
    assert.equal(await page.evaluate(() => state.pointer.index), 1);
    await page.locator('#resetButton').dispatchEvent('click');
    await page.mouse.move(resetDrag.x + 15, resetDrag.y + 10); await page.mouse.up();
    assert.deepEqual(await points(), []);
    assert.equal(await page.evaluate(() => state.pointer), null);
    assert.deepEqual(errors, []);
    for (const point of adjusted) {
      const position = await screenPoint(point); await page.mouse.click(position.x, position.y);
    }
    adjusted = await points();

    // Failed suggestions must leave the user's landmarks intact.
    await page.unroute('**/api/images/*/landmarks');
    await page.route('**/api/images/*/landmarks', route => route.fulfill({ status: 400,
      json: { error: 'The model could not locate both landmarks.', model: 'gpt-6-sol',
        elapsed_seconds: 1.4, usage: { input_tokens: 40, output_tokens: 80, total_tokens: 120 } } }));
    await page.locator('#autoPlaceButton').click(); await ready();
    assert.match(await page.locator('#status').innerText(), /could not locate/);
    assert.deepEqual(await points(), adjusted);
    assert.match(await page.locator('#apiUsageSummary').innerText(), /1\.4 s.*120/);
    unchangedLayout(await layout(), idleLayout);

    await page.unroute('**/api/images/*/landmarks');
    await page.route('**/api/images/*/landmarks', route => route.fulfill({ status: 504,
      json: { error: 'Could not reach the API in time.', elapsed_seconds: 90, usage: null } }));
    await page.locator('#autoPlaceButton').click(); await ready();
    assert.doesNotMatch(await page.locator('#apiUsageSummary').innerText(), /120|1,690/);
    assert.deepEqual(await points(), adjusted);
    unchangedLayout(await layout(), idleLayout);

    for (const width of [320, 390, 820]) {
      await page.setViewportSize({ width, height: 844 });
      await page.waitForFunction(() => {
        const canvas = document.getElementById('sourceCanvas');
        return canvas.width === Math.round(canvas.getBoundingClientRect().width * devicePixelRatio);
      });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Overflow at ${width}px`);
      assert.deepEqual(await points(), adjusted);
      const narrowLayout = await layout();
      await page.locator('#apiSettingsButton').click();
      unchangedLayout(await layout(), narrowLayout);
      await page.keyboard.press('Escape');
      unchangedLayout(await layout(), narrowLayout);
      for (const id of ['zoomInButton', 'zoomOutButton', 'fitButton', 'moveButton', 'previousButton', 'nextButton']) {
        const target = await page.locator(`#${id}`).boundingBox();
        assert.ok(target.width >= 35.9 && target.height >= 35.9, `Small touch target ${id} at ${width}px`);
      }
    }
    await page.setViewportSize({ width: 1440, height: 1100 });
    // A failed keep blocks and returns the scalpel; success turns it fully.
    await page.evaluate(() => {
      const icon = document.querySelector('#keepButton .keep-icon');
      const animate = icon.animate.bind(icon);
      window.__keepAnimations = [];
      icon.animate = (frames, options) => {
        window.__keepAnimations.push({ frames, options });
        return animate(frames, options);
      };
    });
    await page.route('**/api/images/*/crop', route => route.request().method() === 'POST'
      ? route.fulfill({ status: 500, json: { error: 'The crop could not be saved.' } }) : route.continue());
    await page.locator('#keepButton').click(); await ready();
    const failedAnimation = await page.evaluate(() => window.__keepAnimations);
    assert.equal(failedAnimation.length, 1);
    assert.deepEqual(failedAnimation[0].frames.map(frame => frame.transform),
      ['rotate(0deg)', 'rotate(110deg)', 'rotate(110deg)', 'rotate(-8deg)', 'rotate(0deg)']);
    assert.equal(failedAnimation[0].frames.at(-1).offset, 1);
    assert.equal(failedAnimation[0].options.duration, 420);
    assert.equal(await page.evaluate(() => current().kept), false);
    assert.deepEqual(await points(), adjusted);
    await page.unroute('**/api/images/*/crop');
    const cropRequest = page.waitForRequest(request => request.url().endsWith('/crop') && request.method() === 'POST');
    await page.locator('#keepButton').click(); await ready();
    assert.deepEqual((await cropRequest).postDataJSON(), { first: adjusted[0], center: adjusted[1] });
    assert.equal(await page.locator('#savedPreview').isVisible(), true);
    const animation = await page.evaluate(() => window.__keepAnimations);
    assert.equal(animation.length, 2);
    assert.deepEqual(animation[1].frames, [{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }]);
    assert.ok(animation[1].options.duration >= 280 && animation[1].options.duration <= 350);
    unchangedLayout(await layout(), idleLayout);

    // Changing a kept crop is a draft until the user keeps it again.
    await drag(await screenBadge(1), -10, 5);
    assert.equal(await page.locator('#cropState').innerText(), 'Unkept changes');
    assert.match(await page.locator('#status').innerText(), /last kept crop/);
    assert.deepEqual(await page.evaluate(() => current().savedPoints), adjusted);

    const beforeReducedMotion = await page.evaluate(() => ({ animations: window.__keepAnimations.length, revision: state.revision }));
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.locator('#keepButton').click(); await ready();
    assert.equal(await page.evaluate(() => state.revision), beforeReducedMotion.revision + 1);
    assert.equal(await page.evaluate(() => window.__keepAnimations.length), beforeReducedMotion.animations);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    adjusted = await points();
    await page.locator('#keepButton').click(); await ready();
    assert.equal(await page.locator('#cropState').innerText(), 'Kept');
    assert.deepEqual(await page.evaluate(() => current().savedPoints), adjusted);

    // Cancelling the native picker must not fetch or mark the crops exported.
    await page.evaluate(() => { window.__saveMode = 'abort'; window.__saveEvents = []; });
    await page.locator('#exportButton').click(); await ready();
    assert.deepEqual(await page.evaluate(() => window.__saveEvents), ['picker']);
    assert.equal(await page.evaluate(() => unexported()), true);
    assert.match(await page.locator('#status').innerText(), /cancelled/);

    // A failed close also leaves the crops unexported, even after writing bytes.
    await page.evaluate(() => { window.__saveMode = 'close-error'; window.__saveEvents = []; });
    await page.locator('#exportButton').click(); await ready();
    assert.deepEqual(await page.evaluate(() => window.__saveEvents), ['picker', 'export-fetch', 'write', 'close-start', 'abort']);
    assert.equal(await page.evaluate(() => unexported()), true);
    assert.match(await page.locator('#status').innerText(), /could not be saved/);

    // Browsers without a native picker cannot confirm a successful download.
    await page.evaluate(() => { window.showSaveFilePicker = undefined; });
    const downloadEvent = page.waitForEvent('download');
    await page.locator('#exportButton').click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), 'images_clip.zip');
    assert.equal(await download.failure(), null);
    await ready();
    assert.equal(await page.evaluate(() => unexported()), true);
    assert.match(await page.locator('#status').innerText(), /Check it is saved/);
    const quitDialog = page.waitForEvent('dialog');
    const quitClick = page.locator('#quitButton').click();
    const confirmation = await quitDialog;
    assert.equal(confirmation.type(), 'confirm');
    await confirmation.dismiss(); await quitClick;
    assert.equal(await page.evaluate(() => state.closed), false);

    // Only the native stream's successful close confirms the export.
    await page.evaluate(() => { window.showSaveFilePicker = window.__testSavePicker; window.__saveMode = 'hold'; window.__saveEvents = []; });
    await page.locator('#exportButton').click();
    await page.waitForFunction(() => typeof window.__finishSave === 'function');
    assert.equal(await page.evaluate(() => unexported()), true);
    assert.equal(await page.evaluate(() => state.busy), true);
    assert.deepEqual(await page.evaluate(() => window.__saveEvents), ['picker', 'export-fetch', 'write', 'close-start']);
    await page.evaluate(() => window.__finishSave()); await ready();
    assert.equal(await page.evaluate(() => unexported()), false);
    assert.equal(await page.evaluate(() => window.__suggestedName), 'images_clip.zip');
    assert.deepEqual(zipNames(await page.evaluate(() => window.__savedZip)), ['images_clip/fixture.png']);
    unchangedLayout(await layout(), idleLayout);

    // A second tab has a separate image set, kept crops and API key.
    const tabA = await page.evaluate(() => ({ token: state.token, id: current().id }));
    const tabB = await page.context().newPage();
    tabB.on('pageerror', error => errors.push(error.message));
    await installSavePicker(tabB);
    await tabB.goto(base); await ready(tabB);
    assert.notEqual(await tabB.evaluate(() => state.token), tabA.token);
    await tabB.locator('#imageInput').setInputFiles([
      { name: 'other.png', mimeType: 'image/png', buffer: Buffer.from(fixture, 'base64') },
      { name: 'second.png', mimeType: 'image/png', buffer: Buffer.from(fixture, 'base64') },
    ]);
    await tabB.waitForFunction(() => !!state.image && !state.busy);
    assert.equal(await tabB.locator('#keepButtonLabel').innerText(), 'Keep crop & next');
    for (const point of [[100, 100], [180, 150]]) {
      const position = await screenPoint(point, tabB); await tabB.mouse.click(position.x, position.y);
    }
    await tabB.locator('#keepButton').click(); await ready(tabB);
    assert.equal(await tabB.locator('#keepButtonLabel').innerText(), 'Keep crop');
    await tabB.evaluate(() => { window.__saveMode = 'success'; });
    await tabB.locator('#exportButton').click(); await ready(tabB);
    assert.deepEqual(zipNames(await tabB.evaluate(() => window.__savedZip)), ['images_clip/other.png']);
    assert.equal(await tabB.evaluate(async id => (await fetch(`/api/images/${id}/source`, { headers: { 'X-Clip-Token': state.token } })).status, tabA.id), 404);
    assert.deepEqual(await points(), adjusted);
    assert.equal(await page.evaluate(() => current().kept), true);
    await page.evaluate(() => { window.__saveMode = 'success'; });
    await page.locator('#exportButton').click(); await ready();
    assert.deepEqual(zipNames(await page.evaluate(() => window.__savedZip)), ['images_clip/fixture.png']);
    await tabB.locator('#apiSettingsButton').click();
    await tabB.locator('#apiKey').fill('tab-b-key');
    await tabB.locator('#closeApiSettings').click();
    const tabBToken = await tabB.evaluate(() => state.token);
    const tabBBeforeQuit = await tabB.evaluate(() => ({ images: state.images, index: state.index,
      revision: state.revision, exportedRevision: state.exportedRevision, sourceUrl: state.sourceUrl }));
    await tabB.route('**/api/shutdown', route => route.abort('failed'));
    await tabB.locator('#quitButton').click(); await ready(tabB);
    assert.equal(await tabB.evaluate(() => state.closed), false);
    assert.deepEqual(await tabB.evaluate(() => ({ images: state.images, index: state.index,
      revision: state.revision, exportedRevision: state.exportedRevision, sourceUrl: state.sourceUrl })), tabBBeforeQuit);
    assert.equal(await tabB.locator('#quitButton').isEnabled(), true);
    assert.equal(await tabB.locator('#sourceCanvas').isVisible(), true);
    await tabB.unroute('**/api/shutdown');
    await tabB.locator('#quitButton').click(); await ready(tabB);
    assert.equal(await tabB.evaluate(() => state.closed), true);
    assert.equal(await tabB.locator('#apiKey').inputValue(), '');
    assert.match(await tabB.locator('#status').innerText(), /This tab is closed/);
    assert.equal(await page.evaluate(async token => (await fetch('/api/export', { headers: { 'X-Clip-Token': token } })).status, tabBToken), 403);
    await page.locator('#exportButton').click(); await ready();
    assert.deepEqual(zipNames(await page.evaluate(() => window.__savedZip)), ['images_clip/fixture.png']);
    await tabB.close();

    // Reload closes only the old session, starts a fresh one and clears the key.
    await page.reload(); await ready();
    assert.equal(await page.locator('#apiKey').inputValue(), '');
    assert.notEqual(await page.evaluate(() => state.token), tabA.token);
    await page.waitForFunction(async token => (await fetch('/api/export', { headers: { 'X-Clip-Token': token } })).status === 403, tabA.token);

    // Closing a page during confirmation must also clean its already-known token.
    const pendingTab = await context.newPage();
    pendingTab.on('dialog', async dialog => { errors.push(`Unexpected handshake dialog: ${dialog.type()}`); await dialog.accept(); });
    let confirmationReceived, releaseConfirmation;
    const serverConfirmed = new Promise(resolve => { confirmationReceived = resolve; });
    const confirmationHeld = new Promise(resolve => { releaseConfirmation = resolve; });
    await pendingTab.route('**/api/confirm', async route => {
      const response = await route.fetch();
      confirmationReceived();
      await confirmationHeld;
      if (!pendingTab.isClosed()) await route.fulfill({ response });
    });
    await pendingTab.goto(base); await serverConfirmed;
    const pendingToken = await pendingTab.evaluate(() => state.pendingToken);
    assert.ok(pendingToken);
    assert.equal(await pendingTab.evaluate(() => state.token), '');
    assert.equal(await pendingTab.locator('#chooseImages').isDisabled(), true);
    assert.equal(await page.evaluate(async token => (await fetch('/api/export', { headers: { 'X-Clip-Token': token } })).status, pendingToken), 400);
    const pendingClosed = pendingTab.waitForEvent('close');
    await pendingTab.close({ runBeforeUnload: true }); await pendingClosed;
    releaseConfirmation();
    await page.waitForFunction(async token => (await fetch('/api/export', { headers: { 'X-Clip-Token': token } })).status === 403, pendingToken);
    assert.deepEqual(errors, []);
    console.log('Browser passed: isolated tabs and cleanup; native save cancel/failure/success and fallback warnings; marker/badge drag and pan; kept-draft state; API usage, keyboard and key lifetime; stable layouts at 320/390/820/1440px.');
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
