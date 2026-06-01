#!/usr/bin/env python3
"""Restore PostgreSQL databases from the latest Keybase backup via kubectl exec."""
import os, subprocess, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    KEYBASE_ROOT, info, warn, error, set_debug, print_header,
    env_config, check_and_login, check_cnpg_cluster,
)


def find_latest_backup(env: str) -> Path:
    root = Path(KEYBASE_ROOT) / env
    if not root.is_dir():
        raise FileNotFoundError(f"Backup directory not found: {root}")
    dirs = sorted(root.glob("????????_??????"))
    if not dirs:
        raise FileNotFoundError(f"No backups found in {root}")
    latest = dirs[-1]
    info(f"Latest backup: {latest}")
    return latest


def restore(env: str, cluster: str):
    cfg = env_config(env)

    backup_dir = find_latest_backup(env)
    sql_files = sorted(backup_dir.glob("*.sql"))
    if not sql_files:
        error(f"No .sql files found in {backup_dir}")
        sys.exit(1)
    info(f"Databases to restore: {', '.join(f.stem for f in sql_files)}")

    if not check_and_login(cfg["api_url"], cfg["context"]):
        sys.exit(1)
    primary = check_cnpg_cluster(cfg["namespace"], cluster)
    if not primary:
        sys.exit(1)

    for sql_file in sql_files:
        db = sql_file.stem
        info(f"Restoring '{db}'...")
        proc = subprocess.Popen(
            ["kubectl", "exec", "-i", "-n", cfg["namespace"], primary, "--",
             "psql", "-U", "postgres", "-d", db],
            stdin=subprocess.PIPE, capture_output=True,
        )
        proc.communicate(input=sql_file.read_bytes())
        if proc.returncode == 0:
            info(f"✓ '{db}' restored")
        else:
            error(f"✗ Failed to restore '{db}'")

    info("Done")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    env, cluster = "", "postgres-cluster"
    for arg in args:
        if arg == "--test":       env = "test"
        elif arg == "--prod":     env = "prod"
        elif arg == "--debug":    set_debug(True)
        elif arg == "--no-debug": set_debug(False)
        else: cluster = arg
    if not env:
        print("Usage: sopec import [--test|--prod] [--debug] [cluster_name]", file=sys.stderr)
        sys.exit(1)
    print_header("import", env=env, cluster=cluster)
    warn("DATABASE RESTORATION WARNING")
    warn(f"This will OVERWRITE data in {env} from the latest backup.")
    answer = input("Continue? (yes/no): ").strip()
    if answer != "yes":
        info("Cancelled")
        sys.exit(0)

    restore(env, cluster)


if __name__ == "__main__":
    main()
