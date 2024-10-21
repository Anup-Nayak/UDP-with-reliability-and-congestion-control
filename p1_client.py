import socket
import argparse

# Constants
MSS = 1400  # Maximum Segment Size

def receive_file(server_ip, server_port):
    """
    Receive the file from the server with reliability, handling packet loss
    and reordering.
    """
    client_socket = initialize_socket()

    # Initialize parameters
    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = "received_file.txt"

    # Open the file to write received data
    with open(output_file_path, 'wb') as file:
        establish_connection(client_socket, server_address)
        
        while True:
            try:
                packet, _ = receive_packet(client_socket)

                if check_end_signal(packet):
                    print("File transfer complete")
                    break

                seq_num, data = parse_packet(packet)
                
                if seq_num == expected_seq_num:
                    # Write data and send ACK
                    file.write(data)
                    expected_seq_num += len(data)
                    send_ack(client_socket, server_address, expected_seq_num)
                elif seq_num < expected_seq_num:
                    # Resend ACK for duplicate packets
                    send_ack(client_socket, server_address, expected_seq_num)
                else:
                    # Out-of-order packet handling
                    handle_out_of_order_packet(seq_num, data)

            except socket.timeout:
                print("Timeout: No data received, retrying...")

def initialize_socket():
    """
    Initialize the UDP socket with necessary configurations.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)  # Set timeout for server response
    return client_socket

def establish_connection(client_socket, server_address):
    """
    Establish the initial connection with the server by sending a request.
    """
    print("Sending connection request to server...")
    while True:
        try:
            client_socket.sendto(b"START", server_address)
            # Optionally wait for a server response
            return
        except socket.timeout:
            print("Retrying connection request...")

def receive_packet(client_socket):
    """
    Receive a packet from the server.
    """
    return client_socket.recvfrom(MSS + 100)

def parse_packet(packet):
    """
    Parse the packet to extract sequence number and data.
    """
    seq_num, data = packet.split(b'|', 1)
    return int(seq_num), data

def send_ack(client_socket, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = f"{seq_num}|ACK".encode()
    client_socket.sendto(ack_packet, server_address)
    print(f"Sent cumulative ACK for sequence number {seq_num}")

def check_end_signal(packet):
    """
    Check if the received packet is the end of the file transfer.
    """
    # Define logic to check for an end signal in the packet
    return b"END" in packet

def handle_out_of_order_packet(seq_num, data):
    """
    Handle packets that arrive out of order.
    """
    # Add logic to store and reorder out-of-order packets

# Command-line argument parsing
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()

# Run the client
receive_file(args.server_ip, args.server_port)
