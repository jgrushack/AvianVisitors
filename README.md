# AvianVisitors — Wireless Bird Frame

A battery-powered, Wi-Fi e-paper frame for the birds heard outside your window, built on **Teddy Warner’s AvianVisitors** and refined by **Jesse Grushack**. This fork adds a BirdWeather-powered wireless frame and illustrations for the northeastern United States.

**[See the Black Creek Falls bird page →](https://birds.blackcreekfallsny.com/)**

## Building the listener? Start with Teddy’s repo

For the Raspberry Pi microphone/listener build, parts list, and installation instructions, go to **[Teddy Warner’s AvianVisitors GitHub repository](https://github.com/Twarner491/AvianVisitors)**. Read the story behind the original project on [Teddy’s website](https://theodore.net/projects/AvianVisitors/).

The wireless frame setup here uses an existing **BirdWeather station** as its detection source. Our build uses a BirdWeather PUC, with a separate Linux server rendering the images. The included adapter reads BirdWeather data; it does not directly connect to a standalone BirdNET-Pi database.

## Wireless frame bill of materials

| Qty | Part | Build notes |
| --- | --- | --- |
| 1 | **Good Display GDEP133C02, 13.3-inch Spectra 6 e-paper panel** | Six-color display, used in portrait at 1200 × 1600. This is the panel used in this build. |
| 1 | **[Seeed Studio XIAO ePaper Display Board EE02](https://wiki.seeedstudio.com/getting_started_with_ee02/)** | Includes the XIAO ESP32-S3 Plus, display driver circuitry, battery charging, and three user buttons. No separate ESP32 is needed. |
| 1 | **3.7 V rechargeable single-cell Li-ion/LiPo battery** | This build uses 2,000 mAh. Match the EE02’s two-pin JST 2.0 mm connector **and polarity**; connector fit alone does not guarantee that positive and negative match. Verify before connecting. |
| 1 | **USB-C data cable and USB power supply** | For initial firmware flashing and charging. |
| 1 | **Frame with mat, backing, and mounting spacers** | Allow space for the panel, controller, battery, and ribbon cable. Support the panel without clamping the active display. See the [proposed mat dimensions and cutting template](integrations/ee02/mat/MAT-SPEC.md). |
| Optional | **USB-C extension/panel-mount cable** | Makes the charging port accessible after framing. |

You also need **Wi-Fi**, an existing **BirdWeather station**, and an **always-on Linux server**. This build runs the renderer in a Debian 12 container on an Intel NUC with Proxmox. Home Assistant is not required; the renderer runs separately. The frame connects over Wi-Fi and can run from its battery, while the server stays powered.

Battery runtime has not been benchmarked. The firmware sleeps between scheduled checks, powers down the display circuitry, and supports waking with the buttons.

## How it works

```text
BirdWeather station → BirdWeather data → Linux renderer → Wi-Fi → EE02 e-paper frame
                                              └────────→ Bird website
```

- **Heard Today:** birds detected since midnight in New York time, with illustration size based on detection counts and bird-name labels.
- **More frame pages:** stamps, Most Heard, activity, and first detections.
- **Button navigation:** KEY1 changes modes; KEY2 and KEY3 move between pages. Closely spaced presses are collected before loading the final selection.
- **Web experience:** the original collage, statistics, Avian Atlas, species details, and available recordings, backed by a local station archive.
- **Wireless updates:** ESPHome firmware, scheduled checks, deep sleep, and OTA updates after the first USB flash.

**[Build and configure the wireless frame →](integrations/ee02/README.md)**

## Northeast bird illustrations

This fork adds **66 additional Northeast bird species, with two illustrations per species — 132 new illustrations**. The additions expand the artwork available for northeastern U.S. stations while preserving the original AvianVisitors visual style.

The repository includes the corresponding image dimensions and masks used by the renderer. Bird-name labels, portrait composition, and clipping checks are included in the EE02 integration. Artwork coverage and detections are separate: adding a bird illustration makes it available to display when that species is heard.

## Credits

**Conceptualized by [Teddy Warner](https://theodore.net/projects/AvianVisitors/)** — original AvianVisitors project, artwork presentation, and web experience. See [his source repository](https://github.com/Twarner491/AvianVisitors) for the listener build and upstream development.

**Refined by [Jesse Grushack](https://github.com/jgrushack/AvianVisitors)** — Northeast bird additions and this BirdWeather / NUC / wireless EE02 frame integration.

The frame uses Philipp Waller’s [ESPHome Spectra 6 display driver](https://github.com/philippwaller/esphome-epaper-spectra6-133), fetched separately during setup. Existing project licenses and attribution remain in place; see [LICENSE](LICENSE).
