#!/usr/bin/env python3
"""Mirror a Docker image to quay-its.epfl.ch."""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import print_header

QUAY        = "quay-its.epfl.ch"
DEFAULT_ORG = "svc0176"


def mirror(source: str, target_org: str = DEFAULT_ORG):
    image_name = source.split("/")[-1]
    target = f"{QUAY}/{target_org}/{image_name}"
    subprocess.run(["docker", "pull", source], check=True)
    subprocess.run(["docker", "tag", source, target], check=True)
    subprocess.run(["docker", "push", target], check=True)
    print("Mirror completed successfully")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    if not args:
        print("Usage: sopec mirror <source_image> [target_org]", file=sys.stderr)
        print(f"Example: sopec mirror ghcr.io/org/image:tag {DEFAULT_ORG}", file=sys.stderr)
        sys.exit(1)
    source     = args[0]
    target_org = args[1] if len(args) > 1 else DEFAULT_ORG
    target     = f"{QUAY}/{target_org}/{source.split('/')[-1]}"
    print_header("mirror", source=source, target=target)
    mirror(source, target_org)


if __name__ == "__main__":
    main()
