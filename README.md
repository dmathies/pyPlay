# pyPlay

[![GitHub License](https://img.shields.io/github/license/dmathies/pyPlay)](https://github.com/dmathies/pyPlay/blob/main/LICENSE)
[![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/dmathies/pyPlay/total)](https://github.com/dmathies/pyPlay/releases/latest)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A flexible and performant video player for theatre.

## Installation

Clone the repo:
```bash
git clone https://github.com/dmathies/pyPlay.git
cd pyPlay
```

Create a new virtual environment (optional):  
(Unix):
```bash
python3 -m venv pyPlay_venv
source pyPlay_venv/bin/activate
```
(Windows):
```ps1
python -m venv pyPlay_venv
pyPlay_venv\Scripts\activate
```

Install the required packages:
```bash
pip install requirements.txt
# If you intend on contributing to the project, get the dev-dependencies instead
# pip install requirements-dev.txt
```

Run pyPlay:
```bash
python main.py
```

### Building for Rasperry Pi

When building for Rasperry Pis, it's recommended to build `pyAv` yourself to take full advantage of the hardware acceleration available on the pi.

<!--TODO: Instructions for building pyAv for Pi-->

### Code format

Before committing any code to the repo, it's recommend to run it through the [black](https://github.com/psf/black) formatter.
```bash
# cd pyPlay
python -m black .
```

Static typing is also highly recommended, this can be checked using mypy:
```bash
# cd pyPlay
# Explicit package bases is required for, this option should be removed once the ArtNet library stuff is cleaned up
mypy . --explicit-package-bases --follow-untyped-imports
```
