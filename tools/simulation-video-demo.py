#!/usr/bin/env python3
"""Render a flat-terrain exercise scene from a fixed or simulated-aircraft camera."""

import argparse
from copy import deepcopy
import json
from itertools import count
import math
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageDraw

from takctl.simulation.model import active_members, advance_path


def unit(vector):
    norm = math.hypot(*vector)
    if norm == 0:
        raise ValueError("Camera axes require nonzero vectors")
    return tuple(value / norm for value in vector)


def subtract(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    x, y, z = a
    i, j, k = b
    return (y * k - z * j, z * i - x * k, x * j - y * i)


class Scene:
    def __init__(self, config):
        self.origin = config["origin"]
        self.ground = float(config.get("ground_hae_m", 0))
        self.cameras = config["cameras"]
        self.scale = 111_195 * math.cos(math.radians(self.origin["lat"]))
        self.faces = []
        for feature in config["buildings"]:
            geometry = feature["geometry"]
            if not geometry or geometry["type"] != "Polygon":
                continue
            ring = geometry["coordinates"][0]
            if len(ring) < 4 or ring[0] != ring[-1]:
                continue
            tags = feature.get("tags", {})
            try:
                height = float(tags["height"].removesuffix(" m")) if "height" in tags else 3 * float(tags.get("building:levels", 2))
            except (TypeError, ValueError):
                height = 6
            if not math.isfinite(height) or not 1 <= height <= 300:
                height = 6
            floor = [self.xyz({"lon": lon, "lat": lat}, 0) for lon, lat in ring[:-1]]
            roof = [(x, y, height) for x, y, _ in floor]
            for index, lower in enumerate(floor):
                previous = index - 1
                self.faces.append(((lower, floor[previous], roof[previous], roof[index]), "#999181"))
            self.faces.append((roof, "#d4c9b6"))

    def xyz(self, point, height):
        return (self.scale * (point["lon"] - self.origin["lon"]),
                111_195 * (point["lat"] - self.origin["lat"]), height)

    def frame(self, camera_name, actors, width, height):
        camera = self.cameras[camera_name]
        aircraft = actors.get(camera.get("aircraft_uid"))
        if "aircraft_uid" in camera and aircraft is None:
            image = Image.new("RGB", (width, height), "#272f35")
            ImageDraw.Draw(image).text((10, 10), "SIMULATED VIDEO | AIRCRAFT OFFLINE", fill="white")
            return image
        fields = aircraft["position"] if aircraft else camera["position"]
        hae = aircraft.get("metadata", {}).get("altitude_hae_m", self.ground + 40) if aircraft else camera["hae_m"]
        eye = self.xyz(fields, hae - self.ground)
        direction = unit(subtract(self.xyz(camera["look_at"], 0), eye))
        right = unit(cross(direction, (0, 0, 1))) if abs(direction[2]) < .99999 else (1, 0, 0)
        up = cross(right, direction)
        focal = width * .65

        def project(vertex):
            relative = subtract(vertex, eye)
            depth = dot(relative, direction)
            if depth <= .5:
                return None
            return (width / 2 + focal * dot(relative, right) / depth,
                    height / 2 - focal * dot(relative, up) / depth, depth)

        layers = []
        for vertices, fill in self.faces:
            projected = [project(vertex) for vertex in vertices]
            if all(projected):
                depth = sum(p[2] for p in projected) / len(projected)
                layers.append((depth, "building", [p[:2] for p in projected], fill))
        for actor in actors.values():
            if actor is aircraft or not actor.get("cot_type", "").startswith("a-f-G"):
                continue
            top = project(self.xyz(actor["position"], 1.8))
            bottom = project(self.xyz(actor["position"], 0))
            if top and bottom and 0 <= bottom[0] < width and 0 <= bottom[1] < height:
                radius = max(2, min(16, abs(bottom[1] - top[1]) / 4))
                left, right_edge = sorted((top[0], bottom[0]))
                upper, lower = sorted((top[1], bottom[1]))
                box = (left - radius, upper, right_edge + radius, lower + 1)
                layers.append((bottom[2], "actor", box, "#2295e9"))

        image = Image.new("RGB", (width, height), "#5c6b59")
        draw = ImageDraw.Draw(image)
        for _, kind, shape, fill in sorted(layers, reverse=True):
            if kind == "building":
                draw.polygon(shape, fill=fill, outline="#675f53")
            else:
                draw.rectangle(shape, fill=fill)
        draw.text((10, 10), f"SIMULATED VIDEO | {camera_name}", fill="white", stroke_width=1, stroke_fill="black")
        return image


def read_snapshot(path):
    state = json.loads(path.read_text())
    actors = {actor["uid"]: actor for unit in state["units"].values() for actor in active_members(unit)}
    return actors, bool(state.get("paused"))


def preview_actors(actors, age):
    # Fill the subsecond gaps for individual movements without writing state
    # or predicting a new route. Wait for the next snapshot after one second.
    return {
        uid: {**actor, "position": advance_path(deepcopy(actor["move"]), age)[0]}
        if actor.get("move") else actor for uid, actor in actors.items()
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", type=Path)
    parser.add_argument("state", type=Path, help="Read-only SimKeeper state JSON")
    parser.add_argument("camera")
    parser.add_argument("output", help="MP4 file or MediaMTX RTSP publish URL")
    parser.add_argument("--seconds", type=int, help="Omit for continuous RTSP")
    args = parser.parse_args()
    width, height, fps = 320, 180, 5
    rtsp = args.output.startswith(("rtsp://", "rtsps://"))
    if (args.seconds is not None and args.seconds < 1) or (not rtsp and not args.seconds):
        parser.error("Local recordings require positive --seconds")
    scene = Scene(json.loads(args.scene.read_text()))
    if args.camera not in scene.cameras:
        parser.error("Unknown camera")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if rtsp:
        command += ["-re"]
    command += ["-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
                "-framerate", str(fps), "-i", "pipe:0", "-c:v", "libx264", "-preset", "ultrafast",
                "-tune", "zerolatency", "-threads", "1", "-pix_fmt", "yuv420p", "-g", str(fps)]
    if rtsp:
        command += ["-f", "rtsp", "-rtsp_transport", "tcp"]
    command.append(args.output)
    with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
        version = object()
        frames = range(args.seconds * fps) if args.seconds else count()
        for _ in frames:
            try:
                mtime = args.state.stat().st_mtime_ns
            except FileNotFoundError:
                mtime = None
            changed = mtime != version
            if changed:
                actors, paused = read_snapshot(args.state) if mtime is not None else ({}, True)
                moving = not paused and any(actor.get("move") for actor in actors.values())
                version = mtime
            if changed or moving:
                age = max(0, min(1, time.time() - mtime / 1e9)) if moving else 0
                snapshot = preview_actors(actors, age) if moving else actors
                frame = scene.frame(args.camera, snapshot, width, height).tobytes()
            encoder.stdin.write(frame)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("Video encoder failed")


if __name__ == "__main__":
    main()
