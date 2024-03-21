"""
    Sample code for Receiver
    Python 3
    Usage: python3 receiver.py receiver_port sender_port FileReceived.txt flp rlp
    coding: utf-8

    Notes:
        Try to run the server first with the command:
            python3 receiver_template.py 9000 10000 FileReceived.txt 1 1
        Then run the sender:
            python3 sender_template.py 11000 9000 FileToReceived.txt 1000 1

    Author: Rui Li (Tutor for COMP3331/9331)
"""
# here are the libs you may find it useful:
import datetime, time  # to calculate the time delta of packet transmission
import logging, sys  # to write the log
import socket  # Core lib, to send packet via UDP socket
from threading import Thread  # (Optional)threading will make the timer easily implemented
import random  # for flp and rlp function

BUFFERSIZE = 1024
DATA = 0
ACK = 1
SYN = 2
FIN = 3
RESET = 4
MAXSEQNO = 65535
MSS = 1000


class Receiver:
    def __init__(self, receiver_port: int, sender_port: int, filename: str, flp: float, rlp: float) -> None:
        '''
        The server will be able to receive the file from the sender via UDP
        :param receiver_port: the UDP port number to be used by the receiver to receive PTP segments from the sender.
        :param sender_port: the UDP port number to be used by the sender to send PTP segments to the receiver.
        :param filename: the name of the text file into which the text sent by the sender should be stored
        :param flp: forward loss probability, which is the probability that any segment in the forward direction (Data, FIN, SYN) is lost.
        :param rlp: reverse loss probability, which is the probability of a segment in the reverse direction (i.e., ACKs) being lost.

        '''
        self.address = "127.0.0.1"  # change it to 0.0.0.0 or public ipv4 address if want to test it between different computers
        self.receiver_port = int(receiver_port)
        self.sender_port = int(sender_port)
        self.server_address = (self.address, self.receiver_port)
        self.sender_address = (self.address, self.sender_port)

        random.seed()
        self.receiver_port = receiver_port
        self.sender_port = sender_port
        self.fileName = filename
        self.flp = float(flp)
        self.rlp = float(rlp)
        self.packetBuffer = []
        self.lastACKNo = 0  
        self.dataReceived = 0
        self.segmentsReceived = 0
        self.dupSegReceived = 0
        self.dataSegDropped = 0
        self.ackSegDropped = 0

        # init the UDP socket
        # define socket for the server side and bind address
        self.receiver_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.receiver_socket.bind(self.server_address)
        pass

    def run(self) -> None:
        '''
        This function contain the main logic of the receiver
        '''
        openCon = False
        firstrun = True
        while openCon == False:
            incoming_message, sender_address = self.receiver_socket.recvfrom(BUFFERSIZE)
            if firstrun: self.startTime = time.time()
            firstrun = False
            sendTime = round((time.time() - self.startTime) * 100, 2)
            type = self.typeConv(incoming_message)
            if type != SYN: exit(0)
            typestr = "SYN"
            seqNo = self.seqNoConv(incoming_message)
            data = self.dataConv(incoming_message)
            if random.random() > self.flp:            
                self.lastACKNo = (seqNo + len(data) + 1) % MAXSEQNO
                logging.info(f"rcv\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{0:4}")
                self.sendPacket(self.lastACKNo, ACK)
                openCon = True
            else:
                logging.info(f"drp\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{0:4}")
            file = open(self.fileName, "wb")
        
        while True:
            incoming_message, sender_address = self.receiver_socket.recvfrom(BUFFERSIZE)
            type = self.typeConv(incoming_message)
            if type == DATA: typestr = "DATA"
            if type == ACK: typestr = "ACK"
            if type == SYN: typestr = "SYN"
            if type == FIN: typestr = "FIN"
            if type == RESET: typestr = "RESET" 
            seqNo = self.seqNoConv(incoming_message)
            data = self.dataConv(incoming_message)
            sendTime = round((time.time() - self.startTime) * 100, 2)

            if random.random() > self.flp or type == RESET:
                if seqNo % MAXSEQNO == self.lastACKNo:
                    if type == DATA:
                        file.write(data)
                        self.segmentsReceived += 1
                        self.dataReceived += len(data)
                        self.lastACKNo = (seqNo + len(data)) % MAXSEQNO
                        self.processBuffer(file)    
                    elif type == FIN:
                        self.lastACKNo = (seqNo + len(data)) % MAXSEQNO
                        logging.info(f"rcv\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{len(data):4}")
                        self.sendPacket(((seqNo + len(data) + 1) % MAXSEQNO), ACK)
                        break
                    elif type == RESET or type == SYN:
                        logging.info(f"rcv\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{len(data):4}")
                        exit(0)
                        pass
                else:
                    if seqNo < self.lastACKNo or [seqNo, data, incoming_message] in self.packetBuffer:
                        self.dupSegReceived += 1
                    self.packetBuffer.append([seqNo, data, incoming_message])
                logging.info(f"rcv\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{len(data):4}")
                    
                # reply "ACK" once receive any message from sender
                self.sendPacket((self.lastACKNo), ACK)
            else:
                if type == DATA:
                    self.dataSegDropped += 1
                logging.info(f"drp\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{len(data):4}")
        #close
        endTime = time.time() + 2
        while (time.time() < endTime):
            self.receiver_socket.settimeout(endTime - time.time())
            try:
                incoming_message, sender_address = self.receiver_socket.recvfrom(BUFFERSIZE)
                type = self.typeConv(incoming_message)
                seqNo = self.seqNoConv(incoming_message)
                data = self.dataConv(incoming_message)
                sendTime = round((time.time() - self.startTime) * 100, 2)
                if random.random() > self.flp and type == FIN:
                    logging.info(f"rcv\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{len(data):4}")
                    self.sendPacket(((seqNo + len(data) + 1) % MAXSEQNO), ACK)
                else:
                    if type == DATA:
                        self.dataSegDropped += 1
                    logging.info(f"drp\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{0:4}")
            except:
                pass
        logging.info(f"Amount of (original) Data Received (in bytes) – does not include retransmitted data:\t{self.dataReceived}")
        logging.info(f"Number of (original) Data Segments Received – does not include retransmitted data:\t{self.segmentsReceived}")
        logging.info(f"Number of duplicate segments received (if any):\t{self.dupSegReceived}")
        logging.info(f"Number of Data segments dropped:\t{self.dataSegDropped}")
        logging.info(f"Number of ACK segments dropped:\t{self.ackSegDropped}")
        file.close()
        exit(0)

    def sendPacket(self, seqNo: int, type: int):
        formType = bytearray(type.to_bytes(2, "big"))
        formSeqNo = bytearray(seqNo.to_bytes(2, "big"))
        message = bytes(formType + formSeqNo)
        sendTime = round((time.time() - self.startTime) * 100, 2)
        if type == DATA: typestr = "DATA"
        if type == ACK: typestr = "ACK"
        if type == SYN: typestr = "SYN"
        if type == FIN: typestr = "FIN"
        if type == RESET: typestr = "RESET"
        if random.random() > self.rlp:
            logging.info(f"snd\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{0:4}")
            self.receiver_socket.sendto(message, self.sender_address)
        else :
            if type == ACK:
                self.ackSegDropped += 1
            logging.info(f"snd\t{sendTime:8}\t{typestr:4}\t{seqNo:8}\t{0:4}")

    def typeConv(self, content: bytes) -> int:
        return int.from_bytes(bytes(bytearray(content)[:2]), "big")

    def seqNoConv(self, content: bytes) -> int:
        return int.from_bytes(bytes(bytearray(content)[2:4]), "big")

    def dataConv(self, content: bytes) -> bytes:
        return bytes(bytearray(content)[4:])

    def processBuffer(self, file):
        for packet in self.packetBuffer:
            if (self.lastACKNo > packet[0]):
                self.packetBuffer.remove(packet)
                continue
            if (self.lastACKNo == packet[0]  or self.lastACKNo + 1 == packet[0]):
                file.write(packet[1])
                self.segmentsReceived += 1
                self.dataReceived += len(packet[1])
                self.lastACKNo = (packet[0] + len(packet[1])) % MAXSEQNO
                self.packetBuffer.remove(packet)
                self.processBuffer(file) 
                break;   

            


if __name__ == '__main__':
    # logging is useful for the log part: https://docs.python.org/3/library/logging.html
    logging.basicConfig(
        filename="Receiver_log.txt",
        filemode="w",
        format="%(message)s",
        level=logging.NOTSET)

    if len(sys.argv) != 6:
        print(
            "\n===== Error usage, python3 receiver.py receiver_port sender_port FileReceived.txt flp rlp ======\n")
        exit(0)

    receiver = Receiver(*sys.argv[1:])
    receiver.run()