# Third-party components for Music Relay

The project installs packages from their public package registries into a local `.venv`; it does not vendor their source or send audio to their maintainers.

| Component | Pinned version | Role | Source / documentation | Project license |
|---|---:|---|---|---|
| aiortc | 1.15.0 | WebRTC peer, ICE/DTLS/SRTP, Opus negotiation | [aiortc documentation](https://aiortc.readthedocs.io/) / [source](https://github.com/aiortc/aiortc) | BSD-3-Clause |
| SoundCard | 0.4.6 | Windows WASAPI loopback capture | [SoundCard documentation](https://soundcard.readthedocs.io/) / [source](https://github.com/bastibe/SoundCard) | BSD-3-Clause |
| aiohttp | 3.14.1 | Loopback-only sidecar HTTP control | [aiohttp documentation](https://docs.aiohttp.org/) / [source](https://github.com/aio-libs/aiohttp) | Apache-2.0 AND MIT |
| PyAV | 17.1.0 | Audio frames and codec interface used by aiortc | [PyAV documentation](https://pyav.org/docs/stable/) / [source](https://github.com/PyAV-Org/PyAV) | BSD-3-Clause |
| NumPy | 2.4.6 | Deterministic PCM conversion/downmix | [NumPy documentation](https://numpy.org/doc/) / [source](https://github.com/numpy/numpy) | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 (installed metadata) |

WebRTC Opus encoding is provided through aiortc/PyAV's installed media stack. Binary-wheel notices and bundled-library licenses remain authoritative for the exact artifacts installed on the PC; inspect `.venv` package metadata if redistributing the environment.

Windows WASAPI is an operating-system API. The browser implementation is the Galaxy A70's installed Chrome/WebView and is not bundled here.
