#!/usr/bin/env python3
"""Build the browser-only Pages demo from the maintained local workbench UI."""
from pathlib import Path
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
DOCS = ROOT / "docs"
VERSION = "workbench-demo-23"
DOWNLOAD_URL = "https://github.com/laleoarrow/jingwei-uveitis/archive/refs/heads/main.zip"
WEIGHTS_URL = "https://pan.baidu.com/s/1r7gfecgxxbtCQnV0FmZlSg?pwd=7a7c"
INSTALL_URL = "https://github.com/laleoarrow/jingwei-uveitis#installation"
LLM_INSTALL_URL = "https://github.com/laleoarrow/jingwei-uveitis#install-with-llm"

readme = (ROOT / "README.md").read_text(encoding="utf-8")
install_section = re.search(r'^### Install with LLM\n(.*?)(?=^##? |\Z)', readme, re.M | re.S)
install_prompt = re.search(r'^```text\n(.*?)\n```', install_section.group(1), re.M | re.S) if install_section else None
if not install_prompt:
    raise ValueError("README must contain an Install with LLM text prompt.")


def download_actions():
    return f'''<div class="demo-install-options">
      <div class="demo-download-actions">
        <a class="button button-primary" href="{DOWNLOAD_URL}">Download offline app <span aria-hidden="true">↓</span></a>
        <div class="demo-weight-download">
          <a class="button button-secondary" href="{WEIGHTS_URL}" target="_blank" rel="noopener">Download model weights <span aria-hidden="true">↗</span></a>
          <span class="demo-weight-code">Access code: <strong>7a7c</strong></span>
        </div>
        <button class="button button-secondary" type="button" data-copy-install title="Copy installation instructions for your AI assistant">Install with LLM</button>
        <a class="button button-secondary demo-setup-link" href="{INSTALL_URL}" target="_blank" rel="noopener">Installation guide <span aria-hidden="true">↗</span></a>
      </div>
      <p class="demo-install-feedback" role="status" aria-live="polite" hidden><span></span> <a href="{LLM_INSTALL_URL}" target="_blank" rel="noopener" hidden>Copy from README ↗</a></p>
    </div>'''


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
html = replace_once(html, '<body>\n', f'''<body>
  <dialog id="demoEntryDialog" class="demo-entry-dialog" aria-labelledby="demoEntryTitle" aria-describedby="demoEntryDescription">
    <span class="demo-notice-badge">Demo only</span>
    <h2 id="demoEntryTitle">JingWei online demo</h2>
    <div id="demoEntryDescription">
      <p>Explore the JingWei workflow, visualizations, and report layout.</p>
      <p class="demo-entry-warning"><strong>No image analysis is performed.</strong> All results are illustrative and are not calculated from your image.</p>
      <p>For actual analysis, download the offline app, follow the installation guide, and configure your model weights in Settings before selecting an image.</p>
    </div>
    {download_actions()}
    <button class="button button-secondary demo-entry-continue" id="continueDemo" type="button" autofocus>Continue to demo</button>
  </dialog>
''')
html = replace_once(html, '    <main>\n', f'''    <main>
      <aside class="demo-notice" aria-label="Demo notice">
        <span class="demo-notice-badge">Demo only</span>
        <div class="demo-notice-copy"><strong>No image analysis is performed.</strong><span>Results are fixed examples, not predictions from your image.</span></div>
        <div class="demo-download">{download_actions()}</div>
      </aside>
''')
html = replace_once(html, 'accept=".jpg,.jpeg,.png,.tif,.tiff,.webp,image/jpeg,image/png,image/tiff,image/webp"', 'accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"')
html = html.replace('<span>This image</span>', '<span>Demo result</span>')
html = replace_section(html, '      <section id="settingsView"', '      <section id="reportView"', f'''      <section id="settingsView" class="view hidden">
        <div class="page-heading"><h1>Settings</h1></div>
        <section class="settings-card demo-local-settings"><h2>Offline use</h2><p>Download and unzip the app, then double-click <strong>start.command</strong> on macOS or <strong>start.bat</strong> on Windows. The launcher installs the environment and opens JingWei. Model weights are supplied separately.</p>{download_actions()}</section>
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
    "  startHealthPolling();\n",
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
app = replace_once(app, "  const includeHeatmap = $('includeHeatmap').checked;", "  const includeHeatmap = false; // Heatmaps require the offline application.")
app = replace_once(app, "async function analyzeFile(file, includeHeatmap = $('includeHeatmap').checked)", "async function analyzeFile(file, includeHeatmap = false)")
app = replace_once(app, "  const isTiff = ['tif', 'tiff'].includes(extension) || file.type?.toLowerCase() === 'image/tiff';", "  const isTiff = false; // TIFF decoding requires the offline application.")
app = app.replace('Choose a JPG, PNG, TIFF or WEBP image.', 'Choose a JPG, PNG or WebP image.')
app = app.replace("'Analyzing image…'", "'Preparing demo…'")
app = app.replace('Analysis time · ${', 'Demo time · ${')
app = replace_once(app, "  return result.positive ? 'Predicted RVL: positive' : 'Predicted RVL: negative';", "  return 'Illustrative result — not calculated from your image';")
app = app.replace('src="/jingwei-wordmark.svg', 'src="jingwei-wordmark.svg')
app = app.replace('>Model input</button>', '>Preview crop</button>')
app = app.replace("imagePanel(snapshot.aiGeneratedSample ? 'AI-generated sample' : 'Model input'", "imagePanel(snapshot.aiGeneratedSample ? 'AI-generated sample' : 'Preview crop'")
app = app.replace('>Clinical report</span>', '>DEMO / illustrative output</span>')
app = replace_once(app, '>Model-based RVL prediction in uveitis</p>', '>Illustrative result — not calculated from your image</p>')
app = app.replace('<span>Analyzed: ', '<span>Demo created: ')
app = app.replace(' of the analyzed field', ' preview; not analyzed')
app = app.replace('This image</span>', 'Demo result</span>')
app = replace_once(app, 'Reference cohort · ${e(referenceTitle)} (RVL assessed by FFA)', 'Reference cohort · ${e(referenceTitle)} (RVL assessed by FFA) · illustrative marker')
app = replace_section(app, '    // Licensed local faces are optional', '    if (state.result !== result', '    await document.fonts.ready;\n')
app = replace_once(app, '\ninitialize();', '\nconst jingweiInstallPrompt = ' + json.dumps(install_prompt.group(1), ensure_ascii=True) + ';\n' + '''
document.querySelectorAll('[data-copy-install]').forEach((button) => {
  const feedback = button.closest('.demo-install-options').querySelector('.demo-install-feedback');
  const message = feedback.querySelector('span');
  const manualCopy = feedback.querySelector('a');
  let resetTimer;
  button.addEventListener('click', async () => {
    clearTimeout(resetTimer);
    button.disabled = true;
    button.textContent = 'Install with LLM';
    feedback.hidden = true;
    manualCopy.hidden = true;
    try {
      await navigator.clipboard.writeText(jingweiInstallPrompt);
      button.textContent = 'Copied';
      message.textContent = 'Paste into your preferred AI assistant to install JingWei.';
      resetTimer = setTimeout(() => { button.textContent = 'Install with LLM'; }, 3000);
    } catch {
      message.textContent = 'Could not copy automatically.';
      manualCopy.hidden = false;
    } finally {
      button.disabled = false;
      feedback.hidden = false;
    }
  });
});

const demoEntryDialog = document.getElementById('demoEntryDialog');
document.getElementById('continueDemo').addEventListener('click', () => demoEntryDialog.close());
demoEntryDialog.showModal();
initialize();''')

css = (STATIC / "styles.css").read_text(encoding="utf-8")
css, removed = re.subn(r'@font-face\s*\{[^}]*\}\s*', '', css)
assert removed == 3, 'Review changed local report font declarations.'
css = css.replace('"Helvetica Neue LT Std Light"', '"Helvetica Neue"').replace('"Helvetica Neue LT Std Bold"', '"Helvetica Neue"').replace('"Helvetica Neue LT Std Bold Condensed"', '"Arial Narrow"').replace('"Arial Narrow", "Arial Narrow"', '"Arial Narrow"')
css = css.replace('/* Original report faces; equal-level sections share one condensed heading style. */', '/* Demo uses system fonts; no proprietary font files are distributed. */')

DOCS.mkdir(exist_ok=True)
for name, content in [('index.html', html), ('app.js', app), ('styles.css', css)]:
    (DOCS / name).write_text(content, encoding='utf-8')
shutil.copyfile(STATIC / 'jingwei-wordmark.svg', DOCS / 'jingwei-wordmark.svg')
(DOCS / 'assets').mkdir(exist_ok=True)
for name in ['sample-cfp-generated.png', 'sample-oct-generated.png', 'README.md']:
    shutil.copyfile(STATIC / 'assets' / name, DOCS / 'assets' / name)
bundle = json.loads((ROOT / 'data/reference_distributions.json').read_text(encoding='utf-8'))
references = json.dumps(bundle['references'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
(DOCS / 'reference-data.js').write_text('// Frozen aggregate research reference data; no individual records.\nwindow.JINGWEI_DEMO_REFERENCES = ' + references + ';\n', encoding='utf-8')
# Retire the separately maintained landing page implementation and duplicate logo.
for obsolete in [DOCS / 'demo.js', DOCS / 'assets/jingwei-wordmark.svg']:
    obsolete.unlink(missing_ok=True)
print('Built docs/ from static/ with browser-only demo behavior.')
