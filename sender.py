"""
    Sample code for Sender (multi-threading)
    Python 3
    Usage: python3 sender.py receiver_port sender_port FileToSend.txt max_recv_win rto
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
import random  # for seqNo
import threading  # (Optional)threading will make the timer easily implemented

BUFFERSIZE = 1024
DATA = 0
ACK = 1
SYN = 2
FIN = 3
RESET = 4
MAXSEQNO = 65535
MSS = 1000

class ControlBlock:
    seqNo = 0
    sentPackets = []

class Sender:
    def __init__(self, sender_port: int, receiver_port: int, filename: str, max_win: int, rot: int) -> None:
        '''
        The Sender will be able to connect the Receiver via UDP
        :param sender_port: the UDP port number to be used by the sender to send PTP segments to the receiver
        :param receiver_port: the UDP port number on which receiver is expecting to receive PTP segments from the sender
        :param filename: the name of the text file that must be transferred from sender to receiver using your reliable transport protocol.
        :param max_win: the maximum window size in bytes for the sender window.
        :param rot: the value of the retransmission timer in milliseconds. This should be an unsigned integer.
        '''
        self.sender_port = int(sender_port)
        self.receiver_port = int(receiver_port)
        self.sender_address = ("127.0.0.1", self.sender_port)
        self.receiver_address = ("127.0.0.1", self.receiver_port)

        self.cb = ControlBlock()
        self.control_lock = threading.Lock()
        self.badACKS = []
        self.startTime = time.time()
        self.dataTransferred = 0
        self.dataSegments = 0
        self.retransmittedSegments = 0
        self.duplicateACKS = 0
        self.rot = rot
        self.fileName = filename
        self.max_win = int(max_win)
        self.acksRecieved = []

        random.seed()
        self.cb.seqNo = random.randint(0, MAXSEQNO)
        while (self.cb.seqNo > (MAXSEQNO - 100)):
            self.cb.seqNo = random.randint(0, MAXSEQNO)


        # init the UDP socket
        self.sender_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        self.sender_socket.bind(self.sender_address)

        #  (Optional) start the listening sub-thread first
        self._is_active = True  # for the multi-threading
        self.listenThread = threading.Thread(target=self.listen)
        self.listenThread.daemon = True
        self.listenThread.start()

        self.timeOutThread = threading.Thread(target=self.timeOut)
        self.timeOutThread.daemon = True
        self.timeOutThread.start()

    def ptp_open(self):
        #CLOSED -> SYNSENT: Open/send SYN
        time.sleep(0.5)
        self.startTime = time.time()
        self.sendPacket(bytearray(0), SYN)
        self.cb.seqNo += 1

    def ptp_send(self):
        '''(Multithread is used)send packets'''
        #copy data to send
        packetsToSend = []
        file = open(self.fileName, "rb")
        data = bytearray(file.read())
        self.dataTransferred = len(data)
        file.close()
        i = 0
        while i < len(data):
            packetsToSend.append(data[i:(i + MSS)])
            i+=MSS
        self.dataSegments = len(packetsToSend)
        #idle waiting for first response
        while True:
            self.control_lock.acquire()  
            if (len(self.cb.sentPackets) == 0):
                self.control_lock.release() 
                break
            if (len(self.cb.sentPackets) > 0 and self.cb.sentPackets[0][3] >= 3):
                self.sendPacket(bytearray(0), RESET)
                self.control_lock.release() 
                exit(0)
            self.control_lock.release() 
        #send rest of packets
        while self._is_active:
            self.control_lock.acquire()
            if len(packetsToSend) == 0 and len(self.cb.sentPackets) == 0:
                self.control_lock.release() 
                break
            if len(self.cb.sentPackets) < self.max_win/MSS and len(packetsToSend) > 0:
                self.sendPacket(packetsToSend.pop(0), DATA)
            self.control_lock.release() 


    def ptp_close(self):
        self.sendPacket(bytearray(0), FIN)
        while True:
            self.control_lock.acquire()
            if len(self.cb.sentPackets) == 0:
                self.control_lock.release()
                break
            self.control_lock.release()
        self._is_active = False  # close the sub-thread
        logging.info(f"Amount of (original) Data Transferred (in bytes) (excluding retransmissions):\t{self.dataTransferred}")
        logging.info(f"Number of Data Segments Sent (excluding retransmissions):\t{self.dataSegments}")
        logging.info(f"Number of Retransmitted Data Segments:\t{self.retransmittedSegments}")
        logging.info(f"Number of Duplicate Acknowledgements received:\t{self.duplicateACKS}")
        exit(0)


    def timeOut(self):
        '''(Multithread is used) handler for timeout events'''
        while self._is_active:
            self.control_lock.acquire() 
            if len(self.cb.sentPackets) > 0 and time.time() - self.cb.sentPackets[0][0] > float(self.rot):
                self.control_lock.release()
                self.retransmittedSegments += 1
                self.control_lock.acquire()
                self.sender_socket.sendto(self.cb.sentPackets[0][2], self.receiver_address)
                self.cb.sentPackets[0][0] = time.time()
                self.cb.sentPackets[0][3] += 1
                sendTime = round((time.time() - self.startTime) * 100, 2)
                if self.cb.sentPackets[0][5] == "SYN":
                    logging.info(f"snd\t{sendTime:8}\t{self.cb.sentPackets[0][5]:4}\t{self.cb.sentPackets[0][1] - 1:8}\t{self.cb.sentPackets[0][4]:4}")
                else:
                    logging.info(f"snd\t{sendTime:8}\t{self.cb.sentPackets[0][5]:4}\t{self.cb.sentPackets[0][1]:8}\t{self.cb.sentPackets[0][4]:4}")
                self.control_lock.release()
            else:
                self.control_lock.release()
            time.sleep(0.005)

    def listen(self):
        '''(Multithread is used)listen the response from receiver'''
        while self._is_active:  
            incoming_message, _ = self.sender_socket.recvfrom(BUFFERSIZE)
            rcvTime = round((time.time() - self.startTime) * 100, 2)
            logging.info(f"rcv\t{rcvTime:8}\tACK \t{str(self.seqNoConv(incoming_message)):8}\t{0:4}")
            self.control_lock.acquire()
            #clear older packets
            for packet in self.cb.sentPackets:
                if self.seqNoConv(incoming_message) < MSS:
                    if packet[1] > self.seqNoConv(incoming_message) + MSS * self.max_win/1000 :
                        self.cb.sentPackets.remove(packet)
                elif self.seqNoConv(incoming_message) + MSS * self.max_win/1000 > MAXSEQNO:
                    if packet[1] < self.seqNoConv(incoming_message) and packet[1] > (self.seqNoConv(incoming_message) + MSS * self.max_win/1000) % MAXSEQNO:
                        self.cb.sentPackets.remove(packet)
                else:
                    if packet[1] < self.seqNoConv(incoming_message):
                        self.cb.sentPackets.remove(packet)
            self.control_lock.release()
            #process new packet
            if (int(self.typeConv(incoming_message)) == ACK):
                if (self.seqNoConv(incoming_message) in self.acksRecieved):
                    self.duplicateACKS += 1
                else:
                    self.acksRecieved.append(self.seqNoConv(incoming_message))
                self.control_lock.acquire()
                if len(self.cb.sentPackets) > 0 and self.cb.sentPackets[0][1] == self.seqNoConv(incoming_message):
                    #if its next packet expected, remove it from packet array and see if any other packets have also been acked out of order
                    self.cb.sentPackets.pop(0)
                    self.control_lock.release()  
                    for i in range(0, len(self.badACKS)):
                        for ack in self.badACKS:
                            self.control_lock.acquire()
                            if len(self.cb.sentPackets) > 0 and self.cb.sentPackets[0][1] == self.seqNoConv(ack):
                                self.cb.sentPackets.pop(0)
                            self.control_lock.release() 
                    self.badACKS.clear()
                else:
                    #add it to the out of order packets and check if we need to resent old data segment
                    self.control_lock.release() 
                    if incoming_message in self.badACKS:
                        self.duplicateACKS += 1
                    self.badACKS.append(incoming_message)
                    if len(self.badACKS) >= 3 and self.badACKS[0] == self.badACKS[1] == self.badACKS[2]:
                        self.retransmittedSegments += 1
                        self.control_lock.acquire()
                        self.sender_socket.sendto(self.cb.sentPackets[0][2], self.receiver_address)
                        self.cb.sentPackets[0][0] = time.time()
                        self.cb.sentPackets[0][3] += 1
                        sendTime = round((time.time() - self.startTime) * 100, 2)
                        if self.cb.sentPackets[0][5] == "SYN":
                            logging.info(f"snd\t{sendTime:8}\t{self.cb.sentPackets[0][5]:4}\t{self.cb.sentPackets[0][1] - 1:8}\t{self.cb.sentPackets[0][4]:4}")
                        else:
                            logging.info(f"snd\t{sendTime:8}\t{self.cb.sentPackets[0][5]:4}\t{self.cb.sentPackets[0][1]:8}\t{self.cb.sentPackets[0][4]:4}")
                        self.control_lock.release()
                        self.badACKS.clear()
            

    def run(self):
        '''
        This function contain the main logic of the receiver
        '''
        self.ptp_open()
        self.ptp_send()
        self.ptp_close()

    def sendPacket(self, content: bytearray, type: int):
        formType = bytearray(type.to_bytes(2, "big"))
        formSeqNo = bytearray(self.cb.seqNo.to_bytes(2, "big")) 
        message = bytes(formType + formSeqNo + content)
        sendTime = round((time.time() - self.startTime) * 100, 2)
        if type == DATA: typestr = "DATA"
        if type == ACK: typestr = "ACK"
        if type == SYN: typestr = "SYN"
        if type == FIN: typestr = "FIN"
        if type == RESET: typestr = "RESET" 
        logging.info(f"snd\t{sendTime:8}\t{typestr:4}\t{self.cb.seqNo:8}\t{len(content):4}")
        self.sender_socket.sendto(message, self.receiver_address)
        self.cb.seqNo = (self.cb.seqNo + len(content)) % MAXSEQNO 
        if type == SYN or type == FIN: 
            self.cb.sentPackets.append([time.time(), self.cb.seqNo + 1, message, 0, len(content), typestr])      
        else: 
            self.cb.sentPackets.append([time.time(), self.cb.seqNo, message, 0, len(content), typestr]) 
    
    def typeConv(self, content: bytes) -> int:
        return int.from_bytes(bytes(bytearray(content)[:2]), "big")

    def seqNoConv(self, content: bytes) -> int:
        return int.from_bytes(bytes(bytearray(content)[2:4]), "big")

    def dataConv(self, content: bytes) -> bytes:
        return bytes(bytearray(content)[4:])

if __name__ == '__main__':
    # logging is useful for the log part: https://docs.python.org/3/library/logging.html
    logging.basicConfig(
        filename="Sender_log.txt",
        filemode="w",
        format="%(message)s",
        level=logging.NOTSET)

    if len(sys.argv) != 6:
        print(
            "\n===== Error usage, python3 sender.py sender_port receiver_port FileReceived.txt max_win rot ======\n")
        exit(0)

    sender = Sender(*sys.argv[1:])
    sender.run()