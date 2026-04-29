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

