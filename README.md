# SOPEC

**SOPEC** can mean many things — pick your favorite:

- Service-Oriented Platform for EPFL Campus
- Sustainable Open Source Projects for EPFL Community
- Shared Online Pilot Experiment for Collaborators
- Sustainable Open Platform for EPFL Collaboration
- Software-Oriented Platform for Experimentation and Collaboration
- Shared Open-source Program for Engineering Culture
- ... [propose yours](https://github.com/epfl-si/sopec/issues/new)

SOPEC is a platform for incubating open-source, on-premise web applications
that may evolve into official EPFL services. Operated by the [ISAS-FSD] team,
it provides a controlled environment to experiment with off-the-shelf tools and
assess their relevance for broader institutional use — favouring self-hosted
solutions over SaaS wherever possible.

> [!WARNING]
> Applications hosted on SOPEC are provided on a best-effort basis
> with no guarantees of availability, support, or data protection.


## Project lifecycle

> [!NOTE]
> SOPEC projects follow three levels of maturity:
> `Sandbox` → `Incubating` → `Graduated`

### Sandbox

Early-stage deployments intended for internal testing and experimentation only.
These environments must not be used for real or production purposes.

- Configuration may change frequently
- All data may be deleted at any time without notice

### Incubating

Applications whose initial configuration is complete and are made available to
a broader audience as proofs of concept (POCs). Open for experimentation, but
without support or service guarantees. Users are responsible for their own data.

Incubating projects are generally expected to have:

- [ ] A backup system in place
- [ ] OIDC authentication integration
- [ ] A dedicated subdomain

### Graduated

Applications that have been adopted for production use and are officially
recognised as EPFL services (in the ITIL sense).

[ISAS-FSD]: https://go.epfl.ch/fsd


---


## Adding an application

### 1. Create the app folder

```
apps/
└── <appname>/
    ├── base/
    │   ├── kustomization.yaml
    │   ├── secrets.yaml
    │   └── *.yaml               # Deployments, Services, Routes, etc.
    └── overlays/
        ├── test/
        │   └── kustomization.yaml
        └── prod/
            └── kustomization.yaml
```

The `base/kustomization.yaml` lists all manifests:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
```

The overlays set the target namespace and any env-specific patches:

```yaml
# overlays/prod/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: svc0176p-isas-fsd

resources:
  - ../../base
```

### 2. Register the app in `apps.yaml`

```yaml
apps:
  - name: <appname>
    envs: [test, prod]   # or just [test] while incubating
```

ArgoCD picks up whatever is listed here — adding an entry is enough to
get the application created on the next `sopec deploy`.

### 3. Write `base/secrets.yaml`

Secrets are **not committed in plaintext**. Use the template syntax below;
values are resolved at apply-time from Keybase (see [Secrets](#secrets)).

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: <appname>-credentials
type: Opaque
stringData:
  PASSWORD: "{{ .env.database.password }}"
  API_KEY:  "{{ .env.api_key }}"
```

Template variables:

| Syntax | Resolved from |
|--------|---------------|
| `{{ .env.<path> }}` | `<KB_ROOT>/<app>/secrets.yml` → `<env>.<path>` |
| `{{ .global.<path> }}` | `<KB_ROOT>/<app>/secrets.yml` → `<path>` (no env prefix) |
| `{{ .suffix }}` | `-test` on test, empty string on prod |


---


## Secrets

Secrets are stored in Keybase under the shared team filesystem:

```
/keybase/team/epfl_sopec/<appname>/secrets.yml
```

Each file follows the structure:

```yaml
test:
  database:
    password: "..."
  api_key: "..."
prod:
  database:
    password: "..."
  api_key: "..."
```

The `sopec secrets` command reads from Keybase, renders the templates, and
applies the resulting manifests directly to the cluster — nothing touches disk.

```bash
sopec secrets test              # apply all secrets to test
sopec secrets prod <appname>    # apply one app's secrets to prod
```

> [!IMPORTANT]
> You must have [Keybase](https://keybase.io) installed and be a member of the
> `epfl_sopec` team to run this command.


---


## CLI

The `sopec` script at the repo root is the single entrypoint. All commands
require being on the EPFL network (or VPN).

```
sopec deploy   [test|prod] [--dry-run]     Sync ArgoCD apps from apps.yaml
sopec secrets  [test|prod] [app...]        Apply K8s secrets from Keybase
sopec dump     [--test|--prod] [--debug]   Backup PostgreSQL databases to Keybase
sopec import   [--test|--prod] [--debug]   Restore PostgreSQL databases from backup
sopec mirror   <image> [target_org]        Mirror Docker image to quay-its.epfl.ch
sopec sso      <argocd-server>             Perform ArgoCD SSO login (PKCE)
```

Authentication is cached in `.cli/.token` (chmod 600) and refreshed
automatically via browser-based PKCE when expired.


---


## Deployment

See [DEPLOY.md](DEPLOY.md) for setup, secrets, and step-by-step deployment instructions.
