import socket
import time
import argparse
import json,hashlib
import os
# Constants
MSS = 1400
TIMEOUT = 0.10  # Initial timeout
DUP_ACK_THRESHOLD = 3  # Threshold for fast retransmit
FILE_PATH = "file.txt"
def send_file(server_ip, server_port):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    server_socket = initialize_socket(server_ip, server_port)

    # print(f"Server listening on {server_ip}:{server_port}")

    client_address = await_client_connection(server_socket)
    
    with open(FILE_PATH, 'rb') as file: 
        cwnd ,sshthresh = MSS,2200
        sent_packets = 0
        seq_num, last_ack_received = 0, -1
        unacked_packets = {}
        duplicate_ack_count = 0
        file_complete = False
        last_seq_number = os.path.getsize(FILE_PATH)/MSS
        # print(last_seq_number)
        while True:
            while (sent_packets < cwnd) and (not file_complete):
                size_of_packet = 0
                chunk = file.read(MSS)
                fin_bit = 0
                if not chunk:
                    file_complete = True
                    fin_bit = 1
                    size_of_packet = 0
                else:
                    size_of_packet = MSS
                
                packet = create_packet(seq_num,fin_bit,chunk)
                sent_packets += size_of_packet
                server_socket.sendto(packet, client_address)
                unacked_packets[seq_num] = (packet,size_of_packet, time.time())
                # print(f"Sent packet {seq_num}")    
                seq_num += len(chunk)
            
            if unacked_packets:
                    first_unacked_seq_num = next(iter(unacked_packets))
                    _,_, timestamp = unacked_packets[first_unacked_seq_num]

                    if time.time() - timestamp > TIMEOUT:
                        sshthresh = max(MSS,cwnd/2)
                        cwnd = MSS
                        duplicate_ack_count = 0
                        # Retransmit the first unacked packet
                        packet_to_retransmit,size_of_packt, _ = unacked_packets[first_unacked_seq_num]
                        server_socket.sendto(packet_to_retransmit, client_address)
                        # print(f"Retransmitted packet {first_unacked_seq_num}")
                        # Update timestamp
                        unacked_packets[first_unacked_seq_num] = (packet_to_retransmit,size_of_packt, time.time())
            try:
                ack_packet, _ = receive_ack(server_socket) 
                ack_seq_num = get_seq_no_from_ack(ack_packet)
                fin_bit = get_fin_bit(ack_packet)
                
                if(cwnd<sshthresh):
                    # slow start phase
                    if ack_seq_num > last_ack_received:
                        # new ack in slow start phase
                        duplicate_ack_count = 0
                        cwnd += MSS
                        last_ack_received = ack_seq_num
                        sent_packets = slide_window(unacked_packets, ack_seq_num,sent_packets)
                    else:
                        # duplicate ack in slow start
                        duplicate_ack_count+=1
                        # endACK has been recieved
                        if(fin_bit == 1):
                            # print(f"FIN ACK recieved for Packet {ack_seq_num}, Final Seq Number  {final_seq_number}")
                            print("Recieved Close Signal...")
                            print(cwnd,sshthresh)
                            return
                        if(duplicate_ack_count==3):
                            # retransmit missing segment and enter fast recovery phase
                            sshthresh = cwnd/2
                            cwnd+=sshthresh+3*MSS
                            packet,size_of_packt,_ = unacked_packets[ack_seq_num]
                            unacked_packets[ack_seq_num] = (packet,size_of_packt,time.time())
                            server_socket.sendto(packet,client_address)

                elif(duplicate_ack_count==3):
                    # fast recovery phase 
                    if ack_seq_num > last_ack_received:
                        # new ack in fast recovery phase
                        duplicate_ack_count = 0
                        cwnd = sshthresh
                        last_ack_received = ack_seq_num
                        sent_packets = slide_window(unacked_packets, ack_seq_num,sent_packets)
                    else:
                        # duplicate ack in fast recovery
                        cwnd+=MSS
                        # endACK has been recieved
                        if(fin_bit == 1):
                            # print(f"FIN ACK recieved for Packet {ack_seq_num}, Final Seq Number  {final_seq_number}")
                            print("Recieved Close Signal...")
                            print(cwnd,sshthresh)
                            return
                else:
                    # congeston avoidance
                    if ack_seq_num > last_ack_received:
                        # new ack in congeston avoidance phase
                        cwnd = cwnd+MSS*(MSS/cwnd)
                        duplicate_ack_count = 0 
                        last_ack_received = ack_seq_num
                        sent_packets = slide_window(unacked_packets, ack_seq_num,sent_packets)
                    else:
                        # duplicate ack in  congestion avoidance
                        duplicate_ack_count+=1
                        if(fin_bit == 1):
                            # endACK has been recieved
                            # print(f"FIN ACK recieved for Packet {ack_seq_num}, Final Seq Number  {final_seq_number}")
                            print("Recieved Close Signal...")
                            print(cwnd,sshthresh)
                            return
                        if(duplicate_ack_count==3):
                            # retransmit missing segment and enter fast recovery phase
                            sshthresh = cwnd/2
                            cwnd+=sshthresh+3*MSS
                            packet,size_of_packt,_ = unacked_packets[ack_seq_num]
                            unacked_packets[ack_seq_num] = (packet,size_of_packt,time.time())
                            server_socket.sendto(packet,client_address)
                            
                # print(f"sent_packets:{sent_packets}, cwnd:{cwnd}, sshthresh:{sshthresh}")   

            except socket.timeout:
                pass
                # # print(cwnd,sshthresh,"Socket Timeout...")
            
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
    # print("Waiting for client connection...")
    connect_establ = False
    while( not connect_establ):
        try:
            data, client_address = server_socket.recvfrom(1024)
            if(data == (b'START')):
                start = time.time()
                while(time.time()-start < 0.25):
                    server_socket.sendto(b"START_ACK",client_address)

                connect_establ = True
                # print(f"Connection established with {client_address}")
                return client_address
        except socket.timeout:
            # print("Socket Timeout...")
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
    return server_socket.recvfrom(1024)

def get_seq_no_from_ack(ack_packet):
    """
    Extract the sequence number from an ACK packet.
    """
    return int(ack_packet.decode().split('|')[0])

def get_fin_bit(ack_packet):
    _,fin_bit,_ = ack_packet.decode().split('|',2)
    return int(fin_bit)

def slide_window(unacked_packets, ack_seq_num,sent_packets):
    """
    Slide the window to remove acknowledged packets.
    """
    # Remove packets from the buffer that have been acknowledged
    for seq in list(unacked_packets.keys()):
        if seq < ack_seq_num:
            _,size,_ = unacked_packets[seq]
            sent_packets -= size
            del unacked_packets[seq]
    return sent_packets

def handle_duplicate_ack(ack_seq_num, duplicate_ack_count,unacked_packets,server_socket,client_address):
    """
    Handle duplicate ACKs, and trigger fast recovery if necessary.
    """
    # # print(f"Duplicate ACK received for {ack_seq_num},{duplicate_ack_count}")
    duplicate_ack_count += 1
    if (duplicate_ack_count >= DUP_ACK_THRESHOLD):
        duplicate_ack_count = 0
        packet,_ = unacked_packets[ack_seq_num]
        fast_recovery(packet,server_socket,client_address,ack_seq_num,unacked_packets)
    return duplicate_ack_count

def send_end_signal(server_socket, client_address):
    """
    Send a signal indicating the end of the file transfer.
    """
    # # print("Sending END signal")
    server_socket.sendto(b"END", client_address)

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, _) in unacked_packets.items():
        server_socket.sendto(packet, client_address)
        # # print(f"Retransmitted packet {seq_num}")

def fast_recovery(packet,server_socket,client_address,ack_seq_num,unacked_packets):
    """
    Perform fast recovery by retransmitting the necessary packet.
    """
    unacked_packets[ack_seq_num] = (packet,time.time())
    
    server_socket.sendto(packet,client_address)
    # # print(f"Sent packet {ack_seq_num}")


# Command-line argument parsing
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()
# # # print(args.fast_recovery)
# # # print("server_file is called")
# # # print(math.ceil(-0.4))
# Run the server
start = time.time()
send_file(args.server_ip, args.server_port)
end= time.time()
print(end-start)