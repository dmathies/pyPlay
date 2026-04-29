# pyPlay

A flexible and performant video player for theatre.

`pyPlay` is a Python-based media playback and projection tool using `qproj` show files from [QPlayer](https://github.com/space928/QPlayer). It combines OpenGL rendering, cue playback, warp-mesh output mapping, OSC control, WebSocket control, Art-Net/DMX integration, DMX-controlled image planes, and optional NDI output.

This branch is the newer active version of the project and includes support for preconverted `.pyp` still-image assets in addition to existing media playback workflows.

## Features

- Plays `.qproj` cue files, defaulting to `Cues.qproj`
- OpenGL renderer with bloom and tonemap post processing
- DMX-driven image planes for lighting and media control workflows
- Single or dual displays
- Independent perspective and mesh warping (for dual projector use)
    - versioned mesh warp save files
- Up to 4 framing shutters
    - Width, angle and softness setting for each shutter.
- OSC remote control and feedback
- HTTP UI for perspective, mesh warp, and framing.
- Art-Net / DMX support
- Optional NDI output
- EXR-to-`.pyp` conversion for faster still-image workflows

## Repository Layout

- [main.py](main.py) - main runtime entry point
- [renderer.py](renderer.py) - rendering pipeline
- [cue_engine.py](cue_engine.py) - cue playback engine
- [qplayer_config.py](qplayer_config.py) - qproj loading and data model
- [osc_handler.py](osc_handler.py) - OSC receive/transmit handling
- [websocket_handler.py](websocket_handler.py) - WebSocket server (for web UI)
- [http_handler.py](http_handler.py) - static file server
- [scripts/convert_exr_to_pyp.py](scripts/convert_exr_to_pyp.py) - EXR conversion utility
- [pyPlayUI](pyPlayUI) - React/Vite UI project

## Requirements

- Python 3.10+ recommended
- An OpenGL-capable GPU/driver
- FFmpeg/PyAV-compatible media environment
- Network access for OSC / WebSocket / Art-Net use cases

Python dependencies are listed in [requirements.txt](requirements.txt).

## Installation

Clone the repo:

```powershell
git clone https://github.com/dmathies/pyPlay.git
cd pyPlay
```

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If you want to work on the React UI as well:

```powershell
cd pyPlayUI
npm install
```

## Running pyPlay

Run the default show file:

```powershell
python main.py
```

Run a specific qproj file:

```powershell
python main.py Cues.qproj
```

Show command-line help:

```powershell
python main.py --help
```

## Main Runtime Options

- `--single-screen` render to a single debug window
- `--no-post` disable bloom and tonemapping
- `--profile` print periodic render timing data
- `--show-fps` enable on-screen FPS display
- `--warp-mesh NxM` set warp mesh resolution, for example `16x16`
- `--scene-scale S` set internal scene scale between `0.1` and `1.0`
- `--ndi` enable NDI output
- `--ndi-only` hidden-window NDI-only mode
- `--ndi-name NAME` set the NDI stream name
- `--ndi-size WxH` downscale NDI output before sending
- `--ndi-fps N` limit NDI send rate

Example:

```powershell
python main.py --single-screen --ndi --ndi-name "pyPlay Stage Feed" Cues.qproj
```

## Network Interfaces

By default the current code exposes:

- HTTP static UI on port `8080`
- WebSocket server on port `8765`
- OSC receive on port `8000`
- OSC transmit/broadcast on port `9000`

## DMX Interface

`pyPlay` can render image planes that are controlled from DMX/Art-Net data, making it useful for lighting-style playback and media layers that need to respond like fixtures.

Using the additive blending shaders, you can simlate DMX controlled lights in the rendered video.

## `.pyp` Still Images

This version supports `.pyp` assets as a preconverted still-image format. The `.pyp` assets are full HDR (half-float) format but are much faster to load than EXR.

Convert EXR files with:

```powershell
python scripts\convert_exr_to_pyp.py path\to\image.exr
```

Convert a directory recursively:

```powershell
python scripts\convert_exr_to_pyp.py assets\stills -r
```

Overwrite existing outputs:

```powershell
python scripts\convert_exr_to_pyp.py assets\stills -r --overwrite
```

## UI Development

The React UI lives in [pyPlayUI](pyPlayUI).

Start the UI dev server:

```powershell
cd pyPlayUI
npm run dev
```

Build the UI:

```powershell
cd pyPlayUI
npm run build
```

## License

`pyPlay` is licensed under the GNU General Public License v3.0.

See [LICENSE](LICENSE) for the full license text.

## Notes

- The default cue file is `Cues.qproj` if none is provided.
- Mesh versions are written to `mesh_versions/`.
