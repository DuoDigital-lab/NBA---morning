/* NBA Ráno – frontend bez spoilerov. Žiadny build krok, len statické JSON z data/. */
(function () {
  "use strict";

  var TZ = "Europe/Bratislava";
  var DEFAULT_TEAMS = ["PHI", "BOS", "TOR", "IND", "SA", "DAL", "DET", "HOU", "MIN", "CLE", "MIA", "GS", "WSH"];
  var STALE_HOURS = 30;
  var YT = {
    gametime: { label: "GameTime", hint: "~9 min", url: "https://www.youtube.com/@thegametimehighlights/search?query=" },
    motion: { label: "Motion Station", hint: "~2–3 min", url: "https://www.youtube.com/@motionstation4342/search?query=" },
    all: "https://www.youtube.com/results?search_query=",
  };

  // ---------------- nastavenia (localStorage) ----------------
  var settings = loadSettings();
  function loadSettings() {
    var s = null;
    try { s = JSON.parse(localStorage.getItem("nba-rano-settings") || "null"); } catch (e) { s = null; }
    s = s || {};
    return {
      teams: Array.isArray(s.teams) ? s.teams : DEFAULT_TEAMS.slice(),
      showAll: !!s.showAll,
      browser: s.browser === "default" ? "default" : "brave",
    };
  }

  // Highlights v Brave: na Androide cez intent odkaz priamo do Brave (inak by ho mohla zachytiť appka YouTube).
  // Ak Brave nie je nainštalovaný, otvorí sa bežný odkaz. Na počítači sa otvorí v prehliadači, v ktorom beží appka.
  var BRAVE_ANDROID = "com.brave.browser";
  var IS_ANDROID = /Android/i.test(navigator.userAgent || "");
  function ytLink(url) {
    if (settings.browser === "brave" && IS_ANDROID) {
      var intent = "intent://" + url.replace(/^https:\/\//, "") + "#Intent;scheme=https;package=" + BRAVE_ANDROID +
        ";S.browser_fallback_url=" + encodeURIComponent(url) + ";end";
      return ' href="' + esc(intent) + '"';
    }
    return ' href="' + esc(url) + '" target="_blank" rel="noopener"';
  }
  function saveSettings() {
    try { localStorage.setItem("nba-rano-settings", JSON.stringify(settings)); } catch (e) { /* súkromný režim */ }
  }
  function mine(teamId) {
    var t = state.teamById[teamId];
    return !!t && settings.teams.indexOf(t.abbr) !== -1;
  }
  function tracked(teamId) {
    return settings.showAll || mine(teamId);
  }
  // Zápas dvoch sledovaných tímov – jemne zvýraznená karta.
  function derby(awayId, homeId) { return mine(awayId) && mine(homeId); }
  var DERBY_TAG = '<span class="derby-tag">★ oba tvoje tímy</span>';

  // ---------------- dáta ----------------
  var state = { teams: [], teamById: {}, index: null, injuries: null, upcoming: null, status: null, days: {}, fromCache: false, failed: [] };

  function fetchJSON(path) {
    return fetch(path, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(path + " " + r.status);
      if (r.headers.get("x-from-cache") === "1") state.fromCache = true;
      return r.json();
    }).catch(function (e) {
      state.failed.push(path);
      throw e;
    });
  }
  function soft(p) { return p.catch(function () { return null; }); }

  function loadAll() {
    return Promise.all([
      soft(fetchJSON("data/status.json")),
      soft(fetchJSON("data/teams.json")),
      soft(fetchJSON("data/index.json")),
      soft(fetchJSON("data/injuries.json")),
      soft(fetchJSON("data/upcoming.json")),
    ]).then(function (r) {
      state.status = r[0];
      state.teams = (r[1] && r[1].teams) || [];
      state.teamsMeta = r[1] || {};
      state.teamById = {};
      state.teams.forEach(function (t) { state.teamById[t.id] = t; });
      state.index = r[2];
      state.injuries = r[3];
      state.upcoming = r[4];
    });
  }
  function loadDay(date) {
    if (state.days[date]) return Promise.resolve(state.days[date]);
    return fetchJSON("data/days/" + date + ".json").then(function (d) { state.days[date] = d; return d; });
  }

  // ---------------- formátovanie ----------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var fmtTime = new Intl.DateTimeFormat("sk-SK", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  var fmtDayShort = new Intl.DateTimeFormat("sk-SK", { timeZone: TZ, weekday: "short", day: "numeric", month: "numeric" });
  var fmtStamp = new Intl.DateTimeFormat("sk-SK", { timeZone: TZ, day: "numeric", month: "numeric", hour: "2-digit", minute: "2-digit" });
  var fmtUsDay = new Intl.DateTimeFormat("sk-SK", { timeZone: "UTC", weekday: "long", day: "numeric", month: "numeric", year: "numeric" });
  var fmtUsShort = new Intl.DateTimeFormat("sk-SK", { timeZone: "UTC", weekday: "short", day: "numeric", month: "numeric" });
  function tzName(d) {
    try {
      var p = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, timeZoneName: "short" }).formatToParts(d);
      var n = p.filter(function (x) { return x.type === "timeZoneName"; })[0].value;
      return n === "GMT+1" ? "CET" : n === "GMT+2" ? "CEST" : n;
    } catch (e) { return ""; }
  }
  function usDate(s) { return new Date(s + "T12:00:00Z"); }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function shortDate(iso) {
    if (!iso) return "";
    var p = iso.slice(0, 10).split("-");
    return parseInt(p[2], 10) + ". " + parseInt(p[1], 10) + ".";
  }
  function logo(t, cls) {
    return t && t.logo ? '<img class="' + (cls || "logo") + '" src="' + esc(t.logo) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : "";
  }
  // Vážnosť výpadku (počíta generátor z očakávaného návratu): farba hráča aj ikonky.
  var SEVERITY = [
    ["dtd", "zo dňa na deň"],
    ["short", "do mesiaca"],
    ["month", "1–3 mesiace"],
    ["long", "3–6 mesiacov"],
    ["season", "pol roka a viac"],
    ["unknown", "termín neznámy"],
  ];
  function sevOf(pid) {
    var inj = injuryFor(pid);
    return (inj && inj.severity) || "none";
  }
  function sevIcon(q) { return q ? '<span class="sev-ico q" aria-hidden="true">?</span>' : '<span class="sev-ico" aria-hidden="true"></span>'; }
  function missingPill(m) {
    var inj = injuryFor(m.id);
    var sev = sevOf(m.id);
    var title = inj ? inj.statusSk + " · návrat: " + inj.expectedReturn + (inj.severityBasis === "espn" ? " (farba podľa ESPN odhadu)" : "") : "bez záznamu o zranení";
    return '<a class="mp sev-' + sev + '" href="#recovery/' + esc(m.id) + '" title="' + esc(title) + '">' + sevIcon() + esc(m.name) + "</a>";
  }
  function sevLegend() {
    return '<div class="legend" aria-label="Legenda farieb">' + SEVERITY.map(function (s) {
      return '<span class="sev-' + s[0] + '">' + sevIcon() + esc(s[1]) + "</span>";
    }).join("") + "</div>";
  }
  function statusChip(p) {
    return '<span class="chip sev sev-' + esc(p.severity || "none") + '">' + esc(p.statusSk) + "</span>";
  }

  // ---------------- banner (zastarané / chybné dáta) ----------------
  function renderBanner() {
    var el = document.getElementById("banner");
    var msgs = [];
    var st = state.status;
    if (!st && !state.teams.length) {
      msgs.push("Dáta sa nepodarilo načítať. Skontroluj pripojenie a skús to znova.");
    } else {
      if (state.fromCache || state.failed.length) msgs.push("Si offline alebo server neodpovedá – zobrazujem poslednú uloženú verziu.");
      if (st) {
        var age = (Date.now() - new Date(st.generatedAt).getTime()) / 36e5;
        if (age > STALE_HOURS) msgs.push("Dáta sú staršie (" + fmtStamp.format(new Date(st.generatedAt)) + "). Automatická aktualizácia asi neprebehla.");
        if (st.ok === false) msgs.push("Posledná aktualizácia z ESPN mala problém – zobrazujem poslednú platnú verziu" +
          (st.lastSuccessAt ? " (z " + fmtStamp.format(new Date(st.lastSuccessAt)) + ")" : "") + ".");
      }
    }
    el.hidden = !msgs.length;
    el.innerHTML = msgs.map(esc).join("<br>");
  }

  // ---------------- Zápasy ----------------
  function availableDays() {
    return ((state.index && state.index.days) || []).map(function (d) { return d.date; });
  }

  function viewGames(params) {
    var days = availableDays();
    var date = params[0] && days.indexOf(params[0]) !== -1 ? params[0] : days[0];
    if (!date) {
      return Promise.resolve('<p class="empty">Zatiaľ žiadne odohrané zápasy.</p>' + upcomingHtml());
    }
    return loadDay(date).then(function (day) {
      return gamesHtml(day, days) + upcomingHtml();
    }, function () {
      return '<p class="empty">Deň ' + esc(date) + " sa nepodarilo načítať.</p>" + upcomingHtml();
    });
  }

  function gamesHtml(day, days) {
    var i = days.indexOf(day.date);
    var prev = days[i + 1], next = days[i - 1];
    var opts = days.map(function (d) {
      return '<option value="' + d + '"' + (d === day.date ? " selected" : "") + ">" + esc(cap(fmtUsShort.format(usDate(d)))) + "</option>";
    }).join("");
    var nav = '<div class="daynav">' +
      '<button type="button" data-go="' + (prev || "") + '" aria-label="Predchádzajúci deň"' + (prev ? "" : " disabled") + ">‹</button>" +
      '<div class="day"><strong>' + esc(cap(fmtUsDay.format(usDate(day.date)))) + "</strong>" +
      "<span>" + (i === 0 ? "posledná noc · " : "") + "US dátum · ťukni = história</span>" +
      '<select aria-label="Vybrať deň" data-pick>' + opts + "</select></div>" +
      '<button type="button" data-go="' + (next || "") + '" aria-label="Nasledujúci deň"' + (next ? "" : " disabled") + ">›</button>" +
      "</div>";
    var games = day.games.filter(function (g) { return tracked(g.away.teamId) || tracked(g.home.teamId); });
    var hidden = day.games.length - games.length;
    var body = games.length ? '<div class="games">' + games.map(gameCard).join("") + "</div>"
      : '<p class="empty">Tvoje tímy v tento deň nehrali.</p>';
    if (hidden > 0) body += '<p class="note">Ďalšie zápasy ostatných tímov: ' + hidden + " (zapni „Ukáž aj ostatné tímy“ v Nastaveniach).</p>";
    if (games.length) body += '<p class="note">Farba chýbajúceho hráča = očakávaná dĺžka výpadku (aktuálny stav, ťukni pre detail):</p>' + sevLegend();
    return nav + body;
  }

  function teamRow(side, isHome) {
    var t = state.teamById[side.teamId] || { name: "Tím " + side.teamId };
    var names = side.missing.map(missingPill);
    var absent;
    if (!side.coreGames) absent = '<div class="absent none">základná päťka zatiaľ neznáma (prvý zápas sezóny)</div>';
    else if (names.length) absent = '<div class="absent"><span class="lbl">' + (names.length === 1 ? "nehral" : "nehrali") + "</span>" + names.join("") + "</div>";
    else absent = '<div class="absent none">základná päťka kompletná</div>';
    return '<div class="team-row">' + logo(t) + "<div><div class=\"name\">" + esc(t.name) +
      "<small>" + (isHome ? "DOMÁCI" : "HOSTIA") + "</small></div>" + absent + "</div></div>";
  }

  function gameCard(g) {
    var a = state.teamById[g.away.teamId] || {}, h = state.teamById[g.home.teamId] || {};
    var start = new Date(g.startUTC);
    var q = g.ytQuery || "";
    var pending = g.lineupReady ? "" : '<p class="note">Zostava sa ešte spracúva – skús neskôr.</p>';
    var both = derby(g.away.teamId, g.home.teamId);
    return '<article class="game' + (both ? " derby" : "") + '">' +
      '<div class="stripe"><i style="background:' + esc(a.color || "#2a6bf2") + '"></i><i style="background:' + esc(h.color || "#e0283c") + '"></i></div>' +
      '<div class="body">' + (both ? DERBY_TAG : "") + '<div class="meta"><span>' + esc(a.abbr || "") + " @ " + esc(h.abbr || "") + "</span><span>začiatok " +
      esc(fmtTime.format(start)) + " " + esc(tzName(start)) + "</span></div>" +
      teamRow(g.away, false) + '<div class="at">@</div>' + teamRow(g.home, true) + pending +
      '<div class="hl">' +
      '<a class="gt"' + ytLink(YT.gametime.url + encodeURIComponent(q)) + ">" + YT.gametime.label + " <small>highlights " + YT.gametime.hint + "</small></a>" +
      '<a class="ms"' + ytLink(YT.motion.url + encodeURIComponent(q)) + ">" + YT.motion.label + " <small>highlights " + YT.motion.hint + "</small></a>" +
      "</div>" +
      '<a class="hl-all"' + ytLink(YT.all + encodeURIComponent(q + " highlights")) + ">hľadať na celom YouTube</a>" +
      "</div></article>";
  }

  // ---------------- Nadchádzajúce zápasy (Zápasy + Kalendár) ----------------
  var fmtNightDay = new Intl.DateTimeFormat("sk-SK", { timeZone: "UTC", weekday: "long", day: "numeric", month: "numeric" });
  var fmtChipWd = new Intl.DateTimeFormat("sk-SK", { timeZone: "UTC", weekday: "short" });
  var fmtUsToday = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });
  function addDays(s, n) { var d = usDate(s); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  var ACCUSATIVE = { streda: "stredu", sobota: "sobotu", "nedeľa": "nedeľu" };
  function nightHead(s) {
    var next = fmtNightDay.format(usDate(addDays(s, 1))).replace(/^\S+/, function (w) { return ACCUSATIVE[w] || w; });
    return '<div class="night-h" id="n-' + esc(s) + '"><strong>' + esc(cap(fmtNightDay.format(usDate(s)))) +
      "</strong><span>noc na " + esc(next) + "</span></div>";
  }
  function upcomingTracked() {
    var now = Date.now();
    return ((state.upcoming && state.upcoming.games) || []).filter(function (g) {
      return (tracked(g.awayId) || tracked(g.homeId)) && new Date(g.startUTC).getTime() > now - 4 * 36e5;
    });
  }
  function byNight(games) {
    var out = [], idx = {};
    games.forEach(function (g) {
      if (!(g.usDate in idx)) { idx[g.usDate] = out.length; out.push({ date: g.usDate, games: [] }); }
      out[idx[g.usDate]].games.push(g);
    });
    return out;
  }
  function absPill(e, doubtful) {
    var t = (doubtful ? "otázny" : "isto nehrá") + (e.note ? " – " + e.note : "");
    return '<a class="mp' + (e.isCore ? "" : " sm") + (doubtful ? " q" : "") + " sev-" + esc(e.severity) +
      '" href="#recovery/' + esc(e.id) + '" title="' + esc(t) + '">' + sevIcon(doubtful) + esc(e.name) +
      (e.note ? " <i>" + esc(e.note) + "</i>" : "") + "</a>";
  }
  function isCoreE(e) { return e.isCore; }
  function absBlock(side, coreOnly) {
    var out = (side && side.out) || [], dbt = (side && side.doubtful) || [];
    var o = coreOnly ? out.filter(isCoreE) : out, d = coreOnly ? dbt.filter(isCoreE) : dbt;
    var html = "";
    if (o.length) html += '<div class="abs"><span class="lbl">isto ' + (o.length > 1 ? "nehrajú" : "nehrá") + "</span>" +
      o.map(function (e) { return absPill(e, false); }).join("") + "</div>";
    if (d.length) html += '<div class="abs"><span class="lbl">' + (d.length > 1 ? "otázni" : "otázny") + "</span>" +
      d.map(function (e) { return absPill(e, true); }).join("") + "</div>";
    return html;
  }
  function nonCoreCount(side) {
    return ((side && side.out) || []).concat((side && side.doubtful) || []).filter(function (e) { return !e.isCore; }).length;
  }
  function upGame(g, coreOnly) {
    var a = state.teamById[g.awayId] || {}, h = state.teamById[g.homeId] || {};
    var d = new Date(g.startUTC);
    var when = g.state === "live" ? '<span class="live">práve sa hrá</span>' : "<time>" + esc(fmtTime.format(d)) + "</time>";
    var sides = [[a, g.away], [h, g.home]].map(function (x) {
      var body = absBlock(x[1], coreOnly);
      return body ? '<div class="side"><div class="side-t">' + logo(x[0], "") + esc(x[0].short || x[0].name) + "</div>" + body + "</div>" : "";
    }).join("");
    var hidden = coreOnly ? nonCoreCount(g.away) + nonCoreCount(g.home) : 0;
    if (hidden) sides += '<a class="abs more" href="#kalendar/' + esc(g.usDate) + '">+ ' + hidden +
      " zranených mimo základnej päťky › Kalendár</a>";
    var both = derby(g.awayId, g.homeId);
    return '<div class="up' + (both ? " derby" : "") + '">' + (both ? DERBY_TAG : "") +
      '<div class="up-head"><div class="teams">' + logo(a, "") + esc(a.short || a.name) +
      ' <span class="vs">@</span> ' + logo(h, "") + esc(h.short || h.name) + "</div>" + when + "</div>" +
      (sides ? '<div class="up-abs">' + sides + "</div>" : "") + "</div>";
  }

  function upcomingHtml() {
    var nights = byNight(upcomingTracked()).slice(0, 3);
    var html = '<h2 class="section-title">Najbližšie noci<span class="count">čas v ' + esc(tzName(new Date())) + "</span></h2>";
    if (!nights.length) return html + '<p class="note">Tvoje tímy v najbližších dňoch nehrajú.</p>';
    html += nights.map(function (n) {
      return '<section class="night">' + nightHead(n.date) + '<div class="upcoming">' +
        n.games.map(function (g) { return upGame(g, true); }).join("") + "</div></section>";
    }).join("");
    return html + '<a class="btn more-cal" href="#kalendar">Celý kalendár na 14 dní ›</a>';
  }

  // ---------------- Kalendár ----------------
  function viewCalendar(params) {
    var games = upcomingTracked();
    var nights = byNight(games);
    var counts = {};
    games.forEach(function (g) { counts[g.usDate] = (counts[g.usDate] || 0) + 1; });
    var start = fmtUsToday.format(new Date());
    var span = (state.upcoming && state.upcoming.days) || 14;
    var chips = "";
    for (var i = 0; i < span; i++) {
      var day = addDays(start, i), n = counts[day] || 0;
      chips += '<a class="dchip' + (n ? "" : " off") + '"' + (n ? ' href="#kalendar/' + day + '"' : "") + ">" +
        "<small>" + esc(fmtChipWd.format(usDate(day))) + "</small><b>" + esc(shortDate(day)) + "</b><span>" +
        (n ? n + (n === 1 ? " zápas" : n < 5 ? " zápasy" : " zápasov") : "–") + "</span></a>";
    }
    var html = '<div class="daychips" role="navigation" aria-label="Dni">' + chips + "</div>";
    if (!nights.length) html += '<p class="empty">Tvoje tímy v najbližších ' + span + " dňoch nehrajú.</p>";
    html += nights.map(function (n) {
      return '<section class="night">' + nightHead(n.date) + '<div class="upcoming">' +
        n.games.map(function (g) { return upGame(g, false); }).join("") + "</div></section>";
    }).join("");
    html += '<h2 class="section-title">Ako to čítať</h2>' + sevLegend() +
      '<ul class="info"><li><b>Isto nehrá</b> – ESPN ho na najbližší zápas vedie ako „Out“, alebo je zápas pred jeho očakávaným návratom.</li>' +
      "<li><b>Otázny</b> (prerušovaný okraj, ?) – Day-To-Day na najbližší zápas, alebo zápas pripadá na obdobie možného návratu.</li>" +
      "<li>Väčšie mená = základná päťka. Čas je v " + esc(tzName(new Date())) + ", dátum je deň zápasu v USA. Stav sa aktualizuje každé ráno o 7:00.</li></ul>";
    if (params[0]) setTimeout(function () {
      var el = document.getElementById("n-" + params[0]);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 30);
    return Promise.resolve(html);
  }

  // ---------------- Tímy ----------------
  function orderedTeams() {
    var mine = state.teams.filter(function (t) { return settings.teams.indexOf(t.abbr) !== -1; });
    var rest = state.teams.filter(function (t) { return settings.teams.indexOf(t.abbr) === -1; });
    var byName = function (a, b) { return a.name.localeCompare(b.name, "en"); };
    mine.sort(byName); rest.sort(byName);
    return { mine: mine, rest: settings.showAll ? rest : [] };
  }

  function viewTeams(params) {
    if (params[0]) return Promise.resolve(teamDetail(params[0]));
    var o = orderedTeams();
    var tile = function (t) {
      return '<a class="team-tile" style="--tc:' + esc(t.color || "#2a6bf2") + '" href="#timy/' + esc(t.abbr) + '">' + logo(t, "") + "<span>" + esc(t.name) + "</span></a>";
    };
    var html = '<h2 class="section-title" style="margin-top:4px">Moje tímy</h2>';
    html += o.mine.length ? '<div class="team-grid">' + o.mine.map(tile).join("") + "</div>" : '<p class="empty">Nemáš vybrané žiadne tímy – nastav ich v Nastaveniach.</p>';
    if (o.rest.length) html += '<h2 class="section-title">Ostatné tímy</h2><div class="team-grid">' + o.rest.map(tile).join("") + "</div>";
    return Promise.resolve(html);
  }

  function injuryFor(pid) {
    var list = (state.injuries && state.injuries.players) || [];
    for (var i = 0; i < list.length; i++) if (list[i].id === pid) return list[i];
    return null;
  }

  function playerCard(p, starts, games) {
    var inj = injuryFor(p.id);
    var sub = [p.pos, starts != null ? "štartoval " + starts + " z " + games + " odohraných" : null].filter(Boolean).join(" · ");
    var chip = inj ? statusChip(inj) : "";
    var hs = p.headshot ? '<img class="hs" src="' + esc(p.headshot) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '<div class="hs"></div>';
    var name = inj ? '<a href="#recovery/' + esc(p.id) + '">' + esc(p.name) + "</a>" : esc(p.name);
    return '<div class="player' + (starts != null ? " core" : "") + '">' + hs +
      '<div><div class="nm">' + name + "</div><div class=\"sub\">" + esc(sub) + (chip ? " " + chip : "") + "</div></div>" +
      '<div class="num">' + (p.jersey != null ? "#" + esc(p.jersey) : "") + "</div></div>";
  }

  function teamDetail(abbr) {
    var t = state.teams.filter(function (x) { return x.abbr === abbr; })[0];
    if (!t) return '<p class="empty">Tím sa nenašiel.</p>';
    var byId = {};
    t.roster.forEach(function (p) { byId[p.id] = p; });
    var core = t.core.map(function (c) {
      return playerCard(byId[c.id] || { id: c.id, name: c.name }, c.starts, c.played != null ? c.played : t.coreGames);
    }).join("");
    var rest = t.roster.filter(function (p) { return !p.isCore; }).sort(function (a, b) {
      return (parseInt(a.jersey, 10) || 0) - (parseInt(b.jersey, 10) || 0);
    }).map(function (p) { return playerCard(p, null); }).join("");
    var window = (state.teamsMeta && state.teamsMeta.window) || 10;
    return '<a class="back" href="#timy">‹ Všetky tímy</a>' +
      '<div class="team-head" style="--tc:' + esc(t.color || "#2a6bf2") + '">' + logo(t, "") +
      "<div><h1>" + esc(t.name) + "</h1><p>Súpiska: " + t.roster.length + " hráčov</p></div></div>" +
      '<h2 class="section-title">Základná päťka</h2>' +
      (core ? '<div class="players">' + core + "</div>" : '<p class="note">Zatiaľ bez odohraných zápasov.</p>') +
      '<p class="note">Hráči, ktorí v posledných ' + t.coreGames + " zápasoch tímu (max. " + window + ") štartujú, keď hrajú – vynechané zápasy (zranenie) sa nepočítajú. Iba hráči na aktuálnej súpiske. Zdroj: ESPN box score.</p>" +
      t.notes.map(function (n) { return '<p class="note">⚠︎ ' + esc(n) + "</p>"; }).join("") +
      '<h2 class="section-title">Celý káder<span class="count">' + t.roster.length + "</span></h2>" +
      '<div class="players">' + rest + "</div>" +
      '<p class="note">Súpiska podľa ESPN, aktualizuje sa pri každej synchronizácii.</p>';
  }

  // ---------------- Recovery ----------------
  var recFilter = "core";
  function viewRecovery(params) {
    var list = ((state.injuries && state.injuries.players) || []).filter(function (p) { return tracked(p.teamId); });
    if (recFilter === "core") list = list.filter(function (p) { return p.isCore; });
    var groups = {};
    list.forEach(function (p) { (groups[p.teamId] = groups[p.teamId] || []).push(p); });
    var ids = Object.keys(groups).sort(function (a, b) {
      return ((state.teamById[a] || {}).name || "").localeCompare((state.teamById[b] || {}).name || "", "en");
    });
    var html = '<div class="filters" role="group" aria-label="Filter">' +
      '<button type="button" data-rf="core" aria-pressed="' + (recFilter === "core") + '">Len základná päťka</button>' +
      '<button type="button" data-rf="all" aria-pressed="' + (recFilter === "all") + '">Všetci zranení</button></div>';
    if (!state.injuries) html += '<p class="empty">Údaje o zraneniach nie sú dostupné.</p>';
    else if (!ids.length) html += '<p class="empty">Žiadne zranenia ' + (recFilter === "core" ? "v základných päťkách " : "") + "tvojich tímov. 🎉</p>";
    ids.forEach(function (tid) {
      var t = state.teamById[tid] || {};
      html += '<section class="rec-team"><h2>' + logo(t, "") + esc(t.name || tid) + "</h2>" + groups[tid].map(recCard).join("") + "</section>";
    });
    html += sevLegend() +
      '<p class="note">Zdroj: ESPN injuries (poznámky zhrnuté bez detailov zápasov). „Termín neznámy“ = žiadny zdroj neuvádza konkrétny odhad. ' +
      "Farba sa počíta z odhadu zo zdroja; ak ho zdroj neuvádza, z automatického ESPN odhadu, ktorý je len orientačný.</p>";
    if (params[0]) setTimeout(function () { focusRec(params[0]); }, 30);
    return Promise.resolve(html);
  }

  function recCard(p) {
    var src = [];
    if (p.reportDate) src.push("info z " + shortDate(p.reportDate));
    if (p.returnSource) src.push("zdroj: " + esc(p.returnSource));
    if (p.espnReturnDate) src.push("ESPN odhad: " + shortDate(p.espnReturnDate));
    return '<article class="rec sev-' + esc(p.severity || "none") + '" id="p-' + esc(p.id) + '">' +
      '<div class="top">' + sevIcon() + "<b>" + esc(p.name) + "</b>" + statusChip(p) + (p.isCore ? ' <span class="chip core">základná päťka</span>' : "") + "</div>" +
      '<div class="why">' + esc(p.reason) + "</div>" +
      '<div class="ret"><span>Návrat</span><em>' + esc(p.expectedReturn) + "</em> <small>" +
      esc((p.severityBasis === "espn" ? "podľa ESPN odhadu: " : "") + (p.severityLabel || "")) + "</small></div>" +
      (src.length ? '<div class="src">' + src.join(" · ") + "</div>" : "") + "</article>";
  }

  function focusRec(pid) {
    var el = document.getElementById("p-" + pid);
    if (!el && recFilter === "core") { recFilter = "all"; render(); return; }
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); el.classList.add("flash"); }
  }

  // ---------------- Nastavenia ----------------
  var installEvt = null;
  window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); installEvt = e; });

  function viewSettings() {
    var all = state.teams.slice().sort(function (a, b) { return a.name.localeCompare(b.name, "en"); });
    var st = state.status || {};
    var html = '<label class="setting"><div><strong>Ukáž aj ostatné tímy</strong><p>Zápasy, súpisky a zranenia všetkých 30 tímov.</p></div>' +
      '<span class="switch"><input type="checkbox" data-showall' + (settings.showAll ? " checked" : "") + '><span></span></span></label>' +
      '<label class="setting"><div><strong>Highlights otvárať v Brave</strong><p>' +
      (IS_ANDROID ? "Odkazy sa otvoria priamo v Brave (nie v appke YouTube). Ak Brave nemáš, otvorí sa bežný prehliadač."
        : "Na Androide otvorí odkazy priamo v Brave. Na počítači sa otvoria v prehliadači, v ktorom beží appka.") +
      '</p></div><span class="switch"><input type="checkbox" data-brave' + (settings.browser === "brave" ? " checked" : "") +
      "><span></span></span></label>" +
      '<h2 class="section-title">Sledované tímy<span class="count">' + settings.teams.length + " / 30</span></h2>" +
      '<div class="pick">' + all.map(function (t) {
        return '<label><input type="checkbox" data-team="' + esc(t.abbr) + '"' + (settings.teams.indexOf(t.abbr) !== -1 ? " checked" : "") + ">" +
          logo(t, "") + "<span>" + esc(t.name) + "</span></label>";
      }).join("") + "</div>" +
      '<div class="row-btns"><button type="button" class="btn" data-reset>Obnoviť predvolené tímy</button></div>' +
      '<h2 class="section-title">Pridať na plochu</h2>' +
      '<p class="info">iPhone: v Safari ťukni na <b>Zdieľať</b> → <b>Pridať na plochu</b>. Android: menu prehliadača → <b>Inštalovať aplikáciu</b>.</p>' +
      (installEvt ? '<div class="row-btns"><button type="button" class="btn primary" data-install>Inštalovať appku</button></div>' : "") +
      '<h2 class="section-title">Dáta</h2><ul class="info">' +
      "<li>Posledná synchronizácia: " + (st.generatedAt ? esc(fmtStamp.format(new Date(st.generatedAt))) : "–") + "</li>" +
      "<li>Posledná úspešná: " + (st.lastSuccessAt ? esc(fmtStamp.format(new Date(st.lastSuccessAt))) : "–") + "</li>" +
      "<li>Synchronizácia beží automaticky každé ráno o 7:00.</li>" +
      ((st.errors || []).length ? "<li>Chyby: " + st.errors.map(esc).join("; ") + "</li>" : "") +
      "</ul>" +
      '<p class="note">Appka zámerne neukazuje skóre, výsledky, bilancie, štatistiky, predĺženia ani kurzy.</p>';
    return Promise.resolve(html);
  }

  // ---------------- router ----------------
  var views = { zapasy: viewGames, kalendar: viewCalendar, timy: viewTeams, recovery: viewRecovery, nastavenia: viewSettings };
  function parseHash() {
    var h = (location.hash || "#zapasy").slice(1).split("/");
    return { tab: views[h[0]] ? h[0] : "zapasy", params: h.slice(1).map(decodeURIComponent) };
  }
  function render() {
    var r = parseHash();
    document.querySelectorAll(".tabbar a").forEach(function (a) {
      if (a.dataset.tab === r.tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    renderBanner();
    return views[r.tab](r.params).then(function (html) {
      document.getElementById("view").innerHTML = html;
    });
  }

  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-go],[data-rf],[data-reset],[data-install]");
    if (!t) return;
    if (t.hasAttribute("data-go") && t.dataset.go) location.hash = "#zapasy/" + t.dataset.go;
    if (t.dataset.rf) { recFilter = t.dataset.rf; render(); }
    if (t.hasAttribute("data-reset")) { settings.teams = DEFAULT_TEAMS.slice(); saveSettings(); render(); }
    if (t.hasAttribute("data-install") && installEvt) { installEvt.prompt(); installEvt = null; }
  });
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (t.hasAttribute("data-pick")) location.hash = "#zapasy/" + t.value;
    if (t.hasAttribute("data-showall")) { settings.showAll = t.checked; saveSettings(); }
    if (t.hasAttribute("data-brave")) { settings.browser = t.checked ? "brave" : "default"; saveSettings(); }
    if (t.dataset.team) {
      var i = settings.teams.indexOf(t.dataset.team);
      if (t.checked && i === -1) settings.teams.push(t.dataset.team);
      if (!t.checked && i !== -1) settings.teams.splice(i, 1);
      saveSettings();
      var c = document.querySelector(".section-title .count");
      if (c) c.textContent = settings.teams.length + " / 30";
    }
  });
  window.addEventListener("hashchange", function () { render(); window.scrollTo(0, 0); });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(function () { /* bez offline režimu */ });
  }
  loadAll().then(render);
})();
