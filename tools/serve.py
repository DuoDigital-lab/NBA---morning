"""Lokálny náhľad appky.

    python3 tools/serve.py           # len tento Mac: http://localhost:8765
    python3 tools/serve.py --lan     # aj telefón na rovnakej Wi-Fi: http://<IP Macu>:8765
"""
import argparse
import functools
import http.server
import os
import socket
import subprocess
import sys
import webbrowser

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def lan_ip():
    """IP adresa Macu v domácej sieti (UDP socket nič neodošle, len zistí lokálnu adresu)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.0.1", 9))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def open_in_brave(url):
    """Na Macu otvorí appku v Brave (aj highlights sa potom otvoria v Brave); bez Brave v predvolenom prehliadači."""
    if sys.platform == "darwin" and subprocess.run(["open", "-a", "Brave Browser", url],
                                                   stderr=subprocess.DEVNULL).returncode == 0:
        return
    webbrowser.open(url)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", type=int, default=8765)
    ap.add_argument("--lan", action="store_true", help="sprístupniť aj ostatným zariadeniam na Wi-Fi")
    ap.add_argument("--open", action="store_true", help="otvoriť appku v prehliadači")
    args = ap.parse_args()

    os.chdir(DOCS)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DOCS)
    server = http.server.ThreadingHTTPServer((host, args.port), handler)

    print("\n  NBA Ráno beží.\n")
    print(f"  Na tomto Macu:   http://localhost:{args.port}")
    if args.lan:
        ip = lan_ip()
        print(f"  Na telefóne:     http://{ip}:{args.port}   (telefón musí byť na rovnakej Wi-Fi)" if ip
              else "  IP adresu Macu sa nepodarilo zistiť (Systémové nastavenia → Wi-Fi → Podrobnosti).")
    print("\n  Ukončenie: zatvor toto okno alebo stlač Ctrl+C.\n")
    if args.open:
        open_in_brave(f"http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
