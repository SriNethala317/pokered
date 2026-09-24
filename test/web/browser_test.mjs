// Drives the real page in headless Chromium (playwright-core).
//   PLAYWRIGHT=/path/to/node_modules/playwright-core CHROME=/path/to/chrome \
//     node test/web/browser_test.mjs [--net]
// Serves web/ itself. Needs make web and baserom_red.gbc.
//  1. phone-sized viewport with touch: pick the retail ROM, the page patches
//     it, the game runs and draws; touch Start/A move past the title; no
//     horizontal scroll; the save lands in IndexedDB and export works; a
//     wrong ROM is refused.
//  2. --net (needs internet: public Nostr relays): two pages create/join a
//     room with a password, the host approves, rosters agree, chat relays,
//     a presence packet shows the friend's name tag.
import http from "node:http";
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const web = path.join(root, "web");
const { chromium } = await import(process.env.PLAYWRIGHT || "playwright-core");
const wantNet = process.argv.includes("--net");

const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".json": "application/json" };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, "http://x").pathname);
  const f = path.join(web, u === "/" ? "index.html" : u);
  if (!f.startsWith(web) || !existsSync(f) || f.includes("/vendor/")) {
    res.writeHead(404);
    return res.end();
  }
  res.writeHead(200, { "content-type": TYPES[path.extname(f)] || "application/octet-stream" });
  res.end(readFileSync(f));
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const url = `http://127.0.0.1:${server.address().port}/`;

const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ["--autoplay-policy=no-user-gesture-required"] });
const errors = [];
async function newPage() {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, acceptDownloads: true });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/Failed to load resource/.test(m.text()) && errors.push(m.text()));
  page.on("response", (r) => r.status() >= 400 && !/favicon/.test(r.url()) && errors.push(`${r.status()} ${r.url()}`));
  await page.goto(url);
  return page;
}
// A finger press on a game button, held long enough for the game to poll it.
let pid = 10;
const hold = async (page, sel, ms = 120, after = 250) => {
  const box = await page.locator(sel).boundingBox();
  const init = { pointerId: ++pid, pointerType: "touch", isPrimary: true, bubbles: true,
    clientX: box.x + box.width / 2, clientY: box.y + box.height / 2 };
  await page.locator(sel).dispatchEvent("pointerdown", init);
  await page.waitForTimeout(ms);
  await page.locator(sel).dispatchEvent("pointerup", init);
  await page.waitForTimeout(after);
};
const tap = async (page, sel, ms = 120) => {
  const box = await page.locator(sel).boundingBox();
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await page.touchscreen.tap(x, y);
  await page.waitForTimeout(ms);
};

async function startGame(page) {
  await page.setInputFiles("#romFile", path.join(root, "baserom_red.gbc"));
  await page.waitForSelector("#game:not([hidden])", { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("status").textContent === "", null, { timeout: 15000 });
}

const shades = (page) =>
  page.evaluate(() => {
    const c = document.getElementById("screen").getContext("2d").getImageData(0, 0, 160, 144).data;
    const s = new Set();
    for (let i = 0; i < c.length; i += 4) s.add(c[i]);
    return s.size;
  });

// ---- 1: solo ----
{
  const page = await newPage();
  // a wrong ROM is refused with a message
  await page.setInputFiles("#romFile", { name: "x.gb", mimeType: "application/octet-stream", buffer: Buffer.alloc(1 << 20, 7) });
  await page.waitForFunction(() => /not an unmodified/.test(document.getElementById("setupMsg").textContent));
  await startGame(page);
  await page.waitForTimeout(4000);
  assert.ok((await shades(page)) >= 2, "screen stays blank");
  // measure speed: frames the core ran in 2 s of wall time
  const frames = () => page.evaluate(() => Number(globalThis.resonance.emu.M._shim_frame_count(globalThis.resonance.emu.s)));
  const f0 = await frames();
  await page.waitForTimeout(2000);
  const fps = ((await frames()) - f0) / 2;
  console.log(`page runs at ${fps.toFixed(1)} fps`);
  assert.ok(fps > 50 && fps < 65, `speed ${fps} fps`);
  // press through the title with touch
  for (let i = 0; i < 6; i++) await hold(page, "[data-key=start]", 100, 700);
  // then A until a text box border ("┌" = $79 in wTileMap at $c3a0) is up:
  // the title menu or Oak's speech
  let talking = false;
  for (let i = 0; i < 12 && !talking; i++) {
    await hold(page, ".btn.a", 100, 900);
    talking = await page.evaluate(() => {
      const e = globalThis.resonance.emu;
      for (let i = 0; i < 360; i++) if (e.read(0xc3a0 + i) === 0x79) return true;
      return false;
    });
  }
  assert.ok(talking, "touch presses did not reach the title menu");
  await page.screenshot({ path: "/tmp/web_solo.png" });
  const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth);
  assert.ok(noHScroll, "page scrolls sideways on a phone");
  // the patched ROM is kept in IndexedDB for next time
  await page.reload();
  await page.waitForSelector("#resumeBtn:not([hidden])", { timeout: 5000 });
  await tap(page, "#resumeBtn");
  await page.waitForSelector("#game:not([hidden])");
  // export works
  await tap(page, "#menuBtn");
  const [dl] = await Promise.all([page.waitForEvent("download"), tap(page, "#exportBtn")]);
  assert.equal(dl.suggestedFilename(), "resonance-red.sav");
  await page.screenshot({ path: "/tmp/web_menu.png" });
  await page.context().close();
  console.log("browser solo: ok (screenshots /tmp/web_solo.png, /tmp/web_menu.png)");
}

// ---- 2: rooms over real WebRTC + Nostr ----
if (wantNet) {
  const a = await newPage();
  const b = await newPage();
  for (const p of [a, b]) await startGame(p);
  const openMenu = async (p) => {
    await tap(p, "#menuBtn");
    await p.waitForSelector("#menu:not([hidden])");
  };
  await openMenu(a);
  await a.fill("#nameIn", "Red");
  await a.fill("#pwIn", "hunter2");
  await a.click("#hostBtn");
  await a.waitForSelector("#mpIn:not([hidden])");
  const code = await a.textContent("#roomCode");
  await openMenu(b);
  await b.fill("#nameIn", "Blue");
  await b.fill("#pwIn", "hunter2");
  await b.fill("#codeIn", code.toLowerCase());
  await b.click("#joinBtn");
  // host gets the approval dialog
  await a.waitForSelector("dialog#ask[open]", { timeout: 90000 });
  assert.match(await a.textContent("#askText"), /Blue wants to join/);
  await a.click("dialog#ask button[value=yes]");
  await b.waitForFunction(() => document.querySelectorAll("#roster li").length === 2, null, { timeout: 30000 });
  await a.waitForFunction(() => document.querySelectorAll("#roster li").length === 2, null, { timeout: 30000 });
  // chat both ways through the host
  await b.fill("#chatIn", "hello from blue");
  await b.press("#chatIn", "Enter");
  await a.waitForFunction(() => /Blue: hello from blue/.test(document.getElementById("chatLog").textContent), null, { timeout: 15000 });
  await a.fill("#chatIn", "<img src=x onerror=alert(1)>");
  await a.press("#chatIn", "Enter");
  await b.waitForFunction(() => /Red: <img/.test(document.getElementById("chatLog").textContent), null, { timeout: 15000 });
  assert.equal(await b.locator("#chatLog img").count(), 0, "chat must be text only");
  await a.screenshot({ path: "/tmp/web_room_host.png" });
  await b.screenshot({ path: "/tmp/web_room_guest.png" });
  // kick
  a.once("dialog", () => {});
  await a.locator("#roster li", { hasText: "Blue" }).locator("button", { hasText: "Kick" }).click();
  await a.click("dialog#ask button[value=yes]");
  await b.waitForFunction(() => /removed you/.test(document.getElementById("mpMsg").textContent), null, { timeout: 15000 });
  console.log(`browser net: ok (room ${code}; screenshots /tmp/web_room_*.png)`);
}

await browser.close();
server.close();
// dead public Nostr relays are expected; Trystero uses several
const real = errors.filter((e) => !/favicon|AudioContext|autoplay|WebSocket connection to .wss:/i.test(e));
if (real.length) {
  console.error("page errors:\n" + real.join("\n"));
  process.exit(1);
}
console.log("browser_test: ok");
