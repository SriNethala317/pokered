// Page glue: ROM setup, the game loop, saves, the menu, rooms, presence, chat
// and link sessions.
import { patchRom, sha1Hex, BpsError } from "./bps.js";
import { Emulator } from "./emu.js";
import { setupInput } from "./input.js";
import * as store from "./saves.js";
import { Net, loadTrystero, newRoomCode, normalizeCode } from "./net.js";
import { Presence } from "./presence.js";
import { LinkHost } from "./linkhost.js";
import { cleanName, CHAT_MAX } from "./protocol.js";

const $ = (id) => document.getElementById(id);
const PRESETS = ["Hi!", "Follow me", "Wait here", "Battle?", "Trade?", "Good game!", "Brb", "Over here!"];
const prefs = {
  get(k, d) {
    try {
      return localStorage.getItem(`resonance.${k}`) ?? d;
    } catch {
      return d;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem(`resonance.${k}`, v);
    } catch {}
  },
};

let manifest, patch, emu, romBytes, presence, net, link;

function status(text) {
  $("status").textContent = text;
}
function setupMsg(text) {
  $("setupMsg").textContent = text;
}
function mpMsg(text) {
  $("mpMsg").textContent = text;
}

async function ask(text) {
  const d = $("ask");
  $("askText").textContent = text;
  d.showModal();
  return new Promise((res) => d.addEventListener("close", () => res(d.returnValue === "yes"), { once: true }));
}

// ---------- setup ----------
async function boot() {
  try {
    [manifest, patch] = await Promise.all([
      fetch("build/manifest.json").then((r) => r.json()),
      fetch("build/pokered.bps").then((r) => r.arrayBuffer()).then((b) => new Uint8Array(b)),
    ]);
  } catch {
    setupMsg("This page is missing its build files (build/manifest.json, build/pokered.bps).");
    return;
  }
  try {
    const saved = await store.get(store.romKey(manifest.romSha1));
    if (saved) {
      $("resumeBtn").hidden = false;
      $("resumeBtn").onclick = () => start(new Uint8Array(saved));
    }
  } catch {}
  $("romFile").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) return setupMsg("That file is too big to be a Game Boy ROM.");
    setupMsg("Checking…");
    try {
      const { rom } = await patchRom(new Uint8Array(await f.arrayBuffer()), patch, manifest);
      try {
        await store.put(store.romKey(manifest.romSha1), rom);
      } catch {}
      start(rom);
    } catch (err) {
      setupMsg(err instanceof BpsError ? err.message : `Could not read that file: ${err.message}`);
    }
  });
}

async function start(rom) {
  // the stored ROM could have been tampered with; check it every time
  if ((await sha1Hex(rom)) !== manifest.romSha1) {
    setupMsg("The stored game is not this build. Please pick your ROM again.");
    $("resumeBtn").hidden = true;
    return;
  }
  romBytes = rom;
  $("setup").hidden = true;
  $("game").hidden = false;
  status("Loading…");
  emu = await Emulator.create($("screen"));
  emu.loadRom(rom);
  try {
    const sram = await store.get(store.sramKey(manifest.romSha1));
    if (sram && sram.byteLength === emu.sramSize()) emu.loadSram(new Uint8Array(sram));
  } catch {}
  emu.enableAudio().catch(() => {});
  const muted = prefs.get("muted", "0") === "1";
  emu.setMuted(muted);
  $("muteBtn").textContent = `Sound: ${muted ? "off" : "on"}`;

  setupInput({
    dpad: $("dpad"),
    buttons: [...document.querySelectorAll("[data-key]")],
    onChange: (m) => emu.setKeys(m),
    isTyping: () => ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName),
  });

  presence = new Presence({
    emu, rom, manifest,
    canvas: $("overlay"),
    tags: $("tags"),
    nameOf: (slot) => net?.roster.get(slot)?.name,
  });
  emu.on("frame", () => {
    const pkt = presence.tick();
    if (pkt && net && net.slot >= 0) net.sendPos(pkt);
  });
  emu.on("draw", () => presence.render());

  setInterval(persistSram, 1000);
  addEventListener("pagehide", persistSram);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) persistSram();
  });
  emu.start();
  globalThis.resonance = { emu, manifest }; // for the console and tests
  status("");
}

let saving = false;
async function persistSram() {
  if (!emu || saving || !emu.sramDirty()) return;
  saving = true;
  try {
    await store.put(store.sramKey(manifest.romSha1), emu.saveSram());
  } catch {
    status("Could not save to this browser's storage. Export your save!");
  } finally {
    saving = false;
  }
}

// ---------- menu ----------
$("menuBtn").onclick = () => {
  const m = $("menu");
  m.hidden = !m.hidden;
  $("menuBtn").setAttribute("aria-expanded", String(!m.hidden));
  if (!m.hidden) emu?.enableAudio().catch(() => {});
};
$("muteBtn").onclick = () => {
  if (!emu) return;
  const m = !(prefs.get("muted", "0") === "1");
  prefs.set("muted", m ? "1" : "0");
  emu.setMuted(m);
  $("muteBtn").textContent = `Sound: ${m ? "off" : "on"}`;
};
$("fsBtn").onclick = () => {
  const el = document.documentElement;
  if (document.fullscreenElement) document.exitFullscreen();
  else (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
};
$("exportBtn").onclick = () => {
  if (!emu) return;
  store.download(emu.saveSram(), "resonance-red.sav");
};
$("importFile").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f || !emu) return;
  if (link?.active) return status("Not during a link.");
  const bytes = new Uint8Array(await f.arrayBuffer());
  if (bytes.length !== emu.sramSize()) return status(`A save for this game is ${emu.sramSize()} bytes; that file is ${bytes.length}.`);
  if (!(await ask("Replace your current save with this file? The game will restart."))) return;
  emu.loadSram(bytes);
  await store.put(store.sramKey(manifest.romSha1), bytes);
  emu.reset();
  status("Save imported.");
});

// ---------- multiplayer ----------
$("nameIn").value = prefs.get("name", "");
$("turnUrl").value = prefs.get("turnUrl", "");
$("turnUser").value = prefs.get("turnUser", "");

async function openRoom(asHost) {
  if (!emu) return mpMsg("Start the game first.");
  const name = cleanName($("nameIn").value);
  if (!name) return mpMsg("Pick a name first.");
  prefs.set("name", name);
  let code;
  if (asHost) code = newRoomCode();
  else if (!(code = normalizeCode($("codeIn").value))) return mpMsg("Enter the room code your friend gave you.");
  const turnUrl = $("turnUrl").value.trim();
  prefs.set("turnUrl", turnUrl);
  prefs.set("turnUser", $("turnUser").value.trim());
  let turn = null;
  if (turnUrl) {
    if (!/^turns?:[^\s]+$/.test(turnUrl)) return mpMsg("A TURN URL starts with turn: or turns:");
    turn = { urls: turnUrl, username: $("turnUser").value.trim(), credential: $("turnPass").value };
  }
  mpMsg("Connecting…");
  let trystero;
  try {
    trystero = await loadTrystero();
  } catch {
    return mpMsg("Could not load the networking library. Are you online?");
  }
  net = new Net({
    joinRoom: trystero.joinRoom, selfId: trystero.selfId,
    build: manifest.romSha1, protocol: manifest.protocol, name, turn,
  });
  wireNet(net);
  net.open(code, $("pwIn").value, asHost);
  $("roomCode").textContent = code;
  $("mpOut").hidden = true;
  $("mpIn").hidden = false;
  mpMsg(asHost ? "Room created. Send your friends the code (and the password, if you set one)." : "Looking for the room…");
}

function wireNet(n) {
  n.on("status", mpMsg);
  n.on("notice", mpMsg);
  n.on("error", mpMsg);
  n.on("joined", () => mpMsg(""));
  n.on("roster", renderRoster);
  n.on("pos", (p) => presence.update(p));
  n.on("chat", (m) => addChat(m.slot, m.text));
  n.on("request", async ({ peerId, name }) => {
    const ok = await ask(`${name} wants to join. Let them in?`);
    if (ok) n.approve(peerId);
    else n.deny(peerId);
  });
  n.on("closed", (reason) => {
    mpMsg(reason);
    leaveRoom(false);
  });
  link = new LinkHost({
    emu, net: n, manifest,
    ui: {
      state: (t) => ($("linkState").textContent = t),
      incoming: (m) => ask(`${n.roster.get(n.slotOf(m.from))?.name || "Someone"} wants to ${m.mode === "trade" ? "trade" : "battle"} over the link cable. OK?`),
      started: () => {
        $("linkBadge").hidden = false;
        $("endLinkBtn").hidden = false;
      },
      ended: (reason, reset) => {
        $("linkBadge").hidden = true;
        $("endLinkBtn").hidden = true;
        $("linkState").textContent = reset ? `${reason} Your game was restarted from your last save.` : reason;
      },
    },
  });
}

async function leaveRoom(send = true) {
  link?.dispose();
  const n = net;
  net = null;
  link = null;
  presence?.clear();
  if (n && send) await n.leave();
  $("mpOut").hidden = false;
  $("mpIn").hidden = true;
  $("roster").textContent = "";
  $("chatLog").textContent = "";
}

function renderRoster(players) {
  const ul = $("roster");
  ul.textContent = "";
  const live = new Set(players.map((p) => p[0]));
  for (const slot of presence.friends.keys()) if (!live.has(slot)) presence.remove(slot);
  for (const [slot, peerId, name] of players) {
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.className = "name";
    span.textContent = `${name}${slot === 0 ? " (host)" : ""}${slot === net.slot ? " (you)" : ""}`;
    li.append(span);
    if (slot !== net.slot) {
      for (const mode of ["battle", "trade"]) {
        const b = document.createElement("button");
        b.className = "small";
        b.textContent = mode === "battle" ? "Battle" : "Trade";
        b.onclick = () => link.invite(peerId, mode) || ($("linkState").textContent = "You already have a link open.");
        li.append(b);
      }
      if (net.isHost) {
        const k = document.createElement("button");
        k.className = "small";
        k.textContent = "Kick";
        k.onclick = async () => (await ask(`Remove ${name} from the room?`)) && net.kick(peerId);
        li.append(k);
      }
    }
    ul.append(li);
  }
}

function addChat(slot, text) {
  if (!$("chatOn").checked) return;
  const li = document.createElement("li");
  const b = document.createElement("b");
  b.textContent = `${net?.roster.get(slot)?.name || "?"}: `;
  li.append(b, document.createTextNode(text));
  const log = $("chatLog");
  log.append(li);
  while (log.children.length > 100) log.firstChild.remove();
  log.scrollTop = log.scrollHeight;
  if (slot !== net?.slot) presence.say(slot, text);
}

$("endLinkBtn").onclick = () => link?.end("Link ended.");
$("hostBtn").onclick = () => openRoom(true);
$("joinBtn").onclick = () => openRoom(false);
$("leaveBtn").onclick = () => leaveRoom(true);
$("copyBtn").onclick = () => navigator.clipboard?.writeText($("roomCode").textContent).catch(() => {});
$("chatOn").checked = prefs.get("chat", "1") === "1";
const syncChatOn = () => {
  prefs.set("chat", $("chatOn").checked ? "1" : "0");
  $("chatForm").hidden = $("presets").hidden = $("chatLog").hidden = !$("chatOn").checked;
};
$("chatOn").onchange = syncChatOn;
syncChatOn();
for (const p of PRESETS) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = p;
  b.onclick = () => net?.sendChat(p) === false && mpMsg("Slow down a little.");
  $("presets").append(b);
}
$("chatIn").maxLength = CHAT_MAX;
$("chatForm").onsubmit = (e) => {
  e.preventDefault();
  if (!net) return;
  if (net.sendChat($("chatIn").value)) $("chatIn").value = "";
  else mpMsg("Slow down a little.");
};

boot();
