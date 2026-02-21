import sys

from pytubefix import YouTube
from typing import cast 
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow,
                               QPushButton)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Video Downloader App")
        button = QPushButton("Press Me!")#buton oluşturma
        self.setFixedSize(QSize(100,100))
        self.setCentralWidget(button)
        button.setCheckable(True)
        button.clicked.connect(self.the_button_was_toggled)
        button.setCentrealWidget(QPushButton)
        button.setCentraWidget(button)
    #buton etkileşimi
    def the_button_was_clicked(self):
        print("Clicked!") #receiving data
    def the_button_was_toggled(self):
        print("Checked?")
    


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


#url = input("enter video url: ")

#yt = YouTube(url)

#yt.streams.get_highest_resolution().download("py_projects")     