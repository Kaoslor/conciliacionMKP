"""Ejecuta 001_multimarketplace.sql sobre la base `conciliacion` (se usa una sola vez).

Uso (PowerShell, dentro de la carpeta Dashboard_conciliacion):
    py migrar.py

Toma la conexión de .streamlit\\secrets.toml, así que en ese momento el usuario
configurado ahí debe ser el administrador (sysadmin). Cuando termine, cambia
secrets.toml al usuario de solo lectura (metabase_reader).
"""
import sys
import tomllib
from pathlib import Path

import psycopg2

BASE = Path(__file__).resolve().parent
SQL_FILE = BASE / "001_multimarketplace.sql"
SECRETS = BASE / ".streamlit" / "secrets.toml"


def main() -> None:
    if not SQL_FILE.exists():
        sys.exit(f"No encuentro {SQL_FILE.name} en {BASE}")
    if not SECRETS.exists():
        sys.exit(f"No encuentro {SECRETS}")

    cfg = tomllib.loads(SECRETS.read_text(encoding="utf-8"))["connections"]["postgres"]
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg.get("port", 5432), dbname=cfg["database"],
        user=cfg["username"], password=cfg["password"], sslmode="require", connect_timeout=15,
    )
    conn.autocommit = True  # el script trae su propio BEGIN/COMMIT
    cur = conn.cursor()
    print(f"Conectado a {cfg['database']} como {cfg['username']}")

    cur.execute("SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY 1")
    tablas = [r[0] for r in cur.fetchall()]
    print("Tablas actuales:", ", ".join(tablas) or "(ninguna)")

    if "conciliacion_marketplace" in tablas:
        print("La migración ya estaba hecha (existe conciliacion_marketplace). No se ejecuta de nuevo.")
    else:
        if "conciliacion_falabella" not in tablas:
            r = input("No existe conciliacion_falabella: se crearán las tablas vacías. ¿Continuar? (s/n): ")
            if r.strip().lower() != "s":
                sys.exit("Cancelado.")
        try:
            cur.execute(SQL_FILE.read_text(encoding="utf-8"))
        except psycopg2.Error as e:
            cur.execute("ROLLBACK")
            sys.exit(f"\nERROR, no se aplicó ningún cambio:\n{e}")
        print("Migración aplicada.")

    print("\nResultado en conciliacion_marketplace:")
    cur.execute("SELECT marketplace, estado, COUNT(*) FROM conciliacion_marketplace "
                "GROUP BY 1, 2 ORDER BY 1, 2")
    for mkp, est, n in cur.fetchall():
        print(f"  {mkp:<12} {est:<20} {n}")
    cur.execute("SELECT codigo, activo FROM marketplace ORDER BY orden")
    print("\nMarketplaces:", ", ".join(f"{c}{' (activo)' if a else ''}" for c, a in cur.fetchall()))
    conn.close()


if __name__ == "__main__":
    main()
