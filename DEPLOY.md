# Deployment

## Prerequisites

- [Keybase](https://keybase.io) — member of `epfl_sopec` team
- `kubectl` in `$PATH`
- Access to the EPFL network or VPN
- Python 3.10+, `pyyaml` (`pip install pyyaml`)

## First-time setup

```bash
git clone https://github.com/epfl-si/sopec.git
cd sopec
chmod +x sopec
```

## Deploying a new app

```bash
# 1. Push secrets to Keybase (out of band — edit the file directly in Keybase FS)
#    /keybase/team/epfl_sopec/<appname>/secrets.yml

# 2. Apply secrets to the cluster
sopec secrets test <appname>

# 3. Register the app in apps.yaml, then create the ArgoCD application
sopec deploy test --dry-run   # preview what will be created/deleted
sopec deploy test             # apply

# 4. Repeat for prod when ready
sopec secrets prod <appname>
sopec deploy prod
```

## Deploying secrets only (day-to-day)

When a secret value changes in Keybase, re-apply it:

```bash
sopec secrets prod <appname>
```

CloudNativePG secrets tagged `cnpg.io/reload: "true"` are reloaded
automatically by the operator.

## Syncing ArgoCD state

```bash
sopec deploy test             # create missing apps, delete removed ones
sopec deploy prod --dry-run   # preview without touching anything
```

ArgoCD then reconciles each application to `HEAD` of the repo automatically
(`selfHeal: true`).

## Environment reference

| | Test | Prod |
|---|---|---|
| **Namespace** | `svc0176t-isas-fsd` | `svc0176p-isas-fsd` |
| **ArgoCD** | `openshift-gitops-server-…t0001…` | `openshift-gitops-server-…p0001…` |
| **API** | `api.ocpitst0001.xaas.epfl.ch:6443` | `api.ocpitsp0001.xaas.epfl.ch:6443` |
