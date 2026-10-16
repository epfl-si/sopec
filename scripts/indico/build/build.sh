#!/usr/bin/env bash
set -euo pipefail

# Rebuilds getindico/indico (see Dockerfile in this directory) so it runs
# under OpenShift's arbitrary-UID security model, and pushes the result to
# EPFL's internal quay registry under the same version tag.
#
# Usage: ./build.sh <indico-version>
#   e.g. ./build.sh 3.3.14
#
# Requires either a prior `docker login quay-its.epfl.ch`, or QUAY_USERNAME
# and QUAY_TOKEN set in the environment.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_PATH="quay-its.epfl.ch/svc0176/indico"

VERSION="${1:?Usage: $0 <indico-version>, e.g. 3.3.14}"

if [[ -n "${QUAY_USERNAME:-}" && -n "${QUAY_TOKEN:-}" ]]; then
    echo "${QUAY_TOKEN}" | docker login quay-its.epfl.ch -u "${QUAY_USERNAME}" --password-stdin
fi

docker build \
    --build-arg "INDICO_VERSION=${VERSION}" \
    -t "${REGISTRY_PATH}:${VERSION}" \
    "${SCRIPT_DIR}"

docker push "${REGISTRY_PATH}:${VERSION}"

echo
echo "Pushed ${REGISTRY_PATH}:${VERSION}"
echo "If this is a new version, update the image tag in:"
echo "  apps/indico/base/web.yaml"
echo "  apps/indico/base/celery.yaml"
