#!/usr/bin/env python3
"""Backup PostgreSQL databases from a CNPG cluster via kubectl exec."""
import os, subprocess, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    KEYBASE_ROOT, info, warn, error, set_debug, print_header,
    env_config, check_and_login, check_cnpg_cluster,
)


def backup(env: str, cluster: str):
    cfg = env_config(env)
    if not check_and_login(cfg["api_url"], cfg["context"]):
        sys.exit(1)
    primary = check_cnpg_cluster(cfg["namespace"], cluster)
    if not primary:
        sys.exit(1)

    backup_dir = Path(KEYBASE_ROOT) / env / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True)
    info(f"Backup directory: {backup_dir}")

    r = subprocess.run(
        ["kubectl", "exec", "-n", cfg["namespace"], primary, "--",
         "psql", "-U", "postgres", "-d", "postgres", "-t", "-c",
         "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';"],
        capture_output=True, text=True,
    )
    databases = [db.strip() for db in r.stdout.splitlines() if db.strip()]
    if not databases:
        warn("No user databases found")
        return
    info(f"Databases: {', '.join(databases)}")

    for db in databases:
        out_file = backup_dir / f"{db}.sql"
        info(f"Backing up '{db}'...")
        result = subprocess.run(
            ["kubectl", "exec", "-n", cfg["namespace"], primary, "--",
             "pg_dump", "-U", "postgres", "-d", db, "--clean", "--if-exists"],
            capture_output=True,
        )
        if result.returncode == 0:
            out_file.write_bytes(result.stdout)
            size = out_file.stat().st_size // 1024
            info(f"✓ '{db}' backed up ({size} KB)")
        else:
            error(f"✗ Failed to backup '{db}'")

    total = sum(f.stat().st_size for f in backup_dir.iterdir()) // 1024
    info(f"Done — {backup_dir} ({total} KB total)")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    env, cluster = "", "postgres-cluster"
    for arg in args:
        if arg == "--test":     env = "test"
        elif arg == "--prod":   env = "prod"
        elif arg == "--debug":  set_debug(True)
        elif arg == "--no-debug": set_debug(False)
        else: cluster = arg
    if not env:
        print("Usage: sopec dump [--test|--prod] [--debug] [cluster_name]", file=sys.stderr)
        sys.exit(1)
    print_header("dump", env=env, cluster=cluster)
    backup(env, cluster)


if __name__ == "__main__":
    main()
