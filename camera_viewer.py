import cv2
import socket
import struct
import pickle

def start_viewer():
    # Socket Create
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Input Server IP
    host_ip = input("Enter Camera Server IP: ") 
    port = 5000 # Must match server port

    try:
        client_socket.connect((host_ip, port))
    except ConnectionRefusedError:
        print(f"Connection failed on port {port}, trying 5001...")
        port = 5001
        try:
            client_socket.connect((host_ip, port))
        except:
             print("Could not connect. Check IP and ensure server is running.")
             return

    data = b""
    payload_size = struct.calcsize("Q") # Q: unsigned long long (8 bytes)

    print("Connected to server. Receiving video...")

    try:
        while True:
            # Retrieve message size
            while len(data) < payload_size:
                packet = client_socket.recv(4*1024) # 4K buffer
                if not packet: break
                data += packet
            
            if not data: break
            
            packed_msg_size = data[:payload_size]
            data = data[payload_size:]
            msg_size = struct.unpack("Q", packed_msg_size)[0]

            # Retrieve frame data based on size
            while len(data) < msg_size:
                data += client_socket.recv(4*1024)
            
            frame_data = data[:msg_size]
            data = data[msg_size:]

            # Decode frame
            frame = pickle.loads(frame_data)
            
            # Display
            cv2.imshow("RECEIVING VIDEO", frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client_socket.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    start_viewer()

