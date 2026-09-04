**English** · [Español](README.es.md)

# Clean Assistant

A **local, no-cloud** app to manage the **Cecotec Conga 8090 Ultra** — and other Conga
models on the same platform (e.g. the **4690 Ultra**, confirmed by a user): live map,
per-room cleaning, zones, schedules, history and every setting, in its own polished web
interface, **available in 5 languages** (Spanish, English, Portuguese, French, Polish).
In the spirit of Valetudo/Congatudo, but for the 8000 generation (which uses TLS +
WebSocket + JSON + Protobuf, not supported by those projects).

> Built on the reverse engineering from the documentation repo:
> [conga_8090_mqtt_bridge](https://github.com/miguelsg29/conga_8090_mqtt_bridge).

![Clean Assistant — live map and controls](panel.png)

## 🔌 100% local — independent of Cecotec's cloud

This is the goal of the project: **your robot keeps working even if Cecotec shuts down
its servers.** Clean Assistant impersonates **all** the services the robot looks for on
the internet, redirecting them via DNS to your server:

- **Control** (port 9090, WSS): commands, map, status, zones and schedules.
- **OTA** (port 8001): on boot, the robot asks "is there new firmware and where are the
  services?". Clean Assistant answers "no update" and hands it a directory pointing back
  to itself. This is the **key** piece of the boot: without it the robot doesn't know
  where to connect. (Also, automatic updates are **disabled by default**, so the robot
  doesn't download firmware on its own.)
- **History** (ports 8002/8006): the robot uploads a report for each cleaning; Clean
  Assistant accepts them and pours them into its **history** (date, time, m², duration).

And best of all: **you don't need the cloud, not even the first time.** On a fresh
install, Clean Assistant **learns the robot's own identity** (serial number, model,
identifier…) from the requests it makes right after booting, gets the MAC from the
network and self-configures. You can also export that identity as a **"recovery key"**
to restore it on another server.

## Home Assistant install (quick)

The recommended way to use Clean Assistant. It opens from HA's sidebar, with no separate
login.

> Since **Home Assistant 2026.2**, "Add-ons" are now called **"Apps"**. I use the new
> term; if your Home Assistant is older, it's exactly the same thing as "Add-ons".

1. **Add this repository** to your Home Assistant. One click:

   [![Add repository to your Home Assistant instance](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fmiguelsg29%2Fclean-assistant)

   Or manually: in Home Assistant, **Settings → Apps → App Store → ⋮ menu (top right) →
   Repositories**, paste `https://github.com/miguelsg29/clean-assistant` and click
   **Add**.
2. **Install "Clean Assistant"** from the App Store (if it doesn't show up, refresh with
   ⋮ → Reload) and open it.
3. **Redirect the robot to Home Assistant** with a DNS server (AdGuard Home, Pi-hole or
   your router). For full independence, make **all** these domains point to the **Home
   Assistant IP**:
   ```
   tcp-cecotec.3irobotix.net     (control)
   cecotec-ota.3irobotix.net     (OTA)
   eu-ota.3irobotix.net          (OTA)
   web-eu.3irobotix.net          (history)
   web-cecotec.3irobotix.net     (history)
   ```
   Then **restart the robot** (power cut) so it reconnects there. *(The first-run wizard
   shows you these instructions with the IP already detected and a live indicator of
   whether the robot connects.)*
4. **Start the app.** You don't need to fill in the robot's IDs: they
   **self-configure** by learning the robot's own identity.
5. Open **Clean Assistant** in the sidebar: you'll see the **real map** and all the
   controls. 🎉
6. *(Optional)* **Entities in Home Assistant (MQTT):** if you have the **Mosquitto
   broker** app, Clean Assistant picks up host/user/password **automatically**. A
   **Conga** device (named after your real model — 8090 Ultra, 4690 Ultra…) will appear
   with vacuum, battery, per-room buttons, selectors, schedules… Only fill in the `MQTT_*` fields by hand if you use a broker external to
   Home Assistant.

## What it offers

A complete app, **verified end to end with a real Conga 8090**, packaged for **Docker**
and as a **Home Assistant app** (add-on/ingress). It includes a **simulated robot** to
develop the interface without a Conga.

### 🗺️ Live map
- Real robot map decoded (zlib + Protobuf) and drawn on canvas, with the **rooms**,
  their names and the **robot's position** in real time (an overlay layer with animated
  movement and a pulsing ring while cleaning).
- **Zoom and pan**: mouse wheel, pinch and drag on mobile, double tap to zoom in, and
  +/−/fit buttons.
- **Rotate and mirror** the map to align it with your home (the mirror is on by
  default). Header with the map name, status and m²/time of the last cleaning.

### 🧹 Cleaning and control
- Start, pause, resume, return to dock, locate.
- Clean **individual rooms** (tap them on the map) or a full clean.
- Settings: **suction, water and mop**, mode (auto/mopping/edges/spiral), double pass,
  carpet turbo, dock type, dust bin **emptying frequency**, voice and volume, **do not
  disturb**, and automatic updates (OTA).
- **Consumables**: remaining life of brushes, filter and mop, with a button to reset to
  zero when you replace the part.
- Robot warnings and errors in the header (e.g. "Water tank low").

### 🚪 Rooms
- Name, **room type** (with icon) and **floor type** (wood, tiles, carpet, soft) per
  room, drawn on the map with texture.
- **Merge** and **split** rooms directly on the map.
- **Square metres** per room and total for the house.

### 🚫 Zones
- **No-go**, **no-mop** and **double-pass (x2)** zones: drawn as rectangles on the map,
  moved/resized and sent to the robot (`set_virwall`/`set_area`). Persistent and
  **per map**.
- Automatically adopts the zones created in the official Cecotec app.
- Re-sent to the robot if it loses them after a restart (without accumulating them if
  you control the robot from two servers).

### ⏰ Schedules
- Visual editor: name, time, days, **rooms and per-room mode** (`setOrder6090`).
  Enable/disable, edit and delete. Persistent and **per map**.
- Synced in both directions with the robot (imports the missing ones, including those
  from the official app; uploads Clean Assistant's).
- The robot's clock is set on connect (`set_time`) so schedules **fire at the correct
  time** even after a long time without the cloud (using the Home Assistant time zone).

### 🏠 House maps
- List, **switch**, rename, **create** (remaps the house) and **delete** maps —
  including the active one or the last one (the robot is left with no map to start from
  scratch).
- When you create the **first** map, the robot's previous ones are deleted, avoiding the
  **duplicate/ghost maps** the Conga accumulated with each mapping.
- Zones and schedules are assigned to the **correct map** when you switch.

### 📊 Cleaning history
- **Activity** tab: each cleaning (manual/scheduled type, rooms, m², duration, day and
  time) and the robot's warnings/errors.
- Also fed by the **reports the robot uploads** (ingested without the cloud).

### 🔐 Cloud independence and backup
- Impersonation of **control + OTA + history** to run 100% locally (see above).
- **Local auto-provisioning** of the robot's identity (no cloud, no stored data).
- **Backup**: export/import on one side the **configuration** (maps, zones, schedules)
  and on the other the **robot's identity** ("recovery key") to move or restore on
  another server.

### 📱 Home Assistant and mobile
- **MQTT bridge** (autodiscovery): a **Conga** device (shown with your real model:
  8090 Ultra, 4690 Ultra…) with vacuum, battery/area/time, consumables, a button per room,
  selectors for power/water/mop/mode/dock/**emptying frequency**, switches for
  do-not-disturb/voice/OTA/turbo/double-pass, volume, a "Low water" sensor and a switch
  per schedule. Mounted **on top of** the same
  robot (no second server). Activates on its own with HA's broker.
- **Touch** interface: draw zones, split/merge rooms and select rooms by hand, without
  the page scrolling.

### 🌍 Languages & easy updates
- Interface **in 5 languages** — Spanish, English, Portuguese, French and Polish. Pick it
  from the header; it auto-detects your browser language.
- The Home Assistant add-on ships as a **prebuilt image**, so **updates are fast**
  (downloaded, not built on your device) and show a real progress bar.

## Architecture

```
   Conga 8090 Ultra
       │  (DNS: Cecotec domains → this server)
       ▼
┌───────────────────────────────────────────────────────┐
│                Clean Assistant (backend)               │
│   RealRobot   → control TLS+WebSocket (9090)           │
│   cloud_stub  → OTA (8001) + history (8002/8006)       │
│   conga_core  → protocol + state + map (Protobuf)      │
│   backend/app → FastAPI: REST + WebSocket + static     │
│                 + optional MQTT bridge for HA          │
└───────────────────────────┬───────────────────────────┘
                            ▼
              Browser / mobile  ·  Home Assistant (MQTT)
```

The robot connects to Clean Assistant believing it's Cecotec's cloud. `RealRobot`
terminates the TLS 1.2, does the WebSocket handshake and answers login (synthetic JWT),
heartbeat and report_data; `cloud_stub` answers OTA and history. The web interface and
the MQTT bridge are mounted on the same robot. There's a `MockRobot` with the same
interface (`.state`, `command(control)`, `tick()`) to develop without a Conga.

## Getting started (development)

```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload --port 8000   # simulated robot (default CONGA_MODE)
```

Open **http://localhost:8000**: press *Start* and watch the live status (WebSocket).

### Real mode (against your Conga)

1. Copy `.env.example` to `.env` and set `CONGA_MODE=real`. **You don't need to fill in
   the robot's IDs**: they self-configure (see below).
2. Redirect the Cecotec domains (the same as the HA install) via DNS to this machine's
   IP and open ports **9090, 8001, 8002 and 8006**. The certificates are generated on
   their own (openssl, with the SAN of all the domains) if they don't exist.
3. Start it (`uvicorn backend.app:app`) and restart the robot (power cut). In the log
   you'll see `[robot] LOGIN` and the real status in the interface.

**Auto-configuration (first run).** Clean Assistant gets the robot's identity in this
order, without you having to enter anything:

1. **Local, from the robot itself** (preferred, no cloud): learns the DID, serial number
   and model from the requests the robot makes (OTA/history), the MAC from the ARP table,
   and mints the account identifier. Saved in `identity.json`.
2. **Cloud gateway** (fallback): if you only redirect `tcp-cecotec`, it captures the
   identity from the real cloud's login response and switches to local.
3. **Manual / recovery key**: fill in the IDs by hand or import an exported identity.

You can choose the mode in **Settings → Operating mode** (Local / Cloud + Local).

## Docker

```bash
cp .env.example .env          # set CONGA_MODE=real
docker compose up -d --build
```

The web ends up at `http://this-host:8000` and the robot's servers at `:9090` (control)
and `:8001/:8002/:8006` (OTA/history). The certificates, maps, zones, schedules,
history, identity and view are stored in `./data` (persistent).

## Home Assistant app (ingress)

This repository **is also a Home Assistant Apps repository** (add-ons; see "Home
Assistant install"). The interface opens from the sidebar (ingress, with the HA
session). The app reads the **time zone** and the host's **LAN IP** from the Supervisor
(for the DNS instructions), picks up HA's **MQTT** broker on its own, and opens the
robot's ports (9090/8001/8002/8006).

The add-on ships as a **prebuilt multi-arch image** (aarch64/amd64), built by GitHub
Actions and published to GHCR on every release. Home Assistant **downloads** it instead of
building it on your device, so **updates are fast and show a real progress bar** — no
on-device compilation.

## Structure

```
clean-assistant/
├── conga_core/           # protocol core (source of truth, shareable)
│   ├── commands.py       # command builders (set_mode, setOrder6090, …)
│   ├── state.py          # RobotState from report_data
│   ├── map.py            # map decoder (zlib + Protobuf)
│   ├── robot.py          # RealRobot: TLS+WebSocket control server (9090)
│   ├── ws.py             # WebSocket utilities (handshake, frames)
│   └── config.py         # robot identity + synthetic JWT
├── backend/
│   ├── app.py            # FastAPI: REST + WebSocket + static + orchestration
│   ├── cloud_stub.py     # impersonates OTA (8001) and history (8002/8006); auto-provision
│   ├── maps.py           # house map management
│   ├── zones.py          # persistent zones (virwall/area)
│   ├── schedules.py      # persistent schedules (setOrder6090)
│   ├── history.py        # cleaning history
│   ├── mqtt_bridge.py    # Home Assistant bridge (autodiscovery), optional
│   ├── mock.py           # simulated robot
│   └── static/           # frontend (index.html)
├── requirements.txt
├── Dockerfile            # standalone Docker image
├── docker-compose.yml    # deployment with Compose
├── repository.yaml       # this repo as a HA Apps repository (add-ons)
└── clean_assistant/      # Home Assistant app (add-on/ingress)
    ├── config.yaml
    ├── CHANGELOG.md       # what's new in each version
    ├── Dockerfile
    └── run.sh
```

## Status

**Working and verified end to end with a real Conga 8090 Ultra.** The robot works
**100% locally** (control + OTA + history impersonated) and **self-configures without
the cloud** from the first boot. See [`clean_assistant/CHANGELOG.md`](clean_assistant/CHANGELOG.md)
for what's new in each version.

## Supported robots

Built and verified end to end with a **Conga 8090 Ultra**. Because these robots share the
same cloud stack (3irobotix: TLS + WebSocket + JSON), **other Conga models on that platform
also work** — the **4690 Ultra** is confirmed by a community user. Home Assistant shows the
real model (from the robot's `project_type`). If you try another model, please
[open an issue](https://github.com/miguelsg29/clean-assistant/issues) with your
`PROJECT_TYPE` and what does/doesn't work.

## Support

Clean Assistant is free and 100% local. If it's useful to you, you can support development
(and buying more robots to add support for): ☕ **[ko-fi.com/miguelsg29](https://ko-fi.com/miguelsg29)** — completely optional, and thank you!

## License

[MIT](LICENSE). Independent reverse-engineering project for interoperability and personal
use — **not affiliated with or endorsed by Cecotec or 3irobotix**. "Conga" and "Cecotec"
are trademarks of their respective owners.
