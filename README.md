# pyPlay

`pyPlay` is a Python-based media playback and projection tool for qproj show files. It combines OpenGL rendering, cue playback, warp-mesh output mapping, OSC control, WebSocket control, Art-Net/DMX integration, DMX-controlled image planes, and optional NDI output.

This branch is the newer active version of the project and includes support for preconverted `.pyp` still-image assets in addition to existing media playback workflows.

## Features

- Plays `.qproj` cue files, defaulting to `Cues.qproj`
- OpenGL renderer with bloom and tonemapping
- DMX-driven image planes for lighting and media control workflows
- Single-screen debug mode and hidden-window NDI-only mode
- Output warp mesh support with versioned mesh saves
- OSC remote control and feedback
- WebSocket control channel
- HTTP static UI hosting
- Art-Net / DMX support
- Optional NDI output
- EXR-to-`.pyp` conversion for faster still-image workflows

## Repository Layout

- [main.py](/d:/Derek/GAOS/KB/pyPlay/main.py) - main runtime entry point
- [renderer.py](/d:/Derek/GAOS/KB/pyPlay/renderer.py) - rendering pipeline
- [cue_engine.py](/d:/Derek/GAOS/KB/pyPlay/cue_engine.py) - cue playback engine
- [qplayer_config.py](/d:/Derek/GAOS/KB/pyPlay/qplayer_config.py) - qproj loading and data model
- [osc_handler.py](/d:/Derek/GAOS/KB/pyPlay/osc_handler.py) - OSC receive/transmit handling
- [websocket_handler.py](/d:/Derek/GAOS/KB/pyPlay/websocket_handler.py) - WebSocket server
- [http_handler.py](/d:/Derek/GAOS/KB/pyPlay/http_handler.py) - static file server
- [scripts/convert_exr_to_pyp.py](/d:/Derek/GAOS/KB/pyPlay/scripts/convert_exr_to_pyp.py) - EXR conversion utility
- [pyPlayUI](/d:/Derek/GAOS/KB/pyPlay/pyPlayUI) - React/Vite UI project

## Requirements

- Python 3.10+ recommended
- An OpenGL-capable GPU/driver
- FFmpeg/PyAV-compatible media environment
- Network access for OSC / WebSocket / Art-Net use cases

Python dependencies are listed in [requirements.txt](/d:/Derek/GAOS/KB/pyPlay/requirements.txt).

## Installation

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

The current defaults avoid an HTTP/OSC port collision: HTTP serves on `8080` while OSC receives on `8000`.

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

The React UI lives in [pyPlayUI](/d:/Derek/GAOS/KB/pyPlay/pyPlayUI).

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

See [LICENSE](/d:/Derek/GAOS/KB/pyPlay/LICENSE) for the full license text.

## Notes

- The default cue file is `Cues.qproj` if none is provided.
- Mesh versions are written to `mesh_versions/`.
