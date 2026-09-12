# HackBattle

HackBattle is a lightweight Python project scaffold for building a command-line client and a background watchdog service.

## Project structure

```text
.
├── cli/
│   └── main.py              # Command-line entry point
└── daemon/
    ├── watchdog.py          # Watchdog service implementation
    └── watchdog.service     # systemd service definition
```

The repository is currently an initial scaffold. The Python modules and systemd unit are intentionally empty and provide the locations where the application and service logic will be implemented.

## Requirements

- Python 3.9 or newer
- Linux with `systemd` if the watchdog is run as a service

The current scaffold has no third-party dependencies.

## Getting started

Clone the repository and enter its directory:

```bash
git clone https://github.com/AtharvaAmbast/HackBattle.git
cd HackBattle
```

Run the command-line entry point directly:

```bash
python3 cli/main.py
```

Run the watchdog module directly while developing it:

```bash
python3 daemon/watchdog.py
```

Both commands are currently placeholders until their implementations are added.

## Running the watchdog with systemd

Once `daemon/watchdog.py` has been implemented, the service can be installed on a Linux host by copying the unit file into the systemd unit directory, updating its paths and user settings for the host, and then enabling it:

```bash
sudo cp daemon/watchdog.service /etc/systemd/system/hackbattle-watchdog.service
sudo systemctl daemon-reload
sudo systemctl enable --now hackbattle-watchdog.service
```

Check its status and logs with:

```bash
systemctl status hackbattle-watchdog.service
journalctl -u hackbattle-watchdog.service -f
```

## Configuration and secrets

Local CLI environment files are ignored by Git. Store development-only variables in `cli/.env`, and never commit credentials or other secrets.

## Development

Keep runtime code in the `cli/` and `daemon/` directories, document new dependencies in this file, and add tests as functionality is introduced.
