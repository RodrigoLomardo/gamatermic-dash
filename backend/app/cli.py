"""CLI operacional: python -m app.cli <comando>."""
import argparse
import asyncio
import os
import secrets
from pathlib import Path

from app.core.db import dispose_engine
from app.core.logging import configure_logging


async def _main(args: argparse.Namespace) -> None:
    from app.bootstrap import seed

    if args.cmd == "bootstrap":
        email = args.admin_email or os.environ.get("GAMA_ADMIN_EMAIL", "admin@gamatermic.local")
        pw = args.admin_password or os.environ.get("GAMA_ADMIN_PASSWORD")
        generated = False
        if not pw:
            pw, generated = secrets.token_urlsafe(14) + "aZ9x", True
        await seed.bootstrap(email, pw, with_seed=not args.no_seed)
        print(f"Bootstrap concluído. Admin: {email}")
        if generated:
            print(f"Senha gerada (anote, não será exibida novamente): {pw}")
    elif args.cmd == "import-xlsx":
        for r in await seed.import_xlsx(Path(args.path)):
            print(r)
    await dispose_engine()


def main() -> None:
    configure_logging("WARNING")
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap", help="Semeia permissões, roles, setor, datasets, dashboards e o admin")
    b.add_argument("--admin-email")
    b.add_argument("--admin-password")
    b.add_argument("--no-seed", action="store_true", help="Somente catálogo e admin (sem datasets/dashboards)")
    i = sub.add_parser("import-xlsx", help="Importa as abas do relatório Ploomes pelo pipeline de ingestão")
    i.add_argument("path")
    asyncio.run(_main(ap.parse_args()))


if __name__ == "__main__":
    main()
