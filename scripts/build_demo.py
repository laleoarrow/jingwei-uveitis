#!/usr/bin/env python3
"""Build the browser-only Pages demo from the maintained local workbench UI."""
from pathlib import Path
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
DOCS = ROOT / "docs"
VERSION = "workbench-demo-3"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Local UI changed; review the demo adaptation: {old[:85]!r}")
    return text.replace(old, new, 1)


def replace_section(text, start, end, replacement):
    begin = text.index(start)
    finish = text.index(end, begin)
    return text[:begin] + replacement + text[finish:]


html = (STATIC / "index.html").read_text(encoding="utf-8")
html = replace_once(html, "  <script>\n    if (window.location.protocol === 'file:') window.location.replace('http://127.0.0.1:8765/');\n  </script>\n", "")
html, count = re.subn(r'href="/styles\.css(?:\?[^\"]*)?"', f'href="styles.css?v={VERSION}"', html)
assert count == 1, 'Review the local stylesheet link.'
html, count = re.subn(r'  <script src="/app\.js(?:\?[^\"]*)?" defer></script>', f'  <link rel="stylesheet" href="demo.css?v={VERSION}">\n  <script src="reference-data.js?v={VERSION}" defer></script>\n  <script src="demo-adapter.js?v={VERSION}" defer></script>\n  <script src="app.js?v={VERSION}" defer></script>', html)
assert count == 1, 'Review the local application script link.'
html = html.replace('src="/jingwei-wordmark.svg', 'src="jingwei-wordmark.svg')
html = replace_once(html, '  <title>JingWei System</title>', '  <title>JingWei System · Demo</title>\n  <meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'; style-src \'self\' \'unsafe-inline\'; img-src \'self\' blob: data:; connect-src \'none\'; font-src \'none\'; object-src \'none\'; base-uri \'self\'; form-action \'none\'">')
html = replace_once(html, '    <main>\n', '    <main>\n      <aside class="demo-notice" aria-label="Demo notice"><span class="demo-notice-badge">Demo only</span><div class="demo-notice-copy"><strong>No image analysis is performed.</strong><span>Results are fixed examples, not predictions from your image.</span></div></aside>\n')
html = replace_once(html, 'accept=".jpg,.jpeg,.png,.tif,.tiff,.webp,image/jpeg,image/png,image/tiff,image/webp"', 'accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"')
html = replace_once(html, '            <div class="image-fileline">', '            <div class="demo-sample-action"><button class="text-button" id="useDemoSample" type="button">Use sample</button></div>\n            <div class="image-fileline">')
html = html.replace('<span>This image</span>', '<span>Demo result</span>')
html = replace_section(html, '      <section id="settingsView"', '      <section id="reportView"', '''      <section id="settingsView" class="view hidden">
        <div class="page-heading"><h1>Settings</h1></div>
        <section class="settings-card demo-local-settings"><h2>Offline use</h2><p>Configure model weights to analyse CFP or OCT images offline.</p><a class="button button-primary" href="https://github.com/laleoarrow/jingwei-uveitis#readme">Installation &amp; source ↗</a></section>
      </section>
''')

app = (STATIC / "app.js").read_text(encoding="utf-8")
app = replace_section(app, 'async function api(', 'function setNotice(', '''// Generated demo: all application requests stay inside this browser adapter.
async function api(path, options = {}) {
  return window.jingweiDemoApi(path, options);
}

''')
app = replace_section(app, 'function renderHealth()', 'function presetInterpretation(', '''function renderHealth() {
  $('connectionText').textContent = 'Demo';
  $('connectionDot').classList.remove('bad');
  $('activeModelStatus').textContent = 'Illustrative results';
  $('modelDot').className = 'status-dot neutral';
}

async function refreshHealth() {
  state.health = await api('/api/health');
  renderHealth();
}

function populateSettings() {}

''')
app = replace_section(app, 'function presetInterpretation(', 'function cancelInterpretation()', '''function presetInterpretation() {
  return { text: window.jingweiDemoInterpretation, source: 'template', fallback: false };
}

''')
for line in [
    "  $('settingsForm').addEventListener('submit', saveSettings);\n",
    "  $('device').addEventListener('change', renderDeviceStatus);\n",
    "  $('llmEnabled').addEventListener('change', renderLlmSettings);\n",
    "  $('llmApiKey').addEventListener('input', () => { if ($('llmApiKey').value) state.clearLlmApiKey = false; renderLlmSettings(); });\n",
    "  $('clearLlmKey').addEventListener('click', () => { $('llmApiKey').value = ''; $('llmEnabled').checked = false; renderLlmSettings(); });\n",
]:
    # Older local UI versions additionally set the clear-key flag in this listener.
    if "clearLlmKey" in line and line not in app:
        line = line.replace("renderLlmSettings();", "state.clearLlmApiKey = true; renderLlmSettings();")
    app = replace_once(app, line, '')
app = replace_once(app, "  const isTiff = ['tif', 'tiff'].includes(extension) || file.type?.toLowerCase() === 'image/tiff';", "  const isTiff = false; // TIFF decoding requires the offline application.")
app = app.replace('Choose a JPG, PNG, TIFF or WEBP image.', 'Choose a JPG, PNG or WebP image.')
app = app.replace("'Analyzing image…'", "'Preparing demo…'")
app = app.replace('Analysis time · ${', 'Demo time · ${')
app = replace_once(app, "  return result.positive ? 'Predicted RVL: positive' : 'Predicted RVL: negative';", "  return 'Illustrative result — not calculated from your image';")
app = app.replace('src="/jingwei-wordmark.svg', 'src="jingwei-wordmark.svg')
app = app.replace('>Model input</button>', '>Preview crop</button>')
app = app.replace('>Clinical report</span>', '>DEMO / illustrative output</span>')
app = app.replace('>Assisted assessment report</p>', '>Illustrative result — not calculated from your image</p>')
app = app.replace('<span>Analyzed: ', '<span>Demo created: ')
app = app.replace(' of the analyzed field', ' preview; not analyzed')
app = app.replace('This image</span>', 'Demo result</span>')
app = app.replace('FFA reference · ${e(referenceTitle)}', 'FFA reference · ${e(referenceTitle)} · illustrative marker')
app = replace_section(app, '    // Licensed local faces are optional', '    if (state.result !== result', '    await document.fonts.ready;\n')
app = replace_once(app, "  $('newCase').addEventListener('click', newCase);", """  $('newCase').addEventListener('click', newCase);
  $('useDemoSample').addEventListener('click', async () => {
    const sequence = state.predictionSequence;
    $('useDemoSample').disabled = true;
    try {
      const file = await window.jingweiDemoSample();
      if (sequence === state.predictionSequence) analyzeFile(file);
    } catch {
      if (sequence === state.predictionSequence) setNotice('predictionError', 'The sample could not load. Choose a JPG, PNG or WebP image.', true);
    } finally { $('useDemoSample').disabled = false; }
  });""")

css = (STATIC / "styles.css").read_text(encoding="utf-8")
css, removed = re.subn(r'@font-face\s*\{[^}]*\}\s*', '', css)
assert removed == 3, 'Review changed local report font declarations.'
css = css.replace('"Helvetica Neue LT Std Light"', '"Helvetica Neue"').replace('"Helvetica Neue LT Std Bold"', '"Helvetica Neue"').replace('"Helvetica Neue LT Std Bold Condensed"', '"Arial Narrow"').replace('"Arial Narrow", "Arial Narrow"', '"Arial Narrow"')
css = css.replace('/* Original report faces; equal-level sections share one condensed heading style. */', '/* Demo uses system fonts; no proprietary font files are distributed. */')

DOCS.mkdir(exist_ok=True)
for name, content in [('index.html', html), ('app.js', app), ('styles.css', css)]:
    (DOCS / name).write_text(content, encoding='utf-8')
shutil.copyfile(STATIC / 'jingwei-wordmark.svg', DOCS / 'jingwei-wordmark.svg')
bundle = json.loads((ROOT / 'data/reference_distributions.json').read_text(encoding='utf-8'))
references = json.dumps(bundle['references'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
(DOCS / 'reference-data.js').write_text('// Frozen aggregate research reference data; no individual records.\nwindow.JINGWEI_DEMO_REFERENCES = ' + references + ';\n', encoding='utf-8')
# Retire the separately maintained landing page implementation and duplicate logo.
for obsolete in [DOCS / 'demo.js', DOCS / 'assets/jingwei-wordmark.svg']:
    obsolete.unlink(missing_ok=True)
print('Built docs/ from static/ with browser-only demo behavior.')
