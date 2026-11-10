/* Service worker: appka funguje offline a pri výpadku ukáže poslednú platnú verziu dát. */
var VERSION = "v14";
var SHELL = "shell-" + VERSION;
var DATA = "data-" + VERSION;
var ASSETS = "assets-" + VERSION;
var SHELL_FILES = ["./", "index.html", "styles.css", "app.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(SHELL).then(function (c) { return c.addAll(SHELL_FILES); }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return [SHELL, DATA, ASSETS].indexOf(k) === -1; }).map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function markCached(resp) {
  return resp.blob().then(function (body) {
    var h = new Headers(resp.headers);
    h.set("x-from-cache", "1");
    return new Response(body, { status: 200, headers: h });
  });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);

  // Dáta: najprv sieť, pri chybe posledná uložená verzia (s príznakom pre banner).
  if (url.origin === location.origin && url.pathname.indexOf("/data/") !== -1) {
    e.respondWith(fetch(req, { cache: "no-store" }).then(function (resp) {
      if (resp.ok) {
        var copy = resp.clone();
        caches.open(DATA).then(function (c) { c.put(req.url.split("?")[0], copy); });
        return resp;
      }
      throw new Error("HTTP " + resp.status);
    }).catch(function () {
      return caches.match(req.url.split("?")[0]).then(function (hit) {
        if (hit) return markCached(hit);
        return new Response("{}", { status: 503, headers: { "content-type": "application/json" } });
      });
    }));
    return;
  }

  // Shell: najprv sieť (nová verzia appky hneď), offline z cache.
  if (url.origin === location.origin) {
    e.respondWith(fetch(req, { cache: "no-cache" }).then(function (resp) {
      if (resp.ok) { var copy = resp.clone(); caches.open(SHELL).then(function (c) { c.put(req, copy); }); }
      return resp;
    }).catch(function () {
      return caches.match(req).then(function (hit) { return hit || caches.match("index.html"); });
    }));
    return;
  }

  // Logá, fotky hráčov, fonty: cache-first.
  if (/espncdn\.com$|fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    e.respondWith(caches.open(ASSETS).then(function (c) {
      return c.match(req).then(function (hit) {
        return hit || fetch(req).then(function (resp) { c.put(req, resp.clone()); return resp; });
      });
    }));
  }
});
