from pathlib import Path
import numpy as np

LUT_SIZE = 64
EXPOSURE = 1.0
GAMMA = 2.2
WHITE_POINT = 1.0

OUTPUT = Path("pyplay_aces_tonemap.cube")


def aces_film(x):
    a = 2.51
    b = 0.03
    c = 2.43
    d = 0.59
    e = 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0)


def tonemap(rgb):
    rgb = rgb * EXPOSURE

    # Optional white point normalization.
    if WHITE_POINT != 1.0:
        rgb = aces_film(rgb) / aces_film(np.array([WHITE_POINT]))[0]
    else:
        rgb = aces_film(rgb)

    rgb = np.clip(rgb, 0.0, 1.0)

    # Linear to display gamma.
    rgb = np.power(rgb, 1.0 / GAMMA)

    return np.clip(rgb, 0.0, 1.0)


with OUTPUT.open("w", encoding="utf-8") as f:
    f.write("# pyPlay ACES-style tonemap LUT\n")
    f.write(f"LUT_3D_SIZE {LUT_SIZE}\n")
    f.write("DOMAIN_MIN 0.0 0.0 0.0\n")
    f.write("DOMAIN_MAX 8.0 8.0 8.0\n")

    for b in range(LUT_SIZE):
        for g in range(LUT_SIZE):
            for r in range(LUT_SIZE):
                rgb = np.array([r, g, b], dtype=np.float32) / (LUT_SIZE - 1)

                # Expand LUT input range to HDR domain.
                rgb *= 8.0

                out = tonemap(rgb)
                f.write(f"{out[0]:.8f} {out[1]:.8f} {out[2]:.8f}\n")

print(f"Wrote {OUTPUT}")
