// Keyboard and touch input. Calls onChange(mask) whenever the held buttons
// change. Touch: one D-pad area (direction from the finger's angle, so a thumb
// can roll between directions) and A/B/Start/Select buttons; multi-touch.

import { KEY } from "./emu.js";

const KEYMAP = {
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  KeyW: "up", KeyS: "down", KeyA: "left", KeyD: "right",
  KeyX: "a", KeyK: "a", KeyZ: "b", KeyJ: "b",
  Enter: "start", ShiftRight: "select", Backspace: "select",
};

export function setupInput({ dpad, buttons, onChange, isTyping }) {
  const kb = new Set();
  const pointers = new Map(); // pointerId -> mask
  let last = -1;

  const emit = () => {
    let m = 0;
    for (const k of kb) m |= KEY[k];
    for (const v of pointers.values()) m |= v;
    // opposing directions cancel, as on the real pad
    if ((m & KEY.left) && (m & KEY.right)) m &= ~(KEY.left | KEY.right);
    if ((m & KEY.up) && (m & KEY.down)) m &= ~(KEY.up | KEY.down);
    if (m !== last) {
      last = m;
      onChange(m);
    }
  };

  addEventListener("keydown", (e) => {
    if (isTyping()) return;
    const k = KEYMAP[e.code];
    if (!k) return;
    e.preventDefault();
    kb.add(k);
    emit();
  });
  addEventListener("keyup", (e) => {
    const k = KEYMAP[e.code];
    if (!k) return;
    kb.delete(k);
    emit();
  });
  addEventListener("blur", () => {
    kb.clear();
    pointers.clear();
    emit();
  });

  const dpadMask = (e) => {
    const r = dpad.getBoundingClientRect();
    const x = e.clientX - (r.left + r.width / 2);
    const y = e.clientY - (r.top + r.height / 2);
    if (Math.hypot(x, y) < r.width * 0.12) return 0; // dead zone
    const a = Math.atan2(y, x) / Math.PI; // -1..1, 0 = right, 0.5 = down
    let m = 0;
    if (a > -0.375 && a < 0.375) m |= KEY.right;
    if (a > 0.125 && a < 0.875) m |= KEY.down;
    if (a > 0.625 || a < -0.625) m |= KEY.left;
    if (a < -0.125 && a > -0.875) m |= KEY.up;
    return m;
  };

  const track = (el, maskOf) => {
    el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      try {
        el.setPointerCapture(e.pointerId); // keep tracking if the finger slides off
      } catch {}
      pointers.set(e.pointerId, maskOf(e));
      navigator.vibrate?.(8);
      emit();
    });
    el.addEventListener("pointermove", (e) => {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, maskOf(e));
      emit();
    });
    const up = (e) => {
      if (pointers.delete(e.pointerId)) emit();
    };
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("contextmenu", (e) => e.preventDefault());
  };

  track(dpad, dpadMask);
  for (const b of buttons) track(b, () => KEY[b.dataset.key]);
}
