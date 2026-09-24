// Saves in IndexedDB, keyed by build sha1. Also keeps the patched ROM so the
// player only picks their cartridge dump once per device.

const DB = "resonance";
const STORE = "kv";

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const req = fn(t.objectStore(STORE));
    t.oncomplete = () => resolve(req && req.result);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  });
}

export const get = (key) => tx("readonly", (s) => s.get(key));
export const put = (key, value) => tx("readwrite", (s) => s.put(value, key));
export const del = (key) => tx("readwrite", (s) => s.delete(key));

export const sramKey = (sha1) => `sram:${sha1}`;
export const romKey = (sha1) => `rom:${sha1}`;

// Download bytes as a file.
export function download(bytes, name) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
