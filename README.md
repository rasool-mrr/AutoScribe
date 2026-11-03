<div align="center">

# AutoScribe

**Find the Windscribe servers and protocols that actually work on your network.**

**English** · [فارسی](README.fa.md) · [Русский](README.ru.md)

</div>

---

AutoScribe is a desktop app that drives the official **Windscribe CLI** for you. It works through every
server, protocol and port you pick, connects to each one, measures ping and packet loss through the
tunnel, and ranks the combinations that work best. It's useful on networks where VPNs are filtered or
throttled and you'd otherwise have to try routes by hand.

## Features

- **Automatic testing** – city × protocol × port, with WireGuard, IKEv2, UDP, TCP, Stealth and WStunnel.
- **Ping & packet loss** through the tunnel, measured with the system `ping` (nothing extra to install).
- **Best routes** – a live leaderboard of the fastest working routes. Double-click a route to connect to it.
- **Searchable location picker** – type to find any country, city or server, filter by region, and select whole countries or single servers. You see how many tests that adds up to before you start.
- **Up-to-date server list** – one click on **Update list** downloads the current server list from windscribe.com.
- **Protocol priority** – reorder protocols and choose exactly which ports to test.
- **Resume** – skip combinations that are already tested and pick up where you left off.
- **Stop on first success** – stop the run and stay connected as soon as one route works.
- **Profiles** – save and load complete sets of settings.
- **Live dashboard** – the server being tested, each step (disconnect → connect → settle → ping), progress, time left, success rate and best ping.
- **What works here** – success rate per protocol, with a tip when a protocol keeps failing.
- **Searchable, sortable results**, with a right-click menu to copy or connect.
- **CSV export** of all results to the `reports/` folder.
- **Keyboard shortcuts** for the common actions.
- **Three languages** – English, Farsi (fully right-to-left) and Russian. Switch at the bottom of the sidebar; the first launch follows your Windows display language.

## Requirements

- **Windows 10/11** (Linux and macOS should work too if `windscribe-cli` is on your `PATH`)
- **Python 3.9+** with Tkinter (included in the standard Windows installer)
- **Windscribe desktop app**, signed in. It ships the CLI at `C:\Program Files\Windscribe\windscribe-cli.exe`.

## Installation

```bash
git clone https://github.com/<your-username>/AutoScribe.git
cd AutoScribe
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

`python main.py --debug` shows a Debug switch that runs CLI commands in a visible window.

## Usage

1. Check that the badge at the bottom-left reads **Windscribe CLI ready**. If it doesn't, click it and set the path to `windscribe-cli`.
2. Under **Locations**, click **Change** (or press `Ctrl+L`). Search for a country, city or server, or pick a region, and tick what you want. Nothing ticked means every server. The sidebar shows how many tests that is. Click **Update list** to get the newest servers from windscribe.com.
3. Under **Protocols**, turn protocols on or off, use **▲ / ▼** to set the order, and click the ports button to choose ports.
4. Press **Start** (or `Ctrl+Enter`). Results appear as they come in.
5. When the run ends, the best route is shown at the top with a **Connect** button. The **Best routes** tab ranks the rest; double-click one to connect.
6. Press **Export CSV** to save a report.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` / `F5` | Start |
| `Esc` | Stop after the current step |
| `Ctrl+F` | Search results |
| `Ctrl+L` | Choose locations |
| `Ctrl+B` | Show or hide the setup panel |
| `Ctrl+S` | Save profile |
| `Ctrl+E` | Export CSV |

### Settings

| Setting | Meaning |
|---|---|
| Ping host | Host to ping through the tunnel (default `1.1.1.1`) |
| Pings per test | Number of pings per successful connection (1–20) |
| Connect timeout | How long to wait for a connection, in seconds (3–300) |
| Settle delay | Pause after connecting, before pinging (0–60 s) |

## Linux CLI extras: censorship tweaks

The Windows `windscribe-cli.exe` cannot change anti-censorship settings, so with it AutoScribe behaves
exactly as described above. The **Linux** `windscribe-cli` keeps its settings in
`~/.config/Windscribe/windscribe_cli.conf`, which AutoScribe can edit between tests. When the CLI path
points at a Linux CLI, a **Censorship tweaks** card appears under **Protocols**:

- **Amnezia** – pick any of the AmneziaWG presets the CLI offers. Each one is tried on every selected
  WireGuard port.
- **Large TLS** – Off, On, or **Test both**.
- **Server routing** – Auto, Regular, Alternate, or **Test both**.

Every combination becomes its own test, so one WireGuard port with one preset and both toggles on
"Test both" runs four tests. Results, the Best routes tab and the CSV carry the preset, TLS and routing
of each row (`awg`, `tls`, `routing` columns; the route reads like `wireguard:443 · A · TLS · alt`).
The original conf file is restored when the run ends.

Two ways to get a Linux CLI:

- Run AutoScribe on Linux with `windscribe-cli` installed and logged in.
- On Windows, install the CLI inside WSL (for example Ubuntu), log in there, and set the CLI path to
  `wsl -d Ubuntu -u <user> -- windscribe-cli`. Pings then run inside WSL too, because a Windows `ping`
  does not go through the WSL tunnel.

## Files

| File | Purpose |
|---|---|
| `main.py` | The application |
| `i18n.py` | Translations and right-to-left text handling |
| `locations.json` | Windscribe server list used by the location picker. Click **Update list** in the app to download the latest one |
| `config.json` | Your settings and profiles (created automatically) |
| `windscribe_results.db` | SQLite database of results (created automatically) |
| `reports/` | Exported CSV files |

## Building a standalone .exe

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name AutoScribe --collect-data customtkinter main.py
```

Put `locations.json` in the same folder as `dist\AutoScribe.exe`.

## Contributing

Issues and pull requests are welcome. Fork the repository, make your change, and open a PR.

## License

Released under the **MIT License with a removal-on-request condition**. See [LICENSE](LICENSE).
You may use, modify and publish this code, but **if the author asks you to delete or take down your
copy or a derivative of it, you must do so.**

## Disclaimer

AutoScribe is an independent, unofficial project. It is **not affiliated with, endorsed by, or
supported by Windscribe Limited**. "Windscribe" is a trademark of its owner. You need your own
Windscribe account, and you are responsible for following Windscribe's terms of service and the
laws where you live.
