import cv2
from flask import Flask, Response, render_template_string, request, jsonify
import socket
import time
import numpy as np
from ultralytics import YOLO

app = Flask(__name__)

# Camera settings
cap = None
use_browser_mode = False
latest_frame = None

def find_camera():
    global cap, use_browser_mode
    
    print("-" * 40)
    print("Select Video Source:")
    print("1. Local Webcam (Default)")
    print("2. IP Camera URL (e.g. from Phone App)")
    print("3. Phone Browser Boadcast (No App Needed)")
    choice = input("Enter choice (1, 2, or 3): ")
    
    if choice == '2':
        url = input("Enter Stream URL (e.g. http://19.168.0.x:8080/video): ")
        print(f"Connecting to {url} ...")
        cap = cv2.VideoCapture(url)
    elif choice == '3':
        print("Selected Browser Mode.")
        print("You will need to open the /broadcast page on your phone.")
        use_browser_mode = True
    else:
        print("Searching for local camera...")
        for i in range(5):
            print(f"Checking camera index {i}...")
            temp_cap = cv2.VideoCapture(i)
            if temp_cap.isOpened():
                ret, _ = temp_cap.read()
                if ret:
                    print(f" * Found working camera at index {i}")
                    cap = temp_cap
                    break
                else:
                    temp_cap.release()
            else:
                temp_cap.release()
    
    if not use_browser_mode and (cap is None or not cap.isOpened()):
        print("Warning: No camera found. Using dummy feed.")

def gen_frames():
    global cap, latest_frame
    # Load YOLO model
    print("Loading YOLO model...")
    model = YOLO('yolov8n.pt')
    print("YOLO model loaded.")

    while True:
        img = None
        
        if use_browser_mode:
            if latest_frame is not None:
                img = latest_frame.copy()
        
        elif cap is not None and cap.isOpened():
            success, frame = cap.read()
            if success:
                img = frame
        
        if img is None:
             # Dummy frame if no camera or no frame yet
             img = np.zeros((480, 640, 3), dtype=np.uint8)
             t = time.time()
             color = (int(t*50)%255, int(t*100)%255, int(t*150)%255)
             cv2.rectangle(img, (100, 100), (400, 400), color, -1)
             cv2.putText(img, "WAITING FOR CAMERA...", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
             time.sleep(0.1)
        else:
             # Run YOLO inference
            try:
                results = model(img)
                img = results[0].plot()
            except Exception as e:
                print(f"YOLO Error: {e}")

        ret, buffer = cv2.imencode('.jpg', img)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    return render_template_string("""
        <html>
        <head>
            <title>YOLO Camera Stream</title>
            <style>
                body { background-color: #222; color: white; text-align: center; font-family: sans-serif; }
                img { border: 5px solid #444; border-radius: 10px; max-width: 100%; height: auto; }
            </style>
        </head>
        <body>
            <h1>YOLO Live Stream</h1>
            <p>View this page on other computers to see the detected video.</p>
            <img src="/video_feed">
        </body>
        </html>
    """)

@app.route('/broadcast')
def broadcast():
    return render_template_string("""
        <html>
        <head>
            <title>Phone Camera Broadcaster</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { background-color: #000; color: white; text-align: center; font-family: sans-serif; overflow: hidden; }
                video { width: 100%; max-height: 80vh; transform: scaleX(-1); }
                button { padding: 15px 30px; font-size: 1.2em; margin: 20px; background: #007bff; color: white; border: none; border-radius: 5px; }
                #status { margin-top: 10px; }
            </style>
        </head>
        <body>
            <h2>Camera Broadcaster</h2>
            <video id="video" autoplay playsinline></video>
            <canvas id="canvas" style="display:none;"></canvas>
            <div id="status">Ready</div>
            <button onclick="startBroadcast()">Start Broadcasting</button>
            <script>
                const video = document.getElementById('video');
                const canvas = document.getElementById('canvas');
                const status = document.getElementById('status');
                const context = canvas.getContext('2d');
                let streaming = false;

                async function startBroadcast() {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ 
                            video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } } 
                        });
                        video.srcObject = stream;
                        streaming = true;
                        status.innerText = "Broadcasting...";
                        setInterval(sendFrame, 100); // 10 FPS
                    } catch (err) {
                        status.innerText = "Error: " + err;
                        console.error(err);
                    }
                }

                function sendFrame() {
                    if (!streaming) return;
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    context.drawImage(video, 0, 0, canvas.width, canvas.height);
                    
                    canvas.toBlob(blob => {
                        const formData = new FormData();
                        formData.append('frame', blob);
                        fetch('/upload_frame', { method: 'POST', body: formData });
                    }, 'image/jpeg', 0.5); // 0.5 Quality
                }
            </script>
        </body>
        </html>
    """)

@app.route('/upload_frame', methods=['POST'])
def upload_frame():
    global latest_frame
    file = request.files['frame']
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    latest_frame = frame
    return "OK"

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

import subprocess
import os

def generate_self_signed_cert(ip):
    print(f"Generating self-signed certificate for IP: {ip}...")
    try:
        # Generate private key
        subprocess.check_call(['openssl', 'genrsa', '-out', 'key.pem', '2048'])
        
        # Generate certificate
        # Critical: addext "subjectAltName = IP:<IP>" for Safari compatibility
        cmd = [
            'openssl', 'req', '-new', '-x509', '-key', 'key.pem',
            '-out', 'cert.pem', '-days', '365', '-nodes',
            '-subj', f'/CN={ip}',
            '-addext', f'subjectAltName=IP:{ip}'
        ]
        subprocess.check_call(cmd)
        print("Certificate generated successfully.")
        return 'cert.pem', 'key.pem'
    except Exception as e:
        print(f"Error generating certificate: {e}")
        print("Falling back to adhoc SSL (might not work on Safari).")
        return 'adhoc'

if __name__ == '__main__':
    find_camera()
    host_ip = get_ip_address()
    port = 5000
    
    print("-" * 40)
    print(f"Server started!")
    print(f"1. For VIEWING (PC): https://{host_ip}:{port}/")
    if use_browser_mode:
        print(f"2. For BROADCASTING (Phone): https://{host_ip}:{port}/broadcast")
    print("-" * 40)
    
    ssl_context = generate_self_signed_cert(host_ip)
    
    # Threaded must be False for simple YOLO safety usually, or use lock. 
    # But YOLOv8 is relatively thread safe. Keeping threaded=True for now.
    app.run(host='0.0.0.0', port=port, threaded=True, ssl_context=ssl_context)
