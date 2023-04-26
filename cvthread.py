import cv2
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import pyqtSignal, QThread
import numpy as np
from pyzbar import pyzbar
from foundqr import FoundQR

# All CV Code will run in this thread to prevent GUI from freezing
class CVThread(QThread):
    live_signal = pyqtSignal(np.ndarray, str)
    found_code_signal = pyqtSignal(list)

    def __init__(self, source, window_size_x, window_size_y):
        super().__init__()
        self.source = source
        self.shouldRun = True
        self.mouse_pos = (0, 0)
        self.bbox_size = 100
        self.window_size = (window_size_x, window_size_y)

    def update_mouse(self, x, y):
        self.mouse_pos = (x, y)

    def update_bbox(self, size):
        self.bbox_size = size




    def run(self):
        # capture from web cam, CAP_DSHOW removes delay on windows
        cap = cv2.VideoCapture(self.source)

        # if the camera is not opened, exit
        if not cap.isOpened():
            #show error message in qt window
            msg = QMessageBox()
            msg.setText("Unable to Open Camera")
            msg.exec()

    
        while self.shouldRun:
            ret, image = cap.read()
            
            if image is None:
                continue

            # draw a box around the mouse of size bbox_size
            x, y = self.mouse_pos

            # map mouse position to image coordinates
            x = int(x * image.shape[1] / self.window_size[0])
            y = int(y * image.shape[0] / self.window_size[1])


            xmin = x - self.bbox_size
            ymin = y - self.bbox_size
            xmax = x + self.bbox_size
            ymax = y + self.bbox_size

            # crop the image to the box, making sure it is within the image
            xmin = max(0, xmin)
            ymin = max(0, ymin)
            xmax = min(image.shape[1], xmax)
            ymax = min(image.shape[0], ymax)

            cropped = image[ymin:ymax, xmin:xmax]

            barcodes = pyzbar.decode(cropped)

            detected = []

            if (x!=0 and y!=0):

                for i in barcodes:
                    # draw a box around the qr code that was found with i.rect
                    detection = cv2.rectangle(image, (xmin+i.rect.left, ymin+i.rect.top), (xmin+i.rect.left+i.rect.width, ymin+i.rect.top+i.rect.height), (0, 0, 255), 2)
                    qr = FoundQR(i.data.decode("utf-8"), detection, i)
                    if qr not in detected:
                        detected.append(qr)

                self.found_code_signal.emit(detected)

            # draw the box
            if len(detected) > 0:
                image = cv2.rectangle(image, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
            else:
                image = cv2.rectangle(image, (xmin, ymin), (xmax, ymax), (0, 0, 255), 2)
            

            # draw blue crosshair that takes up 15% of the image
            crosshair_size = int(min(image.shape[0], image.shape[1]) * 0.15)
            image = cv2.line(image, (image.shape[1] // 2 - crosshair_size // 2, image.shape[0] // 2), (image.shape[1] // 2 + crosshair_size // 2, image.shape[0] // 2), (255, 0, 0), 2)
            image = cv2.line(image, (image.shape[1] // 2, image.shape[0] // 2 - crosshair_size // 2), (image.shape[1] // 2, image.shape[0] // 2 + crosshair_size // 2), (255, 0, 0), 2)
            self.live_signal.emit(image, "live")


        blankImage = np.zeros((1080, 1920, 3), np.uint8)
        self.live_signal.emit(blankImage, "detection")
        self.live_signal.emit(blankImage, "live")

    def endCV(self):
        self.shouldRun = False