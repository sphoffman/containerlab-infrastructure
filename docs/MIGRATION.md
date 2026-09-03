# Migration guide

1. Clone this repository.
2. Customize `labmgmt/config.yml`.
3. Keep the empty registry for a new installation.
4. Copy only desired topology directories into `labs/`.
5. Remove existing `mgmt:` and `mgmt-ipv4:` values if LabMgmt should allocate them anew.
6. Run `labmgmt onboard --dry-run` for each lab.
7. Onboard one lab at a time and review its diff.
8. Generate/install DNS only after customizing every DNS setting.
9. Deploy and test management reachability.
10. Commit the resulting topology and IPAM state.

Do not copy another installation's `labmgmt/ipam/` or `labmgmt/generated/dns/` unless retaining its exact allocation history is intentional.
