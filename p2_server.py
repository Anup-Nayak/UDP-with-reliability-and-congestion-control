import socket
import time
import argparse
import json,hashlib
import os,math
# Constants
MSS = 1400
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
        a ,b = 0.125 ,0.25
        rto,estimated_rtt,dev_rtt = 0.25,None,None
        cwnd ,sshthresh = MSS,2200
        retransmitted_packets = {}
        sent_packets = 0
        seq_num, last_ack_received = 0, -1
        unacked_packets = {}
        duplicate_ack_count = 0
        file_complete = False
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

                    if time.time() - timestamp > rto:
                    
                        sshthresh = max(MSS,cwnd/2)
                        cwnd = MSS
                        duplicate_ack_count = 0
                        # rto = min(60,2*rto)
                        # print(rto)
                        retransmitted_packets[first_unacked_seq_num] = 1
                        # Retransmit the first unacked packet
                        packet_to_retransmit,size_of_packt, _ = unacked_packets[first_unacked_seq_num]
                        server_socket.sendto(packet_to_retransmit, client_address)
                        print(f"Retransmitted packet {first_unacked_seq_num}")
                        # Update timestamp
                        unacked_packets[first_unacked_seq_num] = (packet_to_retransmit,size_of_packt, time.time())
            try:
                ack_packet, _ = receive_ack(server_socket) 
                ack_seq_num = get_seq_no_from_ack(ack_packet)
                fin_bit = get_fin_bit(ack_packet)
                
                if(cwnd<sshthresh):
                    # slow start phase
                    last_packet_received = math.ceil((ack_seq_num-MSS)/MSS)*MSS
                    if ack_seq_num > last_ack_received:
                        last_packet_received = math.ceil((ack_seq_num-MSS)/MSS)*MSS

                        if((last_packet_received in unacked_packets) and(last_packet_received not in retransmitted_packets) and(last_packet_received>=0)):
                            _,_,start_time = unacked_packets[last_packet_received]
                            sample_rtt = time.time()-start_time
                            if(not estimated_rtt):
                                estimated_rtt = sample_rtt
                                dev_rtt = sample_rtt/2 
                            else:
                                estimated_rtt = (1-a)*estimated_rtt+a*(sample_rtt)
                                dev_rtt = (1-b)*dev_rtt+b*abs(sample_rtt-estimated_rtt)
                            # rto = estimated_rtt+4*dev_rtt
                            # if(rto<1): rto = 1
                        
                        # Set the socket timeout to the new RTO value
                        # server_socket.settimeout(rto)
                        
                        # new ack in slow start phase
                        duplicate_ack_count = 0
                        cwnd += MSS
                        last_ack_received = ack_seq_num
                        sent_packets = slide_window(unacked_packets, ack_seq_num,sent_packets,retransmitted_packets)
                    elif(ack_seq_num<last_ack_received):
                        pass
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
                            cwnd=sshthresh+3*MSS
                            packet,size_of_packt,_ = unacked_packets[ack_seq_num]
                            unacked_packets[ack_seq_num] = (packet,size_of_packt,time.time())
                            server_socket.sendto(packet,client_address)

                elif(duplicate_ack_count==3):
                    # fast recovery phase 
                    last_packet_received = math.ceil((ack_seq_num-MSS)/MSS)*MSS
                    if ack_seq_num > last_ack_received:
                        # new ack in fast recovery phase
                        # update rto
                        if((last_packet_received in unacked_packets) and(last_packet_received not in retransmitted_packets) and(last_packet_received>=0)):
                            _,_,start_time = unacked_packets[last_packet_received]
                            sample_rtt = time.time()-start_time
                            if(not estimated_rtt):
                                estimated_rtt = sample_rtt
                                dev_rtt = sample_rtt/2 
                            else:
                                estimated_rtt = (1-a)*estimated_rtt+a*(sample_rtt)
                                dev_rtt = (1-b)*dev_rtt+b*abs(sample_rtt-estimated_rtt)
                            # rto = estimated_rtt+4*dev_rtt
                            # if(rto<1): rto = 1
                        
                        # Set the socket timeout to the new RTO value
                        # server_socket.settimeout(rto)
                        duplicate_ack_count = 0
                        cwnd = sshthresh
                        last_ack_received = ack_seq_num
                        sent_packets = slide_window(unacked_packets, ack_seq_num,sent_packets,retransmitted_packets)
                    elif(ack_seq_num<last_ack_received):
                        pass
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
                    last_packet_received = math.ceil((ack_seq_num-MSS)/MSS)*MSS
                    if ack_seq_num > last_ack_received:
                        # new ack in congeston avoidance phase
                        if((last_packet_received in unacked_packets) and(last_packet_received not in retransmitted_packets) and(last_packet_received>=0)):
                            _,_,start_time = unacked_packets[last_packet_received]
                            sample_rtt = time.time()-start_time
                            if(not estimated_rtt):
                                estimated_rtt = sample_rtt
                                dev_rtt = sample_rtt/2 
                            else:
                                estimated_rtt = (1-a)*estimated_rtt+a*(sample_rtt)
                                dev_rtt = (1-b)*dev_rtt+b*abs(sample_rtt-estimated_rtt)
                            # rto = estimated_rtt+4*dev_rtt
                            # if(rto<1): rto = 1
                        
                        # Set the socket timeout to the new RTO value
                        
                        # server_socket.settimeout(rto)
                        cwnd = cwnd+MSS*(MSS/cwnd)
                        duplicate_ack_count = 0 
                        last_ack_received = ack_seq_num
                        sent_packets = slide_window(unacked_packets, ack_seq_num,sent_packets,retransmitted_packets)
                    elif(ack_seq_num<last_ack_received):
                        pass
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
                            cwnd = sshthresh+3*MSS
                            packet,size_of_packt,_ = unacked_packets[ack_seq_num]
                            unacked_packets[ack_seq_num] = (packet,size_of_packt,time.time())
                            server_socket.sendto(packet,client_address)
                            
                # print(f"sent_packets:{sent_packets}, cwnd:{cwnd}, sshthresh:{sshthresh}")   
            except socket.timeout:
                pass
            # print(rto)
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
    server_socket.settimeout(0.25)
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

def slide_window(unacked_packets, ack_seq_num,sent_packets,retransmitted_packets):
    """
    Slide the window to remove acknowledged packets.
    """
    # Remove packets from the buffer that have been acknowledged
    for seq in list(unacked_packets.keys()):
        if seq < ack_seq_num:
            if(seq in retransmitted_packets):
                del retransmitted_packets[seq]
            _,size,_ = unacked_packets[seq]
            sent_packets -= size
            del unacked_packets[seq]
    return sent_packets

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, _,_) in unacked_packets.items():
        server_socket.sendto(packet, client_address)
        # # print(f"Retransmitted packet {seq_num}")

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