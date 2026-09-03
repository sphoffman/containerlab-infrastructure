# Containerlab Infrastructure

Reusable infrastructure for building a persistent, Git-managed Containerlab environment.

It provides persistent management-network IPAM, deterministic addressing across destroy/redeploy cycles, topology synchronization, optional BIND DNS generation, Junos and LabHost save/restore workflows, runtime link controls, and portable Git helpers.

This starter contains no personal labs, device configurations, IPAM allocations, DNS records, or credentials.

## Layout

```text
.
├── examples/                 Generic topology examples
├── labmgmt/
│   ├── config.yml            Site-specific management and DNS settings
│   ├── ipam/                 Persistent allocation state
│   ├── generated/dns/        Generated DNS staging files
│   └── README.md             Complete operations guide
├── labs/                     Your topologies
├── scripts/                  labmgmt, installer, and Git helpers
└── .gitignore
```

## Quick start

```bash
git clone https://github.com/sphoffman/containerlab-infrastructure.git
cd containerlab-infrastructure
sudo apt update
sudo apt install python3 python3-yaml python3-ruamel.yaml
./scripts/install.sh
```

For integrated DNS:

```bash
sudo apt install bind9 bind9-utils
```

Review `labmgmt/config.yml` before use. Replace the documentation-only DNS server address `192.0.2.53`. The default `labs_root: labs` is relative to the repository, so the project can be cloned anywhere.

For Junos save/restore automation, supply the lab credential locally rather than committing it:

```bash
export LABMGMT_JUNOS_PASSWORD='your-lab-password'
```

Validate the empty state:

```bash
labmgmt validate
```

## First example lab

```bash
mkdir -p labs/LabHost-Demo
cp examples/labhost-demo.clab.yml labs/LabHost-Demo/LabHost-Demo.clab.yml
mkdir -p labs/LabHost-Demo/configs labs/LabHost-Demo/pcaps
touch labs/LabHost-Demo/configs/.gitkeep labs/LabHost-Demo/pcaps/.gitkeep

labmgmt onboard --dry-run labs/LabHost-Demo/LabHost-Demo.clab.yml
labmgmt onboard labs/LabHost-Demo/LabHost-Demo.clab.yml
sudo containerlab deploy -t labs/LabHost-Demo/LabHost-Demo.clab.yml
```

If DNS is configured:

```bash
sudo labmgmt dns install
```

## LabHost

The example uses the public image:

```bash
docker pull ghcr.io/sphoffman/labhost:1.4
```

See [LabHost](https://github.com/sphoffman/labhost) for traffic generation, capture, NetEm, VLAN/LAG/VRF, multicast, DHCP, synthetic clients, and persistence.

For LACP/bonding support:

```bash
echo bonding | sudo tee /etc/modules-load.d/bonding.conf
sudo modprobe bonding
```

## Security

- Keep credentials in local environment variables or a secret manager.
- Review all defaults before use outside an isolated lab.
- Do not expose test services directly to untrusted networks.
- Review `git status` and `git diff` before committing.

## Documentation

- [LabMgmt operations](labmgmt/README.md)
- [Git workflow](docs/GIT_WORKFLOW.md)
- [Migration guide](docs/MIGRATION.md)
- [LabHost](https://github.com/sphoffman/labhost)
