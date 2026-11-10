// Isolated browser regression: no API key, external API calls or patient images.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const path = require('node:path');

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
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const ready = () => page.waitForFunction(() => !!state.token && !state.busy);
    const points = () => page.evaluate(() => current().points);
    async function screenPoint(point) {
      return page.evaluate(([x, y]) => {
        const box = document.getElementById('sourceCanvas').getBoundingClientRect();
        return { x: box.x + state.rect.x + x * state.rect.scale,
          y: box.y + state.rect.y + y * state.rect.scale };
      }, point);
    }
    function near(actual, expected, tolerance = 1) {
      assert.ok(Math.abs(actual - expected) < tolerance, `${actual} != ${expected}`);
    }
    const layout = () => page.evaluate(() => Object.fromEntries(
      ['sourceStage', 'previewStage', 'keepButton', 'autoPlaceButton', 'apiUsage', 'exportButton'].map(id => {
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
    const adjusted = await points();
    assert.equal(adjusted.length, 2);
    near(adjusted[0][0], initial[0][0] + 25 / scale);
    near(adjusted[0][1], initial[0][1] + 12 / scale);
    assert.deepEqual(adjusted[1], initial[1]);

    await page.locator('#moveButton').click();
    const box = await page.locator('#sourceCanvas').boundingBox();
    const oldRect = await page.evaluate(() => state.rect);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 30, box.y + box.height / 2 + 20, { steps: 4 });
    await page.mouse.up();
    assert.deepEqual(await points(), adjusted);
    assert.notEqual(await page.evaluate(() => state.rect.x), oldRect.x);
    await page.locator('#moveButton').click();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    const zoomBefore = await page.evaluate(() => state.view.zoom);
    await page.mouse.wheel(0, -120);
    await page.waitForFunction(value => state.view.zoom > value, zoomBefore);
    assert.deepEqual(await points(), adjusted);
    await page.locator('#fitButton').click();
    assert.equal(await page.evaluate(() => state.view.zoom), 1);
    assert.deepEqual(await points(), adjusted);

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

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => document.getElementById('sourceCanvas').width > 0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(await points(), adjusted);
    await page.setViewportSize({ width: 1440, height: 1100 });
    const cropRequest = page.waitForRequest(request => request.url().endsWith('/crop') && request.method() === 'POST');
    await page.locator('#keepButton').click(); await ready();
    assert.deepEqual((await cropRequest).postDataJSON(), { first: adjusted[0], center: adjusted[1] });
    assert.equal(await page.locator('#savedPreview').isVisible(), true);
    unchangedLayout(await layout(), idleLayout);
    const downloadEvent = page.waitForEvent('download');
    await page.locator('#exportButton').click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), 'images_clip.zip');
    assert.equal(await download.failure(), null);
    await ready();
    await page.reload(); await ready();
    assert.equal(await page.locator('#apiKey').inputValue(), '');
    assert.deepEqual(errors, []);
    console.log('Browser passed: stable layout through settings/loading/results/errors/export, actual usage display, chooser, key lifetime, native-resolution points, drag, zoom, pan and responsive layout.');
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
