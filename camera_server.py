import cv2
import socket
import struct
import pickle
import threading

def start_server():
    # Socket Create
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host_name = socket.gethostname()
    host_ip = socket.gethostbyname(host_name)
    port = 5000
    socket_address = ('0.0.0.0', port)

    # Socket Bind
    try:
        server_socket.bind(socket_address)
    except OSError:
        # Fallback if port is busy or other issue
        print(f"Port {port} busy, trying 5001")
        port = 5001
        socket_address = ('0.0.0.0', port)
        server_socket.bind(socket_address)

    # Socket Listen
    server_socket.listen(5)
    print("LISTENING AT:", socket_address)
    
    print("-" * 40)
    print("POSSIBLE IPs (Try these on the viewer):")
    try:
        # Get all IPs
        start_ip = socket.gethostbyname(host_name)
        print(f" * Maybe: {start_ip}")
        
        # Try to find other real LAN IPs
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            # doesn't even have to be reachable
            s.connect(('10.254.254.254', 1))
            IP = s.getsockname()[0]
            print(f" * RECOMMENDED: {IP}")
        except Exception:
            pass
        finally:
            s.close()
    except:
        pass
    print("-" * 40)

    # Camera setup
    cap = None
    use_dummy = False
    
    print("Searching for camera...")
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
    
    if cap is None:
        print("Warning: Could not open any camera (tried 0-4). Using dummy video feed for testing.")
        use_dummy = True
    
    import numpy as np
    import time

    while True:
        client_socket, addr = server_socket.accept()
        print('GOT CONNECTION FROM:', addr)
        
        try:
            if client_socket:
                while True:
                    if use_dummy:
                        # Create a dummy frame (bouncing rectangle or static color)
                        frame = np.zeros((480, 640, 3), dtype=np.uint8)
                        # Changing color over time
                        t = time.time()
                        color = (int(t*50)%255, int(t*100)%255, int(t*150)%255)
                        cv2.rectangle(frame, (100, 100), (400, 400), color, -1)
                        cv2.putText(frame, "NO CAMERA - DUMMY FEED", (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                        time.sleep(0.05) # ~20 FPS
                    else:
                        ret, frame = cap.read()
                        if not ret:
                            print("Error reading from camera.")
                            break
                    
                    # Serialize frame
                    a = pickle.dumps(frame)
                    
                    # Pack size + data
                    # Q: unsigned long long (8 bytes)
                    try:
                        message = struct.pack("Q", len(a)) + a
                        # Send
                        client_socket.sendall(message)
                    except struct.error:
                        print("Frame too large or error packing.")
                        break
                        
        except Exception as e:
            print(f"Connection lost or error: {e}")
            client_socket.close()
            continue

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    start_server()
