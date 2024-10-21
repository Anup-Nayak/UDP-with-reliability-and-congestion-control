import socket
import time
import argparse

# Constants
MSS = 1400
WINDOW_SIZE = 5  # Example window size for sliding window
TIMEOUT = 1.0  # Initial timeout
DUP_ACK_THRESHOLD = 3  # Threshold for fast retransmit
FILE_PATH = "file_to_send.txt"

def send_file(server_ip, server_port, enable_fast_recovery):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    server_socket = initialize_socket(server_ip, server_port)

    print(f"Server listening on {server_ip}:{server_port}")

    client_address = await_client_connection(server_socket)
    
    with open(FILE_PATH, 'rb') as file:
        seq_num, window_base, last_ack_received = 0, 0, -1
        unacked_packets = {}
        duplicate_ack_count = 0

        while True:
            while len(unacked_packets) < WINDOW_SIZE:
                chunk = file.read(MSS)
                if not chunk:
                    send_end_signal(server_socket, client_address)
                    break
                
                packet = create_packet(seq_num, chunk)
                server_socket.sendto(packet, client_address)
                unacked_packets[seq_num] = (packet, time.time())
                print(f"Sent packet {seq_num}")
                seq_num += len(chunk)

            try:
                ack_packet, _ = receive_ack(server_socket)
                ack_seq_num = get_seq_no_from_ack(ack_packet)

                if ack_seq_num > last_ack_received:
                    print(f"Received ACK for {ack_seq_num}")
                    last_ack_received = ack_seq_num
                    slide_window(unacked_packets, ack_seq_num)
                else:
                    handle_duplicate_ack(ack_seq_num, duplicate_ack_count, enable_fast_recovery)

            except socket.timeout:
                retransmit_unacked_packets(server_socket, client_address, unacked_packets)

def initialize_socket(server_ip, server_port):
    """
    Initialize the UDP socket for the server.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))
    return server_socket

def await_client_connection(server_socket):
    """
    Wait for the client to initiate a connection.
    """
    print("Waiting for client connection...")
    data, client_address = server_socket.recvfrom(1024)
    print(f"Connection established with {client_address}")
    return client_address

def create_packet(seq_num, data):
    """
    Create a packet with sequence number and data.
    """
    return f"{seq_num}|".encode() + data

def receive_ack(server_socket):
    """
    Receive an acknowledgment packet from the client.
    """
    return server_socket.recvfrom(1024)

def get_seq_no_from_ack(ack_packet):
    """
    Extract the sequence number from an ACK packet.
    """
    return int(ack_packet.decode().split('|')[0])

def slide_window(unacked_packets, ack_seq_num):
    """
    Slide the window to remove acknowledged packets.
    """
    # Remove packets from the buffer that have been acknowledged
    for seq in list(unacked_packets.keys()):
        if seq < ack_seq_num:
            del unacked_packets[seq]

def handle_duplicate_ack(ack_seq_num, duplicate_ack_count, enable_fast_recovery):
    """
    Handle duplicate ACKs, and trigger fast recovery if necessary.
    """
    print(f"Duplicate ACK received for {ack_seq_num}")
    duplicate_ack_count += 1
    if enable_fast_recovery and duplicate_ack_count >= DUP_ACK_THRESHOLD:
        fast_recovery()

def send_end_signal(server_socket, client_address):
    """
    Send a signal indicating the end of the file transfer.
    """
    server_socket.sendto(b"END", client_address)

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, _) in unacked_packets.items():
        server_socket.sendto(packet, client_address)
        print(f"Retransmitted packet {seq_num}")

def fast_recovery():
    """
    Perform fast recovery by retransmitting the necessary packet.
    """
    # Add logic to retransmit packet after 3 duplicate ACKs

# Command-line argument parsing
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('fast_recovery', type=int, help='Enable fast recovery')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port, args.fast_recovery)
