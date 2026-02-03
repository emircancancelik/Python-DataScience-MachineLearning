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
import json
import shutil 
import csv
import pandas as pd
import numpy as np
import re
import difflib 
import ctypes
import subprocess

from sklearn.linear_model import LinearRegression 
from difflib import get_close_matches
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.cluster import KMeans
from enum import Enum
from sklearn.preprocessing import StandardScaler
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
                               QDoubleSpinBox, QFileDialog,QStackedWidget,QColorDialog, QTextEdit)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEvent
from PySide6.QtGui import QFont, QCursor, QPixmap, QColor

# =====================================================
# AYARLAR VE KONFİGÜRASYON YÖNETİMİ
# =====================================================
TEST_MODE = False
SHOP_NAME = "BAYİÇ ALCOHOL CENTER"
ADMIN_USER = "admin"
ADMIN_PASS = "123456"

def get_app_path():

    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))
    
def load_pos_config():
    """pos_config.json dosyasından ayarları okur, yoksa oluşturur"""
    config_file = os.path.join(get_app_path(), "pos_config.json")

    # GÜNCEL AYARLAR: Port 6420 ve Cihaz IP'si
    defaults = {
        "primary_ip": "192.168.1.157",  # Cihazın IP adresi (Loglardan aldık)
        "primary_port": 6420,           # GÖSB Bankacılık Portu (DLL gerektirmez, ücretsiz)
        "backup_ip": "192.168.1.158",
        "backup_port": 9100,
        "pos_type": "ingenico_gosb",    # Otomatik arama yapma, direkt bunu kullan
        "timeout": 60,
        "auto_detect": False            # Açılışta hız kazanmak için kapattık
    }
    
    if not os.path.exists(config_file):
        try:
            with open(config_file, "w") as f:
                json.dump(defaults, f, indent=4)
            print(f"✅ {config_file} oluşturuldu (Port 6420).")
        except Exception as e:
            print(f"❌ Config dosyası oluşturulamadı: {e}")
        return defaults
        
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
            # Eğer dosyada eski port (7500 veya 6000) kalmışsa, kod içindeki default ile ez
            if config.get("primary_port") != 6420:
                print("⚠️ Eski ayar tespit edildi, Port 6420'ye güncelleniyor...")
                config["primary_port"] = 6420
                config["primary_ip"] = "192.168.1.157"
                config["pos_type"] = "ingenico_gosb"
                config["auto_detect"] = False
                # Güncel hali dosyaya geri yaz
                with open(config_file, "w") as fw:
                    json.dump(config, fw, indent=4)
            
            print("✅ POS Ayarları yüklendi.")
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

# =====================================================
# TEMA YÖNETİCİSİ (DÜZELTİLMİŞ CSS)
# =====================================================
class ThemeManager:
    # Varsayılan Renkler (Apple Dark Mode Tarzı)
    DEFAULTS = {
        "bg_main": "#121212",
        "bg_panel": "#1c1c1e",      # Apple dark gray
        "bg_secondary": "#2c2c2e",  # Lighter gray
        "text_primary": "#e5e5ea",
        "text_secondary": "#8e8e93",
        "accent": "#0a84ff",        # iOS Blue
        "success": "#30d158",       # iOS Green
        "error": "#ff453a",         # iOS Red
        "warning": "#ff9f0a",       # iOS Orange
        "border": "#3a3a3c",
        "highlight": "#ffffff"
    }

    def __init__(self, filename="theme.json"):
        self.filename = os.path.join(get_app_path(), filename)
        self.current_theme = self.load_theme()

    def load_theme(self):
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
        # NOT: CSS blokları {{ }} çift parantez, Python değişkenleri { } tek parantez.
        template = """
            /* --- GENEL AYARLAR --- */
            QMainWindow {{ background-color: {bg_main}; }}
            QDialog {{ background-color: {bg_main}; }}
            QWidget {{ font-family: '-apple-system', 'Segoe UI', sans-serif; font-size: 14px; color: {text_primary}; outline: none; }}

            /* --- SCROLLBAR --- */
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {bg_main}; width: 6px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: #48484a; min-height: 30px; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

            /* --- INPUT ALANLARI (Apple Tarzı) --- */
            QLineEdit, QComboBox, QDoubleSpinBox {{ 
                background-color: {bg_secondary}; 
                color: {text_primary}; 
                border: 1px solid {border}; 
                padding: 12px 15px; 
                border-radius: 12px; 
                selection-background-color: {accent};
            }}
            QLineEdit:focus, QComboBox:focus {{ 
                border: 1px solid {accent}; 
                background-color: #3a3a3c;
            }}

            /* --- TABLO / SEPET --- */
            QTableWidget {{ 
                background-color: transparent; 
                border-radius: 12px; 
                border: none;
                gridline-color: {border}; 
            }}
            QTableWidget::item {{ 
                border-bottom: 1px solid {border}; 
                padding: 15px; 
            }}
            QTableWidget::item:selected {{ 
                background-color: rgba(10, 132, 255, 0.15); 
                color: white; 
                border-radius: 8px;
            }}
            QHeaderView::section {{ 
                background-color: {bg_main}; 
                color: {text_secondary}; 
                border: none; 
                border-bottom: 1px solid {border}; 
                padding: 10px; 
                font-weight: 600; 
                text-transform: uppercase;
                font-size: 11px;
                letter-spacing: 1px;
            }}

            /* --- BUTONLAR --- */
            QPushButton {{
                border-radius: 12px;
                font-weight: 600;
                border: 1px solid {border};
                background-color: {bg_secondary};
                color: {text_primary};
                padding: 10px;
            }}
            QPushButton:hover {{ 
                background-color: #3a3a3c; 
                border-color: {text_secondary};
            }}

            /* --- KATEGORİ KARTLARI (GRADYANLI) --- */
            /* Tüm Ürünler */
            QFrame#CategoryCard_All {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {accent}, stop:1 #005ecb);
                border-radius: 18px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            /* Normal Kategori */
            QFrame#CategoryCard_Normal {{
                background-color: {bg_secondary}; 
                border-radius: 18px;
                border: 1px solid {border};
            }}
            QFrame#CategoryCard_Normal:hover {{
                border: 1px solid {accent};
                background-color: #3a3a3c;
            }}
            /* Ekleme Kartı */
            QFrame#CategoryCard_Add {{
                background-color: rgba(48, 209, 88, 0.05);
                border-radius: 18px;
                border: 2px dashed {success};
            }}

            /* --- CİRO KUTUSU (NEON TARZI) --- */
            QLabel#CiroBox {{
                background-color: rgba(28, 28, 30, 0.8);
                color: {success};
                border: 1px solid {success};
                border-radius: 16px;
                font-weight: 800;
                font-size: 22px;
                padding: 10px 25px;
                margin-right: 15px;
                font-family: '-apple-system', sans-serif;
            }}
            QLabel#CiroBox:hover {{
                background-color: rgba(48, 209, 88, 0.15);
                cursor: pointer;
            }}

            /* --- SAĞ PANEL (NUMPAD & ÖDEME) --- */
            QFrame#ChangeFrame {{ background-color: {bg_secondary}; border-radius: 16px; border: 1px solid {border}; }}
            QLabel.ChangeResult {{ color: {success}; font-weight: 900; font-size: 28px; font-family: monospace; }}
            
            QPushButton#BtnCash {{ background-color: {success}; color: #000; border: none; font-size: 18px; font-weight: 800; }}
            QPushButton#BtnCash:hover {{ background-color: #2eb548; }}
            
            QPushButton#BtnCard {{ background-color: {accent}; color: #fff; border: none; font-size: 18px; font-weight: 800; }}
            QPushButton#BtnCard:hover {{ background-color: #0071e3; }}

            /* --- PANELLER --- */
            QFrame#LeftPanel {{ background-color: {bg_main}; border-right: 1px solid {border}; }}
            QFrame#CenterPanel {{ background-color: {bg_main}; border-right: 1px solid {border}; }}
            QFrame#RightPanel {{ background-color: {bg_main}; }}
        """
        return template.format(**self.current_theme)

# Global Nesne
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
# LOGGING
# =====================================================
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/pos.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)

logging.info("VoidPOS başlatıldı - GERÇEK POS MODU")

class IngenicoGOSB:
    """Ingenico GÖSB İletişim Sınıfı (Eski adıyla Move5000F)"""
    ACK = 0x06
    NAK = 0x15
    STX = 0x02
    ETX = 0x03
    
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.socket = None
        
    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.ip, self.port))
            return True
        except:
            return False
            
    def disconnect(self):
        if self.socket:
            try: self.socket.close()
            except: pass
            
    def sale(self, amount):
        # Basitleştirilmiş satış simülasyonu
        return {
            'success': True, 
            'response_code': '00', 
            'auth_code': '123456', 
            'rrn': 'TEST1234', 
            'message': 'Onaylandı', 
            'card_number': '****1234'
        }
# =====================================================
# INGENICO MOVE 5000F - POS ENTEGRASYONU
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
        #ingenico
        if port == 6420:
            ingenico = IngenicoGOSB(ip, port)
            if ingenico.test_connection():
                self.logger.info("✅ Ingenico GÖSB algılandı")
                return POSType.INGENICO_GOSB
        #beko
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


class IngenicoRealDriver:
    """
    Gerçek Ingenico Yazar Kasa Sürücüsü
    Python -> ixirYazarkasa.exe -> GMPSmartDLL.dll -> Yazar Kasa
    zincirini kullanarak çalışır.
    """
    def __init__(self):
        # 1. Çalışma dizinini bul
        base_path = get_app_path() # funciston.py içindeki yardımcı fonksiyonu kullanıyoruz
        
        # 2. Exe yolunu oluştur (libs klasörü içinde)
        self.exe_path = os.path.join(base_path, "libs", "ixirYazarkasa.exe")
        
        # 3. Dosya var mı kontrol et
        if os.path.exists(self.exe_path):
            print(f"✅ Yazar Kasa Programı Bulundu: {self.exe_path}")
            self.is_active = True
        else:
            print(f"⚠️ HATA: Yazar Kasa programı bulunamadı!\nAranan yol: {self.exe_path}")
            print("Lütfen 'libs' klasörünü oluşturup ixirYazarkasa.exe ve GMPSmartDLL.dll dosyalarını içine atın.")
            self.is_active = False

    def send_transaction(self, amount, payment_type):
        """
        Satış emrini exe üzerinden gönderir.
        payment_type: 0 = NAKİT, 1 = KREDİ KARTI
        """
        if amount <= 0:
            return {"success": False, "message": "Geçersiz Tutar"}

        # --- SİMÜLASYON MODU (Dosya yoksa veya test için) ---
        if not self.is_active:
            print(f"📡 [SİMÜLASYON] Cihazdan Fiş Çıkıyor... {amount:.2f} TL")
            time.sleep(1) 
            return {"success": True, "message": "Simülasyon Onayı"}
        
        # --- GERÇEK İŞLEM ---
        try:
            # ixirYazarkasa.exe genelde şu formatta çalışır: <Exe> <Tutar> <Kısım> <Tip>
            # Örnek: ixirYazarkasa.exe 1.50 1 1
            
            amount_str = f"{amount:.2f}"
            
            # Parametreler: [Exe Yolu, Tutar, KısımNo(1), ÖdemeTipi(0/1)]
            args = [self.exe_path, amount_str, "1", str(payment_type)]
            
            print(f"🔌 [CİHAZ] Komut Gönderiliyor: {args}")
            
            # Exe'yi çalıştır (capture_output=True ile sonucunu yakala)
            # creationflags=0x08000000 parametresi Windows'ta konsol penceresi açılmasını engeller
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.run(
                args, 
                capture_output=True, 
                text=True, 
                startupinfo=startupinfo
            )
            
            # Exe'nin çıkış kodunu kontrol et (0 genelde başarıdır)
            if process.returncode == 0:
                print(f"Cihaz Çıktısı: {process.stdout}")
                return {"success": True, "message": "Fiş Kesildi"}
            else:
                err_msg = process.stderr if process.stderr else "Bilinmeyen Hata"
                print(f"Cihaz Hatası ({process.returncode}): {err_msg}")
                # Hata olsa bile markette iş durmasın diye True dönebiliriz (Riskli ama pratik)
                # Şimdilik hata dönüyoruz:
                return {"success": False, "message": f"Cihaz Hatası: {err_msg}"}

        except Exception as e:
            return {"success": False, "message": f"Bağlantı Hatası: {str(e)}"}
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

        self.logger = logging.getLogger("POSService")
    
    def process_sale(self, amount: float) -> dict:
        """Satış işlemi - Thread-Safe"""
        tx_id = str(uuid.uuid4())[:8]
        self.logger.info(f"TX START | {tx_id} | {amount:.2f} TL")
        
        try:
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
        try:
            self.cursor.execute("SELECT vat_rate FROM products LIMIT 1")
        except sqlite3.OperationalError:
            # Sütun yoksa ekle (Varsayılan %20)
            self.cursor.execute("ALTER TABLE products ADD COLUMN vat_rate INTEGER DEFAULT 20")
            self.conn.commit()
            print("✅ KDV sütunu eklendi.")

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
    
    def update_product_advanced(self, pid, name, price, stock, critical, category, vat_rate, barcode):
        """Detaylı ürün güncelleme (İsim ve Barkod dahil)"""
        try:
            self.cursor.execute("""
                UPDATE products 
                SET name=?, sell_price=?, stock=?, critical_stock=?, category=?, vat_rate=?, barcode=?
                WHERE id=?
            """, (name, price, stock, critical, category, vat_rate, barcode, pid))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"DB Update Hatası: {e}")
            return False

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
    # __init__ metoduna 'double_click_cb' parametresini ekledik
    def __init__(self, pid, name, price, img_path, is_fav, stock, click_cb, update_cb, db_manager, is_mini=False, double_click_cb=None):
        super().__init__()
        self.pid = pid
        self.name_val = name
        self.price_val = price
        self.stock_val = stock
        self.cb = click_cb
        self.update_cb = update_cb
        self.db = db_manager
        self.fav = is_fav
        self.double_click_cb = double_click_cb  # Yeni callback'i kaydet
        
        # Kart Boyutları
        w, h = (150, 180) if is_mini else (170, 210)
        self.setFixedSize(w, h)
        self.setCursor(Qt.PointingHandCursor)
        
        # --- MODERN CSS TASARIMI ---
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #252525;
                border: 1px solid {'#ff453a' if stock <= 5 else '#3a3a3c'};
                border-radius: 12px;
            }}
            QFrame:hover {{
                background-color: #2a2a2a;
                border: 1px solid #0a84ff;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # --- 1. Menü Butonu ---
        self.btn_menu = QPushButton("⋮", self)
        self.btn_menu.setGeometry(w - 35, 5, 30, 30)
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.setStyleSheet("""
            QPushButton {
                background: transparent; color: #888; font-size: 24px; font-weight: 900; border: none; margin-top: -5px;
            }
            QPushButton:hover {
                color: white; background-color: rgba(255, 255, 255, 0.1); border-radius: 15px;
            }
        """)
        self.btn_menu.clicked.connect(self.show_options_menu)

        # --- 2. Ürün Görseli / İkonu ---
        icon_cont = QLabel()
        icon_cont.setAlignment(Qt.AlignCenter)
        icon_cont.setStyleSheet("border: none; background: transparent;")
        
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            icon_cont.setPixmap(pixmap.scaled(w-40, h-90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon_cont.setText(name[0].upper())
            icon_cont.setFixedSize(60, 60)
            icon_cont.setStyleSheet("""
                background-color: #333; color: #555; font-size: 28px; font-weight: bold;
                border-radius: 30px; border: 1px solid #444;
            """)
            layout_center = QHBoxLayout()
            layout_center.addWidget(icon_cont)
            layout_center.setContentsMargins(0, 15, 0, 0)
            layout.addLayout(layout_center)

        if img_path and os.path.exists(img_path):
            layout.addWidget(icon_cont, 0, Qt.AlignCenter)

        # --- 3. Ürün Adı ---
        name_lbl = QLabel(name)
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setFixedHeight(40) 
        name_lbl.setStyleSheet("color: #e0e0e0; font-weight: 600; font-size: 13px; border: none; background: transparent;")
        layout.addWidget(name_lbl)
        
        # --- 4. Fiyat ---
        price_lbl = QLabel(f"{price:.2f} ₺")
        price_lbl.setAlignment(Qt.AlignCenter)
        price_lbl.setStyleSheet("color: #30d158; font-weight: 800; font-size: 16px; border: none; background: transparent;")
        layout.addWidget(price_lbl)
        
        # --- 5. Stok ---
        if not is_mini:
            stock_color = "#ff453a" if stock <= 5 else "#888"
            lbl_stock = QLabel(f"Stok: {stock}")
            lbl_stock.setAlignment(Qt.AlignCenter)
            lbl_stock.setStyleSheet(f"color: {stock_color}; font-size: 11px; border: none;")
            layout.addWidget(lbl_stock)

    def mousePressEvent(self, e):
        # Tek tıklama (Sepete Ekle)
        child = self.childAt(e.position().toPoint())
        if child == self.btn_menu: return
        if e.button() == Qt.LeftButton: 
            self.cb(self.name_val, self.price_val)

    def mouseDoubleClickEvent(self, e):
        # Çift Tıklama (Düzenle)
        if e.button() == Qt.LeftButton and self.double_click_cb:
            self.double_click_cb(self.name_val)

    def show_options_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2e2e2e; border: 1px solid #555; } QMenu::item { color: white; padding: 5px 20px; } QMenu::item:selected { background-color: #0a84ff; }")
        
        menu.addAction("⭐ Favori Ekle/Çıkar", self.toggle_fav)
        menu.addSeparator()
        menu.addAction("💰 Fiyat Değiştir", self.change_price)
        menu.addAction("📦 Stok Düzenle", self.change_stock)
        menu.addAction("✏️ İsim Düzenle", self.change_name)
        
        menu.exec(QCursor.pos())

    # --- İşlevler ---
    def toggle_fav(self):
        self.db.toggle_favorite(self.pid, 0 if self.fav else 1)
        if self.update_cb: self.update_cb()
    def change_price(self):
        val, ok = QInputDialog.getDouble(self, "Fiyat", "Yeni Fiyat:", self.price_val, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "sell_price", val)
            if self.update_cb: self.update_cb()
    def change_name(self):
        text, ok = QInputDialog.getText(self, "İsim", "Yeni Ad:", text=self.name_val)
        if ok:
            self.db.update_product_field(self.pid, "name", text)
            if self.update_cb: self.update_cb()
    def change_stock(self):
        val, ok = QInputDialog.getInt(self, "Stok", "Yeni Stok:", self.stock_val, -1000, 100000, 1)
        if ok:
            self.db.update_product_field(self.pid, "stock", val)
            if self.update_cb: self.update_cb()
    def change_critical(self):
        val, ok = QInputDialog.getInt(self, "Kritik Stok", "Uyarı Limiti:", 5, 0, 1000, 1)
        if ok:
            self.db.update_product_field(self.pid, "critical_stock", val)
            if self.update_cb: self.update_cb()
    def change_cost(self):
        curr = self.db.get_cost(self.name_val)
        val, ok = QInputDialog.getDouble(self, "Maliyet", "Yeni Maliyet:", curr, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "cost_price", val)
            if self.update_cb: self.update_cb()
    def move_to_category(self, cat):
        self.db.update_product_field(self.pid, "category", cat)
        self.update_cb()


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

        # --- GÖRSEL AYARLAR (DOĞRUDAN STİL TANIMLAMA) ---
        # Bu yöntem ThemeManager'dan bağımsız çalışır ve kesin sonuç verir.
        
        icon_bg = "#333333"
        text_color = "#e0e0e0"
        icon_text = name[0].upper() if name else "?"
        border_style = "1px solid #3a3a3c"

        if is_all_products:
            # 1. TÜM ÜRÜNLER (Mavi Gradyan)
            self.setStyleSheet("""
                QFrame {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #007aff, stop:1 #0056b3);
                    border-radius: 16px;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                }
                QFrame:hover {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0a84ff, stop:1 #006ddb);
                    border: 1px solid white;
                }
            """)
            icon_bg = "rgba(255,255,255,0.2)"
            text_color = "white"
            icon_text = "♾️"
            
        elif is_add_button:
            # 2. EKLE BUTONU (Yeşil Kesikli Çizgi)
            self.setStyleSheet("""
                QFrame {
                    background-color: rgba(48, 209, 88, 0.05);
                    border-radius: 16px;
                    border: 2px dashed #30d158;
                }
                QFrame:hover {
                    background-color: rgba(48, 209, 88, 0.15);
                }
            """)
            icon_bg = "rgba(48, 209, 88, 0.1)"
            text_color = "#30d158"
            icon_text = "+"
            
        else:
            # 3. NORMAL KATEGORİ (Koyu Gri)
            self.setStyleSheet("""
                QFrame {
                    background-color: #252525;
                    border-radius: 16px;
                    border: 1px solid #3a3a3c;
                }
                QFrame:hover {
                    background-color: #2a2a2a;
                    border: 1px solid #0a84ff;
                }
            """)
            icon_bg = "#333333"
            text_color = "#e0e0e0"
            icon_text = name[0].upper() if name else "?"

        # İçerik Düzeni
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 15)
        layout.setSpacing(5)

        # 1. İKON (Yuvarlak)
        icon_container = QLabel(icon_text)
        icon_container.setFixedSize(40, 40)
        icon_container.setAlignment(Qt.AlignCenter)
        # İkonun stili (QFrame stilinden etkilenmesin diye özel tanımlıyoruz)
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
        lbl_name.setStyleSheet(f"background: transparent; border: none; font-weight: 600; font-size: 14px; color: {text_color};")
        layout.addWidget(lbl_name)
        
        # MENÜ BUTONU (Sadece normal kategoriler için)
        if not is_add_button and not is_all_products:
            self.btn_menu = QPushButton("⋮", self)
            self.btn_menu.setGeometry(105, 5, 20, 20)
            self.btn_menu.setStyleSheet("background: transparent; color: #666; font-weight: bold; border: none;")
            self.btn_menu.setCursor(Qt.PointingHandCursor)
            self.btn_menu.clicked.connect(self.show_options)
            self.btn_menu.show()

    # --- TIKLAMA OLAYLARI ---
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
            if self.db and self.db.rename_category(self.name, new_name):
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

    def detect_anomalies(self):
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

# =====================================================
# GELİŞTİRİLMİŞ VOID AI - DOĞAL DİL İŞLEME
# =====================================================


import requests
import json
import datetime

class VoidAI_Local:
    """Tamamen Yerel ve Çevrimdışı Çalışan AI (Ollama)"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.api_url = "http://localhost:11434/api/generate" # Ollama yerel adresi
        self.model = "gemma:2b" # veya "llama3" (daha zeki ama yavaş)

    def get_shop_context(self):
        # (Bu fonksiyon aynı kalacak, veritabanından veriyi çeker)
        today = str(datetime.date.today())
        res = self.db.cursor.execute("SELECT SUM(total_amount) FROM sales WHERE sale_date=?", (today,)).fetchone()
        ciro = res[0] if res[0] else 0
        return f"Bugün tarih: {today}. Şu anki ciro: {ciro} TL."

    def generate_response(self, user_msg):import sqlite3
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import datetime

class VoidBrain_Analytic:
    def __init__(self, db_path="voidpos.db"):
        self.db_path = db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def predict_sales(self, days_ahead=7):
        try:
            conn = self.get_connection()
            query = """
                SELECT sale_date, SUM(total_amount) as daily_total 
                FROM sales 
                GROUP BY sale_date 
                ORDER BY sale_date ASC
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < 5:
                return "Yetersiz veri (En az 5 günlük satış lazım)."

            df['sale_date'] = pd.to_datetime(df['sale_date'])
            df['date_ordinal'] = df['sale_date'].map(datetime.datetime.toordinal)

            X = df[['date_ordinal']] # Girdi (Tarih)
            y = df['daily_total']    # Çıktı (Ciro)

            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)

            # Tahmin Yap
            future_dates = []
            predictions = []
            last_date = df['sale_date'].iloc[-1]

            for i in range(1, days_ahead + 1):
                next_day = last_date + datetime.timedelta(days=i)
                next_ordinal = next_day.toordinal()
                pred = model.predict([[next_ordinal]])[0]
                
                future_dates.append(next_day.strftime("%d.%m"))
                predictions.append(pred)

            return {
                "dates": future_dates,
                "values": predictions,
                "total_predicted": sum(predictions)
            }
        except Exception as e:
            return f"Hata: {str(e)}"

    # --- YENİ ÖZELLİK 4: ABC ANALİZİ (STOK MÜHENDİSLİĞİ) ---
    def perform_abc_analysis(self):
        """
        Pareto İlkesi (80/20 Kuralı):
        - A Sınıfı: Cironun %70'ini oluşturan en önemli ürünler (Stokta ASLA bitmemeli)
        - B Sınıfı: Cironun %20'si (Önemli)
        - C Sınıfı: Cironun %10'u (Çok çeşit ama az ciro)
        """
        try:
            conn = self.get_connection()
            # Her ürünün toplam cirosunu hesapla
            query = """
                SELECT product_name, SUM(total_price) as revenue
                FROM sale_items
                GROUP BY product_name
                ORDER BY revenue DESC
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if df.empty: return "Analiz için veri yok."

            # Kümülatif toplam ve yüzdeleri hesapla
            total_revenue = df['revenue'].sum()
            df['cumulative'] = df['revenue'].cumsum()
            df['percentage'] = df['cumulative'] / total_revenue

            # Sınıflandırma
            def classify(x):
                if x <= 0.70: return 'A'
                elif x <= 0.90: return 'B'
                else: return 'C'

            df['class'] = df['percentage'].apply(classify)

            # Özet Raporu
            a_items = df[df['class'] == 'A']['product_name'].tolist()[:5] # İlk 5 tanesi
            b_count = len(df[df['class'] == 'B'])
            c_count = len(df[df['class'] == 'C'])

            msg = "📊 **ABC Stok Analizi Sonucu:**\n\n"
            msg += f"🥇 **A Sınıfı (En Değerliler):** {', '.join(a_items)}...\n"
            msg += "   *(Bu ürünler cironuzun %70'ini yapıyor! Stoklarını sıkı takip edin.)*\n\n"
            msg += f"🥈 **B Sınıfı:** {b_count} çeşit ürün.\n"
            msg += f"🥉 **C Sınıfı (Yükler):** {c_count} çeşit ürün.\n"
            msg += "   *(C sınıfı ürünler rafta yer kaplıyor olabilir, kampanya yapın.)*"
            
            return msg
        except Exception as e:
            return f"ABC Analizi Hatası: {str(e)}"

    # --- YENİ ÖZELLİK 5: GÜN SONU TAHMİNİ (PROJECTION) ---
    def predict_end_of_day(self):
        """
        Şu anki saat ve ciroya bakarak, geçmişteki benzer günlerin
        performansıyla gün sonu kapanış cirosunu tahmin eder.
        """
        try:
            conn = self.get_connection()
            now = datetime.datetime.now()
            current_hour = now.hour
            today_str = str(datetime.date.today())

            # 1. Bugün şu ana kadar ne yaptık?
            curr_res = conn.execute(f"SELECT SUM(total_amount) FROM sales WHERE sale_date='{today_str}'").fetchone()
            current_revenue = curr_res[0] if curr_res[0] else 0

            if current_revenue == 0:
                conn.close()
                return "Bugün henüz satış yok, tahmin yapılamıyor."

            # 2. Geçmişte bu saatte genelde günün yüzde kaçını tamamlamış oluyoruz?
            # Son 30 günün verisini çek
            query = f"""
                SELECT sale_date, 
                       SUM(CASE WHEN CAST(strftime('%H', timestamp) AS INT) <= {current_hour} THEN total_amount ELSE 0 END) as partial_rev,
                       SUM(total_amount) as total_rev
                FROM sales
                WHERE sale_date < '{today_str}'
                GROUP BY sale_date
                HAVING total_rev > 0
                ORDER BY sale_date DESC
                LIMIT 30
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < 5:
                return "Tahmin için en az 5 günlük geçmiş veri gerekiyor."

            # Ortalama tamamlanma oranını bul (Örn: Saat 14:00'te cironun %40'ı yapılmış oluyor)
            df['completion_rate'] = df['partial_rev'] / df['total_rev']
            avg_rate = df['completion_rate'].mean()

            if avg_rate == 0: return "Yetersiz saatlik veri."

            # 3. Tahmin: (Şu Anki Ciro) / (Tamamlanma Oranı)
            predicted_total = current_revenue / avg_rate
            
            msg = f"🔮 **Gün Sonu Kapanış Tahmini:**\n\n"
            msg += f"⏰ Saat {current_hour}:00 itibarıyla Ciro: **{current_revenue:.2f} ₺**\n"
            msg += f"📈 Tamamlanma Oranı: %{avg_rate*100:.1f}\n"
            msg += f"🏁 **Beklenen Kapanış:** **{predicted_total:.2f} ₺**\n"
            
            if predicted_total > current_revenue:
                msg += f"   *(Kalan sürede tahmini {predicted_total - current_revenue:.2f} ₺ daha satış olacak)*"
            
            return msg

        except Exception as e:
            return f"Projeksiyon Hatası: {str(e)}"
        
    def analyze_basket_segments(self):
        """Alışveriş sepetlerini tiplerine göre gruplar (K-Means)"""
        try:
            conn = self.get_connection()
            # Her fişin toplam tutarını çek
            df = pd.read_sql("SELECT total_amount FROM sales", conn)
            conn.close()

            if len(df) < 10:
                return "Analiz için en az 10 satış gerekli."

            # Veriyi ölçeklendir
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(df[['total_amount']])

            # K-Means Algoritması (3 Küme: Düşük, Orta, Yüksek)
            kmeans = KMeans(n_clusters=3, random_state=42)
            df['cluster'] = kmeans.fit_predict(scaled_data)

            # Kümelerin ortalamalarını bul
            centers = df.groupby('cluster')['total_amount'].mean().sort_values()
            
            summary = "📊 **Müşteri Sepet Analizi:**\n"
            labels = ["Küçük Alışverişler", "Standart Sepetler", "VIP / Toptan"]
            
            for i, avg in enumerate(centers):
                label = labels[i] if i < 3 else f"Grup {i}"
                count = len(df[df['cluster'] == centers.index[i]])
                summary += f"• **{label}:** Ort. {avg:.2f} TL ({count} işlem)\n"

            return summary
        except Exception as e:
            return f"Segmentasyon Hatası: {str(e)}"

    # --- ÖZELLİK 3: ÇAPRAZ SATIŞ ÖNERİSİ (MATRIX FACTORIZATION MANTIĞI) ---
    def recommend_next_product(self, current_cart_items):
        """Sepettekine göre en mantıklı ürünü matematiksel olarak bulur"""
        # Bu basit bir "Birliktelik Kuralı" (Association Rule) implementasyonudur.
        if not current_cart_items: return None
        
        try:
            conn = self.get_connection()
            # Sepetteki ürünlerin geçtiği tüm fişleri bul
            placeholders = ','.join(['?'] * len(current_cart_items))
            query = f"""
                SELECT s2.product_name, COUNT(*) as frequency
                FROM sale_items s1
                JOIN sale_items s2 ON s1.sale_id = s2.sale_id
                WHERE s1.product_name IN ({placeholders})
                AND s2.product_name NOT IN ({placeholders})
                GROUP BY s2.product_name
                ORDER BY frequency DESC
                LIMIT 1
            """
            cursor = conn.cursor()
            result = cursor.execute(query, current_cart_items).fetchone()
            conn.close()
            
            if result:
                return f"💡 Sistem Önerisi: Sepettekilerle en çok **{result[0]}** satılıyor."
            return None
        except:
            return None
        context = self.get_shop_context()
        
        prompt = f"""
        Sen bir market asistanısın. Verilen bilgilere göre cevap ver.
        BİLGİ: {context}
        SORU: {user_msg}
        CEVAP:
        """
        
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        
        try:
            response = requests.post(self.api_url, json=data)
            if response.status_code == 200:
                return response.json()['response']
            else:
                return f"Yerel AI Hatası: {response.status_code}"
        except Exception as e:
            return f"Ollama bağlantısı yok. (Terminalden 'ollama serve' yaptın mı?): {e}"



class VoidBrain_Analytic:
    """
    VoidPOS İçin Özel Geliştirilmiş Saf Python Yapay Zeka Motoru
    - Dışarıdan model indirmez.
    - Veriyi anlık öğrenir ve model oluşturur.
    """
    def __init__(self, db_path="voidpos.db"):
        self.db_path = db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # --- ÖZELLİK 1: GELECEK CİRO TAHMİNİ (REGRESSION) ---
    def predict_sales(self, days_ahead=7):
        """Geçmiş satışlara bakarak gelecek ciroyu tahmin eder."""
        try:
            conn = self.get_connection()
            query = """
                SELECT sale_date, SUM(total_amount) as daily_total 
                FROM sales 
                GROUP BY sale_date 
                ORDER BY sale_date ASC
            """
            df = pd.read_sql(query, conn)
            conn.close()

            if len(df) < 5:
                return "Yetersiz veri (En az 5 günlük satış lazım)."

            # Veriyi Hazırla
            df['sale_date'] = pd.to_datetime(df['sale_date'])
            df['date_ordinal'] = df['sale_date'].map(datetime.datetime.toordinal)

            X = df[['date_ordinal']] # Girdi (Tarih)
            y = df['daily_total']    # Çıktı (Ciro)

            # Modeli Kur ve Eğit (Saniyeler sürer)
            # Random Forest daha karmaşık ilişkileri yakalar
            model = RandomForestRegressor(n_estimators=100, random_state=42)
            model.fit(X, y)

            # Tahmin Yap
            future_dates = []
            predictions = []
            last_date = df['sale_date'].iloc[-1]

            for i in range(1, days_ahead + 1):
                next_day = last_date + datetime.timedelta(days=i)
                next_ordinal = next_day.toordinal()
                pred = model.predict([[next_ordinal]])[0]
                
                future_dates.append(next_day.strftime("%d.%m"))
                predictions.append(pred)

            return {
                "dates": future_dates,
                "values": predictions,
                "total_predicted": sum(predictions)
            }
        except Exception as e:
            return f"Hata: {str(e)}"

    # --- ÖZELLİK 2: SEPET SEGMENTASYONU (CLUSTERING) ---
    def analyze_basket_segments(self):
        """Alışveriş sepetlerini tiplerine göre gruplar (K-Means)"""
        try:
            conn = self.get_connection()
            # Her fişin toplam tutarını çek
            df = pd.read_sql("SELECT total_amount FROM sales", conn)
            conn.close()

            if len(df) < 10:
                return "Analiz için en az 10 satış gerekli."

            # Veriyi ölçeklendir
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(df[['total_amount']])

            # K-Means Algoritması (3 Küme: Düşük, Orta, Yüksek)
            kmeans = KMeans(n_clusters=3, random_state=42)
            df['cluster'] = kmeans.fit_predict(scaled_data)

            # Kümelerin ortalamalarını bul
            centers = df.groupby('cluster')['total_amount'].mean().sort_values()
            
            summary = "📊 **Müşteri Sepet Analizi:**\n"
            labels = ["Küçük Alışverişler", "Standart Sepetler", "VIP / Toptan"]
            
            for i, avg in enumerate(centers):
                label = labels[i] if i < 3 else f"Grup {i}"
                count = len(df[df['cluster'] == centers.index[i]])
                summary += f"• **{label}:** Ort. {avg:.2f} TL ({count} işlem)\n"

            return summary
        except Exception as e:
            return f"Segmentasyon Hatası: {str(e)}"

    # --- ÖZELLİK 3: ÇAPRAZ SATIŞ ÖNERİSİ (MATRIX FACTORIZATION MANTIĞI) ---
    def recommend_next_product(self, current_cart_items):
        """Sepettekine göre en mantıklı ürünü matematiksel olarak bulur"""
        # Bu basit bir "Birliktelik Kuralı" (Association Rule) implementasyonudur.
        if not current_cart_items: return None
        
        try:
            conn = self.get_connection()
            # Sepetteki ürünlerin geçtiği tüm fişleri bul
            placeholders = ','.join(['?'] * len(current_cart_items))
            query = f"""
                SELECT s2.product_name, COUNT(*) as frequency
                FROM sale_items s1
                JOIN sale_items s2 ON s1.sale_id = s2.sale_id
                WHERE s1.product_name IN ({placeholders})
                AND s2.product_name NOT IN ({placeholders})
                GROUP BY s2.product_name
                ORDER BY frequency DESC
                LIMIT 1
            """
            cursor = conn.cursor()
            result = cursor.execute(query, current_cart_items).fetchone()
            conn.close()
            
            if result:
                return f"💡 Sistem Önerisi: Sepettekilerle en çok **{result[0]}** satılıyor."
            return None
        except:
            return None
        
class VoidAI_NLP:
    """
    Void AI 3.0: 
    - Fuzzy Logic (Yazım hatası toleransı)
    - Forecasting (Gelecek tahmini)
    - Cross-Sell (Ürün önerisi)
    - Anomaly Detection (Hata/Fraud yakalama)
    - Dead Stock Logic (Stok eritme stratejisi)
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.context = {} 

        self.intent_patterns = {
            "ciro": ["ciro", "kazanç", "gelir", "hasılat", "satış", "durum"],
            "kar": ["kâr", "kar", "net", "profit", "kazancımız"],
            "stok": ["stok", "kaç tane", "envanter", "kalan", "mevcut"],
            "tahmin": ["tahmin", "gelecek", "beklenti", "yarın ne olur", "haftaya"],
            "oneri_urun": ["ne satalım", "yanına ne gider", "kombin", "öneri"],
            "anomali": ["anomali", "hata", "yanlış işlem", "şüpheli", "kaçak", "kontrol et", "tuhaflık", "güvenlik", "dengesizlik"],
            "olu_stok": ["ölü stok", "olu stok", "satmayan", "elimde kalan", "stok eritme", "ne yapayım", "zarar"],
            "abc_analizi": ["abc", "değerli ürünler", "önemli ürünler", "sınıflandırma", "pareto"],
            "gun_sonu": ["kapanış", "kaçla kapatırız", "akşam ne olur", "gün sonu", "bugün kaç olur"],
            "yardim": ["yardım", "komutlar", "ne yapabilirsin", "destek"],
        }

    def detect_intent(self, user_msg):
        """Fuzzy Matching ile akıllı niyet tespiti"""
        msg_lower = user_msg.lower()
        
        for intent, keywords in self.intent_patterns.items():
            for kw in keywords:
                match = difflib.get_close_matches(kw, msg_lower.split(), n=1, cutoff=0.7)
                if match or kw in msg_lower:
                    return intent
        return "unknown"

    def extract_product_smart(self, user_msg):
        """Mesaj içinden ürün ismini ayıklar"""
        msg_lower = user_msg.lower()
        try:
            products = self.db.cursor.execute("SELECT name FROM products").fetchall()
            product_list = [p[0] for p in products]
            product_list_lower = [p.lower() for p in product_list]
            
            # 1. Tam eşleşme
            for prod in product_list:
                if prod.lower() in msg_lower:
                    return prod
            
            # 2. Yakın eşleşme (Marlbro -> Marlboro)
            words = msg_lower.split()
            for word in words:
                matches = difflib.get_close_matches(word, product_list_lower, n=1, cutoff=0.7)
                if matches:
                    idx = product_list_lower.index(matches[0])
                    return product_list[idx]
        except:
            pass
        return None

    def generate_response(self, user_msg):
        """Ana beyin fonksiyonu"""
        intent = self.detect_intent(user_msg)
        
        # Ürün bağlamını yakala
        found_product = self.extract_product_smart(user_msg)
        if found_product:
            self.context["last_product"] = found_product
        target_product = found_product if found_product else self.context.get("last_product")

        try:
            if intent == "ciro":
                return self.handle_ciro_query()
            elif intent == "tahmin":
                res = self.brain.predict_sales(1) # Yarın için 1 gün
                if isinstance(res, dict):
                    return f"🔮 Yarınki Ciro Tahmini: **{res['total_predicted']:.2f} ₺**"
                return str(res)
            elif intent == "oneri_urun":
                return self.handle_cross_sell(target_product)
            elif intent == "stok":
                return self.handle_stock_query(target_product)
            elif intent == "anomali":
                return self.detect_anomalies() # YENİ
            elif intent == "abc_analizi":
                return self.brain.perform_abc_analysis() 
            elif intent == "gun_sonu":
                return self.brain.predict_end_of_day()
            elif intent == "olu_stok":
                return self.suggest_dead_stock_action() # YENİ
            elif intent == "yardim":
                return self.show_help()
            else:
                return "🤔 Anlayamadım. 'ABC analizi yap' veya 'Gün sonu tahmini' diyebilirsin."
        except Exception as e:
            return f"⚠️ Analiz hatası: {str(e)}"

    # --- ÖZELLİK 1: ANOMALİ TESPİTİ (GÜVENLİK) ---
    def detect_anomalies(self):
        """Isolation Forest algoritması ile şüpheli satışları bulur"""
        try:
            query = "SELECT id, total_amount, sale_date FROM sales ORDER BY id DESC LIMIT 500"
            # pd.read_sql için self.db.conn nesnesi gereklidir
            df = pd.read_sql(query, self.db.conn)
            
            if len(df) < 20:
                return "⚠️ Anomali analizi için daha fazla satış verisi gerekiyor."

            # Modeli eğit
            model = IsolationForest(contamination=0.05, random_state=42)
            df['anomaly'] = model.fit_predict(df[['total_amount']])
            
            # Anomalileri filtrele (-1 anomali demektir)
            anomalies = df[df['anomaly'] == -1]
            
            if anomalies.empty:
                return "✅ Sistem taraması temiz. Şüpheli bir işlem bulunamadı."
            
            msg = "🚨 **DİKKAT! Şüpheli İşlemler Tespit Edildi:**\n"
            msg += "(Ortalamadan sapmış işlemler aşağıdadır)\n\n"
            
            for _, row in anomalies.iterrows():
                msg += f"• Fiş #{row['id']}: **{row['total_amount']:.2f} ₺** ({row['sale_date']})\n"
            
            msg += "\n👉 *Lütfen bu fişleri kontrol ediniz (İade/Hata olabilir).* "
            return msg
        except Exception as e:
            return f"Anomali modülü hatası: {str(e)}"

    # --- ÖZELLİK 2: ÖLÜ STOK YÖNETİMİ (KÂRLILIK) ---
    def suggest_dead_stock_action(self):
        """Son 30 gündür satılmayan ürünler için fiyatlandırma stratejisi önerir"""
        try:
            # SQL: Stokta var ama son 30 gündür satılmamış
            query = """
                SELECT name, stock, sell_price, cost_price 
                FROM products 
                WHERE stock > 0 
                AND name NOT IN (
                    SELECT DISTINCT product_name 
                    FROM sale_items 
                    WHERE sale_date >= date('now', '-30 days')
                )
                ORDER BY stock DESC 
                LIMIT 5
            """
            results = self.db.cursor.execute(query).fetchall()
            
            if not results:
                return "👏 Harika! 'Ölü stok' (hiç satmayan) ürününüz yok."
            
            msg = "❄️ **Stok Eritme Önerileri (Ölü Stoklar):**\n"
            for name, stock, price, cost in results:
                # Başabaş noktası (Maliyet + %10 Masraf)
                breakeven = cost * 1.1 
                
                if price > breakeven:
                    discount_price = breakeven
                    msg += f"• **{name}** ({stock} adet): 30 gündür hareketsiz.\n"
                    msg += f"   👉 Öneri: Fiyatı **{discount_price:.2f} ₺** seviyesine indirin (Maliyetine Satış).\n"
                else:
                    msg += f"• **{name}** ({stock} adet): Zaten dip fiyatta. 1 Alana 1 Bedava yapın.\n"
                    
            return msg
        except Exception as e:
            return f"Analiz hatası: {str(e)}"

    # --- ÖZELLİK 3: GELECEK TAHMİNİ (MAKİNE ÖĞRENMESİ) ---
    def handle_sales_forecast(self):
        """Linear Regression ile yarınki ciroyu tahmin eder"""
        try:
            query = """
                SELECT sale_date, SUM(total_amount) as daily_total 
                FROM sales 
                GROUP BY sale_date 
                ORDER BY sale_date ASC 
                LIMIT 60
            """
            df = pd.read_sql(query, self.db.conn)
            
            if len(df) < 5:
                return "⚠️ Tahmin için en az 5 günlük veri lazım."

            # Tarihleri sayısal veriye çevir
            df['date_ordinal'] = pd.to_datetime(df['sale_date']).map(datetime.datetime.toordinal)
            
            X = df['date_ordinal'].values.reshape(-1, 1)
            y = df['daily_total'].values
            
            model = LinearRegression()
            model.fit(X, y)
            
            # Yarını hesapla
            tomorrow = datetime.date.today() + datetime.timedelta(days=1)
            tomorrow_ordinal = np.array([[tomorrow.toordinal()]])
            prediction = model.predict(tomorrow_ordinal)[0]
            
            trend = "Yükseliş 📈" if model.coef_[0] > 0 else "Düşüş 📉"
            
            return f"🔮 **AI Ciro Tahmini (Yarın):**\nBeklenen: **{max(0, prediction):.2f} ₺**\nTrend: **{trend}**"
            
        except Exception as e:
            return f"Tahmin hatası: {str(e)}"

    # --- DİĞER STANDART FONKSİYONLAR ---
    def handle_cross_sell(self, product_name):
        if not product_name: return "Hangi ürün için öneri istiyorsun? (Örn: 'Viski yanına ne gider?')"
        try:
            query = f"""
                SELECT product_name, COUNT(*) as cnt 
                FROM sale_items 
                WHERE sale_id IN (SELECT sale_id FROM sale_items WHERE product_name = '{product_name}') 
                AND product_name != '{product_name}'
                GROUP BY product_name ORDER BY cnt DESC LIMIT 3
            """
            results = self.db.cursor.execute(query).fetchall()
            if not results: return f"ℹ️ **{product_name}** için henüz yeterli veri yok."
            
            msg = f"💡 **{product_name}** alanlar şunları da alıyor:\n"
            for prod, qty in results: msg += f"• {prod} ({qty} kez)\n"
            return msg
        except: return "Öneri oluşturulamadı."

    def handle_ciro_query(self):
        today = str(datetime.date.today())
        res = self.db.cursor.execute("SELECT SUM(total_amount) FROM sales WHERE sale_date=?", (today,)).fetchone()
        val = res[0] if res[0] else 0.0
        return f"💰 Bugün şu ana kadar **{val:.2f} ₺** ciro yaptık."

    def handle_stock_query(self, product_name):
        if product_name:
            res = self.db.cursor.execute("SELECT stock FROM products WHERE name=?", (product_name,)).fetchone()
            if res: return f"📦 **{product_name}** stoğu: {res[0]} adet."
            return f"❌ {product_name} bulunamadı."
        return "Hangi ürünün stoğunu merak ediyorsun?"

    def show_help(self):
        return """
🧠 **Void AI Gelişmiş Komutlar:**

📊 **Analiz:**
- "ABC analizi yap" (Ürünleri önem sırasına dizer)
- "Gün sonu tahmini" (Bugün kaçla kapatırız?)

🔮 **Tahmin & Güvenlik:**
- "Yarın ciro ne olur?"
- "Anomali var mı?"

📦 **Stok & Satış:**
- "Ölü stoklar neler?"
- "Viski yanına ne gider?"
- "Bugünkü ciro"
        """

class AIChatDialog(QDialog):    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.ai_engine = VoidAI_NLP(db_manager)  
        self.brain = VoidBrain_Analytic(db_manager.db_path)
        
        self.setWindowTitle("🧠 Void AI - Akıllı Asistan (Yerel)")
        self.setFixedSize(600, 800)
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        
        layout = QVBoxLayout(self)
        
        # Başlık
        header = QLabel("🧠 Void AI Asistanı")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #0a84ff; margin-bottom: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Chat Ekranı
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                border: 1px solid #333;
                border-radius: 12px;
                padding: 15px;
                font-size: 15px;
            }
        """)
        layout.addWidget(self.chat_history)
        
        # Karşılama mesajı
        self.add_message("Void AI", "👋 Merhaba! Verilerinizi analiz etmeye hazırım. 'Ciro tahmini', 'Anomali var mı?' veya 'Ölü stoklar' diye sorabilirsiniz.", is_html=True)
        
        # Mesaj girişi
        input_layout = QHBoxLayout()
        
        self.inp_msg = QLineEdit()
        self.inp_msg.setPlaceholderText("Bir komut yazın...")
        self.inp_msg.setStyleSheet("""
            QLineEdit {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                border-radius: 20px;
                padding: 12px 20px;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #0a84ff; }
        """)
        self.inp_msg.returnPressed.connect(self.send_message)
        
        btn_send = QPushButton("➤")
        btn_send.setFixedSize(50, 50)
        btn_send.setCursor(Qt.PointingHandCursor)
        btn_send.setStyleSheet("""
            QPushButton {
                background-color: #0a84ff;
                color: white;
                border-radius: 25px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0077e6; }
        """)
        btn_send.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.inp_msg)
        input_layout.addWidget(btn_send)
        
        layout.addLayout(input_layout)

    # ... (Sınıfın geri kalan fonksiyonları add_message ve send_message aynı kalacak) ...
    def add_message(self, sender, text, is_html=False):
        # ... (Eski kodunuzdaki gibi) ...
        color = "#0a84ff" if sender == "Void AI" else "#30d158"
        align = "left" if sender == "Void AI" else "right"
        bg_color = "#2a2a2a" if sender == "Void AI" else "#1e3a2a"
        
        formatted_text = text if is_html else text.replace('\n', '<br>')
        
        html = f"""
        <div style='text-align:{align}; margin-bottom: 15px;'>
            <div style='display:inline-block; background-color:{bg_color}; padding:12px; border-radius:10px; max-width:80%;'>
                <span style='color:{color}; font-weight:bold; font-size:12px;'>{sender}</span><br>
                <span style='color:#e0e0e0;'>{formatted_text}</span>
            </div>
        </div>
        """
        self.chat_history.append(html)
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())

    def send_message(self):
        msg = self.inp_msg.text().strip()
        if not msg: return
        
        self.add_message("Siz", msg)
        self.inp_msg.clear()
        QApplication.processEvents()
        
        try:
            # VoidAI_NLP sınıfını kullanıyoruz
            response = self.ai_engine.generate_response(msg)
            self.add_message("Void AI", response, is_html=True)
        except Exception as e:
            self.add_message("Void AI", f"⚠️ Hata: {str(e)}")

class VoidAI_Engine:
    def __init__(self, csv_yolu="urunler_klasoru/urunler.csv"):
        self.csv_yolu = csv_yolu

    def verileri_oku(self):
        """CSV dosyasını okur ve bir liste olarak döndürür."""
        if not os.path.exists(self.csv_yolu):
            return []
        
        veriler = []
        try:
            with open(self.csv_yolu, mode='r', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    veriler.append(row)
        except Exception as e:
            print(f"CSV Okuma Hatası: {e}")
        return veriler

    def tum_analizleri_yap(self):
        """Stok ve kritik seviye analizi yapar."""
        urunler = self.verileri_oku()
        oneriler = []

        if not urunler:
            return []

        for urun in urunler:
            try:
                u_id = urun.get('id')
                ad = urun.get('name') or urun.get('urun_adi', 'Bilinmeyen')
                
                # Veri tiplerini güvenli çevir
                try: stok = int(float(urun.get('stock', 0)))
                except: stok = 0
                
                try: kritik = int(float(urun.get('critical_stock', 5)))
                except: kritik = 5

                # --- KURAL: KRİTİK STOK ANALİZİ ---
                if stok <= kritik:
                    eksik = (kritik * 3) - stok 
                    oneriler.append({
                        "tur": "SIPARIS",
                        "mesaj": f"📦 STOK ALARMI: {ad} kritik seviyede (Stok: {stok}).",
                        "aksiyon_verisi": {"id": u_id, "islem": "mail_at", "miktar": eksik}
                    })

            except Exception as e:
                continue 

        return oneriler

    def aksiyonu_uygula(self, aksiyon_verisi):
        if aksiyon_verisi.get("islem") == "mail_at":
            return f"Sipariş listesine {aksiyon_verisi['miktar']} adet eklendi. ✅"
        return "İşlem uygulandı."

class AIWorker(QThread):
    finished = Signal(list)  # Sonuçları ana ekrana taşıyan sinyal

    def __init__(self, csv_path):
        super().__init__()
        self.csv_path = csv_path

    def run(self):
        print("--- AI Worker Başladı (Arka Plan) ---") # Kontrol için
        try:
            if os.path.exists(self.csv_path):
                # VoidAI_Engine sınıfını kullanıyoruz
                motor = VoidAI_Engine(self.csv_path)
                sonuclar = motor.tum_analizleri_yap()
                self.finished.emit(sonuclar)
            else:
                self.finished.emit([])
        except Exception as e:
            print(f"AI Worker Hatası: {e}")
            self.finished.emit([])
        print("--- AI Worker Bitti ---")
            
class VoidPOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.denominations = [200, 100, 50, 20, 10, 5, 1, 0.50, 0.25]
        self.db = DatabaseManager()
        self.pos_driver = IngenicoRealDriver()
        self.installEventFilter(self)
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.interval = 300 # 300 milisaniye bekleme süresi
        self.search_timer.timeout.connect(self.execute_search)
        self.current_category = "Tüm Ürünler" # Varsayılan kategori
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
        left_container.setFixedWidth(480) #ürün arama kısmının uzunluğu
        left_container.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(20, 30, 20, 20) # kenar boşlukları 
        left_layout.setSpacing(15)
        
        # Arama
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Ara...")
        self.search_bar.setFixedHeight(45) #ürün arama kısmının eni
        self.search_bar.textChanged.connect(self.on_search_changed)
        left_layout.addWidget(self.search_bar)
        
        # Ürün Grid (Scroll Area)
        self.selection_scroll = QScrollArea()
        self.selection_scroll.setWidgetResizable(True)
        self.selection_scroll.setStyleSheet("border:none; background:transparent;")
        self.selection_cont = QWidget()
        self.selection_lay = QGridLayout(self.selection_cont)
        self.selection_lay.setContentsMargins(0, 10, 0, 0)
        self.selection_lay.setSpacing(15) # kartlar arası boşluk
        self.selection_scroll.setWidget(self.selection_cont)
        left_layout.addWidget(self.selection_scroll)
        
        main_lay.addWidget(left_container)

        # --- 2. ORTA PANEL ---
        center_container = QFrame()
        # border-right ile sağ paneli ayırıyoruz ama kendi etrafında kutu yok
        center_container.setObjectName("CenterPanel")        
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(10, 20, 10, 10) # Üstten biraz boşluk
        
        # Üst Bar
        top_bar = QHBoxLayout()
        self.lbl_ciro = ClickableLabel(f"Ciro: {self.db.get_daily_turnover():.2f} ₺")
        self.lbl_ciro.setObjectName("CiroBox") # CSS buradan bağlanıyor
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

    def open_product_detail_popup(self, product_name):
        """Ürün detay/düzenleme penceresini açar"""
        dlg = ProductDetailDialog(self.db, product_name, self)
        if dlg.exec():
            # Eğer değişiklik yapıldıysa ve şu an o kategorideysek ekranı yenile
            if self.current_category != "Tüm Ürünler":
                self.load_products_grid(self.current_category)

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress:
            if not isinstance(QApplication.focusWidget(), QLineEdit):
                self.search_bar.setFocus()
                QApplication.sendEvent(self.search_bar, event)
                return True
        return super().eventFilter(source, event)
     
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
        table.setHorizontalHeaderLabels(["ÜRÜN", "FİYAT", "ADET", " "]) 
        
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
        table.setShowGrid(False) 
        
        table.setStyleSheet("background-color: transparent; border: none;")

        # --- KRİTİK GÜNCELLEME: TIKLAMA OLAYLARI ---
        
        # 1. Tek Tık / Değişim: Zaten itemChanged sinyali ile çalışıyor.
        # Fiyat sütunu (1. sütun) editlenebilir olduğu için tek tıkla düzenleme modu açılır.
        # Sadece Adet ve Fiyat sütunlarını düzenlenebilir yapıyoruz.
        table.itemChanged.connect(self.on_cart_item_changed)
        table.itemClicked.connect(self.row_selected)
        
        # 2. Çift Tık: Detay Penceresi Aç
        table.doubleClicked.connect(self.on_table_double_clicked)
        
        return table

    # --- YENİ FONKSİYON: Çift Tıklama İşleyicisi ---
    def on_table_double_clicked(self, index):
        """Tabloya çift tıklandığında çalışır"""
        table = self.sender() # Hangi tablodan geldiğini bul
        row = index.row()
        
        # Ürün adını 0. sütundan al
        item_name = table.item(row, 0).text()
        
        db_ref = None
        # En basit yöntem: parent window'u bulup db'sini almak
        parent = self.window()
        if hasattr(parent, 'db'):
            db_ref = parent.db
            
        if db_ref:
            dlg = ProductDetailDialog(db_ref, item_name, self)
            if dlg.exec():
                # Kaydedildiyse sepeti güncellemek gerekebilir ama 
                # sepetteki fiyat o anlık işlem için kalır, DB güncellenir.
                pass
        else:
            QMessageBox.warning(self, "Hata", "Veritabanı bağlantısı bulunamadı.")

    def open_product_detail_popup(self, product_name):
        """Ürün detay/düzenleme penceresini açar"""
        dlg = ProductDetailDialog(self.db, product_name, self)
        if dlg.exec():
            # Eğer değişiklik yapıldıysa ve şu an o kategorideysek ekranı yenile
            if self.current_category != "Tüm Ürünler":
                self.load_products_grid(self.current_category)
            else:
                # Tüm ürünlerdeysek veya arama sonucundaysak search'ü tetikle veya kategorileri yükle
                pass

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
        
        # --- HATA DÜZELTME KODU ---
        # Eğer panel henüz yüklenmediyse (program açılışındaysa) işlemi yapma, çık.
        if not hasattr(self, 'change_labels') or not self.change_labels:
            return
        # --------------------------

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
        # 1. Kategori Takibini Güncelle
        self.current_category = category_name 
        
        # Arama placeholder'ını duruma göre ayarla
        if category_name == "Tüm Ürünler":
            self.search_bar.setPlaceholderText("🔍 Kategori Ara...")
        else:
            self.search_bar.setPlaceholderText(f"🔍 {category_name} içinde ürün ara...")

        # 2. Güncellemeyi durdur (Performans)
        self.selection_scroll.setUpdatesEnabled(False) 
        
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
        self.selection_lay.addWidget(btn_back, 0, 0, 1, 4) 
        
        # --- ÜRÜN ÇEKME (LIMIT EKLENDİ - DONMAYI ÖNLER) ---
        products = []
        if category_name == "Tüm Ürünler":
             # Sadece son eklenen 60 ürünü göster
            query = "SELECT id, name, sell_price, image_path, is_favorite, stock FROM products ORDER BY id DESC LIMIT 60"
            products = self.db.cursor.execute(query).fetchall()
            
            lbl_limit = QLabel("⚡ Hız için son 60 ürün gösteriliyor. Aradığınızı bulamadıysanız arama yapın.")
            lbl_limit.setStyleSheet("color: #888; font-size:12px; margin: 5px;")
            self.selection_lay.addWidget(lbl_limit, 1, 0, 1, 4)
            row_offset = 2
        else:
            products = self.db.get_products(category_name)
            row_offset = 1

        if not products:
            lbl = QLabel("Bu kategoride ürün yok.")
            lbl.setStyleSheet("color: #666; margin-top: 20px; font-size: 14px;")
            self.selection_lay.addWidget(lbl, 1, 0, 1, 4)
        else:
            col = 0
            row = row_offset
            max_col = 3
            
            for pid, name, price, img, fav, stock in products:
                # Tek Tık Fonksiyonu
                def on_click(n, p):
                    self.add_to_cart(n, p)
                
                # Çift Tık Fonksiyonu (Döngü içinde tanımlanmalı ki 'name' değerini doğru alsın)
                def on_double_click(prod_name):
                    self.open_product_detail_popup(prod_name)

                # ProductCard Oluşturma
                card = ProductCard(
                    pid, name, price, img, fav, stock, 
                    on_click, 
                    lambda: self.load_products_grid(category_name), 
                    self.db, 
                    is_mini=True,
                    double_click_cb=on_double_click # Artık hata vermez
                )
                
                self.selection_lay.addWidget(card, row, col)
                col += 1
                if col >= max_col:
                    col = 0
                    row += 1

        QApplication.processEvents() 
        self.selection_scroll.verticalScrollBar().setValue(0)
        self.selection_scroll.setUpdatesEnabled(True)

    def load_categories_grid(self):
        self.current_category = "Tüm Ürünler"
        self.search_bar.setPlaceholderText("🔍 Tüm ürünlerde ara...")
        self.clear_selection_area()
        self.selection_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # --- 1. KATEGORİ BAŞLIĞI ---
        lbl_cat = QLabel("KATEGORİLER")
        lbl_cat.setStyleSheet("color: #0a84ff; font-weight: 800; font-size: 14px; margin: 10px 0 5px 10px;")
        self.selection_lay.addWidget(lbl_cat, 0, 0, 1, 3)

        # --- 2. KATEGORİ SCROLL (SABİT YÜKSEKLİK) ---
        cat_scroll = QScrollArea()
        cat_scroll.setFixedHeight(300) # Kategoriler çok yer kaplamasın
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setStyleSheet("border: none; background: transparent;")
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        cat_container = QWidget()
        cat_grid = QGridLayout(cat_container)
        cat_grid.setContentsMargins(10, 0, 10, 0)
        cat_grid.setSpacing(15)
        cat_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # TÜM ÜRÜNLER KARTI
        def show_all():
            self.load_products_grid("Tüm Ürünler")
        all_card = CategoryCard("Tüm Ürünler", lambda x: show_all(), is_all_products=True)
        cat_grid.addWidget(all_card, 0, 0)

        # DİĞER KATEGORİLER
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
        
        # EKLEME KARTI
        def trigger_add_cat(_):
            self.add_category()
        add_card = CategoryCard("Kategori Ekle", trigger_add_cat, is_add_button=True)
        cat_grid.addWidget(add_card, c_row, c_col)

        cat_scroll.setWidget(cat_container)
        self.selection_lay.addWidget(cat_scroll, 1, 0, 1, 3)

        # --- 3. ARA ÇİZGİ ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333; margin: 15px 0;")
        self.selection_lay.addWidget(line, 2, 0, 1, 3)

        # --- 4. HIZLI ERİŞİM BAŞLIĞI ---
        lbl_fav = QLabel("HIZLI ERİŞİM")
        lbl_fav.setStyleSheet("color: #ffcc00; font-weight: 800; font-size: 14px; margin-left: 10px;")
        self.selection_lay.addWidget(lbl_fav, 3, 0, 1, 3)

        # --- 5. HIZLI ERİŞİM SCROLL (YENİ EKLENEN ÖZELLİK) ---
        # Buraya özel bir ScrollArea ekliyoruz ki aşağı doğru kayabilsin
        fav_scroll = QScrollArea()
        fav_scroll.setWidgetResizable(True)
        fav_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #121212; width: 6px; }
            QScrollBar::handle:vertical { background: #444; border-radius: 3px; }
        """)
        
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
                if f_col >= 4: # Yan yana 4 ürün
                    f_col = 0
                    f_row += 1
            
            fav_scroll.setWidget(fav_container)
            # Layout'a eklerken esneme payı (stretch) veriyoruz ki kalan alanı kaplasın
            self.selection_lay.addWidget(fav_scroll, 4, 0, 1, 3)
            self.selection_lay.setRowStretch(4, 1) # Bu satır favorilerin aşağı uzamasını sağlar
        else:
            self.selection_lay.addWidget(QLabel("Henüz favori ürün yok.", styleSheet="color: #555; margin-left: 10px;"), 4, 0, 1, 3)
            
        # Alt boşluk (Gerekirse)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        spacer.setFixedHeight(10)
        self.selection_lay.addWidget(spacer, 5, 0)

    def on_search_changed(self, text):
        """Arama kutusuna yazı yazıldığında çalışır (Gecikmeli)"""
        # Her harfe basıldığında zamanlayıcıyı sıfırla
        # Bu sayede kullanıcı yazarken arama yapmaz, durunca yapar.
        if hasattr(self, 'search_timer'):
            self.search_timer.stop()
            self.search_timer.start(300) # 300ms sonra execute_search çalışacak

    def execute_search(self):
        """
        Bağlam Duyarlı Arama:
        - Ana ekrandaysan (Tüm Ürünler) -> KATEGORİ ara
        - Kategori içindeysen -> O kategorideki ÜRÜNLERİ ara
        """
        text = self.search_bar.text().strip()
        
        # 1. Arama kutusu boşsa varsayılan görünüme dön
        if not text:
            if self.current_category == "Tüm Ürünler":
                self.load_categories_grid()
            else:
                self.load_products_grid(self.current_category)
            return
            
        self.clear_selection_area()
        self.selection_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        # ============================================================
        # SENARYO 1: ANA EKRANDAYIZ -> KATEGORİ ARAMASI YAP
        # ============================================================
        if self.current_category == "Tüm Ürünler":
            # Kategoriler tablosunda ara
            query = "SELECT name FROM categories WHERE name LIKE ? AND name != 'Tüm Ürünler'"
            params = [f"%{text}%"]
            results = self.db.cursor.execute(query, params).fetchall()
            
            if not results:
                self.selection_lay.addWidget(QLabel("Kategori bulunamadı.", styleSheet="color:#666; font-size:16px; margin:20px;"), 0, 0)
                return
                
            col = 0
            row = 0
            max_col = 3
            
            for cat_tuple in results:
                cat_name = cat_tuple[0]
                
                # Kategori kartı oluştur
                card = CategoryCard(
                    cat_name, 
                    self.load_products_grid, # Tıklanınca ürünleri yükle
                    is_add_button=False, 
                    db_manager=self.db, 
                    refresh_cb=self.refresh_ui
                )
                self.selection_lay.addWidget(card, row, col)
                
                col += 1
                if col >= max_col:
                    col = 0
                    row += 1

        # ============================================================
        # SENARYO 2: KATEGORİ İÇİNDEYİZ -> ÜRÜN ARAMASI YAP
        # ============================================================
        else:
            # Sadece mevcut kategorideki ürünleri ara + LIMIT 60 (Donmayı Önler)
            query = """
                SELECT id, name, sell_price, image_path, is_favorite, stock 
                FROM products 
                WHERE category = ? AND (name LIKE ? OR barcode LIKE ?)
                LIMIT 60
            """
            params = [self.current_category, f"%{text}%", f"%{text}%"]
            
            results = self.db.cursor.execute(query, params).fetchall()
            
            if not results:
                self.selection_lay.addWidget(QLabel(f"'{self.current_category}' içinde sonuç yok.", styleSheet="color:#666; font-size:16px; margin:20px;"), 0, 0)
                return
                
            col = 0
            row = 0
            max_col = 3
            
            for pid, name, price, img, fav, stock in results:
                def on_click(n, p):
                    self.add_to_cart(n, p)
                
                # Çift tıklama fonksiyonu
                def on_double_click(prod_name):
                    self.open_product_detail_popup(prod_name)

                card = ProductCard(
                    pid, name, price, img, fav, stock, 
                    on_click, 
                    lambda: self.execute_search(), 
                    self.db, 
                    is_mini=True,
                    double_click_cb=on_double_click
                )
                card.setFixedSize(165, 180)
                
                self.selection_lay.addWidget(card, row, col)
                col += 1
                if col >= max_col:
                    col = 0
                    row += 1
        
        # Alttan itmek için spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.selection_lay.addWidget(spacer, row + 1, 0)
        self.selection_lay.setRowStretch(row + 1, 1)

    def toggle_ciro_visibility(self):
        self.ciro_visible = not self.ciro_visible
        self.update_ciro()

    def update_ciro(self):
        daily = self.db.get_daily_turnover()
        if self.ciro_visible:
            # Başına 💰 ikonu ekledik
            self.lbl_ciro = ClickableLabel(f"💰 {self.db.get_daily_turnover():.2f} ₺")
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
        if self.selected_row != -1:
                # Rakam tuşları
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
            if e.text() and e.text().isprintable() and not e.text().isdigit(): 
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
        cart = self.get_current_cart() # Bu bir QTableWidget döndürür
        if not cart: return
        
        # HATA DÜZELTİLDİ: cart.table.currentRow() yerine cart.currentRow()
        row = cart.currentRow() 
        
        if row < 0: return # Seçili satır yok
        
        # HATA DÜZELTİLDİ: cart.table.item yerine cart.item
        current_qty_item = cart.item(row, 2)
        try:
            current_val = int(current_qty_item.text())
        except:
            current_val = 1
            
        new_val = current_val
        
        if key == 'C':
            cart.removeRow(row) # cart.table yerine cart
        elif key == '⌫':
             # Numpad ile silme (Backspace)
            s_val = str(current_val)
            if len(s_val) > 1:
                new_val = int(s_val[:-1])
            else:
                new_val = 1
    
            cart.blockSignals(True)
            cart.item(row, 2).setText(str(new_val))
            cart.blockSignals(False)
            self.recalc_active_cart_total()

        else:
            # Rakam ekleme
            if current_val == 1:
                new_val = int(key)
            else:
                new_val = int(str(current_val) + key)
            
            # Güncelleme
            cart.blockSignals(True)
            cart.item(row, 2).setText(str(new_val))
            cart.blockSignals(False)
            self.recalc_active_cart_total()

    def finish_sale(self, method):
        """NAKİT SATIŞ - Fiş Yazar Kasadan Çıkar"""
        if not self.cart_data:
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
        
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        
        # 1. Yazar Kasaya Gönder (Tip: 0 = Nakit)
        # Ekranı dondurmamak için işlem sırasında fare imlecini bekleme moduna al
        QApplication.setOverrideCursor(Qt.WaitCursor)
        result = self.pos_driver.send_transaction(total, 0) 
        QApplication.restoreOverrideCursor()
        
        if not result['success']:
            # Cihaz hata verdiyse satışı iptal etme şansı ver veya zorla kaydet
            reply = QMessageBox.question(self, "Cihaz Hatası", 
                                       f"Yazar Kasa Hatası: {result['message']}\n\nYine de satışı kaydetmek istiyor musun?", 
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No:
                return

        # 2. Veritabanına Kaydet
        self.db.record_sale(self.cart_data, total, "Nakit")
        
        # 3. Temizlik
        self.get_active_table().setRowCount(0)
        self.cart_data = []
        self.recalc_active_cart_total()
        self.update_ciro()

    def card_payment(self):
        """KARTLI SATIŞ - Fiş Yazar Kasadan Çıkar"""
        # 1. Sepet Kontrolü
        if not self.cart_data:
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
        
        # 2. Tutar Hesapla
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        
        # 3. Görsel Geri Bildirim (Butonu Sarı Yap)
        self.set_payment_processing(True, "KART")
        # Arayüzün donmaması için olayları işle
        QApplication.processEvents() 
        
        try:
            # 4. Sürücü Başlatılmış mı Kontrol Et
            if not hasattr(self, 'pos_driver'):
                self.pos_driver = IngenicoRealDriver()

            # 5. Yazar Kasaya Gönder (Tip: 1 = Kredi Kartı)
            result = self.pos_driver.send_transaction(total, 1)
            
        except Exception as e:
            result = {"success": False, "message": f"Sürücü Hatası: {str(e)}"}

        # 6. Görseli Eski Haline Getir
        self.set_payment_processing(False)

        # 7. Sonuç İşleme
        if result['success']:
            # Başarılı -> Veritabanına Yaz
            self.db.record_sale(self.cart_data, total, "Kredi Kartı")
            
            # Ekranı Temizle
            self.get_active_table().setRowCount(0)
            self.cart_data = []
            self.recalc_active_cart_total()
            self.update_ciro()
            
            # (İsteğe Bağlı) Başarılı Mesajı
            # QMessageBox.information(self, "Onay", "İşlem Başarılı")
        else:
            # Başarısız -> Hata Göster
            QMessageBox.critical(self, "Hata", f"Kart İşlemi Başarısız:\n{result['message']}")

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

    def ai_otomatik_kontrol(self):
        """Arka planda AI kontrolünü başlatır"""
        print("AI Kontrol Tetiklendi...") # Debug çıktısı
        
        # Dosya yolunu al
        csv_yolu = os.path.join(get_app_path(), "urunler_klasoru", "urunler.csv")
        
        # Eğer zaten çalışan bir işçi varsa onu durdurmayalım, yenisini başlatmayalım
        if hasattr(self, 'ai_worker') and self.ai_worker.isRunning():
            print("AI zaten çalışıyor, bu turu atla.")
            return
        self.ai_worker = AIWorker(csv_yolu)
        self.ai_worker.finished.connect(self.ai_sonucunu_isles)
        self.ai_worker.start()

    def ai_sonucunu_isles(self, sonuclar):
        """Arka plandan gelen sonuçları ekrana basar"""
        print(f"AI Sonuçları Geldi: {len(sonuclar)} öneri") # Debug çıktısı
        
        if sonuclar:
            self.ai_btn.setText(f"AI: {len(sonuclar)} ÖNERİ VAR!")
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
            chat_dlg = AIChatDialog(self.db, self)  
            chat_dlg.exec()
                   
# ==========================================
# YÖNETİM PANELİ
# ==========================================
class AdminDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Yönetim Paneli")
        self.resize(1200, 800)

        # 1. Layout ve Tabs oluştur
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # 2. Değişkenleri Tanımla
        self.editing_pid = None
        self.filter_mode = 'day'
        self.last_tab_index = 0

        # 3. Sekmeleri Oluştur (Sırasıyla)
        # Index 0: AI
        self.setup_native_ai_tab()        
        # Index 1: Finansal Rapor
        self.setup_finances()             
        # Index 2: Satış Geçmişi
        self.setup_sales_history()        
        # Index 3: Ürün Listesi
        self.setup_prod_list()            
        # Index 4: Ürün Ekle
        self.setup_add_prod()             
        # Index 5: Stok Takip
        self.setup_stock_tracking()       
        # Index 6: Bekleyen İşlemler
        self.setup_pending_transactions() 
        # Index 7: Toplu İşlemler
        self.setup_bulk_operations()      
        # Index 8: Tema
        self.setup_theme_settings()       
        
        # 4. Sinyali EN SON bağla (Hata almamak için)
        self.tabs.currentChanged.connect(self.on_tab_change)

        # 5. İlk açılışta AI sekmesi (Index 0) açık olacağı için özel bir yükleme gerekmez,
        # ancak Finans verisi hazır olsun derseniz manuel çağırabilirsiniz.
        # self.load_finance_data() # Bunu kaldırdık çünkü ilk sekme artık AI.

    # ... (Diğer setup metodlarınız AYNEN kalacak) ...

    # on_tab_change metodunu GÜNCELLEYİN (İndeksler değiştiği için):
    def on_tab_change(self, index):
        self.last_tab_index = index
        
        if index == 1:   # Finansal (Eskiden 0'dı, şimdi 1 oldu)
            self.load_finance_data()
        elif index == 2: # Satış Geçmişi
            self.load_sales_history_data()
        elif index == 3: # Ürün Listesi
            self.load_table_data()
        elif index == 5: # Stok Takip
            self.stk_stock.setCurrentIndex(0) 
            self.load_stock_categories()
        elif index == 6: # Bekleyen
            self.load_pending_data()

    def setup_theme_settings(self):
        editor = ThemeEditor(self)
        self.tabs.addTab(editor, "🎨 Tema Ayarları")

    def setup_native_ai_tab(self):
        """Kütüphane tabanlı yerel AI sekmesi"""
        self.brain = VoidBrain_Analytic(self.db.db_name) # Motoru başlat
        
        w = QWidget()
        layout = QVBoxLayout(w)
        
        # --- Başlık ---
        lbl_title = QLabel("🧠 Void Dynamics - Analitik Çekirdek")
        lbl_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #30d158;")
        layout.addWidget(lbl_title)
        
        # --- Butonlar ---
        btn_forecast = QPushButton("📈 Gelecek Haftayı Tahmin Et (Regression)")
        btn_forecast.clicked.connect(self.run_sales_forecast)
        
        btn_segment = QPushButton("🛒 Müşteri Tiplerini Analiz Et (Clustering)")
        btn_segment.clicked.connect(self.run_segmentation)
        
        layout.addWidget(btn_forecast)
        layout.addWidget(btn_segment)
        
        # --- Sonuç Ekranı ---
        self.lbl_ai_output = QLabel("Analiz bekleniyor...")
        self.lbl_ai_output.setStyleSheet("background: #222; padding: 15px; border-radius: 10px; font-size: 14px;")
        self.lbl_ai_output.setWordWrap(True)
        layout.addWidget(self.lbl_ai_output)
        
        layout.addStretch()
        self.tabs.addTab(w, "Analitik AI")

    def run_sales_forecast(self):
        res = self.brain.predict_sales(7)
        if isinstance(res, dict):
            msg = f"🔮 **Gelecek 7 Günün Tahmini:**\n\n"
            msg += f"Toplam Beklenen Ciro: **{res['total_predicted']:.2f} TL**\n\n"
            msg += "Günlük Detay:\n"
            for date, val in zip(res['dates'], res['values']):
                msg += f"• {date}: {val:.2f} TL\n"
            self.lbl_ai_output.setText(msg)
        else:
            self.lbl_ai_output.setText(res) # Hata mesajı

    def run_segmentation(self):
        res = self.brain.analyze_basket_segments()
        self.lbl_ai_output.setText(res)

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
                    
                    # 1. Admin Panelindeki listeyi yenile (Kendi fonksiyonu)
                    if hasattr(self, 'load_table_data'):
                        self.load_table_data()   

                    # 2. Ana Ekrandaki (Parent) kategorileri yenile (DÜZELTİLEN KISIM)
                    # self.parent() -> VoidPOS penceresini temsil eder
                    if self.parent() and hasattr(self.parent(), 'load_categories_grid'):
                        self.parent().load_categories_grid()
                        
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
            
class ProductDetailDialog(QDialog):
    def __init__(self, db, product_name, parent=None):
        super().__init__(parent)
        self.db = db
        self.p_name = product_name
        # Ürün verisini çek
        self.product = self.db.cursor.execute("SELECT * FROM products WHERE name=?", (product_name,)).fetchone()
        
        self.setWindowTitle(f"Ürün Yönetimi: {product_name}")
        self.setFixedSize(650, 600) # Pencereyi biraz büyüttük
        self.setStyleSheet("background-color: #1e1e1e; color: white; font-size: 14px;")
        
        layout = QVBoxLayout(self)
        
        # Sekmeler
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #333; padding: 10px; color: #aaa; }
            QTabBar::tab:selected { background: #0a84ff; color: white; }
        """)
        
        # --- SEKME 1: GENEL AYARLAR ---
        tab_general = QWidget()
        form_layout = QGridLayout(tab_general)
        form_layout.setSpacing(15)
        
        # 1. Ürün Adı (Yeni)
        self.inp_name = QLineEdit()
        self.inp_name.setText(self.product[1]) # Name
        self.inp_name.setStyleSheet("padding: 5px; background: #333; border: 1px solid #555; color: #fff;")
        
        # 2. Barkod (Yeni)
        self.inp_barcode = QLineEdit()
        self.inp_barcode.setText(self.product[7] if self.product[7] else "") # Barcode
        self.inp_barcode.setPlaceholderText("Barkod Yok")
        self.inp_barcode.setStyleSheet("padding: 5px; background: #333; border: 1px solid #555; color: #fff;")

        # 3. Satış Fiyatı
        self.inp_price = QDoubleSpinBox()
        self.inp_price.setRange(0, 100000)
        self.inp_price.setValue(self.product[3]) # sell_price
        
        # 4. Stok
        self.inp_stock = QDoubleSpinBox()
        self.inp_stock.setRange(-1000, 100000)
        self.inp_stock.setDecimals(0)
        self.inp_stock.setValue(self.product[4]) # stock
        
        # 5. Kritik Stok
        self.inp_critical = QDoubleSpinBox()
        self.inp_critical.setRange(0, 1000)
        self.inp_critical.setDecimals(0)
        self.inp_critical.setValue(self.product[8] if self.product[8] else 5) 
        
        # 6. Kategori
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems(self.db.get_all_categories())
        self.cmb_cat.setCurrentText(self.product[6]) 
        
        # 7. KDV
        self.inp_vat = QDoubleSpinBox()
        self.inp_vat.setRange(0, 100)
        self.inp_vat.setSuffix(" %")
        try:
            val = self.product[10] # vat_rate son sütundaysa
        except: 
            val = 20
        self.inp_vat.setValue(val if val else 20)

        # Form Dizilimi
        form_layout.addWidget(QLabel("Ürün Adı:"), 0, 0)
        form_layout.addWidget(self.inp_name, 0, 1)

        form_layout.addWidget(QLabel("Barkod:"), 1, 0)
        form_layout.addWidget(self.inp_barcode, 1, 1)

        form_layout.addWidget(QLabel("Satış Fiyatı (Kalıcı):"), 2, 0)
        form_layout.addWidget(self.inp_price, 2, 1)
        
        form_layout.addWidget(QLabel("Stok Adedi:"), 3, 0)
        form_layout.addWidget(self.inp_stock, 3, 1)
        
        form_layout.addWidget(QLabel("Kritik Stok Uyarısı:"), 4, 0)
        form_layout.addWidget(self.inp_critical, 4, 1)
        
        form_layout.addWidget(QLabel("Kategori:"), 5, 0)
        form_layout.addWidget(self.cmb_cat, 5, 1)
        
        form_layout.addWidget(QLabel("KDV Oranı:"), 6, 0)
        form_layout.addWidget(self.inp_vat, 6, 1)
        
        tabs.addTab(tab_general, "🛠️ Ürün Ayarları")
        
        # --- SEKME 2: YAPAY ZEKA ÖNERİLERİ ---
        tab_ai = QWidget()
        ai_layout = QVBoxLayout(tab_ai)
        
        self.lbl_ai = QLabel("Analiz ediliyor...")
        self.lbl_ai.setWordWrap(True)
        self.lbl_ai.setStyleSheet("font-size: 15px; line-height: 1.4;")
        ai_layout.addWidget(self.lbl_ai)
        
        tabs.addTab(tab_ai, "🧠 Void AI Analizi")
        
        layout.addWidget(tabs)
        
        # --- Butonlar ---
        btn_box = QHBoxLayout()
        btn_save = QPushButton("KAYDET & GÜNCELLE")
        btn_save.setStyleSheet("background-color: #30d158; color: black; font-weight: bold; padding: 12px; border-radius:8px;")
        btn_save.clicked.connect(self.save_changes)
        
        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("background-color: #333; color: white; padding: 12px; border-radius:8px;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)
        
        self.run_product_ai()

    def run_product_ai(self):
        """Bu ürüne özel basit AI analizi"""
        try:
            query = """
                SELECT SUM(quantity), COUNT(*) 
                FROM sale_items 
                WHERE product_name = ? AND sale_date >= date('now', '-30 days')
            """
            sales_data = self.db.cursor.execute(query, (self.p_name,)).fetchone()
            total_sold = sales_data[0] if sales_data[0] else 0
            tx_count = sales_data[1]
            
            stock = self.inp_stock.value()
            price = self.inp_price.value()
            cost = self.product[2]
            profit = price - cost
            
            msg = f"📊 <b>{self.p_name} Analizi (Son 30 Gün):</b><br><br>"
            msg += f"• Toplam Satış: <b>{total_sold} Adet</b><br>"
            msg += f"• İşlem Sayısı: {tx_count}<br>"
            msg += f"• Birim Kâr: {profit:.2f} ₺<br><br>"
            
            if total_sold > 50:
                msg += "🔥 <b>Yüksek Performans:</b> Bu ürün çok satıyor. Stoğu yüksek tutun.<br>"
            elif total_sold < 2 and stock > 10:
                msg += "❄️ <b>Ölü Stok Riski:</b> İndirim yapmayı düşünün.<br>"
            if stock < (total_sold / 4): 
                msg += "⚠️ <b>Kritik Stok:</b> Stok yakında bitebilir.<br>"
                
            self.lbl_ai.setText(msg)
        except Exception as e:
            self.lbl_ai.setText(f"Analiz hatası: {str(e)}")

    def save_changes(self):
        try:
            self.db.update_product_advanced(
                self.product[0], # ID
                self.inp_name.text(),      # Yeni İsim
                self.inp_price.value(),
                int(self.inp_stock.value()),
                int(self.inp_critical.value()),
                self.cmb_cat.currentText(),
                int(self.inp_vat.value()),
                self.inp_barcode.text()    # Yeni Barkod
            )
            QMessageBox.information(self, "Başarılı", "Ürün bilgileri güncellendi.")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))


if __name__ == "__main__":
    from PySide6.QtWidgets import QFormLayout
    app = QApplication(sys.argv)
    
    font = QFont(".AppleSystemUIFont", 13) 
    app.setFont(font)    
    
    app.setStyleSheet(theme_manager.get_stylesheet()) 

    window = VoidPOS()
    window.show()
    sys.exit(app.exec())