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

LabMgmt stages DNS during `onboard` and `apply`, so install the BIND utilities before onboarding the first lab:

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

## Required first-time BIND setup

Complete this once **before onboarding the first lab**. LabMgmt reads the live zone serials when generating staged DNS, so the live files and BIND zone declarations must already exist.

First edit `labmgmt/config.yml`. Replace `192.0.2.53` with the reachable address of this DNS server. If you change the forward or reverse zone names, substitute those values throughout the commands below.

Create the zone directory:

```bash
sudo install -d -o root -g bind -m 0755 /etc/bind/zones
```

Create the initial forward zone. Replace `192.0.2.53` here with the same real address used in `config.yml`:

```bash
sudo tee /etc/bind/zones/db.lab.home.arpa >/dev/null <<'EOF'
$TTL 300
@ IN SOA ns1.lab.home.arpa. hostmaster.lab.home.arpa. (
    1          ; serial
    3600       ; refresh
    900        ; retry
    604800     ; expire
    300        ; negative TTL
)
@   IN NS ns1.lab.home.arpa.
ns1 IN A  192.0.2.53
EOF
```

Create the initial reverse zone:

```bash
sudo tee /etc/bind/zones/db.10.255 >/dev/null <<'EOF'
$TTL 300
@ IN SOA ns1.lab.home.arpa. hostmaster.lab.home.arpa. (
    1          ; serial
    3600       ; refresh
    900        ; retry
    604800     ; expire
    300        ; negative TTL
)
@ IN NS ns1.lab.home.arpa.
EOF
```

Set safe ownership and permissions:

```bash
sudo chown root:bind \
  /etc/bind/zones/db.lab.home.arpa \
  /etc/bind/zones/db.10.255
sudo chmod 0644 \
  /etc/bind/zones/db.lab.home.arpa \
  /etc/bind/zones/db.10.255
```

Add both zones to `/etc/bind/named.conf.local`:

```bind
zone "lab.home.arpa" {
    type master;
    file "/etc/bind/zones/db.lab.home.arpa";
};

zone "255.10.in-addr.arpa" {
    type master;
    file "/etc/bind/zones/db.10.255";
};
```

Before editing an existing BIND configuration, make a backup:

```bash
sudo cp -a /etc/bind/named.conf.local \
  /etc/bind/named.conf.local.before-labmgmt
sudoedit /etc/bind/named.conf.local
```

Validate everything before reloading BIND:

```bash
sudo named-checkzone lab.home.arpa \
  /etc/bind/zones/db.lab.home.arpa
sudo named-checkzone 255.10.in-addr.arpa \
  /etc/bind/zones/db.10.255
sudo named-checkconf
sudo systemctl reload bind9
sudo systemctl --no-pager --full status bind9
```

Now confirm that LabMgmt can calculate a new serial and generate its staging files:

```bash
labmgmt dns --dry-run
labmgmt dns
sudo labmgmt dns install
```

The initial serial of `1` is intentional. LabMgmt replaces it with a monotonically increasing `YYYYMMDDNN` serial during the first generation/install cycle.

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
