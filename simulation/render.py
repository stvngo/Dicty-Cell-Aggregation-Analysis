"""
Offline MP4 renders of the 3D lift (PyVista / VTK, offscreen, H.264).

Modes:
  surface    height field z = sum_i H_i g_i(x, y); the microscopy frame is draped
             on the ground and raised Gaussians blend into a colormap
  metaballs  1/e iso-surface of the 3D Gaussian density (domes that fuse when
             cells meet), standing on the textured frame

Each video frame shows the 3D render with the original 2D frame as an inset.
Needs the models from `python -m simulation.build`.

Examples:
  python -m simulation.render --source timeconvol --mode surface
  python -m simulation.render --source c1_inverted --kind spots --mode metaballs \\
    --frames 0:4000:4 --orbit 40
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import imageio.v2 as imageio
import matplotlib
import numpy as np
import pyvista as pv
from PIL import Image, ImageDraw, ImageFont

from .build import OUTPUT_DIR, load_model, normalization_scale
from .field import ISO_LEVEL, density_volume, height_field, reference_amplitude
from .frames import (
    FRAME_SIZE, SECONDS_PER_FRAME, SOURCES, flatten, frame_paths, load_frame, valid_mask,
)

Z_TARGET = 90.0   # world height of the tallest object at --z-scale 1 (matches the viewer)
HALF = FRAME_SIZE / 2
BG_BOTTOM, BG_TOP = "#06070b", "#171b27"
FONT_PATH = "/System/Library/Fonts/HelveticaNeue.ttc"


def font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except OSError:
        return ImageFont.load_default(size=size)


class FrameIndex:
    """Row ranges of each frame in a model table sorted by frame."""

    def __init__(self, df):
        self.df = df.sort_values("frame", kind="stable").reset_index(drop=True)
        frames = self.df["frame"].to_numpy()
        self.starts = np.searchsorted(frames, np.arange(frames.max() + 2))

    def __getitem__(self, f: int) -> dict[str, np.ndarray]:
        sl = slice(self.starts[f], self.starts[f + 1])
        return {c: self.df[c].to_numpy()[sl] for c in self.df.columns}


def grid_faces(n: int) -> np.ndarray:
    """Quad faces of an n x n vertex grid in VTK's flat [4, a, b, c, d, ...] layout,
    counter-clockwise seen from +z (rows run toward -y)."""
    idx = np.arange(n * n).reshape(n, n)
    a, b = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
    c, d = idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    return np.column_stack([np.full(a.size, 4), a, d, c, b]).ravel()


def floor_plane(img_rgb: np.ndarray, gain: float) -> tuple[pv.PolyData, pv.Texture]:
    # pv.Texture already maps image row 0 (the top) to +y, matching the blobs.
    plane = pv.Plane(center=(0, 0, -0.2), direction=(0, 0, 1), i_size=FRAME_SIZE, j_size=FRAME_SIZE)
    tex = pv.Texture(np.clip(img_rgb * gain, 0, 255).astype(np.uint8))
    return plane, tex


class Renderer:
    def __init__(self, args):
        self.args = args
        self.source = SOURCES[args.source]
        self.cmap = matplotlib.colormaps[args.colormap]
        self.floor_paths = frame_paths(self.source.viewer_dir)
        self.src_paths = frame_paths(self.source.frames_dir)
        self.valid = None

        df = load_model(args.source, args.kind)
        self.index = FrameIndex(df)
        self.ref = reference_amplitude(df, args.height)
        self.zs = Z_TARGET * args.z_scale

        w, h = args.size
        self.pl = pv.Plotter(off_screen=True, window_size=(w, h))
        self.pl.set_background(BG_BOTTOM, top=BG_TOP)
        self.pl.remove_all_lights()
        # Key light from the frame's top-right (the cAMP source side), cool fill opposite.
        self.pl.add_light(pv.Light(position=(420, 380, 520), focal_point=(0, 0, 0),
                                    color="#fff1df", intensity=1.0, light_type="scene light"))
        self.pl.add_light(pv.Light(position=(-420, -380, 260), focal_point=(0, 0, 0),
                                   color="#9ab8ff", intensity=0.35, light_type="scene light"))
        self.pl.add_light(pv.Light(light_type="headlight", intensity=0.18))
        if not args.no_ssao:
            self.pl.enable_ssao(radius=10, bias=0.5, kernel_size=128, blur=True)
        self.pl.enable_anti_aliasing("ssaa")

        slab = pv.Box(bounds=(-HALF - 6, HALF + 6, -HALF - 6, HALF + 6, -10, -0.6))
        self.pl.add_mesh(slab, color="#12141b", ambient=0.2, diffuse=0.6, specular=0.1)

        self.surface_mesh = None
        self.base_cam = np.array([0.0, -640.0, 520.0])
        self.focal = np.array([0.0, 30.0, 0.0])

    # -- per-frame content -------------------------------------------------

    def floor_image(self, f: int) -> np.ndarray:
        """Viewer frame as float RGB 0..255 (what the 2D inset shows)."""
        return np.asarray(Image.open(self.floor_paths[f]).convert("RGB"), dtype=np.float32)

    def ground_image(self, f: int, raw: np.ndarray) -> np.ndarray:
        """Texture for the 3D ground: the raw frame, or the background-flattened
        frame the Gaussians were fitted to (removes the c1 vignette and corners)."""
        if self.args.floor == "raw":
            return raw
        if self.valid is None:
            self.valid = valid_mask(self.source, self.src_paths)
            self.scale = normalization_scale(self.source, self.src_paths, self.valid, n_samples=16)
        flat = flatten(load_frame(self.source, self.src_paths[f]), self.source.flatten_radius) * self.valid
        gray = np.clip(flat / self.scale, 0, 1) * 255
        return np.repeat(gray[..., None], 3, axis=2).astype(np.float32)

    def surface(self, g, img: np.ndarray) -> None:
        n = self.args.grid
        t = height_field(g, shape=n, model=self.args.height, sigma_scale=self.args.sigma_scale) / self.ref
        cell = FRAME_SIZE / n
        if self.surface_mesh is None:
            coords = (np.arange(n) + 0.5) * cell - HALF
            xx, yy = np.meshgrid(coords, -coords)   # image row r -> world y = HALF - y
            pts = np.column_stack([xx.ravel(), yy.ravel(), np.zeros(n * n)])
            mesh = pv.PolyData(pts, faces=grid_faces(n))
            mesh.point_data["rgb"] = np.zeros((n * n, 3), np.uint8)
            # smooth_shading=True would render a normals-filtered copy that ignores
            # in-place updates; supply our own normals and Phong-interpolate instead.
            actor = self.pl.add_mesh(mesh, scalars="rgb", rgb=True, smooth_shading=False,
                                     ambient=0.22, diffuse=0.85, specular=0.35, specular_power=28,
                                     show_scalar_bar=False, name="surface")
            actor.prop.interpolation = "phong"
            self.surface_mesh = mesh
        z = t * self.zs
        mesh = self.surface_mesh
        mesh.points[:, 2] = z.ravel()

        # Ground shows the frame; raised Gaussians blend into the colormap.
        img_small = np.asarray(Image.fromarray(img.astype(np.uint8)).resize((n, n), Image.BILINEAR), np.float32)
        img_small *= self.args.image_gain
        cm = self.cmap(np.power(np.clip(t, 0, 1), 0.6))[..., :3] * 255
        blend = np.clip(np.power(t / 0.12, 0.8), 0, 1)[..., None]
        rgb = (1 - blend) * img_small + blend * cm
        mesh.point_data["rgb"][:] = np.clip(rgb, 0, 255).astype(np.uint8).reshape(-1, 3)

        gy, gx = np.gradient(z, cell)
        normals = np.dstack([-gx, gy, np.ones_like(z)])   # world y runs against image rows
        normals /= np.linalg.norm(normals, axis=2, keepdims=True)
        mesh.point_data["Normals"] = normals.reshape(-1, 3)
        mesh.point_data.active_normals_name = "Normals"
        mesh.GetPoints().Modified()
        mesh.Modified()

    def metaballs(self, g, img: np.ndarray) -> None:
        n, nz = self.args.vol, 56
        z_max = self.zs * 1.35 + 4
        vol, dz = density_volume(
            g, shape=n, nz=nz, z_max=z_max, model=self.args.height,
            sigma_scale=self.args.meta_sigma, z_scale=self.zs / self.ref,
        )
        cell = FRAME_SIZE / n
        grid = pv.ImageData(dimensions=(n, n, nz), spacing=(cell, cell, dz),
                            origin=(-HALF + cell / 2, -HALF + cell / 2, 0.0))
        grid.point_data["rho"] = vol[:, ::-1, :].ravel()   # flip rows: image top -> +y
        blobs = grid.contour([ISO_LEVEL], scalars="rho", method="flying_edges")
        plane, tex = floor_plane(img, self.args.image_gain * 0.9)
        self.pl.add_mesh(plane, texture=tex, ambient=0.35, diffuse=0.7, specular=0.0, name="floor")
        if blobs.n_points == 0:
            self.pl.remove_actor("blobs")
            return
        blobs = blobs.compute_normals(auto_orient_normals=False, consistent_normals=False, split_vertices=False)
        h = np.clip(blobs.points[:, 2] / self.zs, 0, 1)
        blobs.point_data["rgb"] = (self.cmap(np.power(h, 0.6))[:, :3] * 255).astype(np.uint8)
        self.pl.add_mesh(blobs, scalars="rgb", rgb=True, smooth_shading=True, ambient=0.2,
                         diffuse=0.85, specular=0.5, specular_power=40, show_scalar_bar=False, name="blobs")

    # -- composition -------------------------------------------------------

    def camera(self, progress: float) -> None:
        ang = np.radians(self.args.orbit * progress - self.args.orbit / 2)
        c, s = np.cos(ang), np.sin(ang)
        pos = np.array([c * self.base_cam[0] - s * self.base_cam[1],
                        s * self.base_cam[0] + c * self.base_cam[1], self.base_cam[2]])
        self.pl.camera_position = [tuple(pos), tuple(self.focal), (0, 0, 1)]
        self.pl.camera.view_angle = 34

    def shoot(self) -> np.ndarray:
        # Off-screen screenshot() returns the last rendered image; render first.
        self.pl.render()
        return self.pl.screenshot(return_img=True)

    def compose(self, render: np.ndarray, img: np.ndarray, f: int, count: int) -> np.ndarray:
        canvas = Image.fromarray(render)
        w, h = canvas.size
        inset = int(h * 0.25)
        pad = int(h * 0.03)
        f_title, f_small = font(int(h * 0.028)), font(int(h * 0.019))
        draw = ImageDraw.Draw(canvas)

        # 2D frame inset in the empty sky, top-right.
        thumb = Image.fromarray(img.astype(np.uint8)).resize((inset, inset), Image.LANCZOS)
        x0, y0 = w - pad - inset, pad
        draw.rectangle([x0 - 2, y0 - 2, x0 + inset + 1, y0 + inset + 1], outline=(90, 96, 112), width=2)
        canvas.paste(thumb, (x0, y0))
        draw.text((x0, y0 + inset + int(h * 0.008)), "2D frame", font=f_small, fill=(160, 166, 182))

        hours = f * SECONDS_PER_FRAME / 3600
        kind = "image Gaussians" if self.args.kind == "image" else "TrackMate spot Gaussians"
        line = int(h * 0.04)
        draw.text((pad, pad), "Dicty aggregation, lifted to 3D", font=f_title, fill=(236, 238, 245))
        draw.text((pad, pad + line),
                  f"{self.args.source} · {kind} · {self.args.mode} · height = {self.args.height}",
                  font=f_small, fill=(160, 166, 182))
        draw.text((pad, pad + 2 * line),
                  f"frame {f:4d}   t = {int(hours)}h {int((hours % 1) * 60):02d}m   {count} Gaussians",
                  font=f_small, fill=(214, 218, 230))
        # Progress bar along the bottom edge.
        frac = f / (len(self.floor_paths) - 1)
        draw.rectangle([0, h - 4, int(w * frac), h], fill=(255, 176, 74))
        return np.asarray(canvas)

    def run(self) -> Path:
        a = self.args
        start, stop, step = a.frames
        frames = list(range(start, min(stop, len(self.floor_paths)), step))
        out = a.out or OUTPUT_DIR / "renders" / f"{a.source}_{a.kind}_{a.mode}_{a.height}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(out, fps=a.fps, codec="libx264", quality=None, macro_block_size=8,
                                    pixelformat="yuv420p", ffmpeg_params=["-crf", str(a.crf), "-preset", "slow"])
        t0 = time.time()
        try:
            for k, f in enumerate(frames):
                g = self.index[f] if f + 1 < len(self.index.starts) else {"x": np.zeros(0)}
                img = self.floor_image(f)
                ground = self.ground_image(f, img)
                if a.mode == "surface":
                    self.surface(g, ground)
                else:
                    self.metaballs(g, ground)
                self.camera(k / max(1, len(frames) - 1))
                render = self.shoot()
                writer.append_data(self.compose(render, img, f, len(g["x"])))
                if (k + 1) % 100 == 0 or k == 0:
                    rate = (time.time() - t0) / (k + 1)
                    print(f"  {k + 1}/{len(frames)} frames  {rate:.2f}s/frame  eta {rate * (len(frames) - k - 1) / 60:.1f} min")
        finally:
            writer.close()
            self.pl.close()
        print(f"wrote {out}")
        return out


def parse_frames(s: str) -> tuple[int, int, int]:
    parts = [int(p) for p in s.split(":")]
    return (parts + [1])[:3] if len(parts) == 2 else tuple(parts)


def main() -> None:
    p = argparse.ArgumentParser(description="Render the 3D lift to MP4.")
    p.add_argument("--source", default="timeconvol", choices=list(SOURCES))
    p.add_argument("--kind", default="image", choices=["image", "spots"])
    p.add_argument("--mode", default="surface", choices=["surface", "metaballs"])
    p.add_argument("--height", default="mound", choices=["mound", "intensity", "mass"])
    p.add_argument("--frames", type=parse_frames, default=(0, 4000, 2), help="start:stop[:step]")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--size", type=lambda s: tuple(int(v) for v in s.split("x")), default=(1920, 1080))
    p.add_argument("--z-scale", type=float, default=1.0)
    p.add_argument("--sigma-scale", type=float, default=1.0, help="surface Gaussian width factor")
    p.add_argument("--meta-sigma", type=float, default=1.25, help="metaball footprint factor")
    p.add_argument("--grid", type=int, default=384, help="surface grid resolution")
    p.add_argument("--vol", type=int, default=192, help="metaball volume resolution (x/y)")
    p.add_argument("--image-gain", type=float, default=1.0)
    p.add_argument("--floor", default="flat", choices=["flat", "raw"],
                   help="ground texture: background-flattened frame (default) or the raw frame")
    p.add_argument("--colormap", default="inferno")
    p.add_argument("--orbit", type=float, default=0.0, help="total camera orbit over the video (deg)")
    p.add_argument("--crf", type=int, default=18)
    p.add_argument("--no-ssao", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    Renderer(p.parse_args()).run()


if __name__ == "__main__":
    main()
