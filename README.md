# P2P Mobile Camera YOLO Stream (Tunnel Compatible)

This project allows you to stream your mobile phone's camera to a web server via a public tunnel (like `localhost.run`), perform real-time YOLO analysis, and view the results on any PC.

## Features
- **Tunnel Friendly**: Uses WebSockets for high-speed frame transfer, bypassing UDP limitations of standard SSH tunnels.
- **Real-time YOLO**: Server-side processing of video frames.
- **Mobile Optimized**: Responsive web interface for broadcasting from a phone.
- **High Speed**: Optimized for low latency (~20 FPS).

## Prerequisites
- Python 3.10+
- `aiohttp`, `aiortc`, `opencv-python`, `numpy`
- `ultralytics` (for YOLO)

## Installation
```bash
pip install aiohttp aiortc opencv-python numpy ultralytics
```

## Running the Project
1. Start the server:
   ```bash
   python3 webrtc_camera_server.py
   ```
2. Start the tunnel (in a new terminal):
   ```bash
   ssh -R 80:localhost:5000 nokey@localhost.run
   ```
3. Open the provided public URL on your phone and PC:
   - **Phone**: `https://<tunnel-url>/broadcast`
   - **PC**: `https://<tunnel-url>/`

## How it Works
1. The **Broadcaster** (Phone) captures camera frames using `getUserMedia`.
2. Frames are drawn to a hidden `<canvas>` and sent to the server via **WebSockets**.
3. The **Server** receives frames, optionally runs YOLO detection, and serves an MJPEG stream to the **Viewer**.
