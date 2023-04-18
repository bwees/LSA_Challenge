
from PyQt6 import QtGui, uic
from PyQt6.QtWidgets import QWidget, QApplication, QTableWidgetItem, QLabel, QMessageBox
from PyQt6.QtGui import QPixmap
import cv2
import sys
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QUrl
import numpy as np
import time
from pyzbar import pyzbar
from PyQt6.QtWebEngineWidgets import QWebEngineView
import requests


class FoundQR():
    def __init__(self, data, img, qr):
        self.data = data
        self.img = img
        self.qr_obj = qr
        self.consecutiveNotSeen = 0

    def __eq__(self, other):
        return self.data == other.data

def list_camera_ports():
    """
    Test the ports and returns a tuple with the available ports and the ones that are working.
    """
    non_working_ports = []
    dev_port = 0
    working_ports = []
    available_ports = []
    while len(non_working_ports) < 6: # if there are more than 5 non working ports stop the testing. 
        camera = cv2.VideoCapture(dev_port)
        if not camera.isOpened():
            non_working_ports.append(dev_port)
            print("Port %s is not working." %dev_port)
        else:
            is_reading, img = camera.read()
            w = camera.get(3)
            h = camera.get(4)
            if is_reading:
                working_ports.append(dev_port)
            else:
                available_ports.append(dev_port)
        dev_port +=1
    return available_ports,working_ports,non_working_ports

# All CV Code will run in this thread to prevent GUI from freezing
class CVThread(QThread):
    live_signal = pyqtSignal(np.ndarray, str)
    found_code_signal = pyqtSignal(list)

    def __init__(self, source):
        super().__init__()
        self.source = source
        self.shouldRun = True

    def run(self):
        # capture from web cam
        cap = cv2.VideoCapture(self.source)

        # if the camera is not opened, exit
        if not cap.isOpened():
            #show error message in qt window
            msg = QMessageBox()
            msg.setText("Unable to Open Camera")
            msg.exec()

    
        while self.shouldRun:
            ret, image = cap.read()
            if ret:
                # convert to grayscale
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

                # threshold the image to get a binary image (black and white only)
                _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

                # dilate to combine adjacent code contours
                kernel = np.ones((5, 5), np.uint8)
                thresh = cv2.dilate(thresh, kernel, iterations=1)
                thresh = 255-thresh

                # find the contours of the code's outline
                contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

                # find boundign boexes for the contours (indicating a possible qr code)
                bboxes = []
                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    xmin, ymin, width, height = cv2.boundingRect(cnt)
                    extent = area / (width * height)
                    
                    # filter non-rectangular objects and small objects
                    if (area > 1000) and (abs(width-height) < 10):
                        bboxes.append((xmin, ymin, xmin + width, ymin + height))
                    
                out = image.copy()
                for xmin, ymin, xmax, ymax in bboxes:
                    out = cv2.rectangle(out, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)

                self.live_signal.emit(out, "detection")
                self.live_signal.emit(image, "live")

                if len(bboxes) < 10:

                    detected = []

                    # crop the image to the bounding box
                    for xmin, ymin, xmax, ymax in bboxes:
                        cropped = image[ymin:ymax, xmin:xmax]
                        # decode the qr codes
                        barcodes = pyzbar.decode(cropped)

                        for i in barcodes:
                            # draw a box around the qr code that was found with i.rect
                            detection = cv2.rectangle(image, (xmin+i.rect.left, ymin+i.rect.top), (xmin+i.rect.left+i.rect.width, ymin+i.rect.top+i.rect.height), (0, 0, 255), 2)
                            qr = FoundQR(i.data.decode("utf-8"), detection, i)
                            if qr not in detected:
                                detected.append(qr)

                    self.found_code_signal.emit(detected)


        blankImage = np.zeros((1080, 1920, 3), np.uint8)
        self.live_signal.emit(blankImage, "detection")
        self.live_signal.emit(blankImage, "live")

    def endCV(self):
        self.shouldRun = False

class DropperConnectionThread(QThread):
    connectionStatusSignal = pyqtSignal(bool)
    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        while True:
            try:
                requests.get(self.url, timeout=1)
                self.connectionStatusSignal.emit(True)
            except:
                self.connectionStatusSignal.emit(False)
            time.sleep(1)

class DropThread(QThread):
    def __init__(self, url, pos):
        super().__init__()
        self.url = url
        self.pos = pos

    def run(self):
        requests.get(self.url + "/?value=" + str(self.pos))
        time.sleep(1)
        requests.get(self.url + "/?value=90")



class Ui(QWidget):
    def __init__(self):
        super(Ui, self).__init__() # Call the inherited classes __init__ method
        uic.loadUi('interface.ui', self) # Load the .ui file
        self.show() # Show the GUI
        

        self.setWindowTitle("LSA Challenge")
        self.disply_width = 1280
        self.display_height = 600

        self.qrCodes = []
        self.previousCapture = None

        self.startCV.clicked.connect(self.startCVHandler)

        # connect the table selection changed signal to the on_qrTable_itemSelectionChanged slot
        self.qrTable.itemSelectionChanged.connect(self.on_qrTable_itemSelectionChanged)
        self.tabWidget.currentChanged.connect(self.onTabChange)

        # browser
        self.browser = QWebEngineView()
        self.browser.setUrl(QUrl("https://www.example.com"))
        self.browser.loadStarted.connect(self.loadStartedHandler)
        self.browser.loadProgress.connect(self.loadProgressHandler)
        self.browser.loadFinished.connect(self.loadFinishedHandler)


        #set the self.webBrowser QWidget to the browser
        self.browserLayout.addWidget(self.browser)
        self.browser.hide()
        self.browserProgressBar.hide()

        self.clearTableButton.clicked.connect(self.clearTable)

        self.dropperConnectionThread = DropperConnectionThread("http://10.0.1.9")
        self.dropperConnectionThread.connectionStatusSignal.connect(self.updateDropperConnectionStatus)
        self.dropperConnectionThread.start()

        self.dropLeftButton.clicked.connect(self.dropLeft)
        self.dropRightButton.clicked.connect(self.dropRight)

        # generate 1920x1080 black openCV image
        blankImage = np.zeros((1080, 1920, 3), np.uint8)

        self.update_image(blankImage, "live")
        self.update_image(blankImage, "detection")

    def startCVHandler(self):

        inText = self.cameraSource.text()
        if inText == "":
            self.cameraSource.setText("0")
            inText = "0"

        try:
            inText = int(inText)
        except:
            pass

        # check if there is already a thread running
        if hasattr(self, 'thread') and type(self.thread) == CVThread and self.thread.isRunning():
            self.startCV.setText("Start")

            # if there is, terminate it
            self.thread.endCV()
            # wait for the thread to finish
            self.thread.wait()

        else:

            # create the video capture thread
            self.thread = CVThread(inText)
            # connect its signal to the update_image slot
            self.thread.live_signal.connect(self.update_image)
            self.thread.found_code_signal.connect(self.update_detected)
            # start the thread
            self.thread.start()

            self.startCV.setText("Stop")

    def clearTable(self):
        self.qrTable.clearContents()
        self.qrTable.setRowCount(0)
        self.qrCodes = []
        self.browser.hide()
        self.browserHelp.show()

    def dropLeft(self):
        self.dThreadLeft = DropThread("http://10.0.1.9", 0)
        self.dThreadLeft.start()

    def dropRight(self):
        self.dThreadRight = DropThread("http://10.0.1.9", 180)
        self.dThreadRight.start()

    def loadProgressHandler(self, progress):
        self.browserProgressBar.setValue(progress)

    def loadStartedHandler(self):
        # if web browser is visible, show the progress bar
        if self.browser.isVisible():
            self.browserProgressBar.show()

    def loadFinishedHandler(self):
        self.browserProgressBar.setValue(0)

    @pyqtSlot(bool)
    def updateDropperConnectionStatus(self, status):
        if status:
            self.dropperStatus.setText("Dropper Connection: Connected")
            self.dropperStatus.setStyleSheet("color: green")
        else:
            self.dropperStatus.setText("Dropper Connection: Disconnected")
            self.dropperStatus.setStyleSheet("color: red")

    # slot for when tab changed
    def onTabChange(self):  
        # if there is a selection
        if self.qrTable.selectedItems():
            # get the selected row
            row = self.qrTable.selectedItems()[0].row()
            self.qrImage.setPixmap(self.convert_cv_qt(self.qrCodes[row].img, self.qrImage.width()))

            

    @pyqtSlot(np.ndarray, str)
    def update_image(self, cv_img, target):
        """Updates the image_label with a new opencv image"""
        qt_img = self.convert_cv_qt(cv_img, self.liveView.width())

        if target == "live":
            self.liveView.setPixmap(qt_img)

        elif target == "detection":
            self.thresholdedView.setPixmap(qt_img)

    def convert_cv_qt(self, cv_img, width):
        """Convert from an opencv image to QPixmap"""
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)

        #scale to fit width of liveView.width()
        p = convert_to_Qt_format.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        return QPixmap.fromImage(p)
        
    def updateTable(self):
        self.qrTable.setRowCount(len(self.qrCodes))
        for i, qr in enumerate(self.qrCodes):
            self.qrTable.setItem(i, 0, QTableWidgetItem("No"))
            self.qrTable.setItem(i, 1, QTableWidgetItem(qr.data))

    def update_current_detected(self, foundCodes):
        for i, code in enumerate(self.qrCodes):
            if code not in foundCodes:
                if code.consecutiveNotSeen > 10:
                    self.qrTable.setItem(i, 0, QTableWidgetItem("No"))
                else:
                    self.qrTable.setItem(i, 0, QTableWidgetItem("Yes"))
            else:
                code.consecutiveNotSeen = 0
                self.qrTable.setItem(i, 0, QTableWidgetItem("Yes"))

    @pyqtSlot(list)
    def update_detected(self, codes):
        
        if codes != self.previousCapture:
            self.previousCapture = codes
            
            for code in codes:
                if code not in self.qrCodes:
                    self.qrCodes.append(code)

            self.updateTable()
            self.update_current_detected(codes)

        for i, code in enumerate(self.qrCodes):
            if code not in codes:
                code.consecutiveNotSeen += 1
                if code.consecutiveNotSeen > 10:
                    self.update_current_detected(codes)
            else:
                code.consecutiveNotSeen = 0

    #when item is selected in qrTable
    def on_qrTable_itemSelectionChanged(self):
        if len(self.qrTable.selectedItems()) > 0:
            row = self.qrTable.selectedItems()[0].row()
            self.browser.setUrl(QUrl(self.qrCodes[row].data))
            self.browser.show()
            self.browserHelp.hide()
            self.qrImage.setPixmap(self.convert_cv_qt(self.qrCodes[row].img, self.qrImage.width()))




    


if __name__=="__main__":
    app = QApplication(sys.argv)
    a = Ui()
    sys.exit(app.exec())