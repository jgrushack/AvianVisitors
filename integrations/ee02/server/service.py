"""LAN image service and scheduled AvianVisitors renderer."""
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(os.environ.get("BIRD_ROOT", "/opt/bird-renderer"))
DATA = Path(os.environ.get("BIRD_DATA", "/var/lib/bird-renderer"))
CONFIG = Path(os.environ.get("BIRD_CONFIG", "/etc/bird-renderer/config.json"))
sys.path.insert(0, str(ROOT / "avian-visitors/frame"))
import display as upstream_frame
import web_features
import history
PALETTE = [0, 0, 0, 255, 255, 255, 255, 255, 0, 255, 0, 0, 0, 0, 255, 0, 255, 0]


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        try:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def publish(image, state, species, activate=True):
    if image.size != (1200, 1600):
        raise ValueError(f"Wrong image dimensions: {image.size}")
    preview = upstream_frame.quantize_spectra6(image)
    # The repo's preview uses approximate physical inks; the EE02 driver accepts
    # six exact RGB codes. Translate the inks after the upstream dithering step.
    codes = [(255,255,255), (0,0,0), (255,0,0), (255,255,0), (0,0,255), (0,255,0)]
    table = []
    for channel in range(3):
        lut = list(range(256))
        for ink, code in zip(upstream_frame.SPECTRA6, codes):
            lut[ink[channel]] = code[channel]
        table.extend(lut)
    quantized = preview.point(table)
    buffer = io.BytesIO()
    quantized.convert("RGB").save(buffer, format="PNG")
    png = buffer.getvalue()
    version = hashlib.sha256(png).hexdigest()
    atomic(DATA / "frames" / f"{version}.png", png)
    preview_buffer = io.BytesIO()
    preview.save(preview_buffer, format="PNG")
    atomic(DATA / "previews" / f"{version}.png", preview_buffer.getvalue())
    manifest = {"version": version, "image": f"/frames/{version}.png", "width": 1200,
                "height": 1600, "state": state, "species": species,
                "updated_at": datetime.now(timezone.utc).isoformat()}
    if activate:
        atomic(DATA / "manifest.json", json.dumps(manifest).encode())
    # Keep old immutable images briefly so clients can finish an in-flight download.
    files = sorted((DATA / "frames").glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    protected = set()
    if (DATA / "catalog.json").exists():
        protected = {m["version"] for m in json.loads((DATA / "catalog.json").read_text())}
    for path in files[300:]:
        if path.stem != version and path.stem not in protected:
            path.unlink()
            (DATA / "previews" / path.name).unlink(missing_ok=True)
    return manifest


def today_period(now=None):
    """Calendar boundaries in New York, including 23/25-hour DST days."""
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return {"from": local.date().isoformat(),
            "to": (local.date() + timedelta(days=1)).isoformat(),
            "timezone": "America/New_York"}


def empty_today_image(config):
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    serif = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    for text, y, size in ((config["title"], 240, 28),
                           (config["subtitle"].upper(), 310, 54),
                           ("No birds heard yet today", 800, 30)):
        draw.text((600, y), text, fill="black", anchor="mm",
                  font=ImageFont.truetype(serif, size))
    return image


def render():
    import birdweather
    import shoot
    config = json.loads(CONFIG.read_text())
    DATA.mkdir(parents=True, exist_ok=True)
    if not config.get("station_id") and not config.get("zip"):
        if not (DATA / "manifest.json").exists():
            image = Image.new("RGB", (1200, 1600), "white")
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 60)
            draw.text((100, 380), "BIRD FRAME", fill="black", font=font)
            draw.text((100, 500), "Server ready", fill="black", font=font)
            draw.text((100, 620), "Waiting for BirdWeather source", fill="black", font=font)
            publish(image, "waiting_for_source", [])
        logging.info("Waiting for BirdWeather station ID or ZIP")
        return
    if config.get("station_id") and config.get("zip"):
        raise ValueError("Choose a station ID or ZIP, not both")
    options = {"target": config["bird_count"], "days": config["days"]}
    period = today_period() if config.get("window") == "today" else None
    if config.get("station_id"):
        options["period"] = period
        species = birdweather.species_for_station(config["station_id"], **options)
    else:
        species = birdweather.species_for_zip(config["zip"], country=config["country"], **options)
        if not species:
            raise RuntimeError("No drawable birds returned; retaining previous frame")
    # Counts affect the layout, and artwork changes must also invalidate the render.
    art = ROOT / "avian-visitors/avian/assets/illustrations"
    art_revision = [(p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(art.glob("*.png"))]
    signature = hashlib.sha256(json.dumps({"renderer_revision": 9, "period": period, "history": history.api("status", {})["as_of"], "config": config, "species": upstream_frame.signature(species),
        "art": art_revision},
        sort_keys=True).encode()).hexdigest()
    sigfile = DATA / "render-signature"
    if sigfile.exists() and sigfile.read_text() == signature:
        logging.info("Bird data unchanged; retaining image")
        return
    collage_signature = hashlib.sha256(json.dumps({"revision": 8, "period": period, "config": config, "art": art_revision,
        "species": species}, sort_keys=True).encode()).hexdigest()
    cached = DATA / "collage-cache.json"
    previous = json.loads(cached.read_text()) if cached.exists() else {}
    if previous.get("signature") == collage_signature:
        collage = previous["manifest"]
    elif not species:
        collage = publish(empty_today_image(config), "ready", [], activate=False)
        atomic(cached, json.dumps({"signature": collage_signature, "manifest": collage}).encode())
    else:
        with tempfile.TemporaryDirectory(dir=DATA) as tmp:
            output = Path(tmp) / "render.png"
            shoot.shoot_birdweather(str(output), species, title=config["title"],
                subtitle=config["subtitle"], bird_names=config["bird_names"], vw=600, vh=1000, dsf=2, cluster_ybias=1.6, small_floor=0)
            with Image.open(output) as image:
                # Keep upstream composition, with configurable spacing for our larger mat.
                upstream_frame.COLLAGE_FRAC = config.get("collage_fraction", 0.66)
                upstream_frame.GAP_FRAC = config.get("title_gap_fraction", 0.1)
                framed = upstream_frame.mat_and_center(image, upstream_frame.DEFAULTS["mat"],
                    config.get("opening", upstream_frame.DEFAULTS["opening"]))
                collage = publish(framed, "ready", species, activate=False)
        atomic(cached, json.dumps({"signature": collage_signature, "manifest": collage}).encode())
    web_features.catalog(ROOT, DATA, atomic, publish, collage)
    atomic(sigfile, signature.encode())


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not web_features.routes(self, ROOT, DATA, atomic):
            self.send_error(404)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            if web_features.routes(self, ROOT, DATA, atomic):
                return
        except Exception as exc:
            logging.exception("Request failed")
            self.send_error(503, "Data temporarily unavailable")
            return
        path = urlsplit(self.path).path
        try:
            manifest = json.loads((DATA / "manifest.json").read_text())
            if path == "/":
                body = b'<!doctype html><title>Bird Frame</title><h1>Bird Frame</h1><p><a href="/status.json">Service status</a></p><img src="/preview.png" style="max-width:100%">'
                kind = "text/html"
            elif path == "/preview.png":
                body = (DATA / "previews" / (manifest["version"] + ".png")).read_bytes()
                kind = "image/png"
            elif path in ("/manifest.json", "/health", "/status.json"):
                result = dict(manifest)
                status = DATA / "status.json"
                if status.exists():
                    result["renderer"] = json.loads(status.read_text())
                body, kind = json.dumps(result).encode(), "application/json"
            elif path == "/version":
                body, kind = manifest["version"].encode(), "text/plain"
            elif path == "/frame.png" or re.fullmatch(r"/frames/[a-f0-9]{64}\.png", path):
                name = manifest["image"] if path == "/frame.png" else path
                body, kind = (DATA / name.lstrip("/")).read_bytes(), "image/png"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400, immutable" if path.startswith("/frames/") else "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(503 if not (DATA / "manifest.json").exists() else 404)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if sys.argv[1:] == ["render"]:
        try:
            render()
        except Exception as exc:
            atomic(DATA / "status.json", json.dumps({"ok": False, "error": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat()}).encode())
            raise
        atomic(DATA / "status.json", json.dumps({"ok": True,
            "checked_at": datetime.now(timezone.utc).isoformat()}).encode())
    else:
        ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
