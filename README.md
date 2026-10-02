# Containerlab Infrastructure

Reusable infrastructure for building a persistent, Git-managed Containerlab environment.

It provides persistent management-network IPAM, deterministic addressing across destroy/redeploy cycles, topology synchronization, optional authoritative DNS generation with BIND or tiny-dns, Junos and LabHost save/restore workflows, runtime link controls, and portable Git helpers.

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

LabMgmt stages DNS during `onboard` and `apply`. Zone syntax is always validated with `named-checkzone`, regardless of the serving backend. For the default BIND backend on Debian/Ubuntu, install:

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

## DNS backend selection

BIND remains the default DNS backend. Existing configurations that omit `dns.backend` continue to behave as BIND configurations, so existing installations do not need to change.

```yaml
dns:
  backend: bind
```

The supported backend values are:

* `bind` - publishes the generated master files to the paths under `dns.bind`, validates `named.conf` with `named-checkconf`, reloads with `rndc reload`, and checks status with `rndc status`.
* `tiny-dns` - publishes the same generated master-file data to the paths under `dns.tiny_dns`, adds the explicit `$ORIGIN` required by simple standalone master-file readers, restarts the configured systemd service, and verifies that service is active.

`named-checkzone` is intentionally used for both backends so LabMgmt retains the same pre-install and post-install zone validation. On Rocky/RHEL systems, install it with:

```bash
sudo dnf install bind-utils
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

## Alternative tiny-dns setup

Use this backend for a systemd-managed DNS server that reads standard BIND-style master files directly, such as the lightweight Python/dnslib `tiny-dns` service described in this project deployment. BIND itself does not need to run, but `named-checkzone` is still required for validation.

Set the backend and live file locations in `labmgmt/config.yml`:

```yaml
dns:
  backend: tiny-dns
  domain: lab.home.arpa
  reverse_zone: 255.10.in-addr.arpa

  tiny_dns:
    forward_zone_file: /etc/tiny-dns/zones/lab.home.arpa.zone
    reverse_zone_file: /etc/tiny-dns/zones/255.10.in-addr.arpa.zone
    service: tiny-dns.service
```

The reverse **zone name** must remain `255.10.in-addr.arpa` for the `10.255.0.0/16` management supernet. A filename such as `10-255.arpa.zone` is only a filename and must not be used as the configured DNS zone name.

Create dedicated initial live files before the first `labmgmt dns` run because LabMgmt reads their SOA serials. Do not overwrite an unrelated reverse zone that may already exist in `/etc/tiny-dns/zones`.

```bash
sudo install -d -m 2775 /etc/tiny-dns/zones

sudo tee /etc/tiny-dns/zones/lab.home.arpa.zone >/dev/null <<'EOF'
$ORIGIN lab.home.arpa.
$TTL 300
@ IN SOA ns1.lab.home.arpa. hostmaster.lab.home.arpa. 1 3600 900 604800 300
@ IN NS ns1.lab.home.arpa.
ns1 IN A 192.0.2.53
EOF

sudo tee /etc/tiny-dns/zones/255.10.in-addr.arpa.zone >/dev/null <<'EOF'
$ORIGIN 255.10.in-addr.arpa.
$TTL 300
@ IN SOA ns1.lab.home.arpa. hostmaster.lab.home.arpa. 1 3600 900 604800 300
@ IN NS ns1.lab.home.arpa.
EOF
```

Replace `192.0.2.53` with the real DNS server address used in `config.yml`, then validate the files and service:

```bash
sudo named-checkzone lab.home.arpa \
  /etc/tiny-dns/zones/lab.home.arpa.zone
sudo named-checkzone 255.10.in-addr.arpa \
  /etc/tiny-dns/zones/255.10.in-addr.arpa.zone
sudo systemctl restart tiny-dns.service
sudo systemctl is-active tiny-dns.service
```

Now generate and publish normally:

```bash
labmgmt dns --dry-run
labmgmt dns
sudo labmgmt dns install
```

For `tiny-dns`, `dns install` preserves the live files' owner, group, and mode; backs them up beneath the common zone directory; atomically replaces both files; restarts the configured service; checks that it is active; and restores the previous files if installation or restart fails.

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
