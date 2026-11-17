# Samsung TV Web Remote

A tiny, phone-friendly web remote for Samsung Tizen smart TVs. One Python file, no dependencies, plus one HTML page.

## Why this exists

We bought a house, and the previous owners left a Samsung TV behind with no remote. The only physical control on the set is a single power button, which turns it on and off and does nothing else. No menus, no inputs, no Wi-Fi setup.

A Flipper Zero got us in: it can act as an IR remote, which was enough to walk through the TV's setup and join it to the home Wi-Fi. Once the TV was on the network, it exposed Samsung's local remote-control API, and this page was built on top of that. Now any phone or laptop on the network (or over a VPN) gets a full remote.

## Features

- Power on (Wake-on-LAN) and power off, with live on/standby/off status
- D-pad with OK, Home, Menu, Back, Exit
- Volume up/down, mute, channel up/down, previous channel
- "Go to channel" box (`7`, `13-1`, ...) plus a full number keypad and channel list
- Source, TV, Info, Guide, and playback controls
- One-tap app launching (Netflix, YouTube, Prime Video, Hulu, Disney+, Peacock, Apple TV, Tubi, Spotify, Internet browser)
- Mobile-first layout; add it to your home screen and it behaves like an app

## How it works

- **Buttons** go to the TV's WebSocket remote API at `wss://<tv>:8002/api/v2/channels/samsung.remote.control` as standard `KEY_*` codes. Only an allowlist of keys is accepted.
- **Apps** are launched through the TV's REST API (`POST http://<tv>:8001/api/v2/applications/<appId>`). Older Tizen sets ignore the "list installed apps" request, so the page uses a list of well-known app IDs; edit `KNOWN_APPS` in `server.py` for your set. You can check whether an app is installed with `GET http://<tv>:8001/api/v2/applications/<appId>`.
- **Power on** uses Wake-on-LAN. Turn on the TV setting that allows it to be powered on over the network (on many models: Settings > General > Network > Expert Settings > Power On with Mobile).
- **Status** comes from `http://<tv>:8001/api/v2/` (`PowerState`).

Tested on a 2017 Samsung M-series (Tizen). Newer Tizen TVs use the same APIs.

## Setup

Requirements: Python 3.8+ on any always-on machine on the same network as the TV (a Raspberry Pi works well).

```sh
git clone https://github.com/tsali/samsung-tv-web-remote.git
cd samsung-tv-web-remote
TV_IP=192.168.1.50 TV_MAC=AA:BB:CC:DD:EE:FF python3 server.py
```

Open `http://<that-machine>:8095` on your phone.

The first time you press a button, the TV shows a prompt asking whether to allow the new remote. Choose **Allow**. The server log prints a pairing token; set it as `TV_TOKEN` so the TV doesn't ask again.

| Variable | Required | Meaning |
|---|---|---|
| `TV_IP` | yes | TV's LAN IP address (give it a DHCP reservation) |
| `TV_MAC` | for Power On | TV's network MAC address |
| `TV_TOKEN` | no | Pairing token printed after you press Allow |
| `REMOTE_NAME` | no | Name shown on the TV's pairing prompt (default `Web Remote`) |
| `PORT` | no | HTTP port (default `8095`) |

### Run it as a service

Copy `tvremote.service.example` to `/etc/systemd/system/tvremote.service`, fill in your values, then:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now tvremote
```

## Security

There is no login. Anyone who can reach the page can control the TV. Keep it on your home network or behind a VPN (Tailscale/WireGuard), not on the open internet.

## License

MIT
