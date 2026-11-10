"""Tenký klient na neoficiálne ESPN API. Vracia surový JSON – nikdy ho neukladaj priamo do výstupu,
vždy ho preveď cez generator.parse (whitelist)."""
import json
import time
import urllib.error
import urllib.request

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"


class EspnError(Exception):
    pass


class Espn:
    # ESPN občas pri viacerých požiadavkách naraz vráti prázdnu odpoveď -> viac pokusov s dlhšou pauzou.
    def __init__(self, timeout=25, retries=5, backoff=3.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def _get(self, url):
        last = None
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "nba-nospoiler/1.0 (personal, non-commercial)",
                    "Accept": "application/json",
                })
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    body = r.read()
                    try:
                        return json.loads(body)
                    except ValueError:
                        raise ValueError(f"neplatný JSON (HTTP {r.status}, {len(body)} B, "
                                         f"{r.headers.get('Content-Type')})") from None
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                last = e
                if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code != 429:
                    break
                if attempt < self.retries - 1:
                    time.sleep(self.backoff * (attempt + 1))
        raise EspnError(f"{url}: {last}")

    def teams(self):
        return self._get(f"{SITE}/teams")

    def scoreboard(self, yyyymmdd):
        return self._get(f"{SITE}/scoreboard?dates={yyyymmdd}")

    def summary(self, event_id):
        return self._get(f"{SITE}/summary?event={event_id}")

    def schedule(self, team_id, season):
        return self._get(f"{SITE}/teams/{team_id}/schedule?season={season}")

    def roster(self, team_id):
        return self._get(f"{SITE}/teams/{team_id}/roster")

    def depthchart(self, team_id, season):
        return self._get(f"{CORE}/seasons/{season}/teams/{team_id}/depthcharts")

    def injuries(self):
        return self._get(f"{SITE}/injuries")
