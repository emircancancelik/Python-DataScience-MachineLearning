import sys
import sqlite3
import datetime
import os
import socket
import time
import logging
import uuid
import struct
import serial
import threading
import time
import json
import shutil 
import csv
import pandas as pd
import numpy as np
import sqlite3

from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.cluster import KMeans
from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                               QLabel, QHeaderView, QFrame, QLineEdit, QDialog, QMessageBox,
                               QGridLayout, QScrollArea, QGraphicsDropShadowEffect,
                               QComboBox, QProgressDialog, QTabWidget, QMenu, QInputDialog,
                               QSplitter, QAbstractItemView, QButtonGroup, QSizePolicy, QGroupBox,
                               QDoubleSpinBox, QFileDialog,QStackedWidget,QColorDialog)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QCursor, QPixmap, QColor

# =====================================================
# AYARLAR VE KONFİGÜRASYON YÖNETİMİ
# =====================================================
TEST_MODE = False
SHOP_NAME = "BAYİÇ ALCOHOL CENTER"
ADMIN_USER = "admin"
ADMIN_PASS = "123456"

def get_app_path():
    """
    Program .exe olduğunda .exe'nin bulunduğu klasörü,
    Python dosyasıyken .py dosyasının bulunduğu klasörü verir.
    """
    if getattr(sys, 'frozen', False):
        # .exe olarak çalışıyorsa
        return os.path.dirname(sys.executable)
    else:
        # Normal python dosyası olarak çalışıyorsa
        return os.path.dirname(os.path.abspath(__file__))
    
def load_pos_config():
    """pos_config.json dosyasından ayarları okur, yoksa oluşturur"""
    config_file = os.path.join(get_app_path(), "pos_config.json")

    defaults = {
        "primary_ip": "192.168.1.157",
        "primary_port": 6420,
        "backup_ip": "192.168.1.158",
        "backup_port": 9100,
        "pos_type": "auto",
        "timeout": 60,
        "auto_detect": True
    }
    
    if not os.path.exists(config_file):
        try:
            with open(config_file, "w") as f:
                json.dump(defaults, f, indent=4)
            print(f"✅ {config_file} oluşturuldu.")
        except Exception as e:
            print(f"❌ Config dosyası oluşturulamadı: {e}")
        return defaults
        
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
            print("✅ POS Ayarları dosyadan yüklendi.")
            return config
    except Exception as e:
        print(f"⚠️ Config dosyası okunamadı, varsayılanlar kullanılıyor: {e}")
        return defaults

# Ayarları yükle ve global değişkenlere ata
POS_CONFIG = load_pos_config()
POS_IP = POS_CONFIG.get("primary_ip", "192.168.1.157")
POS_PORT = POS_CONFIG.get("primary_port", 6420)
POS_TIMEOUT = POS_CONFIG.get("timeout", 60)


    
# TEMA YÖNETİCİSİ 

class ThemeManager:
    # Varsayılan Renkler (Apple Dark Mode Tarzı)
    DEFAULTS = {
        "bg_main": "#121212",
        "bg_panel": "#1e1e1e",
        "bg_secondary": "#252525",
        "text_primary": "#e0e0e0",
        "text_secondary": "#aaaaaa",
        "accent": "#0a84ff",
        "success": "#30d158",
        "error": "#ff453a",
        "warning": "#ff9f0a",
        "border": "#333333",
        "highlight": "#ffffff"
    }

    def __init__(self, filename="theme.json"):
        self.filename = os.path.join(get_app_path(), filename)
        self.current_theme = self.load_theme()

    def load_theme(self):
        # Dosya varsa oku, yoksa varsayılanı dön
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    return {**self.DEFAULTS, **json.load(f)}
            except:
                pass
        return self.DEFAULTS.copy()

    def save_theme(self, new_theme):
        self.current_theme = new_theme
        with open(self.filename, 'w') as f:
            json.dump(new_theme, f, indent=4)
            
    def reset_theme(self):
        self.save_theme(self.DEFAULTS.copy())
        return self.DEFAULTS.copy()

    def get_stylesheet(self):
        # DİKKAT: CSS parantezleri {{ }} çift, değişkenler { } tek.
        template = """
            /* --- GENEL --- */
            QMainWindow, QDialog {{ background-color: {bg_main}; }}
            QWidget {{ font-family: 'Segoe UI', sans-serif; font-size: 15px; color: {text_primary}; outline: none; }}
            
            /* SCROLLBAR */
            QScrollBar:vertical {{ background: {bg_main}; width: 8px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {bg_secondary}; min-height: 30px; border-radius: 4px; }}

            /* Inputlar */
            QLineEdit, QComboBox, QDoubleSpinBox {{
                background-color: {bg_secondary};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 8px;
                color: {text_primary};
                font-weight: bold;
            }}
            QLineEdit:focus {{ border: 1px solid {accent}; }}
            
            /* Tablo */
            QTableWidget {{ background-color: {bg_panel}; gridline-color: {border}; border: none; font-size: 16px; }}
            QTableWidget::item {{ padding: 8px; border-bottom: 1px solid {border}; }}
            QTableWidget::item:selected {{ background-color: {accent}; color: white; }}
            QHeaderView::section {{ background-color: {bg_secondary}; color: {text_primary}; border: none; padding: 6px; font-weight: bold; }}

            /* Butonlar Genel */
            QPushButton {{
                border-radius: 8px; padding: 10px; font-weight: bold;
                border: 1px solid {border}; background-color: {bg_secondary}; color: {text_primary};
            }}
            QPushButton:hover {{ border: 1px solid {accent}; }}

            /* --- ÜRÜN KARTLARI (GÜNCELLENDİ: KENARLIK VE MENÜ) --- */
            QFrame#ProductCard {{ 
                background-color: {bg_secondary}; 
                border: 1px solid #3a3a3c; /* İnce Gri Kenarlık */
                border-radius: 16px; 
            }}
            QFrame#ProductCard:hover {{ 
                background-color: {bg_panel}; 
                border: 1px solid {accent}; /* Mavi Parlama */
            }}

            /* --- KATEGORİ KARTLARI (GÜNCELLENDİ) --- */
            
            /* 1. Normal Kategori */
            QFrame#CategoryCard_Normal {{
                background-color: {bg_secondary}; 
                border-radius: 16px;
                border: 1px solid #3a3a3c; /* İnce Gri Kenarlık */
            }}
            QFrame#CategoryCard_Normal:hover {{
                background-color: {bg_panel}; 
                border: 1px solid {accent};
            }}

            /* 2. Tüm Ürünler Kartı (Mavi Gradyan) */
            QFrame#CategoryCard_All {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #007aff, stop:1 #0056b3);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.3);
            }}
            QFrame#CategoryCard_All:hover {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {accent}, stop:1 #006ddb);
                border: 1px solid white;
            }}

            /* 3. Ekleme Kartı */
            QFrame#CategoryCard_Add {{
                background-color: rgba(48, 209, 88, 0.05);
                border-radius: 16px;
                border: 2px dashed {success};
            }}
            QFrame#CategoryCard_Add:hover {{
                background-color: rgba(48, 209, 88, 0.15);
            }}

            /* Kart Yazıları */
            QFrame#CategoryCard_Normal QLabel, QFrame#CategoryCard_All QLabel, QFrame#CategoryCard_Add QLabel {{
                font-family: 'Segoe UI', sans-serif;
            }}

            /* --- SAĞ PANEL VE BUTONLAR --- */
            QPushButton#BtnCash {{ background-color: {success}; color: black; font-size: 24px; font-weight: 900; border: none; border-radius: 12px; }}
            QPushButton#BtnCash:hover {{ background-color: #2ec4b6; }}
            
            QPushButton#BtnCard {{ background-color: {accent}; color: white; font-size: 24px; font-weight: 900; border: none; border-radius: 12px; }}
            QPushButton#BtnCard:hover {{ background-color: #4cc9f0; }}
            
            QPushButton.DangerBtn {{ background-color: {error}; color: white; border: none; }}
            QPushButton.TopBarBtn {{ background-color: {bg_secondary}; height: 45px; }}
            
            QFrame#ChangeFrame {{ background-color: {bg_panel}; border-radius: 12px; border: 1px solid {border}; }}
            QLabel.ChangeResult {{ color: {success}; font-weight: 900; font-size: 26px; }}
            QLabel.ChangeResultError {{ color: #444; font-size: 16px; }}

            /* PANELLER */
            QFrame#LeftPanel {{ background-color: {bg_main}; border-right: 1px solid {border}; }}
            QFrame#CenterPanel {{ background-color: {bg_panel}; border-right: 1px solid {border}; }}
            QFrame#RightPanel {{ background-color: {bg_main}; }}
            
            /* Numpad */
            QWidget#NumpadContainer {{
                background-color: {bg_secondary};
                border-radius: 12px;
                border: 1px solid {border};
            }}
            QPushButton.NumBtn {{ background-color: transparent; font-size: 24px; border: 1px solid {border}; }}
            QPushButton.NumBtn:hover {{ background-color: {bg_panel}; }}
            QPushButton.NumBtn:pressed {{ background-color: {accent}; color: white; }}
        """
        return template.format(**self.current_theme)

# Global Nesneyi Oluştur (ÖNEMLİ)
theme_manager = ThemeManager()

class ThemeEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(50, 50, 50, 50)
        
        title = QLabel("Tema Kişiselleştirme")
        title.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {theme_manager.current_theme['accent']}; margin-bottom: 20px;")
        title.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(title)

        grid_widget = QWidget()
        self.grid = QGridLayout(grid_widget)
        self.grid.setSpacing(20)
        self.buttons = {}
        
        self.labels_map = {
            "bg_main": "Ana Arka Plan", "bg_panel": "Panel Rengi", "bg_secondary": "Buton Rengi",
            "text_primary": "Yazı Rengi", "accent": "Vurgu (Mavi)", "success": "Yeşil/Nakit",
            "error": "Kırmızı/Sil", "warning": "Uyarı", "border": "Kenarlık"
        }
        
        row, col = 0, 0
        for key in list(self.labels_map.keys()):
            container = QFrame()
            container.setStyleSheet("background: #252525; border-radius: 10px; border: 1px solid #333;")
            vbox = QVBoxLayout(container)
            lbl = QLabel(self.labels_map[key])
            lbl.setStyleSheet("color: #aaa; font-weight: bold; border: none;")
            lbl.setAlignment(Qt.AlignCenter)
            btn = QPushButton()
            btn.setFixedHeight(40)
            btn.setCursor(Qt.PointingHandCursor)
            current_color = theme_manager.current_theme.get(key, "#000000")
            self.update_btn_style(btn, current_color)
            btn.clicked.connect(lambda _, k=key, b=btn: self.pick_color(k, b))
            vbox.addWidget(lbl)
            vbox.addWidget(btn)
            self.grid.addWidget(container, row, col)
            self.buttons[key] = btn
            col += 1
            if col > 2: col, row = 0, row + 1
        
        self.layout.addWidget(grid_widget)
        self.layout.addStretch()

        action_layout = QHBoxLayout()
        btn_save = QPushButton("💾 KAYDET VE UYGULA")
        btn_save.setFixedHeight(50)
        btn_save.setProperty("class", "SuccessBtn")
        btn_save.clicked.connect(self.apply_changes)
        btn_reset = QPushButton("♻️ VARSAYILANA DÖN")
        btn_reset.setFixedHeight(50)
        btn_reset.clicked.connect(self.reset_defaults)
        
        action_layout.addWidget(btn_save, stretch=2)
        action_layout.addWidget(btn_reset, stretch=1)
        self.layout.addLayout(action_layout)

    def update_btn_style(self, btn, color):
        btn.setText(color)
        btn.setStyleSheet(f"background-color: {color}; color: white; border: 1px solid #555; border-radius: 5px; font-weight: bold;")

    def pick_color(self, key, btn):
        color = QColorDialog.getColor(initial=QColor(btn.text()), parent=self, title=self.labels_map[key])
        if color.isValid():
            hex_color = color.name()
            theme_manager.current_theme[key] = hex_color
            self.update_btn_style(btn, hex_color)

    def apply_changes(self):
        theme_manager.save_theme(theme_manager.current_theme)
        app = QApplication.instance()
        app.setStyleSheet(theme_manager.get_stylesheet())
        for widget in app.allWidgets():
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        QMessageBox.information(self, "Başarılı", "Renkler güncellendi!")

    def reset_defaults(self):
        defaults = theme_manager.reset_theme()
        for key, btn in self.buttons.items():
            if key in defaults:
                theme_manager.current_theme[key] = defaults[key]
                self.update_btn_style(btn, defaults[key])
        self.apply_changes()
# =====================================================
# AYARLAR
# =====================================================


# =====================================================
# LOGGING
# =====================================================
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/pos.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logging.info("VoidPOS başlatıldı - GERÇEK POS MODU")


# =====================================================
# INGENICO MOVE 5000F - POS ENTEGRASYONU
# =====================================================
# =====================================================
# ÇOKLU POS DESTEĞİ (BEKO + INGENICO)
# =====================================================

class POSType(Enum):
    INGENICO_GOSB = "ingenico_gosb"
    BEKO_ECR = "beko_ecr"
    AUTO_DETECT = "auto"

class UniversalPOSManager:
    """Hem Beko hem Ingenico için çalışan akıllı POS yöneticisi"""
    
    def __init__(self):
        self.logger = logging.getLogger("UniversalPOS")
        self.detected_type = None
        
        # Ayarlar dosyasından oku
        self.config = self.load_config()
    
    def load_config(self):
        """Config dosyasından POS ayarlarını oku"""
        config_file = "pos_config.json"
        
        default_config = {
            "primary_ip": "192.168.1.157",
            "primary_port": 6420,
            "backup_ip": "192.168.1.100",
            "backup_port": 9100,
            "pos_type": "auto",  # auto, ingenico_gosb, beko_ecr
            "timeout": 60,
            "auto_detect": True
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return {**default_config, **json.load(f)}
            except:
                pass
        
        # Config yoksa oluştur
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        
        return default_config
    
    def detect_pos_type(self, ip: str, port: int) -> Optional[POSType]:
        """POS tipini otomatik algıla"""
        self.logger.info(f"POS tipi algılanıyor: {ip}:{port}")
        
        # 1. Ingenico GÖSB dene (Port 6420)
        if port == 6420:
            ingenico = IngenicoGOSB(ip, port)
            if ingenico.test_connection():
                self.logger.info("✅ Ingenico GÖSB algılandı")
                return POSType.INGENICO_GOSB
        
        # 2. Beko ECR dene (Port 9100 veya RS232)
        if port in [9100, 9600]:
            beko = BekoECR(ip, port)
            if beko.test_connection():
                self.logger.info("✅ Beko ECR algılandı")
                return POSType.BEKO_ECR
        
        self.logger.warning("❌ POS tipi algılanamadı")
        return None
    
    def create_pos_client(self):
        """Doğru POS client'ı oluştur"""
        ip = self.config['primary_ip']
        port = self.config['primary_port']
        
        # Manuel tip belirtilmişse
        if self.config['pos_type'] != "auto":
            if self.config['pos_type'] == "ingenico_gosb":
                return IngenicoGOSB(ip, port)
            elif self.config['pos_type'] == "beko_ecr":
                return BekoECR(ip, port)
        
        # Otomatik algılama
        if self.config['auto_detect']:
            detected = self.detect_pos_type(ip, port)
            self.detected_type = detected
            
            if detected == POSType.INGENICO_GOSB:
                return IngenicoGOSB(ip, port)
            elif detected == POSType.BEKO_ECR:
                return BekoECR(ip, port)
        
        # Varsayılan olarak Ingenico dene
        return IngenicoGOSB(ip, port)
    
    def process_payment(self, amount: float, payment_type: str = "CARD") -> dict:
        """
        Ödeme işlemi - Hem NAKİT hem KART için çalışır
        
        Args:
            amount: Tutar (TL)
            payment_type: "CARD" veya "CASH"
        """
        tx_id = str(uuid.uuid4())[:8]
        self.logger.info(f"💳 ÖDEME | {payment_type} | {amount:.2f} TL | TX:{tx_id}")
        
        try:
            pos_client = self.create_pos_client()
            
            if payment_type == "CASH":
                # NAKİT işlemi - Fiş yazdır ama kart okutma
                result = pos_client.print_receipt_only(amount)
            else:
                # KART işlemi - Tam işlem
                result = pos_client.sale(amount)
            
            if result['success']:
                return {
                    'success': True,
                    'method': payment_type,
                    'amount': amount,
                    'auth_code': result.get('auth_code', 'CASH'),
                    'receipt_no': result.get('rrn', tx_id),
                    'card_number': result.get('card_number', '****'),
                    'tx_id': tx_id,
                    'message': 'İşlem Başarılı'
                }
            else:
                return {
                    'success': False,
                    'method': payment_type,
                    'message': result.get('message', 'İşlem Başarısız'),
                    'tx_id': tx_id
                }
                
        except Exception as e:
            self.logger.exception("Ödeme hatası")
            return {
                'success': False,
                'message': f'Hata: {str(e)}',
                'tx_id': tx_id
            }
        
class TxState(Enum):
    INIT = "INIT"
    SENT = "SENT"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class GOSBMessageType(Enum):
    """GÖSB Mesaj Tipleri"""
    SALE = 0x31
    VOID = 0x32
    REFUND = 0x33
    SETTLEMENT = 0x34
    STATUS = 0x35


class IngenicoGOSB:
    """Ingenico Move 5000F - GÖSB Protokolü (Garanti, Akbank, vb.)"""
    
    ACK = 0x06
    NAK = 0x15
    STX = 0x02
    ETX = 0x03
    
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.socket = None
        self.logger = logging.getLogger("IngenicoGOSB")
    
    def test_connection(self) -> bool:
        """Bağlantı testi"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((self.ip, self.port))
            s.close()
            return True
        except:
            return False
    
    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.ip, self.port))
            self.logger.info(f"✅ Bağlantı başarılı: {self.ip}:{self.port}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Bağlantı hatası: {e}")
            return False
    
    def disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
    
    def _build_gosb_message(self, msg_type: int, fields: dict) -> bytes:
        """GÖSB mesajı oluştur (ISO 8583 benzeri)"""
        payload = bytes([msg_type])
        
        for field_id, value in fields.items():
            field_data = str(value).encode('ascii')
            field_len = len(field_data)
            
            # Field: ID(2) + Length(2) + Data
            payload += struct.pack('!H', field_id)
            payload += struct.pack('!H', field_len)  # ✅ 2 byte (düzeltildi)
            payload += field_data
        
        # Frame: STX + Length(2) + Payload + ETX + LRC
        length = len(payload)
        frame = bytes([self.STX])
        frame += struct.pack('!H', length)
        frame += payload
        frame += bytes([self.ETX])
        
        # LRC hesapla
        lrc = 0
        for b in frame[1:]:
            lrc ^= b
        frame += bytes([lrc])
        
        return frame
    
    def _send_and_wait_ack(self, message: bytes) -> bool:
        """Mesaj gönder ve ACK bekle"""
        try:
            self.logger.debug(f"📤 TX: {message.hex()}")
            self.socket.sendall(message)
            
            # ACK bekle (1 saniye)
            self.socket.settimeout(1)
            ack = self.socket.recv(1)
            
            if ack and ack[0] == self.ACK:
                self.logger.debug("✅ ACK alındı")
                return True
            else:
                self.logger.error(f"❌ NAK alındı: {ack.hex() if ack else 'timeout'}")
                return False
        except Exception as e:
            self.logger.error(f"Gönderim hatası: {e}")
            return False
    
    def _receive_and_send_ack(self, timeout: int = 60) -> Optional[bytes]:
        """Yanıt al ve ACK gönder"""
        try:
            self.socket.settimeout(timeout)
            
            # Frame oku: STX + Len(2) + Payload + ETX + LRC
            stx = self.socket.recv(1)
            if not stx or stx[0] != self.STX:
                return None
            
            len_bytes = self.socket.recv(2)
            if len(len_bytes) != 2:
                return None
            
            payload_len = struct.unpack('!H', len_bytes)[0]
            
            # Payload oku
            payload = b''
            while len(payload) < payload_len:
                chunk = self.socket.recv(payload_len - len(payload))
                if not chunk:
                    return None
                payload += chunk
            
            etx = self.socket.recv(1)
            lrc_received = self.socket.recv(1)
            
            if not etx or etx[0] != self.ETX:
                return None
            
            # LRC doğrula
            frame = stx + len_bytes + payload + etx
            lrc_calc = 0
            for b in frame[1:]:
                lrc_calc ^= b
            
            if lrc_calc != lrc_received[0]:
                self.logger.error("❌ LRC hatası")
                self.socket.send(bytes([self.NAK]))
                return None
            
            # ACK gönder
            self.socket.send(bytes([self.ACK]))
            self.logger.debug(f"📥 RX: {payload.hex()}")
            
            return payload
            
        except socket.timeout:
            self.logger.error("Timeout - Yanıt alınamadı")
            return None
        except Exception as e:
            self.logger.error(f"Alma hatası: {e}")
            return None
    
    def _parse_response(self, payload: bytes) -> dict:
        """GÖSB yanıtını parse et"""
        result = {'msg_type': payload[0]}
        offset = 1
        
        while offset < len(payload):
            if offset + 4 > len(payload):
                break
            
            field_id = struct.unpack('!H', payload[offset:offset+2])[0]
            offset += 2
            
            field_len = struct.unpack('!H', payload[offset:offset+2])[0]
            offset += 2
            
            if offset + field_len > len(payload):
                break
            
            field_data = payload[offset:offset+field_len].decode('ascii', errors='ignore')
            offset += field_len
            
            # Field mapping
            field_names = {
                1: 'response_code',
                2: 'auth_code',
                3: 'terminal_id',
                4: 'merchant_id',
                5: 'card_number',
                6: 'amount',
                7: 'stan',
                8: 'rrn',
                39: 'response_text'
            }
            
            if field_id in field_names:
                result[field_names[field_id]] = field_data
        
        return result
    
    def sale(self, amount: float) -> dict:
        """KART ile satış"""
        if not self.connect():
            return {'success': False, 'message': 'Bağlantı hatası'}
        
        try:
            amount_krs = int(amount * 100)
            
            # SALE mesajı (0x31)
            message = self._build_gosb_message(0x31, {
                6: amount_krs,  # Tutar (kuruş)
                12: datetime.datetime.now().strftime("%y%m%d%H%M%S")  # Zaman
            })
            
            if not self._send_and_wait_ack(message):
                return {'success': False, 'message': 'Mesaj gönderilemedi'}
            
            # Yanıt bekle (60 saniye - kart okutma süresi)
            response = self._receive_and_send_ack(timeout=60)
            
            if not response:
                return {'success': False, 'message': 'POS yanıt vermedi', 'timeout': True}
            
            parsed = self._parse_response(response)
            rc = parsed.get('response_code', 'XX')
            
            if rc == '00':
                return {
                    'success': True,
                    'response_code': rc,
                    'auth_code': parsed.get('auth_code', ''),
                    'rrn': parsed.get('rrn', ''),
                    'card_number': self._mask_card(parsed.get('card_number', '')),
                    'message': 'İşlem Onaylandı'
                }
            else:
                return {
                    'success': False,
                    'response_code': rc,
                    'message': self._get_error_message(rc)
                }
        
        finally:
            self.disconnect()
    
    def print_receipt_only(self, amount: float) -> dict:
        """NAKİT işlem - Sadece fiş yazdır (kart okutma YOK)"""
        # Ingenico'da nakit işlemi için "DISPLAY ONLY" mesajı gönderilir
        # veya hiç mesaj gönderilmez, sadece yazıcı komutu verilir
        
        self.logger.info(f"💵 NAKİT işlem - Fiş yazdırılıyor: {amount:.2f} TL")
        
        # Bazı POS'larda nakit için özel komut var, yoksa sadece Success dön
        return {
            'success': True,
            'message': 'Nakit işlem kaydedildi',
            'rrn': datetime.datetime.now().strftime("%y%m%d%H%M%S")
        }
    
    def _mask_card(self, card: str) -> str:
        if not card or len(card) < 10:
            return "****"
        return f"{card[:6]}{'*' * (len(card) - 10)}{card[-4:]}"
    
    def _get_error_message(self, code: str) -> str:
        errors = {
            '00': 'Onaylandı',
            '05': 'Reddedildi',
            '51': 'Yetersiz Bakiye',
            '54': 'Kart Süresi Dolmuş',
            '55': 'Hatalı PIN',
            '91': 'Banka Yanıt Vermiyor'
        }
        return errors.get(code, f'Hata Kodu: {code}')


# =====================================================
# POS SERVİSİ
# =====================================================
class BekoECR:
    """Beko POS - ECR Protokolü (Seri Port veya TCP/IP)"""
    
    STX = 0x02
    ETX = 0x03
    ACK = 0x06
    NAK = 0x15
    
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.socket = None
        self.logger = logging.getLogger("BekoECR")
    
    def test_connection(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((self.ip, self.port))
            s.close()
            return True
        except:
            return False
    
    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.ip, self.port))
            self.logger.info(f"✅ Beko bağlantı başarılı: {self.ip}:{self.port}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Bağlantı hatası: {e}")
            return False
    
    def disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            finally:
                self.socket = None
    
    def _build_ecr_message(self, command: str, data: str = "") -> bytes:
        """
        Beko ECR mesaj formatı:
        STX + Command + FS + Data + ETX + LRC
        """
        FS = chr(0x1C)  # Field Separator
        
        message = command
        if data:
            message += FS + data
        
        frame = bytes([self.STX])
        frame += message.encode('ascii')
        frame += bytes([self.ETX])
        
        # LRC
        lrc = 0
        for b in frame[1:]:
            lrc ^= b
        frame += bytes([lrc])
        
        return frame
    
    def _send_and_wait_ack(self, message: bytes) -> bool:
        try:
            self.logger.debug(f"📤 TX: {message.hex()}")
            self.socket.sendall(message)
            
            ack = self.socket.recv(1)
            return ack and ack[0] == self.ACK
        except:
            return False
    
    def _receive_and_send_ack(self, timeout: int = 60) -> Optional[bytes]:
        try:
            self.socket.settimeout(timeout)
            
            # STX bekle
            stx = self.socket.recv(1)
            if not stx or stx[0] != self.STX:
                return None
            
            # ETX'e kadar oku
            data = b''
            while True:
                byte = self.socket.recv(1)
                if not byte:
                    return None
                if byte[0] == self.ETX:
                    break
                data += byte
            
            lrc_received = self.socket.recv(1)
            
            # LRC doğrula
            frame = stx + data + bytes([self.ETX])
            lrc_calc = 0
            for b in frame[1:]:
                lrc_calc ^= b
            
            if lrc_calc != lrc_received[0]:
                self.socket.send(bytes([self.NAK]))
                return None
            
            self.socket.send(bytes([self.ACK]))
            self.logger.debug(f"📥 RX: {data.hex()}")
            
            return data
        except:
            return None
    
    def sale(self, amount: float) -> dict:
        """KART satış (Beko formatı)"""
        if not self.connect():
            return {'success': False, 'message': 'Bağlantı hatası'}
        
        try:
            # Beko komut formatı: "SALE" + amount
            amount_str = f"{amount:.2f}".replace('.', '')  # 10.50 -> 1050
            
            message = self._build_ecr_message("SALE", amount_str)
            
            if not self._send_and_wait_ack(message):
                return {'success': False, 'message': 'Komut gönderilemedi'}
            
            response = self._receive_and_send_ack(timeout=60)
            
            if not response:
                return {'success': False, 'message': 'Yanıt alınamadı', 'timeout': True}
            
            # Yanıt parse et (Beko formatı: "OK" veya "ERROR")
            response_str = response.decode('ascii', errors='ignore')
            
            if "OK" in response_str or "00" in response_str:
                # Başarılı - Auth code ve RRN çıkar
                parts = response_str.split(chr(0x1C))
                return {
                    'success': True,
                    'auth_code': parts[1] if len(parts) > 1 else '',
                    'rrn': parts[2] if len(parts) > 2 else '',
                    'card_number': '****',
                    'message': 'İşlem Onaylandı'
                }
            else:
                return {
                    'success': False,
                    'message': f'İşlem Reddedildi: {response_str}'
                }
        
        finally:
            self.disconnect()
    
    def print_receipt_only(self, amount: float) -> dict:
        """NAKİT işlem - Fiş yazdır"""
        self.logger.info(f"💵 NAKİT - Fiş yazdırılıyor: {amount:.2f} TL")
        
        # Beko'da nakit için "PRINT" komutu
        if not self.connect():
            return {'success': True, 'message': 'Offline mode'}
        
        try:
            message = self._build_ecr_message("PRINT", f"{amount:.2f}")
            self._send_and_wait_ack(message)
            
            return {
                'success': True,
                'message': 'Fiş yazdırıldı',
                'rrn': datetime.datetime.now().strftime("%y%m%d%H%M%S")
            }
        finally:
            self.disconnect()

class POSService:
    def __init__(self):
        # ❌ HATA: Burada client oluşturmayın (Thread çakışır)
        # self.client = IngenicoMove5000F(POS_IP, POS_PORT)
        self.logger = logging.getLogger("POSService")
    
    def process_sale(self, amount: float) -> dict:
        """Satış işlemi - Thread-Safe"""
        tx_id = str(uuid.uuid4())[:8]
        self.logger.info(f"TX START | {tx_id} | {amount:.2f} TL")
        
        try:
            # ✅ Her işlem için YENİ client oluştur (Thread güvenliği)
            client = IngenicoGOSB(POS_IP, POS_PORT)
            result = client.sale(amount)
            
            if result['success']:
                return {
                    'success': True,
                    'rc': result['response_code'],
                    'auth_code': result['auth_code'],
                    'receipt_no': result['rrn'],
                    'state': 'APPROVED',
                    'tx_id': tx_id,
                    'card_number': result.get('card_number', '')
                }
            else:
                if result.get('timeout'):
                    return {
                        'success': False,
                        'msg': 'POS zaman aşımı',
                        'state': 'TIMEOUT',
                        'tx_id': tx_id,
                        'pending': True
                    }
                else:
                    return {
                        'success': False,
                        'rc': result.get('response_code', 'XX'),
                        'msg': result['message'],
                        'state': 'DECLINED',
                        'tx_id': tx_id
                    }
        
        except Exception as e:
            self.logger.exception(f"TX ERROR | {tx_id}")
            return {
                'success': False,
                'msg': str(e),
                'state': 'ERROR',
                'tx_id': tx_id
            }


class PaymentWorker(QThread):
    """Ödeme işlemini arka planda yapar"""
    finished = Signal(dict)
    
    def __init__(self, amount: float, method: str):
        super().__init__()
        self.amount = amount
        self.method = method  # "CARD" veya "CASH"
    
    def run(self):
        try:
            pos_manager = UniversalPOSManager()
            result = pos_manager.process_payment(self.amount, self.method)
            self.finished.emit(result)
        except Exception as e:
            self.finished.emit({
                'success': False,
                'message': f'Kritik hata: {str(e)}'
            })


#CSS
# =====================================================
# DİNAMİK STYLESHEET (TEMPLATE)
# =====================================================
STYLESHEET_TEMPLATE = """
    /* --- GENEL AYARLAR --- */
    QMainWindow {{ background-color: {bg_main}; }}
    QDialog {{ background-color: {bg_main}; }}
    QWidget {{ font-family: 'Segoe UI', sans-serif; color: {text_primary}; outline: none; }}

    /* --- SCROLLBAR (Gizli ve Şık) --- */
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: {bg_main}; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #444; min-height: 30px; border-radius: 4px; }}
    QScrollBar::handle:vertical:hover {{ background: {accent}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

    /* --- INPUT ALANLARI (Tam Yuvarlak) --- */
    QLineEdit, QComboBox, QDoubleSpinBox {{ 
        background-color: {bg_secondary}; 
        color: {text_primary}; 
        border: 1px solid {border}; 
        padding: 10px 15px; 
        border-radius: 12px; 
        font-size: 14px;
    }}
    QLineEdit:focus, QComboBox:focus {{ 
        border: 1px solid {accent}; 
        background-color: {bg_panel};
    }}

    /* --- TABLO / SEPET --- */
    QTableWidget {{ 
        background-color: {bg_panel}; 
        border-radius: 12px; 
        border: 1px solid {border};
        gridline-color: transparent; 
    }}
    QTableWidget::item {{ 
        border-bottom: 1px solid {border}; 
        padding: 12px; 
    }}
    QTableWidget::item:selected {{ 
        background-color: {bg_secondary}; /* Seçili satır hafif açık */
        color: white; 
        border-left: 3px solid {accent}; /* Sol tarafa renkli şerit */
        border-radius: 4px;
    }}
    QHeaderView::section {{ 
        background-color: {bg_main}; 
        color: #888; 
        border: none; 
        border-bottom: 2px solid {border}; 
        padding: 8px; 
        font-weight: bold; 
        text-transform: uppercase;
        font-size: 12px;
    }}

    /* --- BUTONLAR (Genel) --- */
    QPushButton {{
        border-radius: 12px;
        font-weight: bold;
        border: 1px solid {border};
        padding: 5px;
    }}

    /* --- KARTLAR VE KUTULAR (Apple Tarzı Gradient) --- */
    /* Ürün Kartları, Kategori Kutuları vb. için genel QFrame */
    QFrame {{
        background-color: {bg_panel}; 
        border-radius: 16px; 
        border: 1px solid {border};
    }}
    
    /* Özel Kategori Butonları */
    QPushButton.CatBoxBtn {{ 
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {bg_panel}, stop:1 {bg_main});
        color: {text_primary}; 
        border: 1px solid {border}; 
        border-radius: 14px; 
        font-size: 15px; 
    }}
    QPushButton.CatBoxBtn:hover {{
        border: 1px solid {accent};
        background-color: {bg_secondary};
    }}
    QPushButton.CatBoxBtn:pressed {{
        background-color: {accent};
        color: white;
    }}

    /* --- SAĞ PANEL (Para Üstü) --- */
    QFrame#ChangeFrame {{ background-color: {bg_main}; border: 1px solid {border}; border-radius: 12px; }}
    QLabel.ChangeResult {{ color: {success}; font-weight: 900; font-size: 26px; font-family: monospace; }}
    
    /* --- ÖZEL BUTONLAR --- */
    QPushButton.PayBtn {{ border-radius: 14px; font-size: 22px; font-weight: 800; border: none; }}
    QPushButton.NumBtn {{ background-color: {bg_panel}; font-size: 24px; border-radius: 0px; border: 1px solid {border}; }}
    QPushButton.NumBtn:hover {{ background-color: {bg_secondary}; }}
    QPushButton.NumBtn:pressed {{ background-color: {accent}; color: white; }}
    
    /* Yönetim Butonları */
    QPushButton.TopBarBtn {{ background-color: {bg_panel}; color: {text_primary}; border-radius: 15px; }}
    QPushButton.TopBarBtn:hover {{ border: 1px solid {accent}; }}
"""

# --- VERİTABANI ---
class DatabaseManager:
    def __init__(self, db_name="voidpos.db"):
        self.db_path = os.path.join(get_app_path(), db_name)
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)      
        self.cursor = self.conn.cursor()       
        self.create_tables()
        
        # Varsayılan Kategoriler
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Sigara', 0)")
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Viski', 1)")
        self.conn.commit()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_no TEXT,
                total_amount REAL,
                total_profit REAL,
                payment_method TEXT,
                sale_date TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS sale_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_id INTEGER,
                product_name TEXT,
                quantity INTEGER,
                sell_price REAL,
                cost_price REAL,
                total_price REAL,
                sale_date TEXT,
                sale_time TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cost_price REAL DEFAULT 0.0,
                sell_price REAL NOT NULL,
                stock INTEGER DEFAULT 0,
                critical_stock INTEGER DEFAULT 5,
                category TEXT DEFAULT 'Tüm Ürünler',
                barcode TEXT UNIQUE,
                image_path TEXT,
                is_favorite INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                sort_order INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id TEXT UNIQUE,
                amount REAL,
                timestamp TEXT,
                resolved INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Sigara', 0)")
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Viski', 1)")
        
        self.conn.commit()
    
    # DatabaseManager sınıfının içine ekleyin:

    def export_products_to_csv(self, filename):
        """Ürünleri CSV dosyasına aktarır"""
        try:
            products = self.cursor.execute("SELECT * FROM products").fetchall()
            headers = [description[0] for description in self.cursor.description]
            
            # utf-8-sig: Excel'in Türkçe karakterleri tanıması için gereklidir
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(products)
            return True, f"{len(products)} ürün dışa aktarıldı."
        except Exception as e:
            return False, str(e)

    # DatabaseManager sınıfının içine yapıştır:

    def import_products_from_csv(self, filename):
        """CSV dosyasından ürünleri ve kategorileri veritabanına aktarır"""
        if not os.path.exists(filename):
            return False, f"❌ DOSYA BULUNAMADI: {filename}"
            
        try:
            with open(filename, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                # Başlıkları küçük harfe çevirip temizleyelim
                if reader.fieldnames:
                    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
                
                added = 0
                updated = 0
                
                # Kategori listesi (Tekrarları önlemek için set kullanıyoruz)
                found_categories = set() 
                
                for row in reader:
                    # --- Veri Okuma ---
                    name = row.get('name') or row.get('stokad') or row.get('urun_adi')
                    if not name: continue 

                    price = row.get('fiyat') or row.get('satis_fiyati') or row.get('gfiyat') or 0
                    stock = row.get('kalana') or row.get('kalanb') or row.get('stok') or 0
                    barcode = row.get('barkod') or row.get('barkod1')
                    
                    # Kategori Okuma (Boşsa 'Genel' yap, boşlukları temizle)
                    raw_cat = row.get('gurup') or row.get('kategori')
                    category = raw_cat.strip() if raw_cat else 'Genel'
                    
                    # Kategoriyi hafızaya at (Daha sonra ekleyeceğiz)
                    found_categories.add(category)

                    cost = row.get('maliyet') or 0
                    image = row.get('resim') or ''

                    # --- Sayısal Dönüşümler ---
                    try: price = float(str(price).replace(',', '.'))
                    except: price = 0.0
                    try: stock = int(float(str(stock).replace(',', '.')))
                    except: stock = 0
                    try: cost = float(str(cost).replace(',', '.'))
                    except: cost = 0.0

                    # --- Ürün Kayıt/Güncelleme ---
                    exists = None
                    if barcode:
                        exists = self.cursor.execute("SELECT id FROM products WHERE barcode=?", (barcode,)).fetchone()
                    if not exists:
                        exists = self.cursor.execute("SELECT id FROM products WHERE name=?", (name,)).fetchone()

                    if exists:
                        self.cursor.execute("""
                            UPDATE products SET sell_price=?, stock=?, cost_price=?, category=?, barcode=?, image_path=?
                            WHERE id=?
                        """, (price, stock, cost, category, barcode, image, exists[0]))
                        updated += 1
                    else:
                        self.cursor.execute("""
                            INSERT INTO products (name, sell_price, stock, cost_price, category, barcode, image_path, sort_order)
                            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                        """, (name, price, stock, cost, category, barcode, image))
                        added += 1

                # --- KRİTİK NOKTA: KATEGORİLERİ KAYDETME ---
                # Toplanan kategorileri veritabanına ekle (Varsa atla - INSERT OR IGNORE)
                for cat_name in found_categories:
                    if cat_name: # Boş değilse
                        # Kategoriyi ekle (sort_order 99 yaparak sona atıyoruz)
                        self.cursor.execute("""
                            INSERT OR IGNORE INTO categories (name, sort_order) 
                            VALUES (?, 99)
                        """, (cat_name,))

            self.conn.commit()
            return True, f"✅ İşlem Tamamlandı:\n• {added} Yeni Ürün\n• {updated} Güncelleme\n• {len(found_categories)} Kategori Kontrol Edildi."
            
        except Exception as e:
            return False, f"Hata Oluştu: {str(e)}"
        
    def get_all_categories(self):
        self.cursor.execute("SELECT name FROM categories ORDER BY sort_order ASC")
        return [r[0] for r in self.cursor.fetchall()]
        
    def get_todays_sales(self):
        today_str = str(datetime.date.today())
        query = f"""
            SELECT s.id, s.receipt_no, s.sale_date, s.timestamp, s.payment_method, s.total_amount,
            (SELECT product_name FROM sale_items WHERE sale_id = s.id LIMIT 1) as first_prod
            FROM sales s 
            WHERE s.sale_date = '{today_str}' 
            ORDER BY s.id DESC
        """
        return self.cursor.execute(query).fetchall()

    def get_todays_totals(self):
        today_str = str(datetime.date.today())
        self.cursor.execute(f"SELECT SUM(total_amount), SUM(total_profit) FROM sales WHERE sale_date='{today_str}'")
        return self.cursor.fetchone()
    
    def get_daily_turnover(self):
        today = str(datetime.date.today())
        self.cursor.execute("SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE sale_date=?", (today,))
        result = self.cursor.fetchone()
        return result[0] if result else 0.0
    
    def get_products(self, cat):
        q = "SELECT id, name, sell_price, image_path, is_favorite, stock FROM products "
        q += "ORDER BY sort_order ASC" if cat == "Tüm Ürünler" else f"WHERE category='{cat}' ORDER BY sort_order ASC"
        return self.cursor.execute(q).fetchall()
    
    def get_favorites(self):
        return self.cursor.execute(
            "SELECT id, name, sell_price, image_path, is_favorite, stock FROM products WHERE is_favorite=1 ORDER BY sort_order ASC"
        ).fetchall()
    
    def get_product_by_barcode(self, b):
        return self.cursor.execute("SELECT name, sell_price, stock FROM products WHERE barcode=?", (b,)).fetchone()
    
    def get_product_by_id(self, pid):
        return self.cursor.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    
    def get_cost(self, n):
        r = self.cursor.execute("SELECT cost_price FROM products WHERE name=?", (n,)).fetchone()
        return r[0] if r else 0
    
    def get_all_products_stock(self):
        return self.cursor.execute("SELECT id, name, stock FROM products ORDER BY name ASC").fetchall()
    
    def update_product_field(self, pid, field, value):
        self.cursor.execute(f"UPDATE products SET {field}=? WHERE id=?", (value, pid))
        self.conn.commit()
    
    def update_product_fully(self, pid, name, cost, price, stock, cat, barcode, img, critical):
        self.cursor.execute("""UPDATE products SET name=?, cost_price=?, sell_price=?, stock=?, 
                            category=?, barcode=?, image_path=?, critical_stock=? WHERE id=?""",
                            (name, cost, price, stock, cat, barcode, img, critical, pid))
        self.conn.commit()
    
    def insert_product(self, name, cost, price, stock, cat, barcode, img, critical):
        m = self.cursor.execute("SELECT MAX(sort_order) FROM products").fetchone()[0] or 0
        self.cursor.execute("""INSERT INTO products (name, cost_price, sell_price, stock, category, 
                            barcode, image_path, critical_stock, sort_order) VALUES (?,?,?,?,?,?,?,?,?)""",
                            (name, cost, price, stock, cat, barcode, img, critical, m + 1))
        self.conn.commit()
    
    def toggle_favorite(self, pid, s):
        self.cursor.execute("UPDATE products SET is_favorite=? WHERE id=?", (s, pid))
        self.conn.commit()
    
    def delete_product(self, pid):
        self.cursor.execute("DELETE FROM products WHERE id=?", (pid,))
        self.conn.commit()
    
    def add_category(self, n):
        self.cursor.execute("INSERT INTO categories (name, sort_order) VALUES (?, 99)", (n,))
        self.conn.commit()

    def rename_category(self, old_name, new_name):
        try:
            self.cursor.execute("UPDATE categories SET name=? WHERE name=?", (new_name, old_name))
            # Ürünlerin de kategorisini güncellememiz lazım ki bağ kopmasın
            self.cursor.execute("UPDATE products SET category=? WHERE category=?", (new_name, old_name))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False # İsim çakışması
        
    def record_sale(self, items, total, method):
        profit = sum([(i['price'] - self.get_cost(i['name'])) * i['qty'] for i in items])
        self.cursor.execute(
            "INSERT INTO sales (total_amount, total_profit, payment_method, sale_date, receipt_no) VALUES (?,?,?,?,?)",
            (total, profit, method, str(datetime.date.today()), "TEMP"))
        sale_id = self.cursor.lastrowid
        today_str = datetime.datetime.now().strftime("%d.%m.%Y")
        receipt_no = f"{today_str}.{sale_id}"
        self.cursor.execute("UPDATE sales SET receipt_no=? WHERE id=?", (receipt_no, sale_id))
        alerts = []
        for i in items:
            self.cursor.execute("UPDATE products SET stock=stock-? WHERE name=?", (i['qty'], i['name']))
            self.cursor.execute(
                "INSERT INTO sale_items (sale_id, product_name, quantity, sell_price, cost_price, total_price, sale_date, sale_time) VALUES (?,?,?,?,?,?,?,?)",
                (sale_id, i['name'], i['qty'], i['price'], self.get_cost(i['name']), i['price'] * i['qty'],
                 str(datetime.date.today()), datetime.datetime.now().strftime("%H:%M")))
            r = self.cursor.execute("SELECT stock, critical_stock FROM products WHERE name=?", (i['name'],)).fetchone()
            if r and r[1] is not None and r[0] <= r[1]:
                alerts.append(f"• {i['name']} (Kalan: {r[0]})")
        self.conn.commit()
        return alerts
    
    def get_sales_history_extended(self):
        query = """
            SELECT s.id, s.receipt_no, s.sale_date, s.timestamp, s.payment_method, s.total_amount,
            (SELECT product_name FROM sale_items WHERE sale_id = s.id LIMIT 1) as first_prod
            FROM sales s ORDER BY s.id DESC
        """
        return self.cursor.execute(query).fetchall()
    
    def get_sale_items(self, sale_id):
        return self.cursor.execute(
            "SELECT product_name, quantity, sell_price, total_price FROM sale_items WHERE sale_id=?",
            (sale_id,)).fetchall()
    
    def get_filtered_stats(self, mode):
        now = datetime.datetime.now()
        if mode == 'day':
            date_str = str(datetime.date.today())
            query = f"""
                SELECT strftime('%H:00', sale_time) as label, SUM(total_price) as turnover, 
                SUM(total_price - (cost_price * quantity)) as profit
                FROM sale_items WHERE sale_date = '{date_str}' 
                GROUP BY strftime('%H', sale_time) ORDER BY sale_time ASC
            """
        elif mode == 'week':
            start_date = (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
            query = f"""
                SELECT sale_date as label, SUM(total_amount) as turnover, SUM(total_profit) as profit
                FROM sales WHERE sale_date >= '{start_date}' GROUP BY sale_date ORDER BY sale_date ASC
            """
        elif mode == 'month':
            start_date = now.replace(day=1).strftime('%Y-%m-%d')
            query = f"""
                SELECT sale_date as label, SUM(total_amount) as turnover, SUM(total_profit) as profit
                FROM sales WHERE sale_date >= '{start_date}' GROUP BY sale_date ORDER BY sale_date ASC
            """
        elif mode == 'year':
            start_year = now.strftime('%Y-01-01')
            query = f"""
                SELECT strftime('%Y-%m', sale_date) as label, SUM(total_amount) as turnover, SUM(total_profit) as profit
                FROM sales WHERE sale_date >= '{start_year}' GROUP BY strftime('%m', sale_date) ORDER BY label ASC
            """
            
        return self.cursor.execute(query).fetchall()
    # --- TOPLU İŞLEMLER ---
    def apply_bulk_update(self, category, operation, value):
        """Toplu fiyat güncelleme SQL mantığı"""
        sql_op = ""
        if operation == "Zam %": 
            sql_op = f"sell_price * (1 + {value}/100.0)"
        elif operation == "İndirim %": 
            sql_op = f"sell_price * (1 - {value}/100.0)"
        elif operation == "Zam TL": 
            sql_op = f"sell_price + {value}"
        elif operation == "İndirim TL": 
            sql_op = f"sell_price - {value}"
        
        # Eksiye düşmeyi önle (MAX(0, ...)) ve 2 hane yuvarla
        query = f"UPDATE products SET sell_price = ROUND(MAX(0, {sql_op}), 2)"
        
        params = []
        if category != "Tüm Ürünler":
            query += " WHERE category = ?"
            params.append(category)
        
        self.cursor.execute(query, params)
        self.conn.commit()
        return self.cursor.rowcount

    # --- YEDEKLEME ---
    def create_backup(self):
        """Veritabanını 'backups' klasörüne yedekler"""
        try:
            if not os.path.exists("backups"): 
                os.makedirs("backups")
            
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_name = f"backups/nexus_backup_{timestamp}.db"
            
            shutil.copy2(self.db_name, backup_name)
            return True, backup_name
        except Exception as e:
            return False, str(e)
    
# --- GRAFİK ---
class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        fig.patch.set_facecolor('#1a1a1a')
        self.axes = fig.add_subplot(111)
        self.axes.set_facecolor('#1a1a1a')
        super(MplCanvas, self).__init__(fig)


# --- UI BİLEŞENLERİ ---
class CustomerCartTab(QWidget):
    # Sinyaller: Toplam değiştiğinde veya Numpad kullanıldığında ana pencereye haber vermek için
    totalChanged = Signal(float) 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cart_data = [] # Her müşterinin kendi sepet verisi
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # --- TABLO ---
        self.table = QTableWidget()
        self.table.setColumnCount(4) # İsim, Fiyat, Adet, Sil Butonu
        self.table.setHorizontalHeaderLabels(["ÜRÜN", "FİYAT", "ADET", "İŞLEM"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch) # İsim genişlesin
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)   # Sil butonu sabit
        self.table.setColumnWidth(3, 80)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        
        # Stil
        self.table.setStyleSheet("""
            QTableWidget { background-color: #1e1e1e; border: none; color: #fff; gridline-color: #303030; font-size: 16px; }
            QTableWidget::item { padding: 5px; border-bottom: 1px solid #303030; }
            QTableWidget::item:selected { background-color: #0a84ff; color: #fff; }
            QLineEdit { background: #333; color: white; border: 1px solid #0a84ff; }
        """)

        # Hücre değişince tetiklenecek sinyal (Manuel düzenleme için)
        self.table.itemChanged.connect(self.on_item_changed)
        
        self.layout.addWidget(self.table)

    def add_item(self, name, price, qty=1):
        # Ürün zaten var mı?
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == name:
                # Varsa adeti artır
                current_qty = int(self.table.item(row, 2).text())
                self.update_row_qty(row, current_qty + qty)
                self.select_row(row)
                return

        # Yoksa yeni satır ekle
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # 1. İsim (Düzenlenebilir)
        item_name = QTableWidgetItem(name)
        item_name.setFlags(item_name.flags() | Qt.ItemIsEditable)
        self.table.setItem(row, 0, item_name)
        
        # 2. Fiyat (Düzenlenebilir)
        item_price = QTableWidgetItem(f"{float(price):.2f}")
        item_price.setFlags(item_price.flags() | Qt.ItemIsEditable)
        self.table.setItem(row, 1, item_price)
        
        # 3. Adet (Düzenlenebilir)
        item_qty = QTableWidgetItem(str(qty))
        item_qty.setTextAlignment(Qt.AlignCenter)
        item_qty.setFont(QFont("Segoe UI", 14, QFont.Bold))
        item_qty.setForeground(QColor("#30d158"))
        item_qty.setFlags(item_qty.flags() | Qt.ItemIsEditable)
        self.table.setItem(row, 2, item_qty)
        
        # 4. Akıllı Silme Butonu
        btn_del = QPushButton("Sil (-1)")
        btn_del.setStyleSheet("background-color: #ff453a; color: white; font-weight: bold; border-radius: 4px;")
        btn_del.clicked.connect(lambda: self.smart_delete(row))
        self.table.setCellWidget(row, 3, btn_del)
        
        self.select_row(row)
        self.recalc_total()

    def update_row_qty(self, row, new_qty):
        # Sinyali geçici olarak durdur (sonsuz döngüyü önlemek için)
        self.table.blockSignals(True)
        self.table.item(row, 2).setText(str(new_qty))
        self.table.blockSignals(False)
        self.recalc_total()

    def on_item_changed(self, item):
        self.recalc_total()

    def smart_delete(self, row=None):
        """Sil butonuna basınca: Adet > 1 ise azalt, 1 ise silmeyi sor"""
        if row is None: 
            row = self.table.currentRow()
        
        if row < 0: return

        try:
            qty_item = self.table.item(row, 2)
            
            if not qty_item: return
            
            qty = int(qty_item.text())
            
            if qty > 1:
                self.update_row_qty(row, qty - 1)
            else:
                reply = QMessageBox.question(self, "Sil", "Ürün sepetten kaldırılsın mı?", 
                                             QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.table.removeRow(row)
                    self.recalc_total()
                    
        except ValueError:
            pass # Sayı değilse işlem yapma
        except Exception as e:
            print(f"Hata: {e}")

class ProductCard(QFrame):
    def __init__(self, pid, name, price, img_path, is_fav, stock, click_cb, update_cb, db_manager, is_mini=False):
        super().__init__()
        self.pid = pid
        self.name_val = name
        self.price_val = price
        self.stock_val = stock
        self.cb = click_cb
        self.update_cb = update_cb
        self.db = db_manager
        self.fav = is_fav
        
        # Kart Boyutlandırma
        if is_mini:
            self.setFixedSize(140, 160) # İdeal boyut
            icon_size = 60
            font_sz = 13
            font_p_sz = 16
        else:
            self.setFixedSize(165, 195)
            icon_size = 70
            font_sz = 14
            font_p_sz = 20
        
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("ProductCard") # CSS'teki stilin uygulanması için şart
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        
        # --- 1. Menü Butonu (Sağ Üst Köşe - Absolute Positioning) ---
        # Layout içine koymuyoruz, doğrudan sağ üste sabitliyoruz.
        self.btn_menu = QPushButton("⋮", self)
        self.btn_menu.setGeometry(self.width() - 30, 5, 25, 25) # Sağ üst köşe
        self.btn_menu.setStyleSheet("""
            QPushButton { background: transparent; color: #888; font-weight: 900; font-size: 18px; border: none; }
            QPushButton:hover { color: white; background: rgba(255,255,255,0.1); border-radius: 12px; }
        """)
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.clicked.connect(self.show_options_menu)
        self.btn_menu.show() # Butonu görünür yap
        
        # --- 2. Yıldız İkonu (Favori ise görünür) ---
        if self.fav:
            self.lbl_star = QLabel("⭐", self)
            self.lbl_star.setGeometry(5, 5, 20, 20) # Sol üst köşe
            self.lbl_star.setStyleSheet("background: transparent; border: none; font-size: 14px;")
            self.lbl_star.show()

        # --- 3. İkon (Ortada) ---
        icon_cont = QWidget()
        ic_lay = QVBoxLayout(icon_cont)
        ic_lay.setContentsMargins(0, 10, 0, 0) # Üstten biraz boşluk (Menü ile çakışmasın)
        
        # Resim yoksa baş harfi göster
        icon = QLabel(name[0].upper() if name else "?")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(icon_size, icon_size)
        icon.setFont(QFont("Segoe UI", icon_size // 2.5, QFont.Bold))
        icon.setStyleSheet(f"background:#333; color:#0a84ff; border-radius:{icon_size // 2}px;")
        
        if img_path and os.path.exists(img_path):
            icon.setPixmap(QPixmap(img_path).scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        ic_lay.addWidget(icon, 0, Qt.AlignCenter)
        layout.addWidget(icon_cont)
        
        # --- 4. İsim ve Fiyat ---
        name_lbl = QLabel(name)
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(f"color:#e0e0e0; font-weight:600; font-size:{font_sz}px; border:none; background:transparent;")
        layout.addWidget(name_lbl)
        
        price_lbl = QLabel(f"{price:.2f} ₺")
        price_lbl.setAlignment(Qt.AlignCenter)
        price_lbl.setStyleSheet(f"color: #30d158; font-weight: 800; font-size: {font_p_sz}px; background-color: rgba(48, 209, 88, 0.1); border-radius: 6px; padding: 2px 5px;")
        layout.addWidget(price_lbl)
        
        if not is_mini:
            stock_lbl = QLabel(f"Stok: {stock}")
            stock_lbl.setAlignment(Qt.AlignCenter)
            stock_lbl.setStyleSheet("color: #888; font-size: 11px; margin-top: 2px; border:none; background:transparent;")
            layout.addWidget(stock_lbl)
        
        layout.addStretch()

    def mousePressEvent(self, e):
        # Menüye basınca kart tıklamasını iptal et
        child = self.childAt(e.position().toPoint())
        if hasattr(self, 'btn_menu') and child == self.btn_menu:
            return
        if e.button() == Qt.LeftButton:
            self.cb(self.name_val, self.price_val)

    def show_options_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #252525; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #0a84ff; }")
        
        # Favori Ekle / Çıkar
        fav_text = "⭐ Hızlı Erişimden Kaldır" if self.fav else "⭐ Hızlı Erişime Ekle"
        act_fav = menu.addAction(fav_text)
        act_fav.triggered.connect(self.toggle_fav)
        
        menu.addSeparator()
        
        # Fiyat Değiştir
        act_price = menu.addAction("💰 Fiyat Değiştir")
        act_price.triggered.connect(self.change_price)
        
        # İsim Değiştir
        act_name = menu.addAction("✏️ İsim Değiştir")
        act_name.triggered.connect(self.change_name)

        # Stok İşlemleri
        act_stock = menu.addAction("📦 Stok Sayım/Düzenle")
        act_stock.triggered.connect(self.change_stock)
        
        menu.addSeparator()
        
        # Kategori Taşıma
        cat_menu = menu.addMenu("📂 Kategoriye Taşı")
        cat_menu.setStyleSheet("QMenu { background-color: #252525; color: white; border: 1px solid #444; }")
        
        categories = self.db.get_all_categories()
        for cat in categories:
            if cat == "Tüm Ürünler": continue
            cat_menu.addAction(cat, lambda c=cat: self.move_to_category(c))
            
        menu.exec(QCursor.pos())

    # --- İşlevler ---
    def toggle_fav(self):
        self.db.toggle_favorite(self.pid, 0 if self.fav else 1)
        if self.update_cb: self.update_cb()

    def change_price(self):
        val, ok = QInputDialog.getDouble(self, "Fiyat", "Yeni Satış Fiyatı:", self.price_val, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "sell_price", val)
            if self.update_cb: self.update_cb()
            
    def change_name(self):
        text, ok = QInputDialog.getText(self, "İsim Değiştir", "Yeni Ürün Adı:", text=self.name_val)
        if ok and text:
            self.db.update_product_field(self.pid, "name", text)
            if self.update_cb: self.update_cb()

    def change_stock(self):
        val, ok = QInputDialog.getInt(self, "Stok", "Yeni Stok Adedi:", self.stock_val, -1000, 100000, 1)
        if ok:
            self.db.update_product_field(self.pid, "stock", val)
            if self.update_cb: self.update_cb()

    def move_to_category(self, cat_name):
        self.db.update_product_field(self.pid, "category", cat_name)
        if self.update_cb: self.update_cb()
        QMessageBox.information(self, "Taşındı", f"Ürün '{cat_name}' kategorisine taşındı.")


class MergedNumpad(QWidget):
    def __init__(self, target_callback):
        super().__init__()
        self.cb = target_callback
        self.setObjectName("NumpadContainer")
        layout = QGridLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(1, 1, 1, 1)
        keys = ['7', '8', '9', '4', '5', '6', '1', '2', '3', 'C', '0', '⌫']
        positions = [(i, j) for i in range(4) for j in range(3)]
        for position, key in zip(positions, keys):
            btn = QPushButton(key)
            btn.setFixedHeight(70)
            btn.setProperty("class", "NumBtn")
            if key == '⌫':
                btn.setStyleSheet("color: #ff453a; font-weight:900;")
            elif key == 'C':
                btn.setStyleSheet("color: #ff9f0a; font-weight:900;")
            btn.clicked.connect(lambda _, k=key: self.cb(k))
            layout.addWidget(btn, *position)


class ReceiptDialog(QDialog):
    def __init__(self, db, sale_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Fiş Detayı #{sale_id}")
        self.setFixedSize(380, 600)
        self.setStyleSheet("background-color: #fff; color: #000; font-family: 'Courier New'; font-size: 14px;")
        layout = QVBoxLayout(self)
        sale_info = db.cursor.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        items = db.get_sale_items(sale_id)
        html = f"""
        <div style='text-align: center;'>
            <h2>{SHOP_NAME}</h2>
            <p>Atatürk Blv. No:1923<br>İzmir / Karşıyaka<br>Vergi Dairesi: Karşıyaka<br>VN: 1234567890</p>
            <p>------------------------------------------</p>
            <p style='text-align: left;'>TARİH : {sale_info[6]}<br>FİŞ NO: {sale_info[1]}</p>
            <p>------------------------------------------</p>
        </div>
        <table width='100%'>
        """
        for name, qty, price, total in items:
            html += f"""<tr><td colspan='2' style='font-weight:bold;'>{name}</td></tr><tr><td align='right'>{qty} x {price:.2f}</td><td align='right'>{total:.2f} *</td></tr>"""
        html += f"""</table><p>------------------------------------------</p><table width='100%'><tr><td>TOPKDV</td><td align='right'>{(sale_info[2] * 0.18):.2f}</td></tr><tr><td style='font-size:18px; font-weight:bold;'>TOPLAM</td><td align='right' style='font-size:18px; font-weight:bold;'>{sale_info[2]:.2f}</td></tr></table><p>------------------------------------------</p><p>ÖDEME TİPİ: {sale_info[4].upper()}</p><br><div style='text-align: center;'><p>MALİ DEĞERİ YOKTUR<br>BİLGİ FİŞİDİR<br>TEŞEKKÜRLER</p></div>"""
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        layout.addWidget(scroll)

class ClickableLabel(QLabel):
    clicked = Signal()
    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class CategoryCard(QFrame):
    def __init__(self, name, click_cb, is_add_button=False, db_manager=None, refresh_cb=None, is_all_products=False):
        super().__init__()
        self.name = name
        self.cb = click_cb
        self.db = db_manager
        self.refresh_cb = refresh_cb
        self.is_add_button = is_add_button

        self.setFixedSize(130, 90) 
        self.setCursor(Qt.PointingHandCursor)

        # --- STİL SEÇİMİ (CSS ID Ataması) ---
        if is_all_products:
            self.setObjectName("CategoryCard_All") # Mavi Gradyan
            icon_bg = "rgba(255,255,255,0.2)"
            text_color = "white"
            icon_text = "♾️" 
        elif is_add_button:
            self.setObjectName("CategoryCard_Add") # Yeşil Kesikli
            icon_bg = "rgba(48, 209, 88, 0.1)"
            text_color = "#30d158"
            icon_text = "+"
        else:
            self.setObjectName("CategoryCard_Normal") # Standart Koyu
            icon_bg = "#333333"
            text_color = "#e0e0e0"
            icon_text = name[0].upper() if name else "?"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(5)

        # 1. İKON (Yuvarlak)
        icon_container = QLabel(icon_text)
        icon_container.setFixedSize(40, 40)
        icon_container.setAlignment(Qt.AlignCenter)
        icon_container.setStyleSheet(f"""
            background-color: {icon_bg}; 
            color: {text_color}; 
            border-radius: 20px; 
            font-size: 18px; 
            font-weight: bold;
            border: none;
        """)
        layout.addWidget(icon_container, 0, Qt.AlignCenter)

        # 2. METİN
        lbl_name = QLabel(name)
        lbl_name.setAlignment(Qt.AlignCenter)
        lbl_name.setWordWrap(True)
        lbl_name.setStyleSheet("background: transparent; border: none; font-weight: 600; font-size: 14px; color: " + text_color + ";")
        layout.addWidget(lbl_name)
        
        # MENÜ BUTONU
        if not is_add_button and not is_all_products:
            self.btn_menu = QPushButton("⋮", self)
            self.btn_menu.setGeometry(135, 5, 20, 20)
            self.btn_menu.setStyleSheet("background: transparent; color: #666; font-weight: bold; border: none;")
            self.btn_menu.setCursor(Qt.PointingHandCursor)
            self.btn_menu.clicked.connect(self.show_options)
            self.btn_menu.show()

    def mousePressEvent(self, e):
        child = self.childAt(e.position().toPoint())
        if hasattr(self, 'btn_menu') and child == self.btn_menu:
            return
        if e.button() == Qt.LeftButton:
            self.cb(self.name)

    def show_options(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #252525; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #0a84ff; }")
        act_rename = menu.addAction("✏️ İsim Değiştir")
        act_rename.triggered.connect(self.rename_category)
        menu.exec(QCursor.pos())

    def rename_category(self):
        new_name, ok = QInputDialog.getText(self, "İsim Değiştir", "Yeni Kategori Adı:", text=self.name)
        if ok and new_name:
            if self.db.rename_category(self.name, new_name):
                QMessageBox.information(self, "Başarılı", "Kategori güncellendi.")
                if self.refresh_cb: self.refresh_cb()


# =================
# AI SERVICE 
# =================
class AIService:
    def __init__(self, db_path="voidpos.db"):
        self.db_path = db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def suggest_bundles(self):
        """Birlikte satılması muhtemel ürün ikililerini bulur (Cross-Sell)."""
        try:
            conn = self.get_connection()
            # Birlikte en çok satılan ikilileri bul
            query = """
                SELECT a.product_name, b.product_name, COUNT(*) as frequency
                FROM sale_items a
                JOIN sale_items b ON a.sale_id = b.sale_id
                WHERE a.product_name < b.product_name 
                GROUP BY a.product_name, b.product_name
                ORDER BY frequency DESC
                LIMIT 3
            """
            pairs = conn.execute(query).fetchall()
            conn.close()
            
            bundles = []
            if not pairs: return None
            
            for p1, p2, freq in pairs:
                # Frekans düşükse önerme
                if freq < 2: continue 
                
                bundles.append(f"📦 **{p1} + {p2} Kampanyası**\n   Bu ikili {freq} kez birlikte satıldı. Paket yapıp vitrine koyun!")
                
            return bundles
        except:
            return None
        
    # --- 1. GÖRSEL TAHMİN VERİSİ ---
    def get_forecast_data(self, days=7):
        """Grafik çizimi için geçmiş ve gelecek verisini hazırlar."""
        try:
            conn = self.get_connection()
            # Son 30 günün verisini al (Geçmişi çizmek için)
            query = """
                SELECT sale_date, SUM(total_amount) as total 
                FROM sales 
                WHERE sale_date >= date('now', '-30 days')
                GROUP BY sale_date ORDER BY sale_date ASC
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < 5: return None, "Yetersiz Veri"

            # Tarih dönüşümleri
            df['sale_date'] = pd.to_datetime(df['sale_date'])
            df['ordinal'] = df['sale_date'].map(datetime.datetime.toordinal)

            # Eğit
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(df[['ordinal']], df['total'])

            # Gelecek Tahmini
            future_dates = []
            future_vals = []
            last_date = datetime.date.today()
            
            for i in range(1, days + 1):
                next_day = last_date + datetime.timedelta(days=i)
                pred = model.predict([[next_day.toordinal()]])[0]
                future_dates.append(next_day.strftime("%d.%m")) # Grafik için kısa tarih
                future_vals.append(round(pred, 2))

            # Geçmiş Veriler (Grafik için)
            history_dates = df['sale_date'].dt.strftime("%d.%m").tolist()
            history_vals = df['total'].tolist()

            return {
                "history": (history_dates, history_vals),
                "forecast": (future_dates, future_vals)
            }, "Başarılı"
        except Exception as e:
            return None, str(e)

    # --- 2. YOĞUNLUK ANALİZİ (PERSONEL PLANLAMA) ---
    def analyze_busy_hours(self):
        """Günün hangi saatleri yoğun? Ekstra personel lazım mı?"""
        try:
            conn = self.get_connection()
            # SQLite'da saat bilgisini çek (HH)
            query = "SELECT strftime('%H', timestamp) as hour, COUNT(*) as count FROM sales GROUP BY hour"
            df = pd.read_sql(query, conn)
            conn.close()

            if df.empty: return None

            # En yoğun saati bul
            busiest = df.loc[df['count'].idxmax()]
            busy_hour = int(busiest['hour'])
            
            # Tavsiye Oluştur
            advice = ""
            if busy_hour >= 17 and busy_hour <= 20:
                advice = "Akşam iş çıkışı yoğunluğu. 2. Kasa açılmalı."
            elif busy_hour >= 11 and busy_hour <= 13:
                advice = "Öğle arası yoğunluğu. Hızlı kasa modu aktif edilmeli."
            else:
                advice = "Standart yoğunluk."

            return {
                "busiest_hour": f"{busy_hour}:00 - {busy_hour+1}:00",
                "transaction_count": busiest['count'],
                "advice": advice
            }
        except:
            return None

    # --- 3. ÖLÜ STOK ANALİZİ (İNDİRİM ÖNERİSİ) ---
    # AIService Sınıfı İçindeki Eski Fonksiyonu Bununla Değiştirin:

    def suggest_discounts(self):
        """Kâr marjını koruyarak ölü stok indirimi önerir."""
        try:
            conn = self.get_connection()
            # Stokta > 5 olan ama son 10 gündür satılmayan ürünleri bul
            # Ayrıca maliyet fiyatını da çekiyoruz
            query = """
                SELECT name, stock, sell_price, cost_price FROM products 
                WHERE stock > 5 
                AND name NOT IN (
                    SELECT DISTINCT product_name FROM sale_items 
                    WHERE sale_date >= date('now', '-10 days')
                )
            """
            products = conn.execute(query).fetchall()
            conn.close()
            
            suggestions = []
            for name, stock, sell_price, cost_price in products:
                # Varsayılan %15 indirim
                discounted_price = sell_price * 0.85
                profit = discounted_price - cost_price
                
                margin_percent = (profit / discounted_price) * 100 if discounted_price > 0 else 0
                
                if profit > 0:
                    status = f"✅ Kârlı İndirim (Marj: %{margin_percent:.1f})"
                    color = "#30d158" # Yeşil
                else:
                    status = f"⚠️ Zararına Satış (Zarar: {abs(profit):.2f} TL)"
                    color = "#ff453a" # Kırmızı
                
                msg = f"{status} -> {name}: {sell_price} ₺ yerine {discounted_price:.2f} ₺ yapın. (Stok: {stock})"
                suggestions.append((msg, color))
            
            return suggestions
        except:
            return []

    # --- (Eski Özellikler Korunuyor: Anomali, Segmentasyon, Ürün Önerisi) ---
    def detect_anomalies(self):
        # ... (Eski kodunuzdaki detect_anomalies içeriği aynen kalsın) ...
        try:
            conn = self.get_connection()
            df = pd.read_sql("SELECT id, total_amount, sale_date FROM sales", conn)
            conn.close()
            if len(df) < 10: return None
            model = IsolationForest(contamination=0.05, random_state=42)
            df['anomaly'] = model.fit_predict(df[['total_amount']])
            return df[df['anomaly'] == -1].values.tolist()
        except: return None

    def segment_baskets(self):
        # ... (Eski kodunuzdaki segment_baskets içeriği aynen kalsın) ...
        try:
            conn = self.get_connection()
            df = pd.read_sql("SELECT total_amount FROM sales", conn)
            conn.close()
            if len(df) < 10: return None
            kmeans = KMeans(n_clusters=3, random_state=42)
            df['cluster'] = kmeans.fit_predict(df[['total_amount']])
            centers = kmeans.cluster_centers_
            sorted_indices = np.argsort(centers.flatten())
            mapping = {sorted_indices[0]: "Düşük", sorted_indices[1]: "Orta", sorted_indices[2]: "VIP"}
            return df['cluster'].map(mapping).value_counts().to_dict()
        except: return None

    def recommend_product(self, current_cart_names):
        # ... (Eski kodunuzdaki recommend_product içeriği aynen kalsın) ...
        if not current_cart_names: return None
        try:
            conn = self.get_connection()
            placeholders = ','.join(['?'] * len(current_cart_names))
            query = f"""
                SELECT s2.product_name, COUNT(*) as cnt
                FROM sale_items s1
                JOIN sale_items s2 ON s1.sale_id = s2.sale_id
                WHERE s1.product_name IN ({placeholders})
                AND s2.product_name NOT IN ({placeholders})
                GROUP BY s2.product_name
                ORDER BY cnt DESC LIMIT 1
            """
            res = conn.execute(query, current_cart_names).fetchone()
            conn.close()
            return res[0] if res else None
        except: return None

    # --- 4. AKILLI STOK UYARISI ---
    def check_critical_stock_smart(self):
        """Satış hızına göre dinamik stok uyarısı."""
        try:
            conn = self.get_connection()
            query = """
                SELECT product_name, SUM(quantity) as total_sold, p.stock
                FROM sale_items s
                JOIN products p ON s.product_name = p.name
                WHERE s.sale_date >= date('now', '-7 days')
                GROUP BY product_name
            """
            df = pd.read_sql(query, conn)
            conn.close()

            alerts = []
            for _, row in df.iterrows():
                avg_daily_sales = row['total_sold'] / 7
                if avg_daily_sales == 0: continue
                
                suggested_min = (avg_daily_sales * 3) + 2 # 3 günlük stok + 2 güvenlik
                
                if row['stock'] < suggested_min:
                    alerts.append(f"{row['product_name']}: Stok {row['stock']} (Önerilen Min: {int(suggested_min)})")
            return alerts
        except:
            return []
    
    # --- 5. ÜRÜN ÖNERİSİ ---
    def recommend_product(self, current_cart_names):
        """Sepetteki ürünlerin yanına ne gider?"""
        if not current_cart_names: return None
        try:
            conn = self.get_connection()
            placeholders = ','.join(['?'] * len(current_cart_names))
            query = f"""
                SELECT s2.product_name, COUNT(*) as cnt
                FROM sale_items s1
                JOIN sale_items s2 ON s1.sale_id = s2.sale_id
                WHERE s1.product_name IN ({placeholders})
                AND s2.product_name NOT IN ({placeholders})
                GROUP BY s2.product_name
                ORDER BY cnt DESC
                LIMIT 1
            """
            cursor = conn.cursor()
            res = cursor.execute(query, current_cart_names).fetchone()
            conn.close()
            return res[0] if res else None
        except:
            return None

# Hatalı kısmı silip bunu yapıştır:
class AIBackgroundWorker(QThread):
    finished = Signal(list) 
    error = Signal(str)

    def __init__(self, db_manager):
        super().__init__()
        self.db = db_manager

    def run(self):
        try:
            conn = sqlite3.connect(self.db.db_name)
            cursor = conn.cursor()
            
            # --- PROFESYONEL SORGULAMA ---
            # 1. Adım: Sadece son 30 günde satışı olan ürünleri ve ne kadar sattıklarını bul.
            # Ürünler tablosuyla birleştirerek güncel stoğu da al.
            query = """
                SELECT p.id, p.name, p.stock, SUM(s.quantity) as toplam_satis
                FROM sale_items s
                JOIN products p ON s.product_name = p.name
                WHERE s.sale_date >= date('now', '-30 days')
                GROUP BY p.name
            """
            cursor.execute(query)
            aktif_urunler = cursor.fetchall()
            conn.close()

            oneriler = []
            analiz_suresi = 30 # Son 30 günü baz alıyoruz

            for pid, name, stock, toplam_satis in aktif_urunler:
                # 2. Adım: Satış Hızını Hesapla (Adet / Gün)
                gunluk_ortalama = toplam_satis / analiz_suresi
                
                # Eğer ürün çok çok az satıyorsa (Ayda 1-2 tane) uyarı vermeye değmez
                if gunluk_ortalama < 0.1: 
                    continue

                # 3. Adım: Kritik Eşik Belirle (Ürün bizi kaç gün idare eder?)
                # Güvenlik stoğu: Ürünün bitmesine 3 günden az kaldıysa uyar.
                kalan_gun_omru = stock / gunluk_ortalama if gunluk_ortalama > 0 else 0
                
                if kalan_gun_omru <= 3:
                    # 4. Adım: Akıllı Sipariş Miktarı Hesapla
                    # Bizi 14 gün (2 hafta) idare edecek kadar sipariş öner.
                    hedef_stok = int(gunluk_ortalama * 14) 
                    gereken_siparis = hedef_stok - stock
                    
                    # Sipariş miktarı çok küçükse (örn: 1 tane) yuvarla
                    if gereken_siparis < 5: gereken_siparis = 10 

                    # Mesajı Hazırla
                    acil_durum = "ÇOK ACİL" if kalan_gun_omru < 1 else "Dikkat"
                    
                    oneriler.append({
                        "tur": "STOK",
                        "mesaj": f"📉 {acil_durum}: **{name}**\n"
                                 f"• Günlük Satış Hızı: {gunluk_ortalama:.1f} adet\n"
                                 f"• Kalan Stok: {stock} (Yeteceği gün: {kalan_gun_omru:.1f})\n"
                                 f"• Öneri: **{gereken_siparis}** adet sipariş verin (2 haftalık stok).",
                        "aksiyon_verisi": {"id": pid, "islem": "siparis_ver"}
                    })
            
            self.finished.emit(oneriler)

        except Exception as e:
            self.error.emit(str(e))
            
class VoidAI_Engine:
    def __init__(self, csv_adi="urunler.csv"):
        base_path = get_app_path()
        
        self.klasor_yolu = os.path.join(base_path, "urunler_klasoru")
        
        if not os.path.exists(self.klasor_yolu):
            os.makedirs(self.klasor_yolu)
            
        self.csv_yolu = os.path.join(self.klasor_yolu, csv_adi)
        
        self.db_path = os.path.join(base_path, "voidpos.db")

    def verileri_cek(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Not: Tablo adlarının doğruluğundan emin ol (products vs urunler)
        try:
            cursor.execute("SELECT id, name, stock, critical_stock FROM products")
            veriler = cursor.fetchall()
        except:
            veriler = []
        conn.close()
        
        urun_listesi = []
        for v in veriler:
            urun_listesi.append({
                "id": v[0], "ad": v[1], "stok": v[2], "kritik": v[3], "skt": "2030-01-01" # SKT yoksa varsayılan
            })
        return urun_listesi
    
    def verileri_oku(self):
        """CSV dosyasını okur ve bir liste olarak döndürür."""
        if not os.path.exists(self.csv_yolu):
            return []
        
        veriler = []
        with open(self.csv_yolu, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            for row in reader:
                veriler.append(row)
        return veriler

    def tum_analizleri_yap(self):
        """
        Kritik stoğun altındaki ürünleri kontrol eder.
        ANCAK: Sadece son 30 gün içinde satışı olan (Aktif) ürünleri dikkate alır.
        Böylece 'Ölü Stok' için gereksiz sipariş uyarısı vermez.
        """
        conn = sqlite3.connect(self.db_path)
        
        # SORGUYU GÜNCELLEDİK:
        # products tablosu ile sale_items tablosunu birleştiriyoruz (JOIN).
        # Sadece son 30 günde satışı olanları seçiyoruz.
        query = """
            SELECT DISTINCT p.id, p.name, p.stock, p.critical_stock, p.sell_price 
            FROM products p
            JOIN sale_items s ON p.name = s.product_name
            WHERE p.stock <= p.critical_stock
            AND s.sale_date >= date('now', '-30 days')
        """
        
        try:
            cursor = conn.execute(query)
            kritik_aktif_urunler = cursor.fetchall()
        except Exception as e:
            print(f"AI Analiz Hatası: {e}")
            kritik_aktif_urunler = []
        finally:
            conn.close()

        oneriler = []
        for pid, ad, stok, kritik, fiyat in kritik_aktif_urunler:
            # Kritik stok boş gelebilir, varsayılan 5 yapalım
            kritik_limiti = kritik if kritik is not None else 5
            
            eksik = (kritik_limiti * 2) - stok
            if eksik < 1: eksik = 5 # En az 5 tane sipariş verdir
            
            oneriler.append({
                "tur": "SIPARIS",
                "mesaj": f"📦 STOK ALARMI (Aktif Ürün): {ad}\nStok: {stok} (Kritik: {kritik_limiti}).\nBu ürün satılıyor, acil {eksik} adet sipariş geçilmeli.",
                "aksiyon_verisi": {"id": pid, "islem": "mail_at", "miktar": eksik, "yeni_fiyat": fiyat}
            })
        
        return oneriler

    def aksiyonu_uygula(self, aksiyon_verisi):
        if aksiyon_verisi["islem"] == "mail_at":
            return f"Tedarikçiye {aksiyon_verisi['miktar']} adetlik sipariş maili gönderildi. ✅"
        elif aksiyon_verisi["islem"] == "fiyat_dusur":
            return f"Fiyat güncellendi. ✅"
        return "İşlem başarısız."

# --- ANA UYGULAMA ---
class NexusPOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.denominations = [200, 100, 50, 20, 10, 5, 1, 0.50, 0.25]
        self.db = DatabaseManager()
        self.cart_data = []
        try:
            urun_sayisi = self.db.cursor.execute("SELECT Count(*) FROM products").fetchone()[0]
            if urun_sayisi == 0:
                print("Veritabanı boş. CSV aranıyor...")
                csv_yolu = os.path.join(get_app_path(), "urunler_temiz.csv")
                
                if os.path.exists(csv_yolu):
                    basari, mesaj = self.db.import_products_from_csv(csv_yolu)
                    print(f"Otomatik Yükleme Sonucu: {mesaj}")
                else:
                    print(f"UYARI: {csv_yolu} dosyası bulunamadı!")
        except Exception as e:
            print(f"Otomatik yükleme hatası: {e}")
            
        self.selected_row = -1
        self.barcode_buffer = ""
        self.ciro_visible = True # Ciro görünürlük durumu
        
        self.init_ui()
        self.setWindowTitle("VoidPOS")
        self.resize(1600, 900)
        self.ai = AIService("voidpos.db")
        base_path = get_app_path()
        klasor_yolu = os.path.join(base_path, "urunler_klasoru")
        csv_path = os.path.join(get_app_path(), "urunler_temiz.csv")
        if not os.path.exists(klasor_yolu):
            os.makedirs(klasor_yolu)
        self.db.export_products_to_csv("urunler_klasoru/urunler.csv")
        self.ai_timer = QTimer(self)
        self.ai_timer.timeout.connect(self.ai_otomatik_kontrol)
        self.ai_timer.start(10000) # 10.000 ms = 10 
        
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QHBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        
        # --- 1. SOL PANEL (AYNI) ---
        left_container = QFrame()
        left_container.setFixedWidth(520)
        left_container.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(left_container)
        
        # Arama
        search_cont = QWidget()
        search_lay = QHBoxLayout(search_cont)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Ürün Ara...")
        self.search_bar.setFixedHeight(40)
        self.search_bar.textChanged.connect(self.on_search_changed)
        search_lay.addWidget(self.search_bar)
        left_layout.addWidget(search_cont)
        
        # Ürün Grid
        self.selection_scroll = QScrollArea()
        self.selection_scroll.setWidgetResizable(True)
        self.selection_scroll.setStyleSheet("border:none; background:transparent;")
        self.selection_cont = QWidget()
        self.selection_lay = QGridLayout(self.selection_cont)
        self.selection_scroll.setWidget(self.selection_cont)
        left_layout.addWidget(self.selection_scroll)
        
        main_lay.addWidget(left_container)

        # --- 2. ORTA PANEL (MODERN SEPET) ---
        center_container = QFrame()
        # border-right ile sağ paneli ayırıyoruz ama kendi etrafında kutu yok
        center_container.setObjectName("CenterPanel")        
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(10, 20, 10, 10) # Üstten biraz boşluk
        
        # Üst Bar
        top_bar = QHBoxLayout()
        self.lbl_ciro = ClickableLabel(f"Ciro: {self.db.get_daily_turnover():.2f} ₺")
        self.lbl_ciro.setObjectName("CiroBox")
        self.lbl_ciro.clicked.connect(self.toggle_ciro_visibility)
        top_bar.addWidget(self.lbl_ciro)
        top_bar.addStretch()
        btn_admin = QPushButton("YÖNETİM")
        btn_admin.setProperty("class", "TopBarBtn")
        btn_admin.clicked.connect(self.open_admin)
        top_bar.addWidget(btn_admin)
        center_layout.addLayout(top_bar)
        self.ai_btn = QPushButton("AI: Sistem Stabil")
        self.ai_btn.setProperty("class", "TopBarBtn") 
        self.ai_btn.setCursor(Qt.PointingHandCursor)        
        self.ai_btn.clicked.connect(self.ai_analiz_butonuna_tiklandi)
        top_bar.addWidget(self.ai_btn)
        # Tıklayınca manuel analiz fonksiyonuna gidecek
        self.ai_btn.clicked.connect(self.ai_analiz_butonuna_tiklandi)
        top_bar.addWidget(self.ai_btn)

        # Toplam Tutar (Sepetin üstünde daha şık durur)
        self.lbl_total = QLabel("0.00 ₺")
        self.lbl_total.setAlignment(Qt.AlignRight)
        self.lbl_total.setStyleSheet("font-size: 70px; font-weight:900; color:white; margin: 20px 0;")
        
        # --- SEKMELİ SEPET (ÇERÇEVESİZ) ---
        self.cart_tabs = QTabWidget()
        # QTabWidget::pane { border: none; } diyerek o dış kutuyu siliyoruz
        self.cart_tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab { background: transparent; color: #666; font-size: 16px; font-weight: bold; padding: 10px 15px; margin-right: 10px; }
            QTabBar::tab:selected { color: #0a84ff; border-bottom: 2px solid #0a84ff; }
            QTabBar::tab:hover { color: #ddd; }
        """)
        
        self.cart_tabs.currentChanged.connect(self.recalc_active_cart_total)

        for i in range(1, 4):
            new_table = self.create_cart_table()
            self.cart_tabs.addTab(new_table, f"Müşteri {i}")
        
        self.table = self.cart_tabs.currentWidget()

        center_layout.addWidget(self.cart_tabs)
        center_layout.addWidget(self.lbl_total)
        
        main_lay.addWidget(center_container, stretch=1)

        # --- 3. SAĞ PANEL (AYNI) ---
        right_container = QFrame()
        right_container.setFixedWidth(400)
        right_container.setObjectName("RightPanel")
        right_layout = QVBoxLayout(right_container)
        
        self.change_panel = self.create_change_list_panel()
        right_layout.addWidget(self.change_panel, stretch=1)
        
        self.numpad = MergedNumpad(self.numpad_action)
        right_layout.addWidget(self.numpad, stretch=0)
        

        pay_lay = QHBoxLayout()
        pay_lay.setSpacing(15) # Butonlar arası boşluk
        
        # NAKİT BUTONU
        btn_cash = QPushButton("NAKİT")
        btn_cash.setObjectName("BtnCash")  # <--- CSS'teki #BtnCash buna bağlanır
        btn_cash.setFixedHeight(90)        # <--- Yükseklik veriyoruz ki kaybolmasın
        btn_cash.setCursor(Qt.PointingHandCursor)
        btn_cash.clicked.connect(lambda: self.finish_sale("Nakit"))
        
        # KART BUTONU
        btn_card = QPushButton("KART")
        btn_card.setObjectName("BtnCard")  # <--- CSS'teki #BtnCard buna bağlanır
        btn_card.setFixedHeight(90)        # <--- Yükseklik veriyoruz
        btn_card.setCursor(Qt.PointingHandCursor)
        btn_card.clicked.connect(self.card_payment)
        
        pay_lay.addWidget(btn_cash)
        pay_lay.addWidget(btn_card)
        right_layout.addLayout(pay_lay)
        
        main_lay.addWidget(right_container)
        
        self.load_categories_grid()

    
    def set_payment_processing(self, is_processing, btn_type=""):
        """
        İşlem sırasında butonları kilitler ve görsel geri bildirim verir.
        btn_type: 'NAKİT' veya 'KART'
        """
        # Sağ paneldeki butonları bul (Object Name ile)
        # Not: Butonları oluştururken setProperty("class", "PayBtn") kullanmıştık ama
        # findChild için setObjectName kullanmak daha garantidir. 
        # Aşağıda buton oluşturma kodunda objectName ekleyeceğiz.
        
        btn_cash = self.findChild(QPushButton, "BtnCash") 
        btn_card = self.findChild(QPushButton, "BtnCard") 

        if is_processing:
            # İşlem BAŞLADI: Butonları kilitle (Çift tıklama olmasın)
            if btn_cash: btn_cash.setEnabled(False)
            if btn_card: btn_card.setEnabled(False)
            
            # Görsel Efekt (Sarı Kenarlık ve Yazı)
            style_processing = "background-color:#30d158; color:black; border: 4px solid #ffcc00; height: 80px; font-size:18px;"
            style_processing_card = "background-color:#0a84ff; color:white; border: 4px solid #ffcc00; height: 80px; font-size:18px;"

            if btn_type == "NAKİT" and btn_cash:
                btn_cash.setText("⏳ İŞLENİYOR...")
                btn_cash.setStyleSheet(style_processing)
            elif btn_type == "KART" and btn_card:
                btn_card.setText("⏳ POS BEKLENİYOR...")
                btn_card.setStyleSheet(style_processing_card)
                
        else:
            # İşlem BİTTİ: Butonları aç ve eski haline getir
            if btn_cash: 
                btn_cash.setEnabled(True)
                btn_cash.setText("NAKİT")
                btn_cash.setStyleSheet("background-color:#30d158; color:black; height: 80px;")
                
            if btn_card: 
                btn_card.setEnabled(True)
                btn_card.setText("KART")
                btn_card.setStyleSheet("background-color:#0a84ff; color:white; height: 80px;")

    def create_cart_table(self):
        """Çerçevesiz ve modern tablo oluşturur."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["ÜRÜN", "FİYAT", "ADET", " "]) # İşlem başlığını boş bıraktık
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) 
        header.setSectionResizeMode(1, QHeaderView.Fixed)   
        header.setSectionResizeMode(2, QHeaderView.Fixed)   
        header.setSectionResizeMode(3, QHeaderView.Fixed)   
        
        table.setColumnWidth(1, 100) 
        table.setColumnWidth(2, 60)  
        table.setColumnWidth(3, 80)  

        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setShowGrid(False) # Izgaraları kapattık
        
        # CSS ile çizgileri yönetiyoruz
        # border: none -> Tablo çerçevesi yok
        # QHeaderView::section -> Başlık altındaki çizgi hariç kenarlık yok
        table.setStyleSheet("background-color: transparent; border: none;")

        table.itemChanged.connect(self.on_cart_item_changed)
        table.itemClicked.connect(self.row_selected)
        
        return table
    
    def create_change_list_panel(self):
        """Sağ paneldeki liste şeklindeki para üstü alanını oluşturur"""
        frame = QFrame()
        frame.setObjectName("ChangeFrame")
        
        # Panelin dikeyde genişlemesine izin ver (QSizePolicy)
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(0) # Satır aralarını grid ile halledeceğiz

        # Başlık
        lbl_head = QLabel("PARA ÜSTÜ")
        lbl_head.setStyleSheet("color: #888; font-size: 14px; font-weight: 800; letter-spacing: 1px; margin-bottom: 10px; border:none; background:transparent;")
        lbl_head.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_head)

        # Izgara (Grid) Yapısı
        self.change_grid_widget = QWidget()
        self.change_grid = QGridLayout(self.change_grid_widget)
        self.change_grid.setContentsMargins(0, 0, 0, 0)
        self.change_grid.setHorizontalSpacing(10) 
        
        # --- BURASI ÖNEMLİ: Satır aralığını açıyoruz ---
        self.change_grid.setVerticalSpacing(12) 
        # -----------------------------------------------
        
        self.change_labels = {} 
        self.denominations = [1000, 900, 800, 700, 600, 500, 400, 300, 200, 100, 50]

        for i, amount in enumerate(self.denominations):
            # Yazı boyutlarını (font-size) artırdık:
            
            # 1. Sütun
            lbl_denom = QLabel(f"{amount}")
            lbl_denom.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # font-size: 20px yaptık
            lbl_denom.setStyleSheet("color: #cccccc; font-size: 20px; font-weight: bold; border:none; background:transparent; font-family: 'Consolas', monospace;")
            
            # 2. Sütun
            lbl_arrow = QLabel("➔")
            lbl_arrow.setAlignment(Qt.AlignCenter)
            lbl_arrow.setStyleSheet("color: #555555; font-size: 16px; border:none; background:transparent;")
            
            # 3. Sütun
            lbl_res = QLabel("---")
            lbl_res.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            # font-size: 22px yaptık
            lbl_res.setProperty("class", "ChangeResultError")
            # Varsayılan stil (başlangıç için)
            lbl_res.setStyleSheet("color: #444; font-size: 22px; font-weight: bold; border:none; background:transparent; font-family: 'Consolas', monospace;")
            
            self.change_grid.addWidget(lbl_denom, i, 0)
            self.change_grid.addWidget(lbl_arrow, i, 1)
            self.change_grid.addWidget(lbl_res, i, 2)
            
            self.change_labels[amount] = lbl_res

        layout.addWidget(self.change_grid_widget)
        layout.addStretch() # Altta boşluk bırakıp listeyi yukarı it
        return frame

    def update_change_list(self):
        """Sepet toplamına göre listedeki rakamları günceller"""
        if not self.cart_data:
            total = 0.0
        else:
            total = sum([item['price'] * item['qty'] for item in self.cart_data])

        for amount in self.denominations:
            label = self.change_labels.get(amount)
            if not label: continue

            if total > 0 and amount >= total:
                diff = amount - total
                label.setText(f"{diff:.2f}")
                label.setProperty("class", "ChangeResult")
            else:
                label.setText("---")
                label.setProperty("class", "ChangeResultError")
            
            label.style().unpolish(label)
            label.style().polish(label)

    def refresh_ui(self):
        """UI Yenileme"""
        self.search_bar.clear()
        self.load_categories_grid()
        self.update_ciro()

    def clear_selection_area(self):
        """Grid alanını temizler"""
        while self.selection_lay.count():
            item = self.selection_lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def load_products_grid(self, category_name):
        self.clear_selection_area()
        self.selection_lay.setAlignment(Qt.AlignTop)
        self.selection_scroll.setStyleSheet("border: none; background: transparent;") 
        # --- Geri Dön Butonu ---
        btn_back = QPushButton(f"⬅ {category_name} (Geri Dön)")
        btn_back.setFixedHeight(40)
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton { background-color: transparent; color: #0a84ff; font-size: 16px; font-weight: bold; text-align: left; border: none; }
            QPushButton:hover { color: white; }
        """)
        btn_back.clicked.connect(self.load_categories_grid)
        # Grid'in en üstüne, boydan boya yayılacak şekilde ekle
        self.selection_lay.addWidget(btn_back, 0, 0, 1, 4) 
        
        # Ürünleri Çek
        products = self.db.get_products(category_name)
        
        if not products:
            lbl = QLabel("Bu kategoride ürün yok.")
            lbl.setStyleSheet("color: #666; margin-top: 20px; font-size: 14px;")
            self.selection_lay.addWidget(lbl, 1, 0, 1, 4)
            return

        col = 0
        row = 1 # 0. satırda Geri butonu var
        max_col = 3 # Yan yana kaç ürün olsun?
        
        for pid, name, price, img, fav, stock in products:
            def on_click(n, p):
                self.add_to_cart(n, p)
            
            card = ProductCard(pid, name, price, img, fav, stock, on_click, lambda: self.load_products_grid(category_name), self.db, is_mini=True)
            # Boyutu biraz ayarlayalım ızgaraya sığsın
            card.setFixedSize(140, 160) 
            
            self.selection_lay.addWidget(card, row, col)
            
            col += 1
            if col >= max_col:
                col = 0
                row += 1

    def load_categories_grid(self):
        self.clear_selection_area()
        self.search_bar.setPlaceholderText("🔍 Tüm ürünlerde ara...")
        
        # Layout Ayarları
        self.selection_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # --- BAŞLIKLAR (Eski koddaki gibi) ---
        lbl_cat = QLabel("KATEGORİLER")
        lbl_cat.setStyleSheet("color: #0a84ff; font-weight: 800; font-size: 14px; margin: 10px 0 5px 10px;")
        self.selection_lay.addWidget(lbl_cat, 0, 0, 1, 3)

        # --- SCROLL VE GRID ---
        cat_scroll = QScrollArea()
        cat_scroll.setFixedHeight(320) # Yükseklik artırıldı
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setStyleSheet("border: none; background: transparent;")
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cat_container = QWidget()
        cat_grid = QGridLayout(cat_container)
        cat_grid.setContentsMargins(10, 0, 10, 0)
        cat_grid.setSpacing(15)
        cat_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # 1. TÜM ÜRÜNLER KARTI (Özel Stil)
        def show_all():
            self.load_products_grid("Tüm Ürünler")
        all_card = CategoryCard("Tüm Ürünler", lambda x: show_all(), is_all_products=True)
        cat_grid.addWidget(all_card, 0, 0)

        # 2. DİĞER KATEGORİLER
        categories = self.db.get_all_categories()
        c_row = 0
        c_col = 1 
        max_cat_col = 3 

        for cat in categories:
            if cat == "Tüm Ürünler": continue
            card = CategoryCard(cat, self.load_products_grid, is_add_button=False, db_manager=self.db, refresh_cb=self.refresh_ui)
            cat_grid.addWidget(card, c_row, c_col)
            c_col += 1
            if c_col >= max_cat_col:
                c_col = 0
                c_row += 1
        
        # 3. EKLEME KARTI
        def trigger_add_cat(_):
            self.add_category()
        add_card = CategoryCard("Kategori Ekle", trigger_add_cat, is_add_button=True)
        cat_grid.addWidget(add_card, c_row, c_col)

        cat_scroll.setWidget(cat_container)
        self.selection_lay.addWidget(cat_scroll, 1, 0, 1, 3)

        # --- ALT KISIM (ARA ÇİZGİ VE FAVORİLER) ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333; margin: 15px 0;")
        self.selection_lay.addWidget(line, 2, 0, 1, 3)

        lbl_fav = QLabel("HIZLI ERİŞİM")
        lbl_fav.setStyleSheet("color: #ffcc00; font-weight: 800; font-size: 14px; margin-left: 10px;")
        self.selection_lay.addWidget(lbl_fav, 3, 0, 1, 3)

        # Favorileri yükle (Eski kodunun aynısı)
        fav_container = QWidget()
        fav_grid = QGridLayout(fav_container)
        fav_grid.setContentsMargins(5, 5, 5, 5)
        fav_grid.setSpacing(10)
        fav_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        favorites = self.db.get_favorites()
        if favorites:
            f_row, f_col = 0, 0
            for pid, name, price, img, fav, stock in favorites:
                card = ProductCard(pid, name, price, img, fav, stock, self.add_to_cart, self.refresh_ui, self.db, is_mini=True)
                card.setFixedSize(120, 150)
                fav_grid.addWidget(card, f_row, f_col)
                f_col += 1
                if f_col >= 4:
                    f_col = 0
                    f_row += 1
            self.selection_lay.addWidget(fav_container, 4, 0, 1, 3)
        else:
            self.selection_lay.addWidget(QLabel("Henüz favori ürün yok.", styleSheet="color: #555; margin-left: 10px;"), 4, 0, 1, 3)
            
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.selection_lay.addWidget(spacer, 5, 0)

    def on_search_changed(self, text):
        """Arama kutusu değiştiğinde çalışır"""
        text = text.strip()
        if not text:
            self.load_categories_grid()
            return
            
        self.clear_selection_area()
        
        # Veritabanında arama (İsim veya Barkod)
        # Not: SQL Injection için ? parametresi kullanın, ancak LIKE için % dışarıda eklenmeli.
        query = """
            SELECT id, name, sell_price, image_path, is_favorite, stock 
            FROM products 
            WHERE name LIKE ? OR barcode LIKE ?
        """
        search_term = f"%{text}%"
        results = self.db.cursor.execute(query, (search_term, search_term)).fetchall()
        
        if not results:
            self.selection_lay.addWidget(QLabel("Sonuç bulunamadı...", styleSheet="color:#666;"), 0, 0)
            return
            
        col = 0
        row = 0
        max_col = 3
        
        for pid, name, price, img, fav, stock in results:
            def on_click(n, p):
                self.add_to_cart(n, p)
                self.search_bar.clear() # Ürün seçince aramayı temizle (isteğe bağlı)
                self.search_bar.clearFocus()
            
            card = ProductCard(pid, name, price, img, fav, stock, on_click, lambda: self.on_search_changed(text), self.db, is_mini=True)
            card.setFixedSize(140, 160)
            
            self.selection_lay.addWidget(card, row, col)
            col += 1
            if col >= max_col:
                col = 0
                row += 1

    def toggle_ciro_visibility(self):
        """Ciro gizle/göster"""
        self.ciro_visible = not self.ciro_visible
        self.update_ciro()
        
    def update_ciro(self):
        daily = self.db.get_daily_turnover()
        if self.ciro_visible:
            self.lbl_ciro.setText(f"Ciro: {daily:.2f} ₺") 
        else:
            self.lbl_ciro.setText("Ciro: ***")

    def show_products_popup(self, cat): # hızlı erişim ürünleri
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{cat}")
        dlg.resize(2000, 700)
        dlg.setStyleSheet("background-color: #1a1a1a;")
        
        layout = QVBoxLayout(dlg)
        header = QLabel(f"{cat} - Ürün Seçimi")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: white; margin: 10px;")
        layout.addWidget(header)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border:none;")
        
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(15)
        
        products = self.db.get_products(cat)
        
        if not products:
            grid.addWidget(QLabel("Ürün yok.", styleSheet="color:white; font-size:16px;"), 0, 0)
        else:
            col, row = 0, 0
            max_col = 5
            for pid, name, price, img, fav, stock in products:
                def on_click(n, p):
                    self.add_to_cart(n, p)
                card = ProductCard(pid, name, price, img, fav, stock, on_click, self.refresh_ui, self.db, is_mini=False)
                grid.addWidget(card, row, col)
                col += 1
                if col >= max_col:
                    col = 0
                    row += 1
        
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        btn_close = QPushButton("KAPAT")
        btn_close.setFixedHeight(60)
        btn_close.setStyleSheet("background-color: #333; color: white; border-radius: 8px; font-weight:bold; font-size: 16px;")
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close)
        dlg.exec()

    def get_active_table(self):
        """Aktif sekmedeki tabloyu döndürür"""
        return self.cart_tabs.currentWidget()

    def add_to_cart(self, name, price):
        table = self.get_active_table()
        
        # 1. Önce Ürünü Tabloya Ekle/Güncelle
        found_row = -1
        
        # Tabloda ürün var mı kontrol et
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.text() == name:
                found_row = row
                break
        
        if found_row != -1:
            # Varsa Adeti Artır
            qty_item = table.item(found_row, 2)
            try:
                cur_qty = int(qty_item.text())
            except:
                cur_qty = 1
                
            table.blockSignals(True)
            qty_item.setText(str(cur_qty + 1))
            table.blockSignals(False)
            table.selectRow(found_row)
            self.selected_row = found_row
            
        else:
            # Yoksa Yeni Satır Ekle
            row = table.rowCount()
            table.insertRow(row)
            
            # Ürün Adı
            it_name = QTableWidgetItem(str(name))
            it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 0, it_name)
            
            # Fiyat
            it_price = QTableWidgetItem(f"{float(price):.2f}")
            it_price.setTextAlignment(Qt.AlignCenter)
            it_price.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 1, it_price)
            
            # Adet
            it_qty = QTableWidgetItem("1")
            it_qty.setTextAlignment(Qt.AlignCenter)
            it_qty.setForeground(QColor("#30d158"))
            it_qty.setFont(QFont("Segoe UI", 14, QFont.Bold))
            it_qty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 2, it_qty)
            
            # Sil Butonu
            btn = QPushButton("Sil")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton { background-color: transparent; color: #666; font-weight: bold; border: 1px solid #333; border-radius: 5px; }
                QPushButton:hover { background-color: #ff453a; color: white; border: 1px solid #ff453a; }
            """)
            btn.clicked.connect(lambda: self.smart_delete_row(btn))
            table.setCellWidget(row, 3, btn)
            
            table.selectRow(row)
            self.selected_row = row

        self.recalc_active_cart_total()

        # 2. AI Öneri Kısmı (HATANIN OLDUĞU YER DÜZELTİLDİ)
        suggestion = None  # <-- ÖNEMLİ: Değişkeni başta boş olarak tanımlıyoruz

        try:
            # Sepetteki ürün isimlerini al
            current_cart_names = []
            for r in range(table.rowCount()):
                item = table.item(r, 0)
                if item:
                    current_cart_names.append(item.text())
            
            # AI'dan öneri iste
            suggestion = self.ai.recommend_product(current_cart_names)
            
        except Exception as e:
            print(f"AI Hatası: {e}")
            suggestion = None

        # 3. Öneriyi Ekrana Yaz
        if suggestion:
            self.search_bar.setPlaceholderText(f"💡 ÖNERİ: Müşteriye '{suggestion}' teklif edin!")
            self.search_bar.setStyleSheet("QLineEdit { background-color: #2a1a1a; color: #ffcc00; border: 1px solid #ffcc00; border-radius: 10px; padding-left: 10px; }")
        else:
            self.search_bar.setPlaceholderText("🔍 Ürün Ara...")
            self.search_bar.setStyleSheet("QLineEdit { background-color: #252525; color: white; border-radius: 10px; padding-left: 10px; }")

    def smart_delete_row(self, button_widget):
        """Silme butonuna basıldığında çalışır"""
        table = self.get_active_table()
        
        # Butonun hangi satırda olduğunu bul
        index = table.indexAt(button_widget.pos())
        if not index.isValid(): return
        row = index.row()
        
        qty_item = table.item(row, 2)
        try:
            qty = int(qty_item.text())
        except:
            qty = 1
            
        if qty > 1:
            table.blockSignals(True)
            qty_item.setText(str(qty - 1))
            table.blockSignals(False)
            self.recalc_active_cart_total()
        else:
            reply = QMessageBox.question(self, "Sil", "Ürün sepetten silinsin mi?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                table.removeRow(row)
                self.recalc_active_cart_total()
                self.selected_row = -1
                
    def on_cart_item_changed(self, item):
        """Kullanıcı tabloda elle fiyat veya adet değiştirirse tetiklenir"""
        self.recalc_active_cart_total()

    def recalc_active_cart_total(self):
        """Aktif tablodan verileri okur, cart_data'yı ve toplamı günceller"""
        # Eğer lbl_total henüz yaratılmadıysa (program açılışı) işlem yapma
        if not hasattr(self, 'lbl_total'): 
            return

        table = self.get_active_table()
        self.table = table # Aktif tablo referansını güncelle
        
        self.cart_data = [] # Listeyi sıfırla
        total = 0.0
        
        for r in range(table.rowCount()):
            try:
                name = table.item(r, 0).text()
                price = float(table.item(r, 1).text().replace(",", "."))
                qty = int(table.item(r, 2).text())
                
                total += price * qty
                self.cart_data.append({'name': name, 'price': price, 'qty': qty})
            except:
                pass 
        
        self.lbl_total.setText(f"{total:.2f} ₺")
        
        if hasattr(self, 'update_change_list'):
            self.update_change_list()

    def row_selected(self):
        self.selected_row = self.table.currentRow()

    def keyPressEvent(self, e):
        """Fiziksel Klavye Desteği"""
        # Eğer bir satır seçiliyse
        if self.selected_row != -1:
            # Rakam tuşları (0-9)
            if e.text().isdigit():
                self.numpad_action(e.text())
                return
            # Backspace
            if e.key() == Qt.Key_Backspace:
                self.numpad_action('⌫')
                return
        
        # Barkod Enter tuşu
        if e.key() == Qt.Key_Return or e.key() == Qt.Key_Enter:
            if self.barcode_buffer:
                self.process_barcode_scan(self.barcode_buffer)
                self.barcode_buffer = ""
        else:
            # Barkod okuma (printable karakterler)
            if e.text() and e.text().isprintable() and not e.text().isdigit(): 
                # Rakamları barkoda dahil etmiyoruz ki adet girmeye çalışırken barkod okumasın
                # Burası önemli: Eğer barkodunuz sadece rakamsa, bu mantık çakışabilir.
                # Genelde barkod okuyucular çok hızlı basar, insan eli yavaştır.
                # Şimdilik basit tutuyoruz.
                self.barcode_buffer += e.text()


    def get_current_cart(self):
        """Aktif sekmedeki sepeti döndürür"""
        return self.cart_tabs.currentWidget()

    def update_total_display(self, total):
        """Aktif sekmenin toplamı değişince çalışır"""
        # Sadece o anki görünen sekme ise güncelle
        if self.sender() == self.get_current_cart():
            self.lbl_total.setText(f"{total:.2f} ₺")
            self.update_change_list()
    
    # Sekme değiştiğinde toplamı güncelle
    def on_tab_changed(self):
        cart = self.get_current_cart()
        if cart:
            # Mevcut tablodan toplamı hesapla
            cart.recalc_total() 

    def numpad_action(self, key):
        """Numpad tıklamalarını aktif sepetin seçili satırına yönlendir"""
        cart = self.get_current_cart()
        if not cart: return
        
        row = cart.table.currentRow()
        if row < 0: return # Seçili satır yok
        
        current_qty_item = cart.table.item(row, 2)
        try:
            current_val = int(current_qty_item.text())
        except:
            current_val = 1
            
        new_val = current_val
        
        if key == 'C':
            cart.table.removeRow(row)
        elif key == '⌫':
             # Numpad ile silme (Backsapce) sadece rakam siler, satır silmez
            s_val = str(current_val)
            if len(s_val) > 1:
                new_val = int(s_val[:-1])
            else:
                new_val = 1
            cart.update_row_qty(row, new_val)
        else:
            # Rakam ekleme
            # Eğer şu an 1 ise ve biz rakama basıyorsak (örn 5), direkt 5 olsun. 15 olmasın.
            if current_val == 1:
                new_val = int(key)
            else:
                new_val = int(str(current_val) + key)
            cart.update_row_qty(row, new_val)

    def finish_sale(self, method):
        """NAKİT butonu - Yükleme Ekransız"""
        if not self.cart_data:
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
        
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        
        # 1. Butona basıldığını belli et
        self.set_payment_processing(True, "NAKİT")
        
        # 2. İşlemi başlat (Arka planda)
        # Not: PaymentWorker sınıfın (total, method) alacak şekilde ayarlı olmalı
        self.worker = PaymentWorker(total, method)
        self.worker.finished.connect(self.on_pos_result)
        self.worker.start()

    def card_payment(self):
        """KART butonu - Yükleme Ekransız"""
        if not self.cart_data:
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
        
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        
        # 1. Butona basıldığını belli et
        self.set_payment_processing(True, "KART")
        
        # 2. İşlemi başlat (Arka planda)
        self.worker = PaymentWorker(total, "CARD")
        self.worker.finished.connect(self.on_pos_result)
        self.worker.start()

    def on_pos_result(self, result):
        """POS yanıtı geldiğinde çalışır"""
        
        # 1. Butonları eski haline döndür (Görsel efekti kapat)
        self.set_payment_processing(False)
        
        if result['success']:
            # ✅ Başarılı
            method = result.get('method', 'Bilinmeyen') # method dönmüyorsa hata almamak için get kullan
            
            # İstersen başarılı mesajını da kaldırabilirsin, POS fiş yazıyor zaten.
            # Şimdilik bilgi veriyoruz:
            QMessageBox.information(
                self, 
                "✅ İşlem Başarılı", 
                f"{method} ödemesi onaylandı!\nTutar: {result['amount']:.2f} ₺"
            )
            
            try:
                # Veritabanına Kaydet
                alerts = self.db.record_sale(self.cart_data, result['amount'], method)
                if alerts:
                    QMessageBox.warning(self, "Stok Uyarısı", "\n".join(alerts))
                
                # Sepeti Temizle
                table = self.get_active_table()
                table.setRowCount(0)
                self.cart_data = []
                self.recalc_active_cart_total()
                self.update_ciro()
                
            except Exception as e:
                QMessageBox.critical(self, "Kayıt Hatası", str(e))
        
        else:
            # ❌ Başarısız
            if result.get('timeout'):
                QMessageBox.warning(self, "Zaman Aşımı", "POS yanıt vermedi.")
            else:
                msg = result.get('message', 'Hata oluştu')
                QMessageBox.critical(self, "İşlem Başarısız", msg)            

    def mark_pending(self, result):
       tx_id = result.get('tx_id')
       total = sum([x['price'] * x['qty'] for x in self.cart_data])
       self.db.cursor.execute("INSERT INTO pending_transactions (tx_id, amount, timestamp) VALUES (?, ?, ?)", (tx_id, total, datetime.datetime.now().isoformat()))
       self.db.conn.commit()

    def add_category(self):
       n, ok = QInputDialog.getText(self, "Kategori", "Ad:")
       if ok and n:
           self.db.add_category(n)
           self.refresh_ui()

    def open_admin(self):
       try:
           dlg = AdminDialog(self.db, self)
           dlg.exec()
           self.refresh_ui()
       except Exception as e:
           QMessageBox.critical(self, "Hata", str(e))
    def process_barcode_scan(self, barcode):
       product = self.db.get_product_by_barcode(barcode)
       if product:
           self.add_to_cart(product[0], product[1])
       else:
           QMessageBox.warning(self, "Bulunamadı", f"Barkod kayıtlı değil: {barcode}")
    # --- AI ENTEGRASYON FONKSİYONLARI ---

    def ai_otomatik_kontrol(self):
        """Arka planda sessizce çalışır, buton rengini değiştirir."""
        
        # Klasör ve dosya kontrolü (Hata almamak için)
        if not os.path.exists("urunler_klasoru/urunler.csv"):
            return 

        motor = VoidAI_Engine("urunler_klasoru/urunler.csv")
        sonuclar = motor.tum_analizleri_yap()
        
        if sonuclar:
            # --- DURUM: UYARI VAR (KIRMIZI VE YANIP SÖNEN) ---
            self.ai_btn.setText(f"AI: {len(sonuclar)} ÖNERİ VAR!")
            # Yönetim tuşu boyutlarında (Radius 16px) ama KIRMIZI
            self.ai_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c; 
                    color: white; 
                    border: 1px solid #c0392b;
                    border-radius: 16px; 
                    font-weight: bold;
                    font-size: 13px;
                    padding: 0 15px;
                    height: 45px;
                }
                QPushButton:hover { background-color: #c0392b; }
            """)
            # Not: PySide6 CSS animasyonunu (blink) doğrudan desteklemez, 
            # ama kırmızılık yeterince dikkat çeker. Yanıp sönme için QTimer gerekir.
            
        else:
            self.ai_btn.setText("AI: Sistem Stabil")
            self.ai_btn.setStyleSheet("""
                QPushButton { 
                    background-color: #252525; 
                    color: #e0e0e0; 
                    border: 1px solid #333; 
                    border-radius: 16px; 
                    font-weight: bold; 
                    font-size: 13px; 
                    padding: 0 15px; 
                    height: 45px; 
                }
                QPushButton:hover { background-color: #333; border: 1px solid #555; }
            """)

    def ai_analiz_butonuna_tiklandi(self):
        """Kasiyer butona bastığında detayları gösterir"""
        motor = VoidAI_Engine("urunler_klasoru/urunler.csv")
        sonuclar = motor.tum_analizleri_yap()
        
        if sonuclar:
            for oneri in sonuclar:
                cevap = QMessageBox.question(
                    self, 
                    "VoidAI Önerisi", 
                    oneri["mesaj"] + "\n\nBu işlemi onaylıyor musun?",
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if cevap == QMessageBox.Yes:
                    # İşlemi uygula (Fiyat düşme vb.)
                    sonuc_mesaji = motor.aksiyonu_uygula(oneri["aksiyon_verisi"])
                    
                    # Eğer fiyat değiştiyse veritabanını da güncellememiz gerekir!
                    # CSV motoru CSV'yi günceller, ama SQLite'ı da senkronize etmeliyiz:
                    if oneri["aksiyon_verisi"]["islem"] == "fiyat_dusur":
                        pid = oneri["aksiyon_verisi"]["id"]
                        yeni_fiyat = oneri["aksiyon_verisi"]["yeni_fiyat"]
                        self.db.update_product_field(pid, "sell_price", yeni_fiyat)
                        self.refresh_ui() # Arayüzü yenile
                        
                    QMessageBox.information(self, "Bilgi", sonuc_mesaji)
        else:
            QMessageBox.information(self, "VoidAI", "Harika! Sistem stabil. Kritik stok veya SKT sorunu yok.")
                   
#yönetim paneli
# ==========================================
# YÖNETİM PANELİ
# ==========================================
class AdminDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Yönetim Paneli")
        self.resize(1200, 800)

        # --- DÜZELTME BURADA BAŞLIYOR ---
        
        # 1. Önce Layout ve Tabs OLUŞTURULMALI
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        # Sekme değiştiğinde veriyi yenilemek için sinyal:
        self.tabs.currentChanged.connect(self.on_tab_change) 
        
        layout.addWidget(self.tabs)
        
        # 2. Değişkenleri Tanımla
        self.editing_pid = None
        self.filter_mode = 'day'
        self.last_tab_index = 0

        # 3. ŞİMDİ Setup Fonksiyonlarını Çağırabiliriz (Çünkü self.tabs artık var)
        self.setup_ai_center()            # Void AI
        self.setup_finances()             # Tab 0 (Finans)
        self.setup_sales_history()        # Tab 1 (Geçmiş)
        self.setup_prod_list()            # Tab 2 (Liste)
        self.setup_add_prod()             # Tab 3 (Ekle)
        self.setup_stock_tracking()       # Tab 4 (Stok)
        self.setup_pending_transactions() # Tab 5 (Bekleyen)
        self.setup_bulk_operations()      # Tab 6 (Toplu İşlem)
        self.setup_theme_settings()       # Tab 7 (Tema - Yeni Eklediğimiz)
        
        # 4. İlk veriyi yükle
        self.load_finance_data()
        

    def setup_theme_settings(self):
        editor = ThemeEditor(self)
        self.tabs.addTab(editor, "🎨 Tema Ayarları")

    def setup_ai_center(self):
        self.ai = AIService(self.db.db_name)
        
        w = QWidget()
        layout = QVBoxLayout(w)
        
        # --- Butonlar ---
        btn_layout = QHBoxLayout()
        buttons = {
            "📈 Ciro Tahmini": self.action_forecast_graph,
            "⏰ Yoğunluk Analizi": self.action_busy_hours,
            "🏷️ Akıllı İndirim (Kâr/Zarar)": self.action_discounts,
            "🎁 Kampanya Önerileri": self.action_bundles,       
            "🚨 Güvenlik Taraması": self.action_fraud
        }
        
        for text, func in buttons.items():
            b = QPushButton(text)
            b.setFixedHeight(50)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("background:#333; color:white; border:1px solid #555; border-radius:8px; font-weight:bold;")
            b.clicked.connect(func)
            btn_layout.addWidget(b)
        
        layout.addLayout(btn_layout)
        
        # --- GRAFİK ALANI (YENİ) ---
        # Mevcut MplCanvas sınıfını kullanarak grafik alanı ekliyoruz
        self.ai_canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.ai_canvas.hide() # Başlangıçta gizli
        layout.addWidget(self.ai_canvas)

        # --- METİN ALANI ---
        self.ai_result_box = QLabel("Analiz seçiniz...")
        self.ai_result_box.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.ai_result_box.setStyleSheet("color: #ccc; padding: 10px; font-size: 14px; background:#1a1a1a;")
        self.ai_result_box.setWordWrap(True)
        layout.addWidget(self.ai_result_box)
        
        layout.addStretch()
        self.tabs.addTab(w, "🧠 Void AI")

    # --- AKSİYONLAR ---

    def action_forecast_graph(self):
        """Tahminleri Grafik Olarak Çizer"""
        data, msg = self.ai.get_forecast_data(7)
        
        if not data:
            self.ai_result_box.setText(f"Veri Yok: {msg}")
            self.ai_canvas.hide()
            return
            
        # Grafiği Görünür Yap
        self.ai_canvas.show()
        self.ai_canvas.axes.clear()
        
        # Geçmiş (Mavi)
        hist_dates, hist_vals = data['history']
        self.ai_canvas.axes.plot(hist_dates, hist_vals, label='Geçmiş', color='#0a84ff', marker='o')
        
        # Gelecek (Kesikli Çizgi - Mor)
        future_dates, future_vals = data['forecast']
        # Çizgiyi birleştirmek için son geçmiş veriyi ekle
        if hist_dates and future_dates:
            connect_dates = [hist_dates[-1], future_dates[0]]
            connect_vals = [hist_vals[-1], future_vals[0]]
            self.ai_canvas.axes.plot(connect_dates, connect_vals, color='#e040fb', linestyle='--')
            
        self.ai_canvas.axes.plot(future_dates, future_vals, label='AI Tahmini', color='#e040fb', linestyle='--', marker='x')
        
        self.ai_canvas.axes.legend()
        self.ai_canvas.axes.grid(True, color='#333')
        self.ai_canvas.axes.set_title("Satış Trendi ve AI Tahmini", color='white')
        self.ai_canvas.axes.tick_params(colors='white')
        self.ai_canvas.draw()
        
        total_est = sum(future_vals)
        self.ai_result_box.setText(f"📊 Grafik oluşturuldu. Gelecek 7 gün için tahmini ciro: {total_est:.2f} ₺")

    def action_busy_hours(self):
        self.ai_canvas.hide() # Grafiği gizle
        res = self.ai.analyze_busy_hours()
        if not res:
            self.ai_result_box.setText("Yetersiz zaman verisi.")
            return
            
        html = f"""
        <h3 style='color:#ffcc00'>⏰ En Yoğun Saatler</h3>
        <p><b>Zirve Saati:</b> {res['busiest_hour']}</p>
        <p><b>İşlem Sayısı:</b> {res['transaction_count']}</p>
        <p style='color:#30d158; font-size:16px'><b>💡 AI Tavsiyesi:</b> {res['advice']}</p>
        """
        self.ai_result_box.setText(html)

    def action_discounts(self):
        self.ai_canvas.hide()
        suggestions = self.ai.suggest_discounts() # Artık (mesaj, renk) listesi dönüyor
        
        if not suggestions:
            self.ai_result_box.setText("✅ Ölü stok veya riskli ürün bulunamadı.")
            return
            
        html = "<h3>📉 Kâr Odaklı İndirim Önerileri</h3><ul>"
        for msg, color in suggestions:
            html += f"<li style='color:{color}; font-size:14px; margin-bottom:5px;'>{msg}</li>"
        html += "</ul>"
        self.ai_result_box.setText(html)

    def action_bundles(self):
        self.ai_canvas.hide()
        bundles = self.ai.suggest_bundles()
        
        if not bundles:
            self.ai_result_box.setText("Henüz kampanya önerisi için yeterli satış verisi yok.")
            return
            
        html = "<h3 style='color:#0a84ff'>🎁 Akıllı Paket (Bundle) Önerileri</h3>"
        html += "<p>Müşterilerin alışveriş alışkanlıklarına göre hazırlanan fırsat paketleri:</p><ul>"
        for b in bundles:
            html += f"<li style='margin-bottom:10px;'>{b}</li>"
        html += "</ul>"
        self.ai_result_box.setText(html)

    def action_fraud(self):
        self.ai_canvas.hide()
        # Eski action_fraud kodunu buraya taşıyın
        data = self.ai.detect_anomalies()
        if not data: 
            self.ai_result_box.setText("✅ Güvenlik taraması temiz.")
            return
        html = "<h3>🚨 Şüpheli İşlemler</h3><ul>"
        for row in data:
            html += f"<li>Tutar: {row[1]} ₺ - Tarih: {row[2]}</li>"
        html += "</ul>"
        self.ai_result_box.setText(html)
        
    def load_product_to_form(self, pid):
        """Seçilen ürünü düzenleme formuna yükler"""
        product = self.db.get_product_by_id(pid)
        if not product:
            QMessageBox.warning(self, "Hata", "Ürün bulunamadı!")
            return
            
        # product yapısı: (id, name, cost, sell, stock, critical, cat, barcode, img, sort)
        # Veritabanı sütun sırasına göre indexler değişebilir, kontrol edelim:
        # Genelde: 0:id, 1:name, 2:cost, 3:sell, 4:stock, 5:crit, 6:cat, 7:barcode...
        
        self.editing_pid = product[0] # Düzenleme moduna al
        
        self.inp_name.setText(product[1])
        self.inp_cost.setText(str(product[2]))
        self.inp_sell.setText(str(product[3]))
        self.inp_stok.setText(str(product[4]))
        self.inp_crit.setText(str(product[5] if product[5] is not None else 5))
        self.cmb_cat.setCurrentText(product[6])
        self.inp_code.setText(product[7] if product[7] else "")
        
        # UI Güncellemesi
        self.lbl_form_title.setText(f"ÜRÜN DÜZENLE (ID: {self.editing_pid})")
        self.lbl_form_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #ff9f0a;") # Turuncu başlık
        
        self.btn_save.setText("GÜNCELLE")
        self.btn_save.setProperty("class", "SuccessBtn")
        
        # Sekmeyi "Ürün Ekle / Düzenle"ye (Index 3) kaydır
        self.tabs.setCurrentIndex(3)

    def load_stock_categories(self):
        """Stok takibi için kategori butonlarını yükler"""
        # Önce eski butonları temizle
        while self.cat_btn_layout.count():
            child = self.cat_btn_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
            
        categories = self.db.get_all_categories()
        
        row, col = 0, 0
        max_col = 4 # Yan yana 4 buton
        
        for cat in categories:
            if cat == "Tüm Ürünler": continue # "Tüm Ürünler" çok kasacağı için stokta göstermeyelim veya sona ekleyelim
            
            btn = QPushButton(cat)
            btn.setFixedSize(200, 100)
            btn.setCursor(Qt.PointingHandCursor)
            # Modern Kart Görünümlü Buton
            btn.setStyleSheet("""
                QPushButton { 
                    background-color: #252525; 
                    color: white; 
                    border: 1px solid #444; 
                    border-radius: 12px; 
                    font-size: 16px; 
                    font-weight: bold; 
                }
                QPushButton:hover { 
                    background-color: #303030; 
                    border: 1px solid #0a84ff; 
                    color: #0a84ff;
                }
            """)
            
            # Butona tıklayınca o kategoriyi aç
            btn.clicked.connect(lambda _, c=cat: self.load_stock_products_by_cat(c))
            
            self.cat_btn_layout.addWidget(btn, row, col)
            
            col += 1
            if col >= max_col:
                col = 0
                row += 1
        
        # En sona boşluk atıp yukarı itelim
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.cat_btn_layout.addWidget(spacer, row + 1, 0)
        self.cat_btn_layout.setRowStretch(row + 1, 1)

    def load_stock_products_by_cat(self, category_name):
        """Seçilen kategorideki ürünleri stok tablosuna yükler"""
        self.lbl_selected_cat.setText(f"Kategori: {category_name}")
        self.stock_table.setRowCount(0)
        
        # Sadece o kategorinin ürünlerini çekiyoruz (HIZLI ÇALIŞIR)
        products = self.db.get_products(category_name)
        
        self.stock_table.setSortingEnabled(False) # Hız için kapat
        
        for i, (pid, name, price, img, fav, stock) in enumerate(products):
            self.stock_table.insertRow(i)
            self.stock_table.setItem(i, 0, QTableWidgetItem(str(pid)))
            self.stock_table.setItem(i, 1, QTableWidgetItem(name))
            
            stock_item = QTableWidgetItem()
            stock_item.setData(Qt.DisplayRole, stock)
            self.stock_table.setItem(i, 2, stock_item)
            
            btn = QPushButton("Düzenle")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("background-color: #0a84ff; color: white; border-radius: 4px; font-weight: bold;")
            
            # Güncelleme sonrası tabloyu yenilemek için fonksiyonu güncelledik
            btn.clicked.connect(lambda _, p=pid, s=stock, c=category_name: self.update_stock_filtered(p, s, c))
            
            self.stock_table.setCellWidget(i, 3, btn)
            
        self.stock_table.setSortingEnabled(True)
        
        # Sayfayı değiştir (Tabloyu göster)
        self.stk_stock.setCurrentIndex(1)

    def update_stock_filtered(self, pid, current_stock, category_name):
        """Stok günceller ve aynı kategori sayfasında kalır"""
        val, ok = QInputDialog.getInt(self, "Stok Güncelle", "Yeni Stok Adedi:", current_stock, -1000, 100000, 1)
        if ok: 
            self.db.update_product_field(pid, "stock", val)
            # Sadece mevcut kategoriyi yenile, hepsini değil
            self.load_stock_products_by_cat(category_name)
            QMessageBox.information(self, "Başarılı", "Stok güncellendi.")

    def export_csv(self):
        # Dosya kaydetme penceresi aç
        path, _ = QFileDialog.getSaveFileName(self, "CSV Olarak Kaydet", "urunler.csv", "CSV Dosyaları (*.csv)")
        if path:
            success, msg = self.db.export_products_to_csv(path)
            if success:
                QMessageBox.information(self, "Başarılı", msg)
            else:
                QMessageBox.critical(self, "Hata", msg)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "CSV Dosyası Seç", "", "CSV Dosyaları (*.csv)")
        if path:
            reply = QMessageBox.question(self, "Onay", "Veritabanı güncellenecek. Devam?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                success, msg = self.db.import_products_from_csv(path)
                if success:
                    QMessageBox.information(self, "Başarılı", msg)
                    
                    # --- EKRANI TAMAMEN YENİLE ---
                    self.load_categories_grid()  # Sol paneldeki kategori butonlarını yeniler
                    if hasattr(self, 'load_table_data'):
                        self.load_table_data()   # Admin panelindeki listeyi yeniler
                    # -----------------------------
                else:
                    QMessageBox.critical(self, "Hata", msg)

    def take_z_report(self):
        reply = QMessageBox.question(self, "Z Raporu", "Günü bitirip Z Raporu almak istiyor musunuz?\nBu işlem bugünkü satışları dosyalayacaktır.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return
        
        # 1. Klasörü Oluştur
        if not os.path.exists("z_reports"):
            os.makedirs("z_reports")
            
        # 2. Dosya Adı (Örn: 27012026.json)
        now = datetime.datetime.now()
        filename = f"z_reports/{now.strftime('%d%m%Y')}.json"
        
        # 3. Verileri Topla
        sales = self.db.get_todays_sales()
        totals = self.db.get_todays_totals() # (Total Ciro, Total Kâr)
        
        report_data = {
            "date": now.strftime('%d-%m-%Y'),
            "generated_at": now.strftime('%H:%M:%S'),
            "total_turnover": totals[0] if totals[0] else 0,
            "total_profit": totals[1] if totals[1] else 0,
            "transaction_count": len(sales),
            "transactions": []
        }
        
        for s in sales:
            report_data["transactions"].append({
                "id": s[0],
                "time": s[3],
                "receipt": s[1],
                "amount": s[5],
                "method": s[4]
            })
            
        # 4. Dosyaya Yaz
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=4)
            
            QMessageBox.information(self, "Başarılı", f"Z Raporu alındı ve kaydedildi:\n{filename}")
            
            # Ekranı temizlemeye gerek yok çünkü tarih değişince otomatik boş gelecek.
            # Ama kullanıcı temiz görmek istiyorsa:
            # self.hist_table.setRowCount(0) 
            
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Rapor kaydedilemedi: {str(e)}")

    def on_tab_change(self, index):
        self.last_tab_index = index
        
        if index == 0:   # Finansal
            self.load_finance_data()
        elif index == 1: # Satış
            self.load_sales_history_data()
        elif index == 2: # Ürün Listesi
            self.load_table_data()
        elif index == 4: # STOK TAKİP (BURAYI DEĞİŞTİRDİK)
            # Tabloyu sıfırla ve kategorileri yükle
            self.stk_stock.setCurrentIndex(0) 
            self.load_stock_categories()
        elif index == 5: # Bekleyen
            self.load_pending_data()

    # --- 1. FİNANSAL RAPORLAR ---
    def setup_finances(self):
        w = QWidget()
        l = QVBoxLayout(w)
        
        # Filtre Butonları
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(0)
        
        self.btn_day = QPushButton("Günlük")
        self.btn_day.setObjectName("First")
        self.btn_day.setProperty("class", "FilterBtn")
        self.btn_day.setCheckable(True)
        self.btn_day.setChecked(True)
        
        self.btn_week = QPushButton("Haftalık")
        self.btn_week.setProperty("class", "FilterBtn")
        self.btn_week.setCheckable(True)
        
        self.btn_month = QPushButton("Aylık")
        self.btn_month.setProperty("class", "FilterBtn")
        self.btn_month.setCheckable(True)
        
        self.btn_year = QPushButton("Yıllık")
        self.btn_year.setObjectName("Last")
        self.btn_year.setProperty("class", "FilterBtn")
        self.btn_year.setCheckable(True)
        
        self.group = QButtonGroup(self)
        self.group.addButton(self.btn_day)
        self.group.addButton(self.btn_week)
        self.group.addButton(self.btn_month)
        self.group.addButton(self.btn_year)
        self.group.buttonClicked.connect(self.change_filter)
        
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_day)
        filter_layout.addWidget(self.btn_week)
        filter_layout.addWidget(self.btn_month)
        filter_layout.addWidget(self.btn_year)
        filter_layout.addStretch()
        l.addLayout(filter_layout)
        
        # Grafik
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        l.addWidget(self.canvas, stretch=2)
        
        # Özet Kutuları
        self.summary_frame = QFrame()
        sl = QHBoxLayout(self.summary_frame)
        
        self.lbl_sum_cost = QLabel("Maliyet: 0.00")
        self.lbl_sum_cost.setProperty("class", "StatsLabel")
        self.lbl_sum_cost.setStyleSheet("color:#ff9f0a; border:1px solid #ff9f0a;")
        
        self.lbl_sum_profit = QLabel("Kâr: 0.00")
        self.lbl_sum_profit.setProperty("class", "StatsLabel")
        self.lbl_sum_profit.setStyleSheet("color:#30d158; border:1px solid #30d158;")
        
        self.lbl_sum_turnover = QLabel("Ciro: 0.00")
        self.lbl_sum_turnover.setProperty("class", "StatsLabel")
        self.lbl_sum_turnover.setStyleSheet("color:#0a84ff; border:1px solid #0a84ff;")
        
        sl.addWidget(self.lbl_sum_cost)
        sl.addWidget(self.lbl_sum_profit)
        sl.addWidget(self.lbl_sum_turnover)
        l.addWidget(self.summary_frame)
        
        # Tablo
        self.fin_table = QTableWidget()
        self.fin_table.setColumnCount(4)
        self.fin_table.setHorizontalHeaderLabels(["Zaman", "Ciro", "Maliyet", "Kâr"])
        self.fin_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fin_table.setStyleSheet("QTableWidget { background:#252525; border:none; gridline-color:#333; }")
        self.fin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        l.addWidget(self.fin_table, stretch=2)
        
        self.tabs.addTab(w, "Finansal Rapor")

    def change_filter(self, btn):
        if btn == self.btn_day: self.filter_mode = 'day'
        elif btn == self.btn_week: self.filter_mode = 'week'
        elif btn == self.btn_month: self.filter_mode = 'month'
        elif btn == self.btn_year: self.filter_mode = 'year'
        self.load_finance_data()

    def load_finance_data(self):
        stats = self.db.get_filtered_stats(self.filter_mode)
        self.canvas.axes.clear()
        self.fin_table.setRowCount(0)

        labels = []
        turnovers = []
        profits = []
        costs = []

        total_turnover = 0
        total_profit = 0
        total_cost = 0

        for i, row in enumerate(stats):
            label = row[0]
            turnover = row[1] or 0
            profit = row[2] or 0
            cost = turnover - profit

            labels.append(label)
            turnovers.append(turnover)
            profits.append(profit)
            costs.append(cost)

            total_turnover += turnover
            total_profit += profit
            total_cost += cost

            self.fin_table.insertRow(i)
            self.fin_table.setItem(i, 0, QTableWidgetItem(str(label)))
            self.fin_table.setItem(i, 1, QTableWidgetItem(f"{turnover:.2f}"))
            self.fin_table.setItem(i, 2, QTableWidgetItem(f"{cost:.2f}"))
            self.fin_table.setItem(i, 3, QTableWidgetItem(f"{profit:.2f}"))

        # Grafik Çizimi
        self.canvas.axes.plot(labels, turnovers, label="Ciro", color="#0a84ff", linewidth=2.5, marker='o')
        self.canvas.axes.plot(labels, profits, label="Kâr", color="#30d158", linewidth=2.5, marker='o')
        self.canvas.axes.plot(labels, costs, label="Maliyet", color="#ff9f0a", linewidth=2.5, marker='o')

        self.canvas.axes.legend(facecolor='#252525', labelcolor='white', frameon=False)
        self.canvas.axes.grid(True, color='#333', linestyle='--')
        self.canvas.axes.tick_params(colors='#aaa', labelrotation=45)
        
        self.canvas.axes.spines['top'].set_visible(False)
        self.canvas.axes.spines['right'].set_visible(False)
        self.canvas.axes.spines['left'].set_color('#444')
        self.canvas.axes.spines['bottom'].set_color('#444')
        self.canvas.draw()

        # Özet Güncelleme
        self.lbl_sum_turnover.setText(f"Ciro: {total_turnover:.2f} ₺")
        self.lbl_sum_profit.setText(f"Kâr: {total_profit:.2f} ₺")
        self.lbl_sum_cost.setText(f"Maliyet: {total_cost:.2f} ₺")

    # --- 2. SATIŞ GEÇMİŞİ ---
    def setup_sales_history(self):
        w = QWidget()
        l = QVBoxLayout(w)
        
        # Üst Bar: Başlık ve Z Raporu Butonu
        top_lay = QHBoxLayout()
        top_lay.addWidget(QLabel("GÜNLÜK SATIŞ GEÇMİŞİ (Sadece Bugün)", styleSheet="font-weight:bold; color:#0a84ff; font-size:16px;"))
        top_lay.addStretch()
        
        btn_z_report = QPushButton("Z RAPORU AL (Günü Bitir)")
        btn_z_report.setStyleSheet("background-color: #ff453a; color: white; font-weight: bold; padding: 10px; border-radius: 8px;")
        btn_z_report.clicked.connect(self.take_z_report)
        top_lay.addWidget(btn_z_report)
        
        l.addLayout(top_lay)
        
        self.hist_table = QTableWidget()
        self.hist_table.setColumnCount(6)
        self.hist_table.setHorizontalHeaderLabels(["ID", "Saat", "Fiş No", "İçerik", "Ödeme", "Tutar"])
        self.hist_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        self.hist_table.setStyleSheet("QTableWidget { background:#252525; border:none; }")
        self.hist_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist_table.doubleClicked.connect(self.show_receipt_detail)
        
        l.addWidget(self.hist_table)
        self.tabs.addTab(w, "Günlük Satışlar / Z Raporu")

    def load_sales_history_data(self):
        # Sadece BUGÜNÜN verilerini çek
        data = self.db.get_todays_sales()
        
        self.hist_table.setRowCount(0)
        for r_idx, row in enumerate(data):
            self.hist_table.insertRow(r_idx)
            self.hist_table.setItem(r_idx, 0, QTableWidgetItem(str(row[0])))
            # Timestamp'ten sadece saati al (Örn: 2026-01-27 12:30:00 -> 12:30:00)
            time_part = row[3].split(' ')[1] if ' ' in row[3] else row[3]
            self.hist_table.setItem(r_idx, 1, QTableWidgetItem(str(time_part)))
            
            self.hist_table.setItem(r_idx, 2, QTableWidgetItem(str(row[1])))
            prod_info = str(row[6]) if row[6] else "..."
            self.hist_table.setItem(r_idx, 3, QTableWidgetItem(f"{prod_info}..."))
            self.hist_table.setItem(r_idx, 4, QTableWidgetItem(str(row[4])))
            self.hist_table.setItem(r_idx, 5, QTableWidgetItem(f"{row[5]:.2f} ₺"))

    def show_receipt_detail(self):
        r = self.hist_table.currentRow()
        if r >= 0:
            sale_id = self.hist_table.item(r, 0).text()
            dlg = ReceiptDialog(self.db, sale_id, self)
            dlg.exec()

    # --- 3. ÜRÜN LİSTESİ ---
    # AdminDialog sınıfı içine:
    
    def setup_prod_list(self):
        w = QWidget()
        l = QVBoxLayout(w)
        
        # --- ARAMA VE FİLTRE ALANI (YENİLENDİ) ---
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # 1. Arama Çubuğu (YENİ)
        self.inp_admin_search = QLineEdit()
        self.inp_admin_search.setPlaceholderText("🔍 Yönetimde Ürün Ara (İsim veya Barkod)")
        self.inp_admin_search.setStyleSheet("padding:8px; background:#1a1a1a; border:1px solid #444; color:white; border-radius: 5px;")
        self.inp_admin_search.textChanged.connect(self.load_table_data) # Yazdıkça filtrele
        
        # 2. Kategori Filtresi
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["Tüm Ürünler"] + self.db.get_all_categories())
        self.cmb_filter.setStyleSheet("padding:8px; background:#252525; border:1px solid #444; color:white;")
        self.cmb_filter.currentTextChanged.connect(self.load_table_data)
        
        top_bar.addWidget(self.inp_admin_search, stretch=3) # Arama çubuğu geniş olsun
        top_bar.addWidget(self.cmb_filter, stretch=1)
        l.addLayout(top_bar)
        # -----------------------------------------
        
        self.table = QTableWidget()
        self.table.setColumnCount(7) 
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setHorizontalHeaderLabels(["ID", "AD", "FİYAT", "STOK", "BARKOD", "KRİTİK", "İŞLEM"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed) 
        self.table.setColumnWidth(6, 100)
        
        # Fiyat sütununu belirgin yapalım (Excel gibi düzenlenebilsin diye)
        self.table.setStyleSheet("""
            QTableWidget { background:#252525; border:none; gridline-color:#333; color: white; font-size:14px; }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background:#0a84ff; }
            /* Düzenleme modundaki kutucuk */
            QLineEdit { background: #333; color: #ffcc00; font-weight: bold; border: 2px solid #0a84ff; }
        """)
        
        self.table.itemChanged.connect(self.on_prod_cell_changed)
        
        l.addWidget(self.table)
        
        # Bilgi Notu
        info_lbl = QLabel("💡 İPUCU: Fiyatı veya Stoğu değiştirmek için tablo hücresine ÇİFT TIKLAYIN, değeri yazıp ENTER'a basın. Anında güncellenir.")
        info_lbl.setStyleSheet("color: #888; font-style: italic; margin-top: 5px;")
        l.addWidget(info_lbl)
        
        self.tabs.addTab(w, "Ürün Listesi")
        self.load_table_data()

    def load_table_data(self):
        """Hem Arama Çubuğuna Hem Kategoriye Göre Filtreler"""
        cat = self.cmb_filter.currentText()
        search_text = self.inp_admin_search.text().strip() # Arama metni
        
        query = "SELECT id, name, sell_price, stock, barcode, critical_stock FROM products WHERE 1=1"
        params = []

        # 1. Kategori Filtresi
        if cat != "Tüm Ürünler":
            query += " AND category = ?"
            params.append(cat)
        
        # 2. Metin Araması (İsim veya Barkod)
        if search_text:
            query += " AND (name LIKE ? OR barcode LIKE ?)"
            params.append(f"%{search_text}%")
            params.append(f"%{search_text}%")
            
        data = self.db.cursor.execute(query, params).fetchall()
            
        self.table.blockSignals(True) 
        self.table.setRowCount(0)
        
        for r_idx, row in enumerate(data):
            self.table.insertRow(r_idx)
            
            # ID 
            item_id = QTableWidgetItem(str(row[0]))
            item_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(r_idx, 0, item_id)
            
            # Diğer kolonlar
            for c_idx, val in enumerate(row[1:], 1):
                item = QTableWidgetItem(str(val if val is not None else ""))
                item.setFlags(item.flags() | Qt.ItemIsEditable) # Düzenlenebilir
                
                # Fiyat kolonu (Index 2) ise rengini farklı yap
                if c_idx == 2:
                    item.setForeground(QColor("#30d158")) # Yeşil
                    item.setFont(QFont("Segoe UI", 11, QFont.Bold))
                
                self.table.setItem(r_idx, c_idx, item)
            
            # Sil Butonu
            btn_del = QPushButton("SİL")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setProperty("class", "DangerBtn")            
            btn_del.clicked.connect(lambda _, pid=row[0]: self.delete_product(pid))
            self.table.setCellWidget(r_idx, 6, btn_del)

        self.table.blockSignals(False)

    def on_prod_cell_changed(self, item):
        """Yönetim panelindeki tablo hücresi değişince DB'yi güncelle"""
        row = item.row()
        col = item.column()
        
        try:
            pid = int(self.table.item(row, 0).text())
            new_val = item.text()
            
            field = ""
            if col == 1: field = "name"
            elif col == 2: field = "sell_price"
            elif col == 3: field = "stock"
            elif col == 4: field = "barcode"
            elif col == 5: field = "critical_stock"
            
            if field:
                # Sayısal alan kontrolü (Basitçe string gönderiyoruz, SQLite halleder ama temiz olsun)
                self.db.update_product_field(pid, field, new_val)
                print(f"Ürün {pid} güncellendi: {field} = {new_val}")
                
        except Exception as e:
            print(f"Güncelleme Hatası: {e}")

    def delete_product(self, pid):
        reply = QMessageBox.question(self, "Onay", "Bu ürün kalıcı olarak silinecek!\nEmin misiniz?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_product(pid)
            self.load_table_data()
            QMessageBox.information(self, "Silindi", "Ürün veritabanından silindi.")

    def start_edit(self):
        r = self.table.currentRow()
        if r >= 0:
            pid = self.table.item(r, 0).text()
            prod = self.db.get_product_by_id(pid)
            if prod:
                self.editing_pid = prod[0]
                self.inp_name.setText(prod[1])
                self.inp_cost.setText(str(prod[2]))
                self.inp_sell.setText(str(prod[3]))
                self.inp_stok.setText(str(prod[4]))
                self.inp_crit.setText(str(prod[5]))
                self.cmb_cat.setCurrentText(prod[6])
                self.inp_code.setText(prod[7])
                
                self.btn_save.setText(f"GÜNCELLE (ID: {self.editing_pid})")
                self.btn_save.setStyleSheet("background:#ff9f0a; color:black; font-weight:bold; border-radius:10px; font-size:16px;")
                self.tabs.setCurrentIndex(3)

    # --- 4. ÜRÜN EKLEME / DÜZENLEME ---
    def setup_add_prod(self):
        w = QWidget()
        # Ana Layout (Ortalanmış ve Kenar Boşluklu)
        main_layout = QVBoxLayout(w)
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setContentsMargins(50, 30, 50, 30)
        main_layout.setSpacing(20)
        
        # Başlık
        self.lbl_form_title = QLabel("YENİ ÜRÜN EKLE")
        self.lbl_form_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #0a84ff;")
        main_layout.addWidget(self.lbl_form_title)
        
        # Form Container (Kutucuk içine alalım)
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame { background-color: #202020; border-radius: 15px; border: 1px solid #333; }
            QLineEdit, QComboBox { 
                background-color: #1a1a1a; color: white; border: 1px solid #444; 
                padding: 10px; border-radius: 8px; font-size: 14px; 
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #0a84ff; }
        """)
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(15)
        
        # --- Form Alanları ---
        self.inp_code = QLineEdit()
        self.inp_code.setPlaceholderText("Barkod (Okutunuz veya Yazınız)")
        
        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("Ürün Adı")
        
        # Yan Yana Alanlar (Maliyet - Satış)
        row1 = QHBoxLayout()
        self.inp_cost = QLineEdit()
        self.inp_cost.setPlaceholderText("Maliyet Fiyatı (₺)")
        self.inp_sell = QLineEdit()
        self.inp_sell.setPlaceholderText("Satış Fiyatı (₺)")
        row1.addWidget(self.inp_cost)
        row1.addWidget(self.inp_sell)
        
        # Yan Yana Alanlar (Stok - Kritik Stok)
        row2 = QHBoxLayout()
        self.inp_stok = QLineEdit()
        self.inp_stok.setPlaceholderText("Stok Adedi")
        self.inp_crit = QLineEdit()
        self.inp_crit.setPlaceholderText("Kritik Stok Uyarı Limiti")
        row2.addWidget(self.inp_stok)
        row2.addWidget(self.inp_crit)
        
        # Kategori Seçimi
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems(self.db.get_all_categories())
        
        # Form elemanlarını ekle
        form_layout.addWidget(QLabel("Barkod:", styleSheet="border:none; color:#888; font-size:12px; margin-bottom:-5px;"))
        form_layout.addWidget(self.inp_code)
        
        form_layout.addWidget(QLabel("Ürün Adı:", styleSheet="border:none; color:#888; font-size:12px; margin-bottom:-5px;"))
        form_layout.addWidget(self.inp_name)
        
        form_layout.addLayout(row1)
        form_layout.addLayout(row2)
        
        form_layout.addWidget(QLabel("Kategori:", styleSheet="border:none; color:#888; font-size:12px; margin-bottom:-5px;"))
        form_layout.addWidget(self.cmb_cat)
        
        main_layout.addWidget(form_frame)
        
        # --- Butonlar ---
        btn_layout = QHBoxLayout()
        
        self.btn_save = QPushButton("KAYDET")
        self.btn_save.setFixedHeight(50)
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #30d158; color: black; font-weight: bold; font-size: 16px; border-radius: 10px; }
            QPushButton:hover { background-color: #28b84d; }
        """)
        self.btn_save.clicked.connect(self.save_product)
        
        btn_clear = QPushButton("Temizle / Yeni")
        btn_clear.setFixedHeight(50)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet("""
            QPushButton { background-color: transparent; color: #ff453a; font-weight: bold; font-size: 14px; border: 1px solid #ff453a; border-radius: 10px; }
            QPushButton:hover { background-color: rgba(255, 69, 58, 0.1); }
        """)
        btn_clear.clicked.connect(self.clear_form)
        
        btn_layout.addWidget(self.btn_save, stretch=2)
        btn_layout.addWidget(btn_clear, stretch=1)
        
        main_layout.addLayout(btn_layout)
        main_layout.addStretch()
        
        self.tabs.addTab(w, "Ürün Ekle / Düzenle")

    def save_product(self):
        # 1. Validasyon
        name = self.inp_name.text().strip()
        barcode = self.inp_code.text().strip()
        
        if not name or not self.inp_sell.text():
            QMessageBox.warning(self, "Hata", "Ürün Adı ve Satış Fiyatı zorunludur!")
            return

        try:
            cost = float(self.inp_cost.text()) if self.inp_cost.text() else 0.0
            sell = float(self.inp_sell.text())
            stock = int(self.inp_stok.text()) if self.inp_stok.text() else 0
            crit = int(self.inp_crit.text()) if self.inp_crit.text() else 5
            category = self.cmb_cat.currentText()
            
            # 2. Güncelleme mi, Yeni Kayıt mı?
            if self.editing_pid:
                # GÜNCELLEME
                self.db.update_product_fully(
                    self.editing_pid, name, cost, sell, stock, category, barcode, None, crit
                )
                QMessageBox.information(self, "Başarılı", "Ürün başarıyla güncellendi.")
            else:
                # YENİ KAYIT
                # Barkod kontrolü (Aynı barkod var mı?)
                if barcode and self.db.get_product_by_barcode(barcode):
                     QMessageBox.warning(self, "Hata", "Bu barkod zaten kullanılıyor!")
                     return
                     
                self.db.insert_product(
                    name, cost, sell, stock, category, barcode, None, crit
                )
                QMessageBox.information(self, "Başarılı", "Yeni ürün eklendi.")

            # 3. Formu Temizle ve Hazırla
            self.clear_form()
            
        except ValueError:
             QMessageBox.warning(self, "Hata", "Fiyat ve Stok alanlarına sadece sayı giriniz!")
        except Exception as e:
             QMessageBox.critical(self, "Hata", f"Kayıt hatası: {str(e)}")

    def clear_form(self):
        """Formu temizler ve 'Yeni Kayıt' moduna geçirir"""
        self.editing_pid = None
        self.inp_code.clear()
        self.inp_name.clear()
        self.inp_cost.clear()
        self.inp_sell.clear()
        self.inp_stok.clear()
        self.inp_crit.clear()
        
        # Görünümü "Yeni Ekle" moduna çevir
        self.lbl_form_title.setText("YENİ ÜRÜN EKLE")
        self.lbl_form_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #0a84ff;")
        
        self.btn_save.setText("KAYDET")
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #30d158; color: black; font-weight: bold; font-size: 16px; border-radius: 10px; }
            QPushButton:hover { background-color: #28b84d; }
        """)

    # --- 5. STOK TAKİP ---
    def setup_stock_tracking(self):
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Sayfa Yöneticisi (Stacked Widget)
        self.stk_stock = QStackedWidget()
        
        # --- SAYFA 1: KATEGORİ SEÇİMİ ---
        self.page_stock_cats = QWidget()
        l_cats = QVBoxLayout(self.page_stock_cats)
        
        lbl_info = QLabel("Lütfen Stok Düzenlemek İçin Bir Kategori Seçin")
        lbl_info.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffcc00; margin-bottom: 10px;")
        lbl_info.setAlignment(Qt.AlignCenter)
        l_cats.addWidget(lbl_info)
        
        # Kategori Butonları için Scroll Area (Kategori çoksa kaydırmak için)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        
        self.cat_btn_container = QWidget()
        self.cat_btn_layout = QGridLayout(self.cat_btn_container)
        self.cat_btn_layout.setSpacing(15)
        
        scroll.setWidget(self.cat_btn_container)
        l_cats.addWidget(scroll)
        
        # --- SAYFA 2: ÜRÜN TABLOSU ---
        self.page_stock_table = QWidget()
        l_table = QVBoxLayout(self.page_stock_table)
        
        # Üst Bar (Geri Dön Butonu ve Başlık)
        top_bar = QHBoxLayout()
        
        btn_back = QPushButton("⬅ KATEGORİLERE DÖN")
        btn_back.setFixedSize(200, 40)
        btn_back.setCursor(Qt.PointingHandCursor)
        btn_back.setStyleSheet("""
            QPushButton { background-color: #333; color: white; border: 1px solid #555; border-radius: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #444; border-color: #0a84ff; }
        """)
        btn_back.clicked.connect(lambda: self.stk_stock.setCurrentIndex(0)) # İlk sayfaya dön
        
        self.lbl_selected_cat = QLabel("")
        self.lbl_selected_cat.setStyleSheet("font-size: 16px; font-weight: bold; color: #0a84ff; margin-left: 10px;")
        
        top_bar.addWidget(btn_back)
        top_bar.addWidget(self.lbl_selected_cat)
        top_bar.addStretch()
        l_table.addLayout(top_bar)
        
        # Stok Tablosu
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(4)
        self.stock_table.setHorizontalHeaderLabels(["ID", "Ürün Adı", "Güncel Stok", "İşlem"])
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stock_table.setStyleSheet("QTableWidget { background:#252525; border:none; gridline-color:#333; }")
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        l_table.addWidget(self.stock_table)
        
        # Sayfaları Stack'e ekle
        self.stk_stock.addWidget(self.page_stock_cats)  # Index 0
        self.stk_stock.addWidget(self.page_stock_table) # Index 1
        
        main_layout.addWidget(self.stk_stock)
        self.tabs.addTab(w, "Stok Takip")

    def load_stock_data(self):
        # 1. UI Güncellemesini Durdur (Performansı 100 kat artırır)
        self.stock_table.setSortingEnabled(False) 
        self.stock_table.setUpdatesEnabled(False) 
        
        self.stock_table.setRowCount(0)
        
        data = self.db.get_all_products_stock()
        
        for i, (pid, name, stock) in enumerate(data):
            self.stock_table.insertRow(i)
            self.stock_table.setItem(i, 0, QTableWidgetItem(str(pid)))
            self.stock_table.setItem(i, 1, QTableWidgetItem(name))
            
            # Sayısal sıralama için
            stock_item = QTableWidgetItem()
            stock_item.setData(Qt.DisplayRole, stock)
            self.stock_table.setItem(i, 2, stock_item)
            
            # Buton ekleme (Daha hafif bir yöntemle)
            btn = QPushButton("Düzenle")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("background-color: #0a84ff; color: white; border-radius: 4px; font-weight: bold;")
            # Lambda sorunu olmaması için p=pid, s=stock kopyalaması yapıyoruz
            btn.clicked.connect(lambda _, p=pid, s=stock: self.update_stock_direct(p, s))
            
            self.stock_table.setCellWidget(i, 3, btn)

        # 2. UI Güncellemesini Geri Aç
        self.stock_table.setSortingEnabled(True)
        self.stock_table.setUpdatesEnabled(True)

    def update_stock_direct(self, pid, current_stock):
        val, ok = QInputDialog.getInt(self, "Stok Güncelle", "Yeni Stok Adedi:", current_stock, -1000, 100000, 1)
        if ok: 
            self.db.update_product_field(pid, "stock", val)
            self.load_stock_data()
            self.load_table_data()
            QMessageBox.information(self, "Başarılı", "Stok güncellendi.")

    # --- 6. BEKLEYEN İŞLEMLER   ---
    def setup_pending_transactions(self):
        """Askıdaki POS İşlemleri"""
        w = QWidget()
        l = QVBoxLayout(w)
        
        self.pending_table = QTableWidget()
        self.pending_table.setColumnCount(5)
        self.pending_table.setHorizontalHeaderLabels([
            "TX ID", "Tutar", "Zaman", "Durum", "İşlem"
        ])
        self.pending_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pending_table.setStyleSheet("QTableWidget { background:#252525; border:none; gridline-color:#333; }")
        
        l.addWidget(QLabel("Askıdaki POS İşlemleri (Yanıt Alınamayanlar)"))
        l.addWidget(self.pending_table)
        
        self.tabs.addTab(w, "Bekleyen İşlemler")

    def load_pending_data(self):
        # Verileri yükle
        pending = self.db.cursor.execute(
            "SELECT tx_id, amount, timestamp, resolved FROM pending_transactions ORDER BY id DESC"
        ).fetchall()
        
        self.pending_table.setRowCount(0)
        for i, (tx_id, amount, ts, resolved) in enumerate(pending):
            self.pending_table.insertRow(i)
            self.pending_table.setItem(i, 0, QTableWidgetItem(tx_id))
            self.pending_table.setItem(i, 1, QTableWidgetItem(f"{amount:.2f} ₺"))
            self.pending_table.setItem(i, 2, QTableWidgetItem(ts))
            self.pending_table.setItem(i, 3, QTableWidgetItem(
                "✅ Çözüldü" if resolved else "⏳ Bekliyor"
            ))
            
            btn = QPushButton("Çözüldü İşaretle")
            btn.setStyleSheet("background-color: #0a84ff; color: white; font-weight: bold;")
            btn.clicked.connect(lambda _, tid=tx_id: self.resolve_pending(tid))
            
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(5,5,5,5)
            layout.addWidget(btn)
            
            # Sadece çözülmemişler için buton koy
            if not resolved:
                self.pending_table.setCellWidget(i, 4, container)

    def resolve_pending(self, tx_id):
        """Bekleyen işlemi çözüldü olarak işaretle"""
        self.db.cursor.execute(
            "UPDATE pending_transactions SET resolved=1 WHERE tx_id=?", (tx_id,)
        )
        self.db.conn.commit()
        self.load_pending_data()  # Tabloyu yenile
        QMessageBox.information(self, "Başarılı", f"İşlem {tx_id} çözüldü olarak işaretlendi.")

    # --- 7. TOPLU İŞLEMLER ---
    def setup_bulk_operations(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(50, 50, 50, 50)
        l.setSpacing(20)
        
        title = QLabel("Toplu Fiyat Güncelleme")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #0a84ff; margin-bottom: 20px;")
        title.setAlignment(Qt.AlignCenter)
        l.addWidget(title)
        
        # Kategori Seçimi
        grp_cat = QGroupBox("1. Kategori Seçimi")
        gl = QVBoxLayout(grp_cat)
        self.cmb_bulk_cat = QComboBox()
        self.cmb_bulk_cat.addItems(["Tüm Ürünler"] + self.db.get_all_categories())
        gl.addWidget(self.cmb_bulk_cat)
        l.addWidget(grp_cat)
        
        # İşlem Türü ve Miktar
        grp_op = QGroupBox("2. İşlem Türü ve Miktar")
        gl2 = QHBoxLayout(grp_op)
        
        self.cmb_bulk_type = QComboBox()
        self.cmb_bulk_type.addItems(["Zam %", "İndirim %", "Zam TL", "İndirim TL"])
        
        self.spin_bulk_val = QDoubleSpinBox()
        self.spin_bulk_val.setRange(0.01, 10000.00)
        self.spin_bulk_val.setValue(10.00)
        self.spin_bulk_val.setSuffix(" (Birim)")
        
        gl2.addWidget(self.cmb_bulk_type)
        gl2.addWidget(self.spin_bulk_val)
        l.addWidget(grp_op)
        
        # Uyarı Metni
        lbl_warn = QLabel("Dikkat: Bu işlem geri alınamaz! Fiyatlar veritabanında kalıcı olarak değişecektir.")
        lbl_warn.setStyleSheet("color: #ff453a; font-style: italic; margin-top: 10px;")
        lbl_warn.setAlignment(Qt.AlignCenter)
        l.addWidget(lbl_warn)
        
        # Uygula Butonu
        btn_apply = QPushButton("FİYATLARI GÜNCELLE (UYGULA)")
        btn_apply.setFixedHeight(50)
        btn_apply.setStyleSheet("""
            QPushButton { background-color: #ff9f0a; color: black; font-weight: bold; font-size: 16px; border-radius: 10px; } 
            QPushButton:hover { background-color: #ffb340; }
        """)
        btn_apply.clicked.connect(self.run_bulk_update)
        l.addWidget(btn_apply)
        
        # --- ARA ÇİZGİ ---
        l.addSpacing(20)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333;")
        l.addWidget(line)
        l.addSpacing(10)
        
        # --- CSV / EXCEL İŞLEMLERİ (EKSİK OLAN KISIM BURASIYDI) ---
        lbl_csv = QLabel("Toplu Ürün Düzenleme (Excel / CSV)")
        lbl_csv.setStyleSheet("font-size: 18px; font-weight: bold; color: #34c759; margin-bottom: 10px;")
        lbl_csv.setAlignment(Qt.AlignCenter)
        l.addWidget(lbl_csv)

        csv_layout = QHBoxLayout()
        
        btn_export = QPushButton("📤 DIŞA AKTAR (CSV)")
        btn_export.setFixedHeight(50)
        btn_export.setStyleSheet("background-color: #333; color: white; border: 1px solid #555; border-radius: 8px; font-weight:bold;")
        btn_export.clicked.connect(self.export_csv)
        
        btn_import = QPushButton("📥 İÇE AKTAR (GÜNCELLE)")
        btn_import.setFixedHeight(50)
        btn_import.setStyleSheet("background-color: #0a84ff; color: white; border-radius: 8px; font-weight:bold;")
        btn_import.clicked.connect(self.import_csv)
        
        csv_layout.addWidget(btn_export)
        csv_layout.addWidget(btn_import)
        l.addLayout(csv_layout)
        # ----------------------------------------------------------

        l.addSpacing(20)
        
        # Yedekle Butonu
        btn_backup = QPushButton("YEDEK AL")
        btn_backup.setFixedHeight(40)
        btn_backup.setStyleSheet("""
            QPushButton { background-color: #333; color: #888; font-weight: bold; font-size: 14px; border-radius: 8px; border: 1px dashed #555; } 
            QPushButton:hover { background-color: #444; color: white; border: 1px solid #888; }
        """)
        btn_backup.clicked.connect(self.backup_database)
        l.addWidget(btn_backup)
        
        l.addStretch()
        
        self.tabs.addTab(w, "Toplu İşlemler / Yedek")

    def run_bulk_update(self):
        cat = self.cmb_bulk_cat.currentText()
        op = self.cmb_bulk_type.currentText()
        val = self.spin_bulk_val.value()
        
        confirm = QMessageBox.question(self, "Onay", 
                                       f"Seçili Kategori: {cat}\nİşlem: {op} - {val}\n\nBu işlemi onaylıyor musunuz?", 
                                       QMessageBox.Yes | QMessageBox.No)
        
        if confirm == QMessageBox.Yes:
            try:
                count = self.db.apply_bulk_update(cat, op, val)
                QMessageBox.information(self, "Başarılı", f"{count} adet ürün güncellendi.")
                self.load_table_data() # Ürün listesini yenile
            except Exception as e: 
                QMessageBox.critical(self, "Hata", str(e))

    def backup_database(self):
        success, msg = self.db.create_backup()
        if success: 
            QMessageBox.information(self, "Yedekleme Başarılı", f"Veritabanı yedeklendi:\n{msg}")
        else: 
            QMessageBox.critical(self, "Hata", f"Yedekleme yapılamadı:\n{msg}")

if __name__ == "__main__":
    from PySide6.QtWidgets import QFormLayout
    app = QApplication(sys.argv)
    
    font = QFont(".AppleSystemUIFont", 13) 
    app.setFont(font)    
    
    app.setStyleSheet(theme_manager.get_stylesheet()) 

    window = NexusPOS()
    window.show()
    sys.exit(app.exec())