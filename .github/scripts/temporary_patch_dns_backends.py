#!/usr/bin/env python3

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
LABMGMT = ROOT / "scripts" / "labmgmt"
CONFIG = ROOT / "labmgmt" / "config.yml"
ROOT_README = ROOT / "README.md"
LABMGMT_README = ROOT / "labmgmt" / "README.md"


def replace_between(text, start_marker, end_marker, replacement):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def replace_once(text, old, new):
    if old not in text:
        raise RuntimeError(f"Expected text not found:\n{old}")
    return text.replace(old, new, 1)


labmgmt = LABMGMT.read_text()

backend_helpers_and_replace = r'''def get_dns_backend_config(config):
    dns = config["dns"]
    backend = str(
        dns.get("backend", "bind")
    ).strip().lower()

    if backend == "bind":
        key = "bind"
    elif backend == "tiny-dns":
        key = "tiny_dns"
    else:
        raise LabMgmtError(
            f"Unsupported DNS backend: {backend}. "
            "Supported backends are 'bind' and 'tiny-dns'."
        )

    try:
        backend_config = dns[key]
    except (KeyError, TypeError):
        raise LabMgmtError(
            f"DNS backend '{backend}' requires dns.{key} configuration"
        )

    if not isinstance(backend_config, dict):
        raise LabMgmtError(
            f"dns.{key} must be a mapping"
        )

    return backend, backend_config


def get_live_dns_zone_paths(config):
    _, backend_config = get_dns_backend_config(config)

    try:
        forward_live = Path(
            backend_config["forward_zone_file"]
        )
        reverse_live = Path(
            backend_config["reverse_zone_file"]
        )
    except (KeyError, TypeError) as exc:
        raise LabMgmtError(
            f"Invalid DNS backend configuration: {exc}"
        )

    return forward_live, reverse_live


def dns_backend_display_name(config):
    backend, _ = get_dns_backend_config(config)
    return "BIND" if backend == "bind" else "tiny-dns"


def prepare_live_zone_text(config, zone_name, zone_text):
    backend, _ = get_dns_backend_config(config)

    if backend != "tiny-dns":
        return zone_text

    origin = zone_name.rstrip(".") + "."

    if re.search(
        r"(?im)^\s*\$ORIGIN\s+",
        zone_text,
    ):
        return zone_text

    return f"$ORIGIN {origin}\n{zone_text}"


def validate_dns_server_configuration(config, description=None):
    backend, backend_config = get_dns_backend_config(config)

    if backend == "bind":
        return run_command_checked(
            ["named-checkconf"],
            description or "BIND configuration validation",
        )

    service = str(
        backend_config["service"]
    ).strip()

    return run_command_checked(
        ["systemctl", "cat", service],
        description or "tiny-dns service validation",
    )


def reload_dns_server(config, rollback=False):
    backend, backend_config = get_dns_backend_config(config)

    if backend == "bind":
        return (
            "BIND reload",
            run_command_checked(
                ["rndc", "reload"],
                "Rollback BIND reload"
                if rollback
                else "BIND reload",
            ),
        )

    service = str(
        backend_config["service"]
    ).strip()

    return (
        "tiny-dns restart",
        run_command_checked(
            ["systemctl", "restart", service],
            "Rollback tiny-dns restart"
            if rollback
            else "tiny-dns restart",
        ),
    )


def check_dns_server_status(config):
    backend, backend_config = get_dns_backend_config(config)

    if backend == "bind":
        return run_command_checked(
            ["rndc", "status"],
            "BIND status check",
        )

    service = str(
        backend_config["service"]
    ).strip()

    return run_command_checked(
        ["systemctl", "is-active", service],
        "tiny-dns status check",
    )


def replace_live_file_atomic(path, content):
    path = Path(path)

    if not path.exists():
        raise LabMgmtError(
            f"Live DNS file does not exist: {path}"
        )

    stat_info = path.stat()

    temp_path = path.with_name(
        f".{path.name}.labmgmt-{os.getpid()}"
    )

    try:
        with temp_path.open("wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # Preserve the original file's permissions,
        # owner and group.
        os.chmod(
            temp_path,
            stat_info.st_mode & 0o7777,
        )

        os.chown(
            temp_path,
            stat_info.st_uid,
            stat_info.st_gid,
        )

        os.replace(
            temp_path,
            path,
        )

    except Exception as exc:
        try:
            temp_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass

        raise LabMgmtError(
            f"Unable to install {path}: {exc}"
        )
'''

labmgmt = replace_between(
    labmgmt,
    "def replace_live_file_atomic(path, content):",
    "def install_dns_zones(",
    backend_helpers_and_replace,
)

install_dns = r'''def install_dns_zones(
    config,
    registry,
):
    # Publishing DNS requires root because the live zone files and
    # backend reload/restart operations are system-managed resources.
    if os.geteuid() != 0:
        raise LabMgmtError(
            "DNS installation requires root privileges. "
            "Run: sudo labmgmt dns install"
        )

    dns = config["dns"]
    backend, _ = get_dns_backend_config(config)
    backend_name = dns_backend_display_name(config)

    forward_zone = dns["domain"]
    reverse_zone = dns["reverse_zone"]

    forward_live, reverse_live = get_live_dns_zone_paths(
        config
    )

    if not GENERATED_FORWARD_ZONE.exists():
        raise LabMgmtError(
            f"Generated forward zone is missing: "
            f"{GENERATED_FORWARD_ZONE}\n"
            "Run 'labmgmt dns' first."
        )

    if not GENERATED_REVERSE_ZONE.exists():
        raise LabMgmtError(
            f"Generated reverse zone is missing: "
            f"{GENERATED_REVERSE_ZONE}\n"
            "Run 'labmgmt dns' first."
        )

    # Calculate what DNS should look like RIGHT NOW so IPAM cannot
    # change between staging and installation unnoticed.
    serials = calculate_next_dns_serial(
        config
    )

    records = collect_dns_records(
        config,
        registry,
    )

    expected_forward = generate_forward_zone(
        config,
        serials["new"],
        records,
    )

    expected_reverse = generate_reverse_zone(
        config,
        serials["new"],
        records,
    )

    staged_forward = GENERATED_FORWARD_ZONE.read_text(
        encoding="utf-8"
    )
    staged_reverse = GENERATED_REVERSE_ZONE.read_text(
        encoding="utf-8"
    )

    if staged_forward != expected_forward:
        raise LabMgmtError(
            "Generated forward zone is stale or does not "
            "match current IPAM/live serial state.\n"
            "Run 'labmgmt dns' as your normal user first."
        )

    if staged_reverse != expected_reverse:
        raise LabMgmtError(
            "Generated reverse zone is stale or does not "
            "match current IPAM/live serial state.\n"
            "Run 'labmgmt dns' as your normal user first."
        )

    live_forward_text = prepare_live_zone_text(
        config,
        forward_zone,
        staged_forward,
    )
    live_reverse_text = prepare_live_zone_text(
        config,
        reverse_zone,
        staged_reverse,
    )

    print()
    print("DNS INSTALL")
    print("===========")
    print(f"Backend: {backend_name}")

    print()
    print("Pre-install validation")
    print("----------------------")

    validate_zone_text(
        forward_zone,
        live_forward_text,
    )
    print("Generated forward zone: OK")

    validate_zone_text(
        reverse_zone,
        live_reverse_text,
    )
    print("Generated reverse zone: OK")

    validate_dns_server_configuration(config)
    print(f"{backend_name} configuration/service: OK")

    if not forward_live.exists():
        raise LabMgmtError(
            f"Live forward zone does not exist: {forward_live}"
        )

    if not reverse_live.exists():
        raise LabMgmtError(
            f"Live reverse zone does not exist: {reverse_live}"
        )

    original_forward = forward_live.read_bytes()
    original_reverse = reverse_live.read_bytes()

    timestamp = (
        datetime.datetime.now()
        .strftime("%Y%m%d-%H%M%S")
    )

    common_parent = Path(
        os.path.commonpath(
            [
                str(forward_live.parent),
                str(reverse_live.parent),
            ]
        )
    )

    backup_dir = (
        common_parent
        / "labmgmt-backups"
        / timestamp
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )
    os.chmod(backup_dir, 0o750)

    forward_backup = backup_dir / forward_live.name
    reverse_backup = backup_dir / reverse_live.name

    shutil.copy2(forward_live, forward_backup)
    shutil.copy2(reverse_live, reverse_backup)

    print()
    print("Backup")
    print("------")
    print(f"Created: {backup_dir}")

    wrote_forward = False
    wrote_reverse = False

    try:
        replace_live_file_atomic(
            forward_live,
            live_forward_text.encode("utf-8"),
        )
        wrote_forward = True

        replace_live_file_atomic(
            reverse_live,
            live_reverse_text.encode("utf-8"),
        )
        wrote_reverse = True

        validate_dns_server_configuration(
            config,
            description=(
                "Post-install BIND configuration validation"
                if backend == "bind"
                else "Post-install tiny-dns service validation"
            ),
        )

        validate_zone_file(
            forward_zone,
            forward_live,
        )
        validate_zone_file(
            reverse_zone,
            reverse_live,
        )

        print()
        print("Post-install validation")
        print("-----------------------")
        print(f"{backend_name} configuration/service: OK")
        print("Live forward zone:  OK")
        print("Live reverse zone:  OK")

        action_name, reload_output = reload_dns_server(
            config
        )

        print()
        print(action_name)
        print("-" * len(action_name))

        if reload_output:
            print(reload_output)
        else:
            print(f"{action_name}: OK")

        status_output = check_dns_server_status(
            config
        )

        if status_output and backend == "tiny-dns":
            print(f"tiny-dns status: {status_output}")

    except Exception as exc:
        print()
        print(
            "DNS installation failed; "
            "restoring previous zone files..."
        )

        rollback_errors = []

        if wrote_forward:
            try:
                replace_live_file_atomic(
                    forward_live,
                    original_forward,
                )
            except Exception as rollback_exc:
                rollback_errors.append(
                    f"forward rollback: {rollback_exc}"
                )

        if wrote_reverse:
            try:
                replace_live_file_atomic(
                    reverse_live,
                    original_reverse,
                )
            except Exception as rollback_exc:
                rollback_errors.append(
                    f"reverse rollback: {rollback_exc}"
                )

        if not rollback_errors:
            try:
                validate_dns_server_configuration(
                    config,
                    description="Rollback DNS backend validation",
                )

                validate_zone_file(
                    forward_zone,
                    forward_live,
                )
                validate_zone_file(
                    reverse_zone,
                    reverse_live,
                )

                reload_dns_server(
                    config,
                    rollback=True,
                )
                check_dns_server_status(config)

            except Exception as rollback_exc:
                rollback_errors.append(
                    f"rollback reload: {rollback_exc}"
                )

        if rollback_errors:
            raise LabMgmtError(
                f"DNS installation failed: {exc}\n"
                "Rollback also encountered errors:\n"
                + "\n".join(
                    f"  {error}"
                    for error in rollback_errors
                )
            )

        raise LabMgmtError(
            f"DNS installation failed and was "
            f"rolled back successfully: {exc}"
        )

    print()
    print("DNS installation successful.")
    print(f"Backend:         {backend_name}")
    print(f"Serial:          {serials['new']}")
    print(f"Forward zone:    {forward_live}")
    print(f"Reverse zone:    {reverse_live}")
    print(f"Backup:          {backup_dir}")
'''

labmgmt = replace_between(
    labmgmt,
    "def install_dns_zones(",
    "def validate_dns_config(config):",
    install_dns,
)

validate_dns_config = r'''def validate_dns_config(config):
    try:
        dns = config["dns"]

        domain = str(dns["domain"]).strip()
        reverse_zone = str(dns["reverse_zone"]).strip()
        ttl = int(dns["ttl"])

        soa = dns["soa"]
        primary_ns = str(
            soa["primary_ns"]
        ).strip()
        responsible = str(
            soa["responsible"]
        ).strip()
        refresh = int(soa["refresh"])
        retry = int(soa["retry"])
        expire = int(soa["expire"])
        negative_ttl = int(
            soa["negative_ttl"]
        )

        nameserver = dns["nameserver"]
        ns_name = str(
            nameserver["name"]
        ).strip()
        ns_address = ipaddress.ip_address(
            str(nameserver["address"])
        )

        backend, backend_config = get_dns_backend_config(
            config
        )

        forward_file = Path(
            backend_config["forward_zone_file"]
        )
        reverse_file = Path(
            backend_config["reverse_zone_file"]
        )

        if backend == "tiny-dns":
            service = str(
                backend_config["service"]
            ).strip()
        else:
            service = None

    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise LabMgmtError(
            f"Invalid DNS configuration: {exc}"
        )

    if not domain:
        raise LabMgmtError(
            "dns.domain cannot be empty"
        )

    if domain.endswith("."):
        raise LabMgmtError(
            "dns.domain should not end with a dot"
        )

    if not reverse_zone.endswith(
        ".in-addr.arpa"
    ):
        raise LabMgmtError(
            "dns.reverse_zone must be an "
            "in-addr.arpa zone"
        )

    if ttl <= 0:
        raise LabMgmtError(
            "dns.ttl must be greater than zero"
        )

    if not primary_ns.endswith("."):
        raise LabMgmtError(
            "dns.soa.primary_ns must be an "
            "absolute DNS name ending in '.'"
        )

    if not responsible.endswith("."):
        raise LabMgmtError(
            "dns.soa.responsible must be an "
            "absolute DNS name ending in '.'"
        )

    if not ns_name:
        raise LabMgmtError(
            "dns.nameserver.name cannot be empty"
        )

    if ns_address.version != 4:
        raise LabMgmtError(
            "DNS nameserver address must be IPv4"
        )

    for value, name in (
        (refresh, "refresh"),
        (retry, "retry"),
        (expire, "expire"),
        (negative_ttl, "negative_ttl"),
    ):
        if value <= 0:
            raise LabMgmtError(
                f"dns.soa.{name} must be "
                "greater than zero"
            )

    if not forward_file.is_absolute():
        raise LabMgmtError(
            "Forward zone path must be absolute"
        )

    if not reverse_file.is_absolute():
        raise LabMgmtError(
            "Reverse zone path must be absolute"
        )

    if backend == "tiny-dns" and not service:
        raise LabMgmtError(
            "dns.tiny_dns.service cannot be empty"
        )
'''

labmgmt = replace_between(
    labmgmt,
    "def validate_dns_config(config):",
    "def read_zone_serial(path):",
    validate_dns_config,
)

read_zone_serial = r'''def read_zone_serial(path):
    path = Path(path)

    if not path.exists():
        raise LabMgmtError(
            f"DNS zone file does not exist: {path}"
        )

    try:
        text = path.read_text()

    except PermissionError:
        raise LabMgmtError(
            f"Unable to read DNS zone file: {path}"
        )

    except OSError as exc:
        raise LabMgmtError(
            f"Unable to read DNS zone file "
            f"{path}: {exc}"
        )

    # Accept both common master-file SOA forms:
    #   SOA ns hostmaster (\n 2026010101 ... )
    #   SOA ns hostmaster 2026010101 3600 900 ...
    match = re.search(
        r"\bSOA\b\s+\S+\s+\S+\s+\(?\s*(\d+)\b",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        raise LabMgmtError(
            f"Unable to locate SOA serial in {path}"
        )

    return int(match.group(1))
'''

labmgmt = replace_between(
    labmgmt,
    "def read_zone_serial(path):",
    "def calculate_next_dns_serial(config):",
    read_zone_serial,
)

calculate_serial = r'''def calculate_next_dns_serial(config):
    forward_file, reverse_file = get_live_dns_zone_paths(
        config
    )

    forward_serial = read_zone_serial(
        forward_file
    )
    reverse_serial = read_zone_serial(
        reverse_file
    )

    today = datetime.date.today()
    today_base = int(
        today.strftime("%Y%m%d") + "00"
    )

    highest_existing = max(
        forward_serial,
        reverse_serial,
    )

    new_serial = max(
        today_base,
        highest_existing,
    ) + 1

    return {
        "forward": forward_serial,
        "reverse": reverse_serial,
        "new": new_serial,
    }
'''

labmgmt = replace_between(
    labmgmt,
    "def calculate_next_dns_serial(config):",
    "def reverse_owner_for_ip(",
    calculate_serial,
)

# User-facing wording that should no longer imply BIND is always selected.
labmgmt = labmgmt.replace(
    "Topology and BIND were NOT modified.",
    "Topology and DNS were NOT modified.",
)
labmgmt = labmgmt.replace(
    "DNS and BIND were NOT modified.",
    "DNS server was NOT modified.",
)
labmgmt = labmgmt.replace(
    'print("BIND reload:        no")',
    'print("DNS server reload/restart: no")',
)
labmgmt = labmgmt.replace(
    '"BIND live zone files were NOT modified."',
    '"Live DNS zone files were NOT modified."',
)

LABMGMT.write_text(labmgmt)

# -------------------------------------------------------------------------
# Configuration: BIND remains the explicit default; tiny-dns is optional.
# -------------------------------------------------------------------------
config = CONFIG.read_text()
config = replace_once(
    config,
    "dns:\n  domain: lab.home.arpa\n",
    "dns:\n  # DNS publishing backend. Supported values: bind, tiny-dns.\n"
    "  # 'bind' remains the default when this setting is omitted.\n"
    "  backend: bind\n"
    "  domain: lab.home.arpa\n",
)
config = replace_once(
    config,
    "  bind:\n    forward_zone_file: /etc/bind/zones/db.lab.home.arpa\n    reverse_zone_file: /etc/bind/zones/db.10.255\n",
    "  bind:\n"
    "    forward_zone_file: /etc/bind/zones/db.lab.home.arpa\n"
    "    reverse_zone_file: /etc/bind/zones/db.10.255\n"
    "  tiny_dns:\n"
    "    forward_zone_file: /etc/tiny-dns/zones/lab.home.arpa.zone\n"
    "    reverse_zone_file: /etc/tiny-dns/zones/255.10.in-addr.arpa.zone\n"
    "    service: tiny-dns.service\n",
)
CONFIG.write_text(config)

# -------------------------------------------------------------------------
# Root README: retain BIND quick-start/default, document backend selection
# and a Rocky/tiny-dns bootstrap path.
# -------------------------------------------------------------------------
readme = ROOT_README.read_text()
readme = readme.replace(
    "optional BIND DNS generation",
    "optional authoritative DNS generation with BIND or tiny-dns",
)
readme = readme.replace(
    "LabMgmt stages DNS during `onboard` and `apply`, so install the BIND utilities before onboarding the first lab:\n",
    "LabMgmt stages DNS during `onboard` and `apply`. Zone syntax is always validated with `named-checkzone`, regardless of the serving backend. For the default BIND backend on Debian/Ubuntu, install:\n",
)

backend_section = r'''## DNS backend selection

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

'''
readme = replace_once(
    readme,
    "## Required first-time BIND setup\n",
    backend_section + "## Required first-time BIND setup\n",
)

small_dns_section = r'''## Alternative tiny-dns setup

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

'''
readme = replace_once(
    readme,
    "## First example lab\n",
    small_dns_section + "## First example lab\n",
)
ROOT_README.write_text(readme)

# -------------------------------------------------------------------------
# LabMgmt operations README: explain the generic backend behavior while
# keeping the existing detailed BIND bootstrap as the default path.
# -------------------------------------------------------------------------
ops = LABMGMT_README.read_text()
ops = replace_once(
    ops,
    "## DNS\n\nDNS is generated entirely from active IPAM entries.\n\n",
    "## DNS\n\nDNS is generated entirely from active IPAM entries. The serving backend is selected with `dns.backend`. BIND is the default, including when `dns.backend` is omitted for backward compatibility. The alternative `tiny-dns` backend uses the same generated master-file records but publishes them to a systemd-managed tiny-dns service.\n\nThe Git-managed staging files remain backend-neutral:\n\n```text\nlabmgmt/generated/dns/db.lab.home.arpa\nlabmgmt/generated/dns/db.10.255\n```\n\nBoth backends require `named-checkzone`; only the BIND backend also requires `named-checkconf` and `rndc`.\n\n",
)

ops = replace_once(
    ops,
    "Do not merely create empty files. Each file must contain a valid SOA and NS record or both BIND validation and LabMgmt serial handling will fail.\n\n",
    "Do not merely create empty files. Each file must contain a valid SOA and NS record or both zone validation and LabMgmt serial handling will fail.\n\n### First-time tiny-dns bootstrap\n\nSet `dns.backend: tiny-dns` and configure `dns.tiny_dns.forward_zone_file`, `dns.tiny_dns.reverse_zone_file`, and `dns.tiny_dns.service`. The complete copy-and-paste procedure is maintained in the repository's [Alternative tiny-dns setup](../README.md#alternative-tiny-dns-setup).\n\nFor the default `10.255.0.0/16` management supernet, the reverse DNS zone is `255.10.in-addr.arpa`. LabMgmt prepends an explicit `$ORIGIN` when publishing to tiny-dns so standalone master-file readers do not have to infer the origin from a separate server configuration. LabMgmt also accepts either parenthesized or single-line SOA records when reading the current live serial.\n\n",
)

old_install = r'''The install process:

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
'''
new_install = r'''The install process:

1. Validates IPAM and DNS configuration.
2. Confirms the staging files match current IPAM and the live SOA serials.
3. Runs `named-checkzone` against both zones.
4. Validates the selected backend (`named-checkconf` for BIND, systemd service definition for tiny-dns).
5. Backs up the current live zone files.
6. Atomically installs both zones while preserving the live files' owner, group, and mode.
7. Validates the installed backend configuration/service and both live zones.
8. Reloads BIND with `rndc reload` or restarts the configured tiny-dns service.
9. Checks backend status.
10. Restores the previous files and reloads/restarts the backend if installation fails.

For the default BIND backend, live zone files are:

```text
/etc/bind/zones/db.lab.home.arpa
/etc/bind/zones/db.10.255
```

For the example tiny-dns backend, live zone files are:

```text
/etc/tiny-dns/zones/lab.home.arpa.zone
/etc/tiny-dns/zones/255.10.in-addr.arpa.zone
```

Backups are kept beneath `labmgmt-backups/` in the common parent directory of the selected backend's two live zone files.
'''
ops = replace_once(ops, old_install, new_install)

ops = ops.replace(
    "* BIND is never reloaded unless generated zones validate.\n* Live BIND files are backed up before replacement.\n",
    "* The selected DNS backend is never reloaded/restarted unless generated zones validate.\n* Live DNS files are backed up before replacement.\n",
)
LABMGMT_README.write_text(ops)

print("DNS backend patch applied")
