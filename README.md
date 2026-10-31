# NBA Ráno – bez spoilerov

Osobná PWA appka: každé ráno ukáže, ktoré zápasy tvojich tímov sa v noci odohrali, kto zo základnej päťky
nehral, a dá ti odkazy na highlights na YouTube. **Žiadne skóre, výsledky, bilancie, štatistiky, OT ani kurzy.**

## Čo appka obsahuje

| Karta | Obsah |
|---|---|
| **Zápasy** | Odohrané zápasy (len stav final) zoradené podľa začiatku, „Hostia @ Domáci“, pri každom tíme „(nehral X)“. Tlačidlá **GameTime** (~9 min) a **Motion Station** (~2–3 min) otvoria vyhľadávanie na danom YouTube kanáli. Šípky / ťuknutie na dátum = história. Dole „Dnes v noci hrajú“ s časom v CET/CEST. |
| **Kalendár** | Zápasy tvojich tímov na 14 dní dopredu, zoskupené po nociach, s rýchlym preskokom na deň. Pri každom tíme **isto nehrá** (ESPN „Out“ na najbližší zápas, alebo zápas pred očakávaným návratom) a **otázny** (Day-To-Day, alebo zápas v období možného návratu). Farba = vážnosť zranenia. Prvé 3 noci sú aj na karte Zápasy. |
| **Tímy** | Základná päťka (najčastejší štartéri z posledných ≤10 zápasov) a celý káder s pozíciou, číslom a stavom zranenia. |
| **Recovery** | Zranení hráči: stav, stručný dôvod, očakávaný návrat, dátum správy a zdroj. Filter „len základná päťka“ / „všetci“. |
| **Nastavenia** | Sledované tímy, prepínač „Ukáž aj ostatné tímy“, stav synchronizácie. Ukladá sa lokálne v prehliadači. |

## Ako to funguje

```
GitHub Actions (7:00 a 16:00) ──► python -m generator.build ──► docs/data/*.json ──► GitHub Pages ──► appka v mobile
                                  │
                                  ├─ ESPN scoreboard  → zoznam zápasov, čas, stav
                                  ├─ ESPN summary     → kto štartoval / hral (box score), skóre sa hneď zahodí
                                  ├─ ESPN schedule    → posledných 10 zápasov každého tímu (základná päťka)
                                  ├─ ESPN roster      → aktuálny káder (zohľadňuje trejdy a prepustenia)
                                  └─ ESPN injuries    → Recovery (+ Claude zhrnutie do slovenčiny)
```

* **Kto hral:** výhradne box score. Hráč „hral“, ak má v box score riadok so štatistikami a nie je DNP.
  Hráč, ktorý v box score úplne chýba (zranení často nie sú uvedení vôbec), sa počíta ako „nehral“.
* **Základná päťka** sa počíta k času pred daným zápasom, takže história je konzistentná.
  Hráč, ktorý už nie je na súpiske, sa vynechá a päťku doplní ďalší najčastejší štartér.
* **Spoiler poistka:** parser skladá výstup iba z vymenovaných polí (whitelist). Pred každým zápisom
  prejde výstup kontrolou (`generator/spoilers.py`). Ak nájde zakázaný kľúč alebo text (skóre, OT, výhra…),
  súbor sa nezapíše. Testy (`tests/`) to overujú na fixtures s vymysleným skóre a umelými titulkami.
* **Výpadok ESPN:** chyba sa zapíše do `status.json`, staré súbory ostanú a appka ukáže banner
  „zobrazujem poslednú platnú verziu“. Offline režim zabezpečuje service worker.
* **Odhad návratu:** z ESPN injury poznámok sa najprv vyhodia vety o priebehu zápasu a štatistikách.
  Potom ich Claude (ak je nastavený kľúč) zhrnie do jednej krátkej poznámky. Bez kľúča sa použijú pravidlá.
  Keď zdroj neuvádza termín, appka napíše „termín neznámy“. Pole „ESPN odhad“ je automatický dátum od ESPN, len orientačný.

## Nasadenie (jednorazovo)

1. Na GitHube si vytvor **nový verejný repozitár**, napr. `nba-rano`. GitHub Pages je zadarmo len pre verejné repo; v dátach nie je nič citlivé.
2. V tomto priečinku:
   ```bash
   git init -b main
   git add .
   git commit -m "NBA Ráno"
   git remote add origin https://github.com/TVOJ-UCET/nba-rano.git
   git push -u origin main
   ```
3. Na GitHube **Settings → Pages**: *Source* = „Deploy from a branch“, *Branch* = `main`, priečinok `/docs`.
   Appka pobeží na `https://TVOJ-UCET.github.io/nba-rano/`.
4. **Settings → Secrets and variables → Actions → New repository secret**:
   `ANTHROPIC_API_KEY` = tvoj kľúč z console.anthropic.com. Je to voliteľné; bez kľúča fungujú pravidlá.
   Predvolený model je `claude-sonnet-5-5` s effort `medium`. Zmeniť ich môžeš cez
   *Settings → Secrets and variables → Actions → Variables*: `CLAUDE_MODEL`, `CLAUDE_EFFORT` (`low` / `medium` / `high`).
5. **Actions → Aktualizácia dát → Run workflow**: prvý beh hneď naplní dáta. Potom beží automaticky
   2× denne o **07:00** a **16:00** bratislavského času, v lete aj v zime. GitHub cron môže pár minút meškať.
6. V mobile otvor URL. iPhone: Safari → **Zdieľať → Pridať na plochu**. Android: Chrome → **Inštalovať aplikáciu**.

## Lokálne spustenie

**Najjednoduchšie:** vo Finderi dvojklik na **`Spustiť NBA Ráno.command`**. Aktualizuje dáta, spustí appku,
otvorí ju v prehliadači a v okne Terminálu vypíše adresu pre telefón. Okno nechaj otvorené, kým appku používaš.

**Android na domácej Wi-Fi (kým nie je GitHub):** v Chrome otvor adresu z okna Terminálu (napr. `http://192.168.x.x:8765`),
potom menu ⋮ → **Pridať na plochu**. Funguje len doma, keď beží Mac so spúšťačom. Plnú inštaláciu, offline režim
a automatické aktualizácie prinesie až GitHub Pages (HTTPS).

Ručne cez Terminál:

```bash
python3 -m generator.build                           # stiahne dáta (posledné 3 US dni + dnes)
python3 -m generator.build --backfill-from 2026-10-20  # celá sezóna od začiatku
python3 tools/serve.py                               # náhľad na http://localhost:8765
python3 -m unittest discover -s tests -t . -v        # testy
```

Potrebný je len Python 3.9+. Claude SDK (`pip install anthropic`, Python 3.10+) je voliteľné.

## Zmena tímov

* **V appke:** Nastavenia → zaškrtni tímy. Uloží sa v prehliadači daného zariadenia.
* **Predvolené tímy** (pre nové zariadenie): `DEFAULT_TEAMS` na začiatku `docs/app.js` (skratky ESPN, napr. `GS`, `SA`, `NY`, `UTAH`).
* Generátor vždy pripraví dáta pre všetkých 30 tímov, takže zmena tímov nevyžaduje nový beh.

## Highlights kanály

V `docs/app.js` (objekt `YT`):
* GAMETIME HIGHLIGHTS: `@thegametimehighlights`, plné highlights ~9 min.
* Motion Station: `@motionstation4342`, krátke recapy ~2–3 min.

Odkaz otvorí **vyhľadávanie v rámci kanála** (napr. „Hornets vs Wizards Oct 30 2026“), nie konkrétne video.
⚠️ Náhľady videí na YouTube môžu obsahovať skóre. To appka neovplyvní.

## Keď sa ESPN API zmení

1. Pozri `docs/data/status.json` alebo kartu Nastavenia → Dáta: tam sú chyby z posledného behu.
2. Endpointy sú v `generator/espn.py`, parsovanie polí v `generator/parse.py`. Každá funkcia číta len pár polí,
   takže stačí upraviť cestu k poľu.
3. Spusti `python3 -m unittest discover -s tests -t .`. Ak sa zmenila štruktúra, aktualizuj fixtures v `tests/fixtures/`
   (skript `make_fixtures.py` ich vyrába z uložených odpovedí a skóre nahrádza vymyslenými hodnotami).
4. Kým to neopravíš, appka ukazuje poslednú platnú verziu s upozornením.

## Štruktúra

```
generator/   espn.py (HTTP), parse.py (whitelist), core_five.py, recovery.py, spoilers.py, build.py
docs/        PWA: index.html, app.js, styles.css, sw.js, manifest, icons/, data/ (generované)
state/       cache zostáv zo zápasov a recovery poznámok (bez skóre)
tests/       testy + fixtures s vymysleným skóre
tools/       make_icons.py, serve.py
```
