class FoundQR():
    def __init__(self, data, img, qr):
        self.data = data
        self.img = img
        self.qr_obj = qr
        self.consecutiveNotSeen = 0

    def __eq__(self, other):
        return self.data == other.data