import socket
import time
import argparse
import json,hashlib
import math,os
# Constants
MSS = 1400
# WINDOW_SIZE = 90  # Example window size for sliding window
TIMEOUT = 0.20  # Initial timeout
DUP_ACK_THRESHOLD = 3  # Threshold for fast retransmit
FILE_PATH = "file_to_send.txt"
RTT_FILE = "rtt.txt"

def send_file(server_ip, server_port, enable_fast_recovery):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    server_socket = initialize_socket(server_ip, server_port)

    print(f"Server listening on {server_ip}:{server_port}")

    client_address = await_client_connection(server_socket)
    
    with open(FILE_PATH, 'rb') as file:
        a = 0.7
        rtt = 0.2
        cwnd = 20
        
        file_size = os.path.getsize(FILE_PATH)
        seq_num, last_ack_received = 0, -1
        unacked_packets = {}
        duplicate_ack_count = 0
        file_complete = False
        while True:
            while (len(unacked_packets) < cwnd) and (not file_complete):
                chunk = file.read(MSS)
                fin_bit = 0
                if not chunk:
                    file_complete = True
                    fin_bit = 1
                
                packet = create_packet(seq_num,fin_bit,chunk)
                
                server_socket.sendto(packet, client_address)

                unacked_packets[seq_num] = (packet, time.time())
                # print(f"Sent packet {seq_num}")
                
                seq_num += len(chunk)
            
            if unacked_packets:
                    first_unacked_seq_num = next(iter(unacked_packets))
                    _, timestamp = unacked_packets[first_unacked_seq_num]

                    if time.time() - timestamp > TIMEOUT:
                    # Retransmit the first unacked packet
                        packet_to_retransmit, _ = unacked_packets[first_unacked_seq_num]
                        server_socket.sendto(packet_to_retransmit, client_address)
                        # print(f"Retransmitted packet {first_unacked_seq_num}")
                        unacked_packets[first_unacked_seq_num] = (packet_to_retransmit, time.time())
            try:
                ack_packet, _ = receive_ack(server_socket) 
                ack_seq_num = get_seq_no_from_ack(ack_packet)
                fin_bit = get_fin_bit(ack_packet)
                # recieved ack 
                # print(ack_seq_num,last_ack_received)
                if ack_seq_num > last_ack_received:
                    last_packet_recvd = math.ceil((ack_seq_num-MSS)/MSS)
                    if((last_ack_received>=0) and (last_ack_received in unacked_packets)):
                        _,start_time = unacked_packets[MSS*last_packet_recvd]
                        new_rtt = time.time()-start_time
                        rtt = a*rtt+(1-a)*new_rtt
                    duplicate_ack_count = 0
                    # print(f"Received ACK for {ack_seq_num}")
                    last_ack_received = ack_seq_num
                    slide_window(unacked_packets, ack_seq_num)
                else:
                    # endACK has been recieved
                    if(fin_bit == 1):
                        # print(f"FIN ACK recieved for Packet {ack_seq_num}, Final Seq Number  {final_seq_number}")
                        # print("Recieved Close Signal...")
                        return
                    duplicate_ack_count = handle_duplicate_ack(ack_seq_num, duplicate_ack_count, enable_fast_recovery,unacked_packets,server_socket,client_address)
                    
                
            except socket.timeout:
                pass
                # print("Socket Timeout...")
            
def check_for_end_signal(packet):
    """
    Check for END ACK from Client.
    """
    if(b"END" in packet):
        return True
    return False

def initialize_socket(server_ip, server_port):
    """
    Initialize the UDP socket for the server.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))
    server_socket.settimeout(TIMEOUT)
    return server_socket

def await_client_connection(server_socket):
    """
    Wait for the client to initiate a connection.
    """
    print("Waiting for client connection...")
    while True:
        try:
            data, client_address = server_socket.recvfrom(1024)
            print(f"Connection established with {client_address}")
            return client_address
        except socket.timeout:
            pass

def create_packet(seq_num,fin_bit, data):
    """
    Create a packet with sequence number and data.
    """
    packet = {
    "sequence_number": seq_num,
    "fin_bit": fin_bit,
    "data": data.decode()
    }

    packet_json = json.dumps(packet)

    checksum = hashlib.sha256(packet_json.encode()).hexdigest()
    packet["checksum"] = checksum

    return json.dumps(packet).encode()


def receive_ack(server_socket):
    """
    Receive an acknowledgment packet from the client.
    """
    ack, a = server_socket.recvfrom(1024)
    while(ack == b"START"):
        ack, a = server_socket.recvfrom(1024)
    return ack, a

def get_seq_no_from_ack(ack_packet):
    """
    Extract the sequence number from an ACK packet.
    """
    return int(ack_packet.decode().split('|')[0])

def get_fin_bit(ack_packet):
    _,fin_bit,_ = ack_packet.decode().split('|',2)
    return int(fin_bit)

def slide_window(unacked_packets, ack_seq_num):
    """
    Slide the window to remove acknowledged packets.
    """
    # Remove packets from the buffer that have been acknowledged
    for seq in list(unacked_packets.keys()):
        if seq < ack_seq_num:
            del unacked_packets[seq]

def handle_duplicate_ack(ack_seq_num, duplicate_ack_count, enable_fast_recovery,unacked_packets,server_socket,client_address):
    """
    Handle duplicate ACKs, and trigger fast recovery if necessary.
    """
    # print(f"Duplicate ACK received for {ack_seq_num},{duplicate_ack_count}")
    duplicate_ack_count += 1
    if enable_fast_recovery and (duplicate_ack_count >= DUP_ACK_THRESHOLD):
        duplicate_ack_count = 0
        packet,_ = unacked_packets[ack_seq_num]
        fast_recovery(packet,server_socket,client_address,ack_seq_num)
    return duplicate_ack_count

def send_end_signal(server_socket, client_address):
    """
    Send a signal indicating the end of the file transfer.
    """
    # print("Sending END signal")
    server_socket.sendto(b"END", client_address)

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, _) in unacked_packets.items():
        server_socket.sendto(packet, client_address)
        # print(f"Retransmitted packet {seq_num}")

def fast_recovery(packet,server_socket,client_address,ack_seq_num):
    """
    Perform fast recovery by retransmitting the necessary packet.
    """
    
    server_socket.sendto(packet,client_address)
    # print(f"Sent packet {ack_seq_num}")


# Command-line argument parsing
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('fast_recovery', type=int, help='Enable fast recovery')

args = parser.parse_args()
# # print(args.fast_recovery)

# print("server_file is called")
start = time.time()
send_file(args.server_ip, args.server_port, args.fast_recovery)
end = time.time()
print(end-start)