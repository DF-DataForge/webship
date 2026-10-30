// Screen recorder for the Stoqflow instruction videos.
//
// Drives Chromium with Playwright at 1920x1080 and records each scene as its
// own clip from the DevTools screencast (JPEG frames with timestamps, turned
// into a constant-frame-rate MP4 by ffmpeg). Headless Chromium draws no mouse
// pointer, so an arrow cursor, a click ripple and a highlight ring are
// injected into every page.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const W = 1920, H = 1080, FPS = 30;
const BASE = process.env.ODOO_URL || 'http://localhost:8069';

const OVERLAY = `
(() => {
  if (window.__recInstalled) return; window.__recInstalled = true;
  const css = \`
    #__rec_cursor { position: fixed; z-index: 2147483647; left: 0; top: 0; width: 28px; height: 28px;
      pointer-events: none; transform: translate(-3px, -2px); transition: none; }
    .__rec_ripple { position: fixed; z-index: 2147483646; width: 44px; height: 44px; margin: -22px 0 0 -22px;
      border-radius: 50%; border: 4px solid rgba(43,143,227,.9); background: rgba(46,211,183,.25);
      pointer-events: none; animation: __rec_ripple .6s ease-out forwards; }
    @keyframes __rec_ripple { from { transform: scale(.3); opacity: 1; } to { transform: scale(1.5); opacity: 0; } }
    .__rec_hl { position: fixed; z-index: 2147483645; pointer-events: none; border-radius: 10px;
      border: 4px solid #2B8FE3; box-shadow: 0 0 0 6px rgba(46,211,183,.35), 0 0 0 9999px rgba(14,27,44,.18);
      transition: opacity .35s; }\`;
  const add = () => {
    if (!document.body) return setTimeout(add, 30);
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const c = document.createElement('div'); c.id = '__rec_cursor';
    c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M3 2 L3 22 L8.5 17 L12.5 26 L16 24.5 L12 15.8 L19.5 15.8 Z" fill="#fff" stroke="#0E1B2C" stroke-width="1.8" stroke-linejoin="round"/></svg>';
    const p = window.__recPos || { x: 960, y: 540 };
    c.style.left = p.x + 'px'; c.style.top = p.y + 'px';
    document.body.appendChild(c);
  };
  add();
  document.addEventListener('mousemove', e => {
    window.__recPos = { x: e.clientX, y: e.clientY };
    const c = document.getElementById('__rec_cursor');
    if (c) { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }
  }, true);
  document.addEventListener('mousedown', e => {
    const r = document.createElement('div'); r.className = '__rec_ripple';
    r.style.left = e.clientX + 'px'; r.style.top = e.clientY + 'px';
    document.body.appendChild(r); setTimeout(() => r.remove(), 700);
  }, true);
  window.__recHighlight = (rect) => {
    document.querySelectorAll('.__rec_hl').forEach(n => n.remove());
    if (!rect) return;
    const h = document.createElement('div'); h.className = '__rec_hl';
    const pad = 8;
    Object.assign(h.style, { left: (rect.x - pad) + 'px', top: (rect.y - pad) + 'px',
      width: (rect.width + 2 * pad) + 'px', height: (rect.height + 2 * pad) + 'px' });
    document.body.appendChild(h);
  };
})();`;

// Wait until Odoo has finished loading: no pending RPC indicator, no block UI.
async function settle(page, ms = 400) {
  try { await page.waitForLoadState('domcontentloaded', { timeout: 15000 }); } catch (e) {}
  try {
    await page.waitForFunction(() => {
      if (document.querySelector('.o_blockUI, .o_loading_indicator, .o_loading')) return false;
      // Odoo backend pages: wait until the current view is rendered
      if (document.querySelector('.o_web_client') && !document.querySelector('.o_action_manager .o_view_controller, .o_action_manager .o_action, .o_home_menu'))
        return false;
      return true;
    }, null, { timeout: 20000, polling: 100 });
  } catch (e) {}
  await page.waitForTimeout(ms);
}

class Recorder {
  constructor(outDir) {
    this.outDir = outDir;
    fs.mkdirSync(outDir, { recursive: true });
    this.mouse = { x: 960, y: 540 };
    this.frames = null;
  }

  async launch() {
    this.browser = await chromium.launch();
    this.context = await this.browser.newContext({
      viewport: { width: W, height: H }, deviceScaleFactor: 1, locale: 'nl-BE',
      timezoneId: 'Europe/Brussels',
    });
    await this.context.addInitScript(OVERLAY);
    this.page = await this.context.newPage();
    this.cdp = await this.context.newCDPSession(this.page);
    this.cdp.on('Page.screencastFrame', async (f) => {
      try { await this.cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) {}
      if (!this.frames || this.paused) return;
      this.frames.push({ t: Date.now() / 1000 - this.cutOffset, data: Buffer.from(f.data, 'base64') });
    });
    return this.page;
  }

  async login(user = 'admin', password = 'admin') {
    const p = this.page;
    await p.goto(BASE + '/web/login');
    await p.fill('input[name=login]', user);
    await p.fill('input[name=password]', password);
    await p.press('input[name=password]', 'Enter');
    await p.waitForURL(/\/odoo/);
    await this.idle();
  }

  // ---- scenes ---------------------------------------------------------------

  async startScene(name) {
    this.sceneName = name;
    // ONLY=s04,s05 re-records just those scenes; the others still run (state) but are not written
    this.skip = !!process.env.ONLY && !process.env.ONLY.split(',').includes(name);
    this.frames = [];
    this.cutOffset = 0;
    this.paused = false;
    this.sceneStart = Date.now() / 1000;
    await this.cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
    // Force one frame immediately so the clip starts with the current view.
    await this.nudge();
  }

  // Force the screencast to emit a frame of the current screen: shift the
  // drawn cursor by one pixel and back (two real repaints).
  async nudge() {
    for (const dx of [1, 0]) {
      await this.page.evaluate(d => {
        const c = document.getElementById('__rec_cursor'); const pos = window.__recPos || { x: 960, y: 540 };
        if (c) c.style.left = (pos.x + d) + 'px';
      }, dx).catch(() => {});
      await this.page.waitForTimeout(80);
    }
  }

  // Run fn without recording the time it takes (slow server calls, page loads).
  async cut(fn) {
    this.paused = true;
    const t0 = Date.now() / 1000;
    try { return await fn(); }
    finally {
      await this.idle();
      this.cutOffset += Date.now() / 1000 - t0;
      this.paused = false;
      await this.nudge();
    }
  }

  async endScene(holdSeconds = 0.4) {
    await settle(this.page, 200);
    await this.page.waitForTimeout(holdSeconds * 1000);
    await this.nudge();
    await this.cdp.send('Page.stopScreencast');
    const end = Date.now() / 1000 - this.cutOffset;
    const frames = this.frames; this.frames = null;
    const file = path.join(this.outDir, this.sceneName + '.mp4');
    if (this.skip) return file + ' (skipped)';
    writeClip(frames, this.sceneStart, end, file);
    return file;
  }

  // ---- interaction helpers ---------------------------------------------------

  async idle(ms = 400) {
    await settle(this.page, ms);
  }

  loc(target) { return typeof target === 'string' ? this.page.locator(target).first() : target; }

  async moveTo(target, { dx = 0, dy = 0, ms = 700 } = {}) {
    const l = this.loc(target);
    await l.scrollIntoViewIfNeeded().catch(() => {});
    const b = await l.boundingBox();
    if (!b) throw new Error('not visible: ' + target);
    const x = b.x + b.width / 2 + dx, y = b.y + b.height / 2 + dy;
    const steps = Math.max(12, Math.round(ms / 16));
    const sx = this.mouse.x, sy = this.mouse.y;
    for (let i = 1; i <= steps; i++) {
      const k = i / steps, e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      await this.page.mouse.move(sx + (x - sx) * e, sy + (y - sy) * e);
      await this.page.waitForTimeout(ms / steps);
    }
    this.mouse = { x, y };
    return l;
  }

  async click(target, opts = {}) {
    const l = await this.moveTo(target, opts);
    await this.page.waitForTimeout(opts.pause ?? 250);
    await this.page.mouse.down(); await this.page.mouse.up();
    await this.idle(opts.after ?? 600);
    return l;
  }

  // Visible click, but the reload it causes is cut out of the recording.
  async clickCut(target, opts = {}) {
    const l = await this.moveTo(target, opts);
    await this.page.waitForTimeout(250);
    await this.cut(async () => {
      await this.page.mouse.down(); await this.page.mouse.up();
      await this.page.waitForTimeout(opts.wait ?? 1500);
      await settle(this.page, 600);
    });
    return l;
  }

  async type(target, text, { delay = 55, clear = true } = {}) {
    const l = await this.click(target, { after: 200 });
    if (clear) { await this.page.keyboard.press('Control+A'); await this.page.keyboard.press('Backspace'); }
    await this.page.keyboard.type(text, { delay });
    await this.page.waitForTimeout(300);
    return l;
  }

  async highlight(target, seconds = 2.0) {
    const l = this.loc(target);
    await l.scrollIntoViewIfNeeded({ timeout: 4000 }).catch(() => {});
    const b = await l.boundingBox({ timeout: 4000 }).catch(() => null);
    if (!b) { console.warn('highlight: not visible', String(target)); await this.page.waitForTimeout(seconds * 1000); return; }
    await this.page.evaluate(r => window.__recHighlight(r), b);
    await this.page.waitForTimeout(seconds * 1000);
    await this.page.evaluate(() => window.__recHighlight(null));
    await this.page.waitForTimeout(150);
  }

  async scroll(dy, ms = 900) {
    await this.page.mouse.move(this.mouse.x, this.mouse.y);
    const steps = Math.round(ms / 16);
    for (let i = 0; i < steps; i++) {
      await this.page.mouse.wheel(0, dy / steps);
      await this.page.waitForTimeout(ms / steps);
    }
    await this.page.waitForTimeout(250);
  }

  // Open an app through the apps menu (so the navbar shows the right app), optionally 'Nieuw'.
  async openApp(name, { create = false } = {}) {
    await this.page.locator('.o_navbar_apps_menu button').first().click();
    await this.page.locator(`.o_app:has-text("${name}")`).first().click();
    await settle(this.page, 600);
    if (create) {
      await this.page.locator('.o_list_button_add, .o-kanban-button-new, button.o_list_button_add').first().click();
      await settle(this.page, 600);
    }
  }

  async wait(seconds) { await this.page.waitForTimeout(seconds * 1000); }

  async goto(url) { await this.page.goto(url.startsWith('http') || url.startsWith('file:') ? url : BASE + url); await this.idle(); }

  async close() { await this.browser.close(); }
}

// Frames arrive only when the screen changes; each one is shown until the next.
// The frames and their durations are kept next to the clip (sKK_frames/) so the
// assembler can lengthen the still moments to match the voice-over.
function writeClip(frames, start, end, file) {
  if (!frames.length) throw new Error('no frames recorded for ' + file);
  const dir = file.replace(/\.mp4$/, '_frames');
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const list = [];
  frames.forEach((f, i) => {
    const name = path.join(dir, String(i).padStart(6, '0') + '.jpg');
    fs.writeFileSync(name, f.data);
    const t = Math.max(f.t, start);
    const next = i + 1 < frames.length ? Math.max(frames[i + 1].t, start) : end;
    list.push({ name, dur: Math.max(next - t, 0) });
  });
  list[0].dur += Math.max(frames[0].t - start, 0);
  fs.writeFileSync(path.join(dir, 'list.json'), JSON.stringify(list));
  renderFrames(list, file);
}

function renderFrames(list, file) {
  let txt = '';
  for (const it of list) txt += `file '${it.name}'\nduration ${it.dur.toFixed(4)}\n`;
  txt += `file '${list[list.length - 1].name}'\n`;
  const lst = file + '.txt';
  fs.writeFileSync(lst, txt);
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
    '-vf', `fps=${FPS},scale=${W}:${H}:flags=lanczos,format=yuv420p`, '-c:v', 'libx264', '-preset', 'medium',
    '-crf', '18', '-movflags', '+faststart', file]);
  fs.rmSync(lst, { force: true });
}

module.exports = { Recorder, BASE };
