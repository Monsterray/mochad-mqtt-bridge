# Hardware Lab Setup

The bridge hardware lab is deliberately separate from Home Assistant and
production MQTT. It uses a restricted SSH account and an isolated broker.

## Account and Lock

The server is Linux. An administrator creates `codex-x10` with home and
workspace `/srv/x10-dev`, membership in `x10dev` and `x10`, and no `sudo` or
`docker` membership. The shared controller lock must be created once:

```sh
sudo getent group x10 >/dev/null || sudo groupadd --system x10
sudo getent group x10dev >/dev/null || sudo groupadd --system x10dev
sudo useradd --create-home --user-group --home-dir /srv/x10-dev \
  --groups x10dev,x10 --shell /bin/bash codex-x10
sudo install -d -o codex-x10 -g x10dev -m 2770 /srv/x10-dev
sudo install -o root -g x10dev -m 0660 /dev/null /run/lock/x10-hardware.lock
```

The existing CM19A udev permission policy must expose `0bc7:0002` as
`root:x10`, mode `0660`.

## Workstation and SSH Setup

These examples use SSH port `2222`. Replace `admin`, `SERVER`, and the port
with your existing administrative connection. `ssh-copy-id` is optional and is
not present on every macOS installation; it also requires an account that can
already authenticate.

### macOS and Linux

Create a dedicated key on the workstation:

```sh
ssh-keygen -t ed25519 -f ~/.ssh/codex_x10 -C "codex-x10 hardware lab"
scp -P 2222 ~/.ssh/codex_x10.pub admin@SERVER:/tmp/codex_x10.pub
ssh -p 2222 admin@SERVER
```

As the server administrator, install that exact public key for the restricted
account. Do not copy an existing user's `authorized_keys` file.

```sh
sudo install -d -o codex-x10 -g codex-x10 -m 0700 /srv/x10-dev/.ssh
sudo install -o codex-x10 -g codex-x10 -m 0600 \
  /tmp/codex_x10.pub /srv/x10-dev/.ssh/authorized_keys
sudo rm -f /tmp/codex_x10.pub
```

Add this to `~/.ssh/config`:

```sshconfig
Host x10-lab
  HostName SERVER
  Port 2222
  User codex-x10
  IdentityFile ~/.ssh/codex_x10
  IdentitiesOnly yes
```

Connect with `ssh x10-lab`, then run `id`. The account must include `x10` and
`x10dev`, but not `sudo` or `docker`.

### Windows 10/11 PowerShell

Current Windows installations include OpenSSH. In PowerShell:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\codex_x10" -C "codex-x10 hardware lab"
scp -P 2222 "$env:USERPROFILE\.ssh\codex_x10.pub" admin@SERVER:/tmp/codex_x10.pub
ssh -p 2222 admin@SERVER
```

Install the uploaded key on the server using the Linux commands above. Create
`%USERPROFILE%\.ssh\config` with the same `Host x10-lab` block; OpenSSH
accepts `~/.ssh/codex_x10` as the identity path on Windows.

### Public-Key and Certificate-Only Servers

When no existing key can access the server, use its local console, IPMI, or a
hosting-provider console to install the public key. Do not enable password
login merely to bootstrap this account. If the server requires an
OpenSSH-CA-signed certificate rather than ordinary public-key authentication,
ask the CA administrator to sign `codex_x10.pub`; a plain key will be rejected.

## Run

Start a CM19A lab instance of mochad on `127.0.0.1:19099`, then run:

```sh
scripts/hardware/run-bridge-hardware-validation.sh
```

The script starts an isolated Mosquitto broker on `127.0.0.1:11883`, selects a
run-specific `x10-test/<sha>` prefix, and sets `MQTT_DISCOVERY_ENABLED=false`.
It verifies command delivery and the action-only chime state contract. RF
receive and audible SC546A effects remain `HARDWARE REQUIRED` until a person
records them.

## Future Self-Hosted Runner

After this manual process has been reviewed and proven, an optional runner may
use the labels `x10-hardware`, `cm19a`, and `sc546a`. Restrict it to manually
dispatched release workflows on trusted commits. Never register it for fork PRs
or automatic unreviewed branch runs.
