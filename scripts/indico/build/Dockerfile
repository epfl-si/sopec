# Rebuilds the public getindico/indico image so it works under OpenShift's
# arbitrary-UID model. Upstream owns /opt/indico as uid:gid 999:999 with no
# group access (mode 0700/0750), which OpenShift's randomly assigned UID
# (always supplementary group 0) cannot read, execute, or traverse at all —
# every process in the pod fails with "Permission denied" on exec.
ARG INDICO_VERSION=3.3.14
FROM getindico/indico:${INDICO_VERSION}

USER root

# Mirror owner permissions onto group 0 so the arbitrary UID OpenShift
# assigns (always a member of gid 0) has the same access as the "indico"
# user baked into the upstream image.
RUN chgrp -R 0 /opt/indico && \
    chmod -R g=u /opt/indico

# The arbitrary UID has no /etc/passwd entry, so $HOME must be set
# explicitly rather than relying on NSS lookups.
ENV HOME=/opt/indico

USER indico

# Sixpay (SIX Payment Services) plugin, enabled via PLUGINS in indico.conf
# (see apps/indico/base/secrets.yaml). Credentials are set in the Indico
# admin UI (Administration > Plugins > SIXPay Saferpay), not in config.
# https://github.com/indico/indico-plugins/tree/master/payment_sixpay
RUN pip install --no-cache-dir indico-plugin-payment-sixpay
