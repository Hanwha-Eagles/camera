import argparse
import asyncio
import json
import logging
import os
import ssl
import time
import cv2
import numpy as np
from aiohttp import web
import aiohttp
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
import base64

# Global variables
pcs = set()
latest_frame = None

class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """
    kind = "video"

    def __init__(self, track):
        super().__init__()  # don't forget this!
        self.track = track

    async def recv(self):
        global latest_frame
        frame = await self.track.recv()
        
        # Convert to numpy array
        img = frame.to_ndarray(format="bgr24")
        
        # Store for viewers without processing
        latest_frame = img
        if time.time() % 2 < 0.1: # Log occasionally
            print(f"Received frame: {img.shape}")

        # We return the original frame to the WebRTC connection usually,
        # but here we are just consuming it.
        # If we wanted to send the PROCESSED frame back to the phone, we would rebuild the VideoFrame.
        # But we only need to save it for the OTHER viewers.
        return frame

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
    ]))
    pc_id = "PeerConnection(%s)" % id(pc)
    pcs.add(pc)

    print(f"Created for {request.remote}")

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)
        elif pc.connectionState == "closed":
             pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        print(f"Track {track.kind} received")
        if track.kind == "video":
            local_video = VideoTransformTrack(track)
            # We don't necessarily need to addTrack back unless the phone wants to see itself (which it already does locally)
            # pc.addTrack(local_video) 

            # CRITICAL: We MUST consume frames from the track for it to be processed
            async def consume_track():
                print(f"Started consuming {track.kind} track")
                try:
                    while True:
                        frame = await local_video.recv()
                        # print("DEBUG: Frame received in consumer")
                except Exception as e:
                    print(f"Track {track.kind} consumption error: {e}")
                finally:
                    print(f"Stopped consuming {track.kind} track")

            asyncio.create_task(consume_track())

            @track.on("ended")
            async def on_ended():
                print(f"Track {track.kind} ended")

    # handle offer
    await pc.setRemoteDescription(offer)

    # answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

async def index(request):
    content = open(os.path.join(os.path.dirname(__file__), "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def broadcast(request):
    content = open(os.path.join(os.path.dirname(__file__), "broadcast.html"), "r").read()
    return web.Response(content_type="text/html", text=content)

async def websocket_handler(request):
    global latest_frame
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    print(f"WebSocket connection opened from {request.remote}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # Handle base64 encoded image
                data = json.loads(msg.data)
                image_data = data['image'].split(',')[1]
                nparr = np.frombuffer(base64.b64decode(image_data), np.uint8)
                latest_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                # Handle raw binary image (JPEG)
                nparr = np.frombuffer(msg.data, np.uint8)
                latest_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f"WebSocket connection closed with exception {ws.exception()}")
    finally:
        print(f"WebSocket connection closed from {request.remote}")

    return ws

async def video_feed(request):
    """
    MJPEG streaming route for viewers (simplest for multiple viewers).
    """
    async def stream_gen():
        while True:
            if latest_frame is not None:
                # Balanced quality = Good clarity + Reasonable bandwidth
                ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            else:
                await asyncio.sleep(0.1)
                continue
            await asyncio.sleep(0.05) # ~20 FPS for smoother motion

    response = web.StreamResponse()
    response.content_type = 'multipart/x-mixed-replace; boundary=frame'
    await response.prepare(request)

    try:
        async for data in stream_gen():
            await response.write(data)
    except (ConnectionResetError, aiohttp.ClientConnectionResetError):
        print(f"Viewer disconnected: {request.remote}")
    
    return response

async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    
    # clear resources
    pcs.clear()

def get_ip_address():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

if __name__ == "__main__":
    # Create SSL context
    # Use the certs we generated earlier
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    use_ssl = True
    try:
        ssl_context.load_cert_chain("cert.pem", "key.pem")
    except FileNotFoundError:
        print("Note: cert.pem or key.pem not found. Running in HTTP mode (suitable for tunneling).")
        ssl_context = None
        use_ssl = False

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/broadcast", broadcast)
    app.router.add_post("/offer", offer)
    app.router.add_get("/video_feed", video_feed)
    app.router.add_get("/ws", websocket_handler)
    
    # Static files (for client-side JS)
    # app.router.add_static('/static/', path='static', name='static')

    host_ip = get_ip_address()
    port = 5000
    
    protocol = "https" if use_ssl else "http"
    print("-" * 40)
    print(f"WebRTC Server Started! ({protocol.upper()} Mode)")
    print(f"1. BROADCASTER (Phone): {protocol}://{host_ip}:{port}/broadcast")
    print(f"2. VIEWER (PC): {protocol}://{host_ip}:{port}/")
    if not use_ssl:
        print("\n[!] Tunneling required for iPhone camera access.")
        print(f"[!] Run this in a NEW terminal: ssh -R 80:localhost:{port} nokey@localhost.run")
    print("-" * 40)

    web.run_app(app, access_log=None, host='0.0.0.0', port=port, ssl_context=ssl_context)
