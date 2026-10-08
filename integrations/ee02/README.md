# BirdWeather + Seeed EE02 integration

Runs the original AvianVisitors artwork and frontend on a Linux server, with an ESPHome client driving a Good Display GDEP133C02 on the Seeed EE02. This is the alternative NUC/ESP32 setup; the upstream Raspberry Pi installer is not used.

## Included behavior

- Portrait 1200 × 1600 six-color output with bird-name labels, larger composition, glyph clipping checks and last-good-image retention.
- **Heard Today** queries the configured BirdWeather station from midnight in `America/New_York`. Counts determine bird size. Calendar dates handle daylight saving; an empty day displays “No birds heard yet today.”
- Original web frontend with Atlas stamps, statistics, species details, calendar and recordings, backed by a station-scoped SQLite archive. Pi administration and live microphone features are not provided by this adapter.
- Five paper modes: Heard Today, stamps, Most Heard (24h/7d/all), activity, and first detections.
- KEY1 cycles modes; KEY2/KEY3 select previous/next page. Pending presses are applied in order before fetching the final image, with a 400 ms settling interval between commands. A refresh already in progress finishes before queued navigation is applied. Up to 64 pending presses; retries retain event IDs to avoid double advances.
- Fifteen-minute server updates and device deep sleep, button wake, panel power-off, immutable image URLs and authenticated OTA. The physical midnight change appears on the next scheduled updates, not necessarily at 00:00 exactly.
- Audio cache evicts least-recently-used FLAC/WAV files above 256 MiB. Download/conversion temporarily needs additional space.

The repository also includes 66 additional Northeast species (two illustrations each), with updated dimensions and masks. Original stamp styling is preserved.

## Server layout and installation

Tested on Debian 12 in a Proxmox container. Run setup commands as root on the intended server. Install `python3-venv`, `git`, `ffmpeg`, `fonts-dejavu-core`, and Chromium dependencies through Playwright. Create an unprivileged `birdframe` account before running `server/install.sh`.

Expected layout:

```text
/opt/bird-renderer/
  service.py, history.py, web_features.py, views.py, config.json
  bird-*.service, bird-*.timer, install.sh
  venv/                  Python virtual environment
  browsers/              Playwright Chromium
  avian-visitors/         full checkout of this repository
/etc/bird-renderer/config.json
/var/lib/bird-renderer/   archive, generated frames, selection, caches
```

Clone this repository into `/opt/bird-renderer/avian-visitors`, then copy the files in `integrations/ee02/server/` to `/opt/bird-renderer/`. Create `/opt/bird-renderer/venv` with `python3 -m venv`; install `Pillow` and `playwright` into it. Install Chromium with:

```sh
PLAYWRIGHT_BROWSERS_PATH=/opt/bird-renderer/browsers /opt/bird-renderer/venv/bin/playwright install --with-deps chromium
```

Make the code, virtual environment and browsers readable/executable by `birdframe`. Edit `config.json` before installation: the included configuration uses public station `19176`, `window: "today"` and the portrait layout above. The adapter currently assumes New York time; another station timezone requires updating `history.TZ` and `service.today_period` together. The installer preserves an existing `/etc/bird-renderer/config.json`.

Run `sh /opt/bird-renderer/install.sh`. It enables the web server and timers, and starts history import; successful import triggers rendering. Initial history import can take time. The server listens on port 8080: `/` provides frame controls; `/app/` serves the original frontend. Keep it on the trusted LAN; this adapter does not provide user authentication.

## Firmware

From this directory, obtain the pinned, unmodified display driver:

```sh
git clone https://github.com/philippwaller/esphome-epaper-spectra6-133 driver
git -C driver checkout e1da8da160850250258f0de0fd294a8519edfae0
cp secrets.example.yaml secrets.yaml
```

Set unique passwords in `secrets.yaml` (ignored by Git). Change the server URLs in `bird-frame.yaml` to your LAN address; the included deployment uses `192.168.1.30:8080`. Tested with ESPHome 2026.9.1:

```sh
esphome compile bird-frame.yaml
esphome upload bird-frame.yaml --device DEVICE_IP_OR_USB_PORT
```

For first-time Wi-Fi, join `Bird Frame Setup` using your setup password and configure the network at `http://192.168.4.1`. To keep the board awake for maintenance, hold KEY1, tap RESET, keep KEY1 held for about three seconds, then release. `bench-test.yaml` is an optional color-bar test that replaces the normal firmware when flashed.

No credentials, firmware dumps, compiled firmware, recordings or private device logs are included. The driver is fetched separately under its own license.

## Validation

On the server:

```sh
cd /opt/bird-renderer
venv/bin/python -m unittest test_features test_service test_audio_cache test_today
PLAYWRIGHT_BROWSERS_PATH=/opt/bird-renderer/browsers venv/bin/python check_bird_labels.py
```

The 13 Python tests passed on the deployed server, including midnight/DST boundaries, empty-day output, request validation, idempotent navigation, image retention and audio eviction. Full catalog rendering additionally checks missing assets and page bounds. The firmware compiles; the native FIFO test runs with:

```sh
c++ -std=c++17 test_button_queue.cpp -o /tmp/test_button_queue
/tmp/test_button_queue
```

The deployed firmware is `button-batch-4`; OTA success and a subsequent device check-in were observed. Rapid multi-press behavior still needs physical confirmation. The SVG and proposed mat dimensions are in `mat/`.
