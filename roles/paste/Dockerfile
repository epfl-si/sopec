# docker build . -t quay-its.epfl.ch/svc0176/hemmelig:latest
# docker push quay-its.epfl.ch/svc0176/hemmelig:latest
FROM hemmeligapp/hemmelig:v7

USER root

# OpenShift runs containers as an arbitrary non-root UID, which breaks the
# upstream gosu-based entrypoint. Replace it with a direct invocation.
RUN printf '#!/bin/sh\nset -e\nnpx prisma migrate deploy && exec npx tsx server.ts\n' \
    > /app/docker-entrypoint-ocp.sh && \
    chmod +x /app/docker-entrypoint-ocp.sh

# OpenShift containers run as a random UID that is always a member of GID 0.
# Make the storage directory group 0-writable so the arbitrary UID can write to it.
# /app/database is omitted: an external PostgreSQL database is used.
RUN mkdir -p /app/storage /app/uploads /app/node_modules && \
    chgrp -R 0 /app/storage /app/uploads /app/node_modules && \
    chmod -R g=u /app/storage /app/uploads /app/node_modules

USER app

ENTRYPOINT ["/app/docker-entrypoint-ocp.sh"]
