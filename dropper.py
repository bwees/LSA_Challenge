
from PyQt6.QtCore import pyqtSignal, QThread
import time
import serial
import serial.tools.list_ports

class DropperConnectionThread(QThread):
    connectionStatusSignal = pyqtSignal(bool, bool)

    def __init__(self, serial):
        super().__init__()
        self.sPort = serial
        self.ser = None

    def run(self):
        # open serial port
        self.ser = serial.Serial(self.sPort, 115200, timeout=1)

        while True:
            serStatus = False
            wirelessStatus = True

            if self.ser.isOpen():
                serStatus = True

                try:
                    ser_in = self.ser.readline().decode("utf-8").strip()
                    print(ser_in)
                    self.ser.flush()



                    if ser_in == "SEND 1":
                        wirelessStatus = False
                except serial.SerialException:
                    serStatus = False
                    wirelessStatus = False

            self.connectionStatusSignal.emit(serStatus, wirelessStatus)

            if not serStatus:
                break

    def left(self):
        if self.ser != None and self.ser.isOpen():
            self.ser.write(b"0")
            print(0)

    def right(self):
        if self.ser != None and self.ser.isOpen():
            self.ser.write(b"180")
            print(180)
    
    def center(self):
        if self.ser != None and self.ser.isOpen():
            self.ser.write(b"90")
            print(90)

    def disconnect(self):
        if self.ser != None and self.ser.isOpen():
            self.ser.close()
            self.connectionStatusSignal.emit(False, False)