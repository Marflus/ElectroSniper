from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser

import uvicorn

from electrosniper.config import load_settings


def _open_browser_later(url: str) -> None:
    time.sleep(1.6)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="ElectroSniper - Chasseur d'électronique HS")
    parser.add_argument(
        "--fb-login",
        action="store_true",
        help="Ouvre un navigateur pour se connecter une fois à Facebook Marketplace.",
    )
    parser.add_argument(
        "--lbc-solve",
        action="store_true",
        help="Affiche comment copier ton cookie DataDome Leboncoin depuis Chrome.",
    )
    parser.add_argument(
        "--diag",
        action="store_true",
        help="Teste Leboncoin, Vinted, Facebook et la clé Anthropic en console.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Ne pas ouvrir automatiquement le navigateur au démarrage.",
    )
    args = parser.parse_args()

    if args.fb_login:
        from electrosniper.scrapers.facebook import run_fb_login_interactive

        run_fb_login_interactive()
        sys.exit(0)

    if args.lbc_solve:
        from electrosniper.scrapers.leboncoin import run_lbc_solve_interactive

        run_lbc_solve_interactive()
        sys.exit(0)

    if args.diag:
        from electrosniper.db import Database
        from electrosniper.scrapers import FacebookScraper, LeboncoinScraper, VintedScraper

        db = Database()
        settings = load_settings(db.get_all_settings())
        print("=== Etat Cle Anthropic ===")
        if settings.anthropic_api_key:
            try:
                import anthropic
                print(f"OK (configuree, SDK v{getattr(anthropic, '__version__', '?')})")
            except Exception as exc:
                print(f"ERREUR import anthropic : {exc}")
        else:
            print("MANQUANTE ou placeholder sk-ant-xxxx dans .env")

        for sc in (LeboncoinScraper(queries_per_cycle=2), VintedScraper(queries_per_cycle=2), FacebookScraper()):
            print(f"\n=== Test {sc.name} ===")
            try:
                if sc.name == "facebook":
                    items = sc.scan(settings, debug=True)
                else:
                    items = sc.scan(settings)
                with_img = sum(1 for it in items if it.image_url)
                print(f"OK -> {len(items)} annonces brutes ({with_img} avec photo)")
                for it in items[:3]:
                    print(f"  - {it.price}EUR | img={'OUI' if it.image_url else 'NON'} | {it.title[:55]}")
            except Exception as exc:
                print(f"ERREUR -> {exc}")
        sys.exit(0)

    settings = load_settings()
    url = f"http://{settings.web_host}:{settings.web_port}"

    if not args.no_browser:
        threading.Thread(target=_open_browser_later, args=(url,), daemon=True).start()

    print(f"ElectroSniper demarre sur {url}")
    uvicorn.run(
        "electrosniper.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
