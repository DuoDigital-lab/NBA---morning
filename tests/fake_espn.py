import json
import os
import re

from generator.espn import Espn, EspnError

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class FixtureEspn(Espn):
    """ESPN klient, ktorý namiesto siete číta tests/fixtures. Neznámy deň = žiadne zápasy."""

    ROUTES = [
        (r"/teams$", "teams.json"),
        (r"/scoreboard\?dates=(\d+)$", "scoreboard_{0}.json"),
        (r"/summary\?event=(\d+)$", "summary_{0}.json"),
        (r"/teams/(\d+)/schedule", "schedule_{0}.json"),
        (r"/teams/(\d+)/roster$", "roster_{0}.json"),
        (r"/injuries$", "injuries.json"),
    ]

    def _get(self, url):
        for pat, name in self.ROUTES:
            m = re.search(pat, url)
            if m:
                path = os.path.join(FIX, name.format(*m.groups()))
                if not os.path.exists(path):
                    if "scoreboard" in pat:
                        return {"events": []}
                    raise EspnError(f"fixture chýba: {path}")
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
        raise EspnError(f"neznáma URL {url}")
