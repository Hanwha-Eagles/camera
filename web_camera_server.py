import cv2
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import time

# Camera settings
cap = None

class CamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    if cap is None or not cap.isOpened():
                         # Dummy frame if no camera
                         import numpy as np
                         img = np.zeros((480, 640, 3), dtype=np.uint8)
                         t = time.time()
                         color = (int(t*50)%255, int(t*100)%255, int(t*150)%255)
                         cv2.rectangle(img, (100, 100), (400, 400), color, -1)
                         cv2.putText(img, "NO CAMERA - DUMMY FEED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    else:
                        ret, img = cap.read()
                        if not ret:
                            continue

                    # Encode to JPEG
                    ret, jpeg = cv2.imencode('.jpg', img)
                    if not ret:
                        continue
                    
                    frame = jpeg.tobytes()
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
                    
                    # Limit FPS slightly to save bandwidth
                    time.sleep(0.01)
            except Exception as e:
                pass
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <head>
                <title>P2P Camera Stream</title>
                <style>
                    body { background-color: #222; color: white; text-align: center; font-family: sans-serif; }
                    img { border: 5px solid #444; border-radius: 10px; max-width: 100%; height: auto; }
                </style>
                </head>
                <body>
                    <h1>Camera Live Stream</h1>
                    <img src="/video_feed" />
                </body>
                </html>
            """)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

def find_camera():
    global cap
    print("Searching for camera...")
    for i in range(5):
        print(f"Checking camera index {i}...")
        temp_cap = cv2.VideoCapture(i)
        if temp_cap.isOpened():
            ret, _ = temp_cap.read()
            if ret:
                print(f" * Found working camera at index {i}")
                cap = temp_cap
                return
            else:
                temp_cap.release()
        else:
            temp_cap.release()
    print("Warning: No camera found. Using dummy feed.")

def start_server():
    find_camera()
    
    # Get IP
    host_name = socket.gethostname()
    
    # Find real IP
    real_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(('10.254.254.254', 1))
        real_ip = s.getsockname()[0]
        s.close()
    except:
        pass

    port = 8000
    try:
        server = ThreadedHTTPServer(('0.0.0.0', port), CamHandler)
    except OSError:
        port = 8001
        server = ThreadedHTTPServer(('0.0.0.0', port), CamHandler)

    print("-" * 40)
    print(f"Server started!")
    print(f"Watch at: http://{real_ip}:{port}")
    print("-" * 40)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if cap: cap.release()
        server.server_close()

if __name__ == '__main__':
    start_server()
