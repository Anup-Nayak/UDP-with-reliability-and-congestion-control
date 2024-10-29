import socket
import argparse
import time,json,hashlib

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
    buffer = {}
    with open(output_file_path, 'wb') as file:
        connection_established = False

        while True:
            try:
                if(not connection_established):
                    packet, _ = establish_connection(client_socket, server_address)
                    connection_established = True
                else:
                    packet, _ = receive_packet(client_socket)

                seq_num, fin_bit, data, correct = parse_packet(packet)

                if(correct):
                    
                    if seq_num == expected_seq_num:

                        if fin_bit and not len(buffer):
                            # send endACK and set timer
                            close_connection(expected_seq_num,server_address,client_socket)
                            return 

                        # Write data and send ACK
                        file.write(data)
                        expected_seq_num += len(data)
                        expected_seq_num, fin = handle_out_of_order_packet(buffer, expected_seq_num, file)
                        
                        # need to close connection
                        if fin:
                            # send endACK and set timer
                            close_connection(expected_seq_num,server_address,client_socket)
                            return
                        send_ack(client_socket, fin, server_address, expected_seq_num)

                        
                    elif seq_num < expected_seq_num:
                        # Resend ACK for duplicate packets
                        send_ack(client_socket,fin_bit, server_address, expected_seq_num)
                    else:
                        # Out-of-order packet handling
                        buffer[seq_num] = (data,fin_bit)
                        #print(f"Buffered out-of-order packet with sequence number {seq_num}")
                        send_ack(client_socket,0,server_address,expected_seq_num)
                
            except socket.timeout:
                pass
                #print("Timeout: No data received, retrying...")

def initialize_socket():
    """
    Initialize the UDP socket with necessary configurations.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(0.2)  # Set timeout for server response
    return client_socket

def establish_connection(client_socket, server_address):
    """
    Establish the initial connection with the server by sending a request.
    """
    print("Sending connection request to server...")
    
    client_socket.sendto(b"START", server_address)
    while True:
        try:
            data,a = client_socket.recvfrom(MSS+1000)
            print("Connection established")
            return data,a
            
        except socket.timeout:
            client_socket.sendto(b"START", server_address)
            print("Retrying connection request...")
            pass

def receive_packet(client_socket):
    """
    Receive a packet from the server.
    """
    packet,a = client_socket.recvfrom(MSS+1000)
    
    return packet,a

def parse_packet(packet):
    """
    Parse the packet to extract sequence number and data.
    """
    packet_json = packet.decode()
    correct = True

    packet_dict = json.loads(packet_json)

    received_checksum = packet_dict.pop("checksum", None)

    recalculated_checksum = hashlib.sha256(json.dumps(packet_dict).encode()).hexdigest()
    if received_checksum != recalculated_checksum:
        #print("Checksum does not match, packet may be corrupted.")
        correct = False

    seq_num = int(packet_dict["sequence_number"])
    fin_bit = packet_dict["fin_bit"]
    data = packet_dict["data"].encode()

    return seq_num, fin_bit, data, correct


def send_ack(client_socket,fin_bit, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = f"{seq_num}|{fin_bit}|ACK".encode()
    client_socket.sendto(ack_packet, server_address)
    #print(f"Sent cumulative ACK {fin_bit}for sequence number {seq_num}")

def check_end_signal(packet):
    """
    Check if the received packet is the end of the file transfer.
    """
    # Define logic to check for an end signal in the packet
    return b"END" in packet
def handle_out_of_order_packet(buffer,expected_seq_num, file):
    """
    Handle packets that arrive out of order.
    """
    fin = 0
    while expected_seq_num in buffer:
        data,fin_bit = buffer.pop(expected_seq_num)
        file.write(data)
        #print(f"Delivered buffered packet with sequence number {expected_seq_num}")
        expected_seq_num += len(data)
        if(fin_bit):
            fin = 1
    return expected_seq_num,fin


def close_connection(seq_num, server_address, client_socket):
    start = time.time()
    #print("Sending Close Signal...")
    ack_packet = f"{seq_num}|{1}|ACK".encode()
    while ((time.time() - start) < 0.25) :
        client_socket.sendto(ack_packet, server_address)
    return

# Command-line argument parsing
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
args = parser.parse_args()

# Run the client
start = time.time()
receive_file(args.server_ip, args.server_port)
end = time.time()
print(end-start)
