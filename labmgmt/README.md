# labmgmt

`labmgmt` manages persistent Containerlab management-network addressing, IPAM, topology synchronization, and optional authoritative DNS. Relative `labs_root` paths resolve from the repository root.

The primary goal is to allow Containerlab labs to be destroyed, modified, and redeployed without unexpectedly changing their management IP addresses or DNS names.

## Architecture

The management network uses:

* Management supernet: `10.255.0.0/16`
* One `/24` per lab
* Lab ID `N` → `10.255.N.0/24`
* Management gateway: `.1`
* Normal node addresses: `.10` through `.249`
* Reserved addresses: `.1-.9` and `.250-.254`
* DNS zone: `lab.home.arpa`
* Reverse DNS zone: `255.10.in-addr.arpa`
* DNS server: `192.0.2.53`

Example:

```text
Lab ID: 1
Lab:    Simple
Subnet: 10.255.1.0/24

vMX1  -> 10.255.1.10 -> vmx1.simple.lab.home.arpa
host1 -> 10.255.1.11 -> host1.simple.lab.home.arpa
vMX2  -> 10.255.1.12 -> vmx2.simple.lab.home.arpa
host2 -> 10.255.1.13 -> host2.simple.lab.home.arpa
```

## Repository Layout

```text
/path/to/containerlab-infrastructure/
├── labs/
│   ├── Simple/
│   │   └── Simple.clab.yml
│   └── ...
│
├── labmgmt/
│   ├── README.md
│   ├── config.yml
│   ├── ipam/
│   │   ├── registry.yml
│   │   ├── labs/
│   │   │   └── simple.yml
│   │   └── archive/
│   │       └── labs/
│   └── generated/
│       └── dns/
│           ├── db.lab.home.arpa
│           └── db.10.255
│
└── scripts/
    └── labmgmt
```

The executable script is:

```text
/path/to/containerlab-infrastructure/scripts/labmgmt
```

A symlink is installed at:

```text
/usr/local/bin/labmgmt
```

so the command can be run simply as:

```bash
labmgmt
```

and can also be found when running through `sudo`.

## Source of Truth

Persistent management identity is stored in IPAM, not in Containerlab runtime state.

Global Lab-ID state:

```text
labmgmt/ipam/registry.yml
```

Per-lab persistent state:

```text
labmgmt/ipam/labs/<lab>.yml
```

Containerlab topology files contain the resulting `mgmt` and `mgmt-ipv4` settings, but IPAM remains authoritative for existing allocations.

A lab is identified by its Containerlab top-level:

```yaml
name: Simple
```

which is normalized to the IPAM/DNS key:

```text
simple
```

Node names are handled similarly:

```text
vMX1 -> vmx1
```

The original Containerlab spelling is retained in IPAM.

## Allocation Policy

New Lab IDs normally use a high-water allocation strategy.

For example:

```text
Lab 1 - active
Lab 2 - retired
Lab 3 - active

Next new Lab ID = 4
```

Retired IDs are not automatically reused.

Node IPs behave the same way:

```text
.10 - existing
.11 - retired
.12 - existing

Next new node = .13
```

A retired Lab ID or node IP remains reserved until it is explicitly recycled.

Recycled addresses are placed into a reusable pool but normal allocation continues upward first. Recycled values are used only after the never-before-used allocation range is exhausted.

## Common Workflows

### New Lab

Preview registration:

```bash
labmgmt onboard --dry-run labs/MyLab/MyLab.clab.yml
```

Register the lab, allocate addresses, synchronize the topology, and stage DNS:

```bash
labmgmt onboard labs/MyLab/MyLab.clab.yml
```

Publish the DNS changes:

```bash
sudo labmgmt dns install
```

The onboarding command asks for confirmation before consuming a new Lab ID.

For unattended use:

```bash
labmgmt onboard --yes labs/MyLab/MyLab.clab.yml
```

### Existing Lab

After adding, removing, or modifying nodes:

```bash
labmgmt apply --dry-run labs/MyLab/MyLab.clab.yml
```

Then:

```bash
labmgmt apply labs/MyLab/MyLab.clab.yml
```

Publish DNS:

```bash
sudo labmgmt dns install
```

`apply` synchronizes IPAM and topology and generates validated DNS staging files.

### Validate IPAM

```bash
labmgmt validate
```

Validation checks items such as:

* Lab-ID collisions
* subnet consistency
* duplicate management IPs
* node addresses outside the allowed range
* high-water allocation state
* recycled-address state
* registry/per-lab consistency
* topology path consistency
* DNS configuration

No changes are made.

### Show a Topology

```bash
labmgmt show labs/MyLab/MyLab.clab.yml
```

This displays how the topology is interpreted by `labmgmt`.

### Synchronize Only

Preview:

```bash
labmgmt sync --dry-run labs/MyLab/MyLab.clab.yml
```

Apply:

```bash
labmgmt sync labs/MyLab/MyLab.clab.yml
```

This synchronizes IPAM and topology but does not publish DNS.

## DNS

DNS is generated entirely from active IPAM entries.

### First-time BIND bootstrap

A fresh BIND installation does not contain the two live files configured under `dns.bind`. Create and declare them before running the first `labmgmt onboard`, `labmgmt apply`, or `labmgmt dns` operation because LabMgmt reads their SOA serials when choosing the next serial.

The complete copy-and-paste procedure is maintained in the repository's [Required first-time BIND setup](../README.md#required-first-time-bind-setup). It covers:

* installing `bind9` and `bind9-utils`
* creating `/etc/bind/zones`
* creating valid initial forward and reverse zones
* declaring both zones in `/etc/bind/named.conf.local`
* setting ownership and permissions
* running `named-checkzone` and `named-checkconf`
* reloading and checking BIND
* generating and installing the first LabMgmt-managed zones

Do not merely create empty files. Each file must contain a valid SOA and NS record or both BIND validation and LabMgmt serial handling will fail.

Generate and validate a preview:

```bash
labmgmt dns --dry-run
```

Generate Git-managed staging files:

```bash
labmgmt dns
```

This creates:

```text
labmgmt/generated/dns/db.lab.home.arpa
labmgmt/generated/dns/db.10.255
```

The staging files are validated with `named-checkzone`.

Publish them to BIND:

```bash
sudo labmgmt dns install
```

The install process:

1. Validates IPAM and DNS configuration.
2. Confirms the staging files match current IPAM.
3. Runs `named-checkzone`.
4. Runs `named-checkconf`.
5. Backs up the current live BIND zone files.
6. Atomically installs both zones.
7. Validates the installed configuration and zones.
8. Runs `rndc reload` only after validation succeeds.
9. Checks BIND status.
10. Restores the previous files if installation fails.

Live zone files are:

```text
/etc/bind/zones/db.lab.home.arpa
/etc/bind/zones/db.10.255
```

BIND backups are kept beneath:

```text
/etc/bind/zones/labmgmt-backups/
```

DNS serials use a `YYYYMMDDNN` format and are always increased relative to the current live zone serials.

Only active labs and active nodes are published in DNS.

A retired node or lab retains its IPAM allocation but is removed from DNS.

## Lab Lifecycle

### Retire a Lab

Preview:

```bash
labmgmt retire-lab --dry-run mylab
```

Retire:

```bash
labmgmt retire-lab mylab
```

Retirement preserves:

* Lab ID
* management subnet
* node IP assignments
* IPAM history

The lab and its nodes are removed from generated DNS.

Publish the DNS removal with:

```bash
sudo labmgmt dns install
```

### Reactivate a Lab

```bash
labmgmt reactivate-lab labs/MyLab/MyLab.clab.yml
```

Previously retired nodes that still exist in the topology regain their original management IPs.

Then publish DNS:

```bash
sudo labmgmt dns install
```

### Recycle a Retired Node

A node must already be retired.

Preview:

```bash
labmgmt recycle-node --dry-run mylab oldrouter
```

Recycle:

```bash
labmgmt recycle-node mylab oldrouter
```

Recycling permanently releases that node's reserved management IP for future reuse while retaining an audit-history entry.

### Recycle a Retired Lab

A lab must already be retired.

Preview:

```bash
labmgmt recycle-lab --dry-run mylab
```

Recycle:

```bash
labmgmt recycle-lab mylab
```

Recycling:

* archives the complete per-lab IPAM file
* removes the lab from the active registry
* releases the Lab ID
* releases the lab `/24`
* records the operation in registry history

Archived IPAM files are stored under:

```text
labmgmt/ipam/archive/labs/
```

Recycling a lab does **not** delete its Containerlab topology directory under `labs/`.

## Node Retirement

Individual nodes do not require a manual retirement command.

Remove the node from the Containerlab topology and run:

```bash
labmgmt apply labs/MyLab/MyLab.clab.yml
```

The missing node is automatically marked retired.

Its management IP remains reserved.

If the same node name later returns to the topology, its original management IP is restored automatically.

## Moving a Topology

Lab identity is based on the Containerlab `name:`, not the topology pathname.

If a registered topology is moved, run:

```bash
labmgmt apply /new/path/MyLab.clab.yml
```

The stored topology path is updated while the Lab ID and management addresses remain unchanged.

## Destroying and Redeploying Labs

Containerlab runtime state does not control IPAM identity.

A lab can be destroyed and later redeployed without changing its management addressing.

For example:

```text
Simple
Lab ID 1
10.255.1.0/24
```

will continue to use the same subnet and node management addresses after redeployment unless those allocations are explicitly recycled.

## Git

`labmgmt` does not automatically commit or push Git changes.

This is intentional so changes can be reviewed first.

Useful commands:

```bash
git status
git diff
```

The Git helper scripts in `/path/to/containerlab-infrastructure/scripts` can then be used to commit and push the changes.

## Safety Principles

`labmgmt` follows several design rules:

* Validate before modifying.
* IPAM is authoritative for persistent identity.
* Retire does not mean reuse.
* Recycling is always explicit.
* Never silently guess that a renamed node is the same device.
* Never silently return an allocated Lab ID after a partial failure.
* DNS is generated from IPAM rather than edited record-by-record.
* BIND is never reloaded unless generated zones validate.
* Live BIND files are backed up before replacement.
* Topology and IPAM writes use atomic replacement and rollback where appropriate.

## Recommended Routine

For most existing-lab changes:

```bash
labmgmt apply --dry-run labs/MyLab/MyLab.clab.yml
labmgmt apply labs/MyLab/MyLab.clab.yml
sudo labmgmt dns install
git status
```

For a new lab:

```bash
labmgmt onboard --dry-run labs/MyLab/MyLab.clab.yml
labmgmt onboard labs/MyLab/MyLab.clab.yml
sudo labmgmt dns install
git status
```

Always review Git changes before committing.



## Junos automation credentials

Save and restore operations do not contain or assume a password. Supply it locally when needed:

```bash
export LABMGMT_JUNOS_PASSWORD='your-lab-password'
```

Optionally override the default username with `LABMGMT_JUNOS_USERNAME`. Never commit credentials to this repository.
