# Containerlab Infrastructure

Reusable infrastructure for operating a persistent, Git-managed Containerlab environment.

This project combines:

- persistent per-lab management-network IPAM;
- deterministic management addressing across destroy/redeploy cycles;
- optional authoritative forward and reverse DNS generation;
- topology synchronization and validation;
- Junos and LabHost configuration save/restore workflows;
- runtime link listing, shutdown, restoration, and flap testing;
- Git commit/push helpers;
- integration with [LabHost](https://github.com/sphoffman/labhost).

The repository intentionally contains no personal labs or device configurations.

> Initial repository setup is in progress.
