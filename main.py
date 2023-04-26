
from PyQt6 import QtGui, uic
from PyQt6.QtWidgets import QWidget, QApplication, QTableWidgetItem, QMessageBox
from PyQt6.QtGui import QPixmap, QDesktopServices
import cv2
import sys
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QUrl
import numpy as np
import time
from pyzbar import pyzbar
from PyQt6.QtWebEngineWidgets import QWebEngineView
import requests
import serial
import serial.tools.list_ports
from cvthread import CVThread
from dropper import DropperConnectionThread


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
        #qr table double click
        self.qrTable.doubleClicked.connect(self.on_qrTable_doubleClicked)
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

        self.dropLeftButton.clicked.connect(self.dropLeft)
        self.dropRightButton.clicked.connect(self.dropRight)
        self.dropCenterButton.clicked.connect(self.dropCenter)

        # generate 1920x1080 black openCV image
        blankImage = np.zeros((1080, 1920, 3), np.uint8)

        self.update_image(blankImage, "live")
        self.update_image(blankImage, "detection")

        # get live mouse position on the live image
        self.liveView.mouseMoveEvent = self.qrDetectMouse
        self.liveView.setMouseTracking(True)

        #get updates from slider named "bbox_slider"
        self.bbox_slider.valueChanged.connect(self.bbox_slider_changed)

        # disable window resizing
        self.setFixedSize(self.size())

        self.openinbrowser.clicked.connect(self.open_in_browser)

        self.refreshSerial.clicked.connect(self.update_serial_ports)
        self.update_serial_ports()

        self.connectSerial.clicked.connect(self.connect_disconnect_dropper)

        self.dropper = None
        self.dropperStatus.setText("Wireless: Disconnected")
        #set red text
        self.dropperStatus.setStyleSheet("QLabel { color : red; }")

    def qrDetectMouse(self, event):
        if hasattr(self, 'cv_thread') and type(self.cv_thread) == CVThread and self.cv_thread.isRunning():
            self.cv_thread.update_mouse(event.pos().x(), event.pos().y())
    
    def bbox_slider_changed(self):
        if hasattr(self, 'cv_thread') and type(self.cv_thread) == CVThread and self.cv_thread.isRunning():
            self.cv_thread.update_bbox(self.bbox_slider.value())

    def wheelEvent(self,event):
        delta = event.angleDelta().y()
        # increase slider value
        self.bbox_slider.setValue(self.bbox_slider.value() + delta)
        
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
        if hasattr(self, 'cv_thread') and type(self.cv_thread) == CVThread and self.cv_thread.isRunning():
            self.startCV.setText("Start")

            # if there is, terminate it
            self.cv_thread.endCV()
            # wait for the thread to finish
            self.cv_thread.wait()

        else:
            # create the video capture thread
            self.cv_thread = CVThread(inText, self.liveView.width(), self.liveView.height())
            # connect its signal to the update_image slot
            self.cv_thread.live_signal.connect(self.update_image)
            self.cv_thread.found_code_signal.connect(self.update_detected)
            # start the thread
            self.cv_thread.start()

            self.startCV.setText("Stop")

    def clearTable(self):
        self.qrTable.clearContents()
        self.qrTable.setRowCount(0)
        self.qrCodes = []
        self.browser.hide()
        self.browserHelp.show()

    def dropLeft(self):
        if self.dropper != None:
            self.dropper.left()
    
    def dropCenter(self):
        if self.dropper != None:
            self.dropper.center()

    def dropRight(self):
        if self.dropper != None:
            self.dropper.right()

    def loadProgressHandler(self, progress):
        self.browserProgressBar.setValue(progress)

    def loadStartedHandler(self):
        # if web browser is visible, show the progress bar
        if self.browser.isVisible():
            self.browserProgressBar.show()

    def loadFinishedHandler(self):
        self.browserProgressBar.setValue(0)

    @pyqtSlot(bool, bool)
    def updateDropperConnectionStatus(self, statusSerial, statusDropper):
        if statusSerial:
            self.connectSerial.setText("Disconnect")
        else:
            self.connectSerial.setText("Connect")

        if statusDropper:
            self.dropperStatus.setText("Wireless: Connected")
            #set green text
            self.dropperStatus.setStyleSheet("QLabel { color : green; }")
        else:
            self.dropperStatus.setText("Wireless: Disconnected")
            #set red text
            self.dropperStatus.setStyleSheet("QLabel { color : red; }")

    # slot for when tab changed
    def onTabChange(self):  
        # if there is a selection
        if self.qrTable.selectedItems():
            # get the selected row
            row = self.qrTable.selectedItems()[0].row()
            self.qrImage.setPixmap(self.convert_cv_qt(self.qrCodes[row].img, self.qrImage.width()))

    # slot for when table selection changed
    @pyqtSlot(np.ndarray, str)
    def update_image(self, cv_img, target):
        """Updates the image_label with a new opencv image"""
        qt_img = self.convert_cv_qt(cv_img, self.liveView.height())

        if target == "live":
            self.liveView.setPixmap(qt_img)

    def convert_cv_qt(self, cv_img, height):
        """Convert from an opencv image to QPixmap"""
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)

        #scale to fit width of liveView.width()
        p = convert_to_Qt_format.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)

        # update liveView width
        self.liveView.setFixedWidth(p.width())
        if hasattr(self, 'cv_thread') and type(self.cv_thread) == CVThread and self.cv_thread.isRunning():
            self.cv_thread.window_size = (p.width(), p.height())
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

    def open_in_browser(self):
        if len(self.qrTable.selectedItems()) > 0:
            row = self.qrTable.selectedItems()[0].row()
            QDesktopServices.openUrl(QUrl(self.qrCodes[row].data))

    #when item is selected in qrTable
    def on_qrTable_itemSelectionChanged(self):
        if len(self.qrTable.selectedItems()) > 0:
            row = self.qrTable.selectedItems()[0].row()
            self.browser.setUrl(QUrl(self.qrCodes[row].data))
            self.browser.show()
            self.browserHelp.hide()
            self.qrImage.setPixmap(self.convert_cv_qt(self.qrCodes[row].img, self.qrImage.width()))

            self.openinbrowser.setEnabled(True)

    def update_serial_ports(self):
        self.serialPorts.clear()

        # get list of serial ports
        ports = serial.tools.list_ports.comports()

        # add each port to the list
        for port in ports:
            self.serialPorts.addItem(port.device)

    def connect_disconnect_dropper(self):
        if self.dropper is None:
            self.dropper = DropperConnectionThread(self.serialPorts.currentText())
            self.dropper.connectionStatusSignal.connect(self.updateDropperConnectionStatus)
            self.dropper.start()
        else:
            self.dropper.disconnect()
            self.dropper = None

    def on_qrTable_doubleClicked(self):
        # show alert with qr code data
        if len(self.qrTable.selectedItems()) > 0:
            row = self.qrTable.selectedItems()[0].row()
            QMessageBox.information(self, "QR Code Data", self.qrCodes[row].data)


if __name__=="__main__":
    app = QApplication(sys.argv)
    a = Ui()
    sys.exit(app.exec())