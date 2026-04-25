import OpenEXR
import Imath
import numpy as np
import sys

def read_exr(filename):
    exr = OpenEXR.InputFile(filename)
    header = exr.header()

    dw = header['dataWindow']
    width = dw.max.x - dw.min.x + 1
    height = dw.max.y - dw.min.y + 1

    pt = Imath.PixelType(Imath.PixelType.FLOAT)

    # Read RGB channels (fallback if not present)
    channels = header['channels'].keys()

    def read_channel(name):
        if name in channels:
            return np.frombuffer(exr.channel(name, pt), dtype=np.float32)
        else:
            return np.zeros(width * height, dtype=np.float32)

    R = read_channel('R')
    G = read_channel('G')
    B = read_channel('B')

    img = np.stack([R, G, B], axis=-1)
    img = img.reshape((height, width, 3))

    return img, width, height


def write_exr(filename, img):
    height, width, _ = img.shape

    header = OpenEXR.Header(width, height)
    pt = Imath.PixelType(Imath.PixelType.FLOAT)

    header['channels'] = {
        'R': Imath.Channel(pt),
        'G': Imath.Channel(pt),
        'B': Imath.Channel(pt),
    }

    out = OpenEXR.OutputFile(filename, header)

    R = img[:, :, 0].astype(np.float32).tobytes()
    G = img[:, :, 1].astype(np.float32).tobytes()
    B = img[:, :, 2].astype(np.float32).tobytes()

    out.writePixels({'R': R, 'G': G, 'B': B})
    out.close()


def main():
    if len(sys.argv) != 4:
        print("Usage: python add_exr.py A.exr B.exr out.exr")
        return

    a_file, b_file, out_file = sys.argv[1:]

    imgA, wA, hA = read_exr(a_file)
    imgB, wB, hB = read_exr(b_file)

    if (wA != wB) or (hA != hB):
        raise ValueError("Images must have same dimensions")

    result = imgA + imgB  # pure additive blend

    write_exr(out_file, result)

    print(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
