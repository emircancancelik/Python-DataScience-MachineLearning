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
import subprocess
import xml.etree.ElementTree as ET


from ctypes import c_char_p, c_int, c_long, POINTER, Structure
from difflib import get_close_matches
from sklearn.linear_model import LinearRegression 
from sklearn.ensemble import RandomForestRegressor, IsolationForest, GradientBoostingRegressor
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


class IngenicoGMP:
    """
    Ingenico Move 5000F - Gerçek GMP3 Entegrasyonu
    XML dosyası oluşturur ve ixirYazarkasa.exe'yi tetikler.
    """
    def __init__(self):
        self.base_path = get_app_path()
        self.exe_path = os.path.join(self.base_path, "libs", "ixirYazarkasa.exe")
        self.xml_request_path = os.path.join(self.base_path, "GMP.XML")
        self.xml_response_path = os.path.join(self.base_path, "GMP_RESPONSE.XML") # Exe'nin cevabı yazdığı yer

        # Klasör kontrolü
        if not os.path.exists(self.exe_path):
            # Eğer libs içinde değilse ana dizine bak
            self.exe_path = os.path.join(self.base_path, "ixirYazarkasa.exe")
    
    def sale(self, amount: float) -> dict:
        """Gerçek Satış İsteği"""
        print(f"🔌 POS: {amount:.2f} TL tutarında gerçek satış başlatılıyor...")
        
        # 1. Önceki cevap dosyasını temizle
        if os.path.exists(self.xml_response_path):
            try:
                os.remove(self.xml_response_path)
            except:
                pass

        # 2. GMP3 XML Dosyasını Oluştur (Standart GMP Formatı)
        # Not: Kuruş formatı gereklidir (1.00 TL -> 100)
        amount_kurus = int(amount * 100)
        
        xml_content = f"""<?xml version="1.0" encoding="ISO-8859-9"?>
<GMP3>
    <Transaction>
        <Type>SALE</Type>
        <Amount>{amount_kurus}</Amount>
        <CurrencyCode>949</CurrencyCode> <KisimNo>1</KisimNo>
        <PaymentType>CREDIT_CARD</PaymentType>
    </Transaction>
</GMP3>"""
        
        try:
            with open(self.xml_request_path, "w", encoding="ISO-8859-9") as f:
                f.write(xml_content)
        except Exception as e:
            return {'success': False, 'message': f'XML Oluşturma Hatası: {e}'}

        # 3. EXE'yi Çalıştır (Cihaza Sinyal Gönderir)
        if not os.path.exists(self.exe_path):
             return {'success': False, 'message': 'ixirYazarkasa.exe bulunamadı!'}

        try:
            # EXE'yi çalıştır ve bitmesini bekle (Timeout 60 saniye)
            subprocess.run([self.exe_path], check=True, timeout=65)
        except subprocess.TimeoutExpired:
            return {'success': False, 'message': 'POS Zaman Aşımı (Cevap gelmedi)'}
        except Exception as e:
            return {'success': False, 'message': f'POS Sürücü Hatası: {e}'}

        # 4. Sonucu Oku
        return self._parse_response()

    def print_receipt_only(self, amount: float) -> dict:
        """Nakit Satış (Sadece Fiş Kes)"""
        # Nakit için XML yapısı farklı olabilir, genellikle PaymentType = CASH
        return {'success': True, 'message': 'Nakit Fiş Simüle Edildi (EXE entegrasyonu gerekebilir)'}

    def _parse_response(self) -> dict:
        """Cihazdan dönen XML/Dosyayı oku"""
        if not os.path.exists(self.xml_response_path):
            return {'success': False, 'message': 'Cihazdan yanıt dosyası oluşmadı.'}
        
        try:
            tree = ET.parse(self.xml_response_path)
            root = tree.getroot()
            
            # XML yapısına göre (Örnek parse, gerçek dosya yapısına göre güncellenebilir)
            # Genellikle <ResponseCode>00</ResponseCode> başarılıdır.
            response_code = root.findtext(".//ResponseCode")
            message = root.findtext(".//Message")
            
            if response_code == "00" or response_code == "OK":
                return {
                    'success': True,
                    'auth_code': root.findtext(".//AuthCode") or "00000",
                    'message': message or "Onaylandı"
                }
            else:
                return {
                    'success': False,
                    'message': message or f"Hata Kodu: {response_code}"
                }
                
        except Exception as e:
            # XML bozuksa dosyayı raw okumayı dene
            try:
                with open(self.xml_response_path, "r") as f:
                    content = f.read()
                    if "OK" in content or "SUCCESS" in content:
                        return {'success': True, 'message': 'İşlem Başarılı (Raw)'}
            except:
                pass
            return {'success': False, 'message': f'Yanıt okuma hatası: {e}'}
        
def get_app_path():

    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))
    
def load_pos_config():
    """pos_config.json dosyasından ayarları okur, yoksa oluşturur"""
    config_file = os.path.join(get_app_path(), "pos_config.json")

    # GÜNCEL VARSAYILANLAR (Senin bulduğun ayarlara göre)
    defaults = {
        "primary_ip": "192.168.1.157",  # Senin cihazın IP'si
        "primary_port": 7500,           # DOĞRU PORT (GMP3)
        "backup_ip": "",
        "backup_port": 9100,
        "pos_type": "ingenico_gosb",
        "timeout": 60,
        "auto_detect": False
    }

    if not os.path.exists(config_file):
        try:
            with open(config_file, "w") as f:
                json.dump(defaults, f, indent=4)
            print(f"✅ {config_file} oluşturuldu (Port 7500).")
        except Exception as e:
            print(f"❌ Config dosyası oluşturulamadı: {e}")
        return defaults
        
    try:
        # Dosya varsa oku ve portu kontrol et
        with open(config_file, "r") as f:
            config = json.load(f)
            
            # Eğer eski port (6420) kaldıysa 7500 yapıp kaydet
            if config.get("primary_port") == 6420:
                print("⚠️ Eski Port (6420) tespit edildi, GMP3 için 7500'e güncelleniyor...")
                config["primary_port"] = 7500
                config["primary_ip"] = "192.168.1.157" # IP'yi de garantiye alalım
                
                with open(config_file, "w") as fw:
                    json.dump(config, fw, indent=4)
            
            print(f"✅ POS Ayarları yüklendi: {config['primary_ip']}:{config['primary_port']}")
            return config
            
    except Exception as e:
        print(f"⚠️ Config dosyası okunamadı, varsayılanlar kullanılıyor: {e}")
        return defaults

# Global Ayarları Yükle
POS_CONFIG = load_pos_config()
POS_IP = POS_CONFIG.get("primary_ip", "192.168.1.157")
POS_PORT = POS_CONFIG.get("primary_port", 7500)
    
POS_CONFIG = load_pos_config()
POS_IP = POS_CONFIG.get("primary_ip", "192.168.1.157")
POS_PORT = POS_CONFIG.get("primary_port", 6420)
POS_TIMEOUT = POS_CONFIG.get("timeout", 60)


    
# TEMA YÖNETİCİSİ 
class ThemeManager:
    DEFAULTS = {
        "bg_main": "#121216",       
        "bg_panel": "#1e1e24",      
        "bg_secondary": "#2d2d3a",  
        "text_primary": "#ffffff",
        "text_secondary": "#a0a0b0",
        "accent": "#5e6ad2",        
        "accent_hover": "#4b56b2",
        "success": "#00b894",       
        "error": "#ff7675",        
        "warning": "#fdcb6e",      
        "border": "#2f2f3d",        
        "shadow": "rgba(0, 0, 0, 0.4)"
    }

    def __init__(self, filename="theme.json"):
        self.filename = os.path.join(get_app_path(), filename)
        self.current_theme = self.load_theme()

    def load_theme(self):
        # (Aynı kalacak, dosya okuma mantığı)
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

    def get_stylesheet(self):
        # MODERN CSS 
        template = """
            /* --- GENEL --- */
            QMainWindow, QDialog {{ background-color: {bg_main}; color: {text_primary}; }}
            QWidget {{ font-family: 'Segoe UI', 'Roboto', sans-serif; font-size: 14px; outline: none; }}
            
            /* --- SCROLLBAR (İnce ve Modern) --- */
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {bg_main}; width: 8px; margin: 0; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: #444; min-height: 40px; border-radius: 4px; }}
            QScrollBar::handle:vertical:hover {{ background: {accent}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

            /* --- INPUTS & COMBOS --- */
            QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit {{ 
                background-color: {bg_secondary}; 
                color: {text_primary}; 
                border: 1px solid {border}; 
                padding: 12px 15px; 
                border-radius: 10px; 
                font-size: 14px;
            }}
            QLineEdit:focus, QComboBox:focus {{ 
                border: 1px solid {accent}; 
                background-color: #353545;
            }}
            QLineEdit::placeholder {{ color: {text_secondary}; }}

            /* --- TABLOLAR (Modern Liste Görünümü) --- */
            QTableWidget {{ 
                background-color: {bg_panel}; 
                border: 1px solid {border}; 
                border-radius: 12px; 
                gridline-color: transparent; 
                outline: none;
            }}
            QTableWidget::item {{ 
                padding: 10px; 
                border-bottom: 1px solid #3a3a3c; /* İnce Gri Çizgi */
            }}
            QTableWidget::item:selected {{ 
                background-color: rgba(255, 255, 255, 0.05); 
                color: white; 
                border-left: 2px solid #888; 
            }}
            QHeaderView::section {{ 
                background-color: {bg_main}; 
                color: {text_secondary}; 
                border: none; 
                padding: 12px; 
                font-weight: 700; 
                text-transform: uppercase; 
                letter-spacing: 1px;
                font-size: 11px;
            }}

            /* --- BUTONLAR --- */
            QPushButton {{
                background-color: {bg_secondary};
                color: {text_primary};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 10px 20px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #3a3a4b;
                border-color: {text_secondary};
            }}
            QPushButton:pressed {{
                background-color: {accent};
                color: white;
                border: none;
            }}

            /* --- ÖZEL BUTON SINIFLARI --- */
            QPushButton[class="SuccessBtn"] {{ background-color: {success}; color: #000; border: none; }}
            QPushButton[class="SuccessBtn"]:hover {{ background-color: #00ce9f; }}
            
            QPushButton[class="DangerBtn"] {{ background-color: {error}; color: #fff; border: none; }}
            QPushButton[class="DangerBtn"]:hover {{ background-color: #ff8888; }}

            QPushButton[class="TopBarBtn"] {{ 
                background-color: {bg_panel}; 
                border: 1px solid {border}; 
                color: {text_secondary};
                min-width: 100px;
            }}
            QPushButton[class="TopBarBtn"]:hover {{ 
                color: {accent}; border-color: {accent}; 
            }}

            /* --- NUMPAD --- */
            QPushButton[class="NumBtn"] {{
                background-color: {bg_panel};
                border: 1px solid {border};
                border-radius: 0px;
                font-size: 20px;
                color: {text_primary};
            }}
            QPushButton[class="NumBtn"]:hover {{ background-color: {bg_secondary}; }}
            QPushButton[class="NumBtn"]:pressed {{ background-color: {accent}; }}

            /* --- KARTLAR & PANELLER --- */
            QFrame#LeftPanel, QFrame#CenterPanel, QFrame#RightPanel {{
                background-color: {bg_panel};
                border-radius: 16px;
                border: 1px solid {border};
            }}
            
            /* --- Ciro Kutusu --- */
            QLabel#CiroBox {{
                background-color: rgba(94, 106, 210, 0.15);
                color: {accent};
                border: 1px solid {accent};
                border-radius: 12px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 18px;
            }}
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

# =====================================================
# INGENICO MOVE 5000F - GMP DLL ENTEGRASYONU
# =====================================================


class IngenicoGMP:
    """Ingenico Move 5000F - GMP Smart DLL Entegrasyonu (GERÇEK)"""
    
    def __init__(self):
        self.logger = logging.getLogger("IngenicoGMP")
        self.dll = None
        self.is_initialized = False
        
        # DLL yolunu bul
        dll_path = os.path.join(get_app_path(), "GMPSmartDLL.dll")
        
        if not os.path.exists(dll_path):
            self.logger.error(f"❌ DLL bulunamadı: {dll_path}")
            raise FileNotFoundError(f"GMPSmartDLL.dll bulunamadı! Lütfen dosyayı {get_app_path()} klasörüne kopyalayın.")
        
        try:
            # DLL'yi yükle
            self.dll = ctypes.WinDLL(dll_path)
            self.logger.info(f"✅ DLL yüklendi: {dll_path}")
            
            # Fonksiyon imzalarını tanımla
            self._setup_dll_functions()
            
        except Exception as e:
            self.logger.error(f"❌ DLL yüklenemedi: {e}")
            raise
    
    def _setup_dll_functions(self):
        try:
            # Initialize
            self.dll.Initialize.argtypes = []
            self.dll.Initialize.restype = c_int
            
            # Sale
            self.dll.Sale.argtypes = [c_long, c_int]  # (tutar_kurus, taksit)
            self.dll.Sale.restype = c_int
            
            # GetLastResponse
            self.dll.GetLastResponse.argtypes = [c_char_p, c_int]  # (buffer, size)
            self.dll.GetLastResponse.restype = c_int
            
            # Close
            self.dll.Close.argtypes = []
            self.dll.Close.restype = c_int
            
            self.logger.info("✅ DLL fonksiyonları tanımlandı")
            
        except AttributeError as e:
            self.logger.warning(f"⚠️ DLL fonksiyon tanımı uyarısı: {e}")
            # Bazı fonksiyonlar farklı isimde olabilir, devam ediyoruz
    
    def initialize(self) -> bool:
        """POS cihazını başlat"""
        if self.is_initialized:
            return True
        
        try:
            self.logger.info("🔧 POS başlatılıyor...")
            result = self.dll.Initialize()
            
            if result == 0:  # 0 = Başarılı (GMP standardı)
                self.is_initialized = True
                self.logger.info("✅ POS başlatıldı")
                return True
            else:
                self.logger.error(f"❌ POS başlatılamadı. Hata kodu: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Initialize hatası: {e}")
            return False
    
    def sale(self, amount: float) -> dict:
        """KART ile satış"""
        if not self.initialize():
            return {
                'success': False,
                'message': 'POS cihazı başlatılamadı'
            }
        
        try:
            # Tutarı kuruşa çevir
            amount_kurus = int(amount * 100)
            
            self.logger.info(f"💳 SATIŞ BAŞLATILIYOR: {amount:.2f} TL ({amount_kurus} kuruş)")
            
            # DLL'ye satış komutu gönder
            result_code = self.dll.Sale(amount_kurus, 0)  # 0 = Tek çekim
            
            # Sonucu al
            response = self._get_last_response()
            
            if result_code == 0:  # Başarılı
                self.logger.info(f"✅ İşlem onaylandı: {response}")
                return {
                    'success': True,
                    'response_code': '00',
                    'auth_code': response.get('auth_code', '000000'),
                    'rrn': response.get('rrn', '000000000000'),
                    'card_number': self._mask_card(response.get('card_number', '')),
                    'message': 'İşlem Onaylandı'
                }
            else:
                error_msg = self._get_error_message(result_code, response)
                self.logger.error(f"❌ İşlem reddedildi: {error_msg}")
                
                return {
                    'success': False,
                    'response_code': str(result_code),
                    'message': error_msg
                }
        
        except Exception as e:
            self.logger.exception("❌ Sale hatası")
            return {
                'success': False,
                'message': f'Hata: {str(e)}'
            }
    
    def _get_last_response(self) -> dict:
        try:
            buffer = ctypes.create_string_buffer(1024)
            
            result = self.dll.GetLastResponse(buffer, 1024)
            
            if result == 0:
                response_str = buffer.value.decode('utf-8', errors='ignore')
                self.logger.debug(f"📥 Yanıt: {response_str}")
                parsed = {}
                for pair in response_str.split('|'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        parsed[key.lower()] = value
                
                return parsed
            else:
                self.logger.warning(f"⚠️ Yanıt alınamadı. Kod: {result}")
                return {}
                
        except Exception as e:
            self.logger.error(f"❌ Yanıt parse hatası: {e}")
            return {}
    
    def print_receipt_only(self, amount: float) -> dict:
        """NAKİT işlem - Fiş yazdır (DLL gerekmiyor)"""
        self.logger.info(f"💵 NAKİT işlem: {amount:.2f} TL")
        
        return {
            'success': True,
            'message': 'Nakit işlem kaydedildi',
            'rrn': datetime.datetime.now().strftime("%y%m%d%H%M%S")
        }
    
    def test_connection(self) -> bool:
        """Bağlantı testi"""
        return self.initialize()
    
    def close(self):
        """Bağlantıyı kapat"""
        if self.is_initialized and self.dll:
            try:
                self.dll.Close()
                self.is_initialized = False
                self.logger.info("🔌 POS bağlantısı kapatıldı")
            except:
                pass
    
    def _mask_card(self, card: str) -> str:
        """Kart numarasını maskele"""
        if not card or len(card) < 10:
            return "****"
        return f"{card[:6]}{'*' * (len(card) - 10)}{card[-4:]}"
    
    def _get_error_message(self, code: int, response: dict) -> str:
        errors = {
            1: "İşlem İptal Edildi",
            2: "Zaman Aşımı",
            3: "Bağlantı Hatası",
            5: "İşlem Reddedildi",
            51: "Yetersiz Bakiye",
            54: "Kartın Süresi Dolmuş",
            55: "Hatalı PIN",
            91: "Banka Yanıt Vermiyor"
        }
        
        # Response içinde mesaj varsa onu kullan
        if 'message' in response:
            return response['message']
        
        return errors.get(code, f"Hata Kodu: {code}")
    
    def __del__(self):
        """Destructor - Bağlantıyı kapat"""
        self.close()
# =====================================================
# INGENICO MOVE 5000F - POS ENTEGRASYONU
# ÇOKLU POS DESTEĞİ (BEKO + INGENICO)
# =====================================================

class POSType(Enum):
    INGENICO_GOSB = "ingenico_gosb"
    BEKO_ECR = "beko_ecr"
    AUTO_DETECT = "auto"

class UniversalPOSManager:
    """Gerçek POS Yöneticisi"""
    
    def __init__(self):
        self.logger = logging.getLogger("UniversalPOS")
        # Ayarları yükle (Yukarıdaki güncel load_pos_config'den gelecek)
        self.config = load_pos_config() 
        self.driver = IngenicoRealDriver()
    
    def process_payment(self, amount: float, payment_type: str = "CARD") -> dict:
        tx_id = str(uuid.uuid4())[:8]
        # IP ve Port bilgisini logda görelim
        target_ip = self.config.get('primary_ip')
        target_port = self.config.get('primary_port')
        
        self.logger.info(f"TX:{tx_id} | Hedef: {target_ip}:{target_port} | Tutar: {amount:.2f}")
        
        try:
            result = self.driver.send_transaction(amount, payment_type)
            
            if result['success']:
                return {
                    'success': True,
                    'method': payment_type,
                    'amount': amount,
                    'auth_code': result.get('auth_code', 'OK'),
                    'tx_id': tx_id,
                    'message': result.get('message', 'Onaylandı')
                }
            else:
                return {
                    'success': False,
                    'method': payment_type,
                    'message': result.get('message', 'Reddedildi'),
                    'tx_id': tx_id
                }
        except Exception as e:
            return {'success': False, 'message': str(e), 'tx_id': tx_id}    
    
    def process_payment(self, amount: float, payment_type: str = "CARD") -> dict:
        """
        Ödeme işlemini başlatır ve sonucu döner.
        payment_type: "CARD" veya "CASH"
        """
        tx_id = str(uuid.uuid4())[:8]
        self.logger.info(f"💳 ÖDEME BAŞLADI | {payment_type} | {amount:.2f} TL | TX:{tx_id}")
        
        try:
            # Tip dönüşümü: IngenicoDriver 0 (Nakit) ve 1 (Kart) bekliyor
            p_type_int = 0 if payment_type == "CASH" else 1
            
            # --- GERÇEK CİHAZA GÖNDERME ANI ---
            result = self.real_driver.send_transaction(amount, p_type_int)
            # ----------------------------------
            
            if result['success']:
                return {
                    'success': True,
                    'method': payment_type,
                    'amount': amount,
                    'auth_code': result.get('auth_code', 'OK'),
                    'receipt_no': result.get('rrn', tx_id),
                    'card_number': '****', # Gerçek cihaz güvenlik gereği bunu dönmeyebilir
                    'tx_id': tx_id,
                    'message': result.get('message', 'İşlem Başarılı')
                }
            else:
                self.logger.warning(f"İşlem Başarısız: {result['message']}")
                return {
                    'success': False,
                    'method': payment_type,
                    'message': result.get('message', 'Bilinmeyen Hata'),
                    'tx_id': tx_id
                }
                
        except Exception as e:
            self.logger.exception("Kritik Ödeme Hatası")
            return {
                'success': False,
                'message': f'Sistem Hatası: {str(e)}',
                'tx_id': tx_id
            }
    
    def process_payment(self, amount: float, payment_type: str = "CARD") -> dict:
        """
        Ödeme işlemini başlatır ve sonucu döner.
        payment_type: "CARD" veya "CASH"
        """
        tx_id = str(uuid.uuid4())[:8]
        self.logger.info(f"💳 ÖDEME BAŞLADI | {payment_type} | {amount:.2f} TL | TX:{tx_id}")
        
        try:
            # Tip dönüşümü: IngenicoDriver 0 (Nakit) ve 1 (Kart) bekliyor
            p_type_int = 0 if payment_type == "CASH" else 1
            
            # --- GERÇEK CİHAZA GÖNDERME ANI ---
            result = self.real_driver.send_transaction(amount, p_type_int)
            # ----------------------------------
            
            if result['success']:
                return {
                    'success': True,
                    'method': payment_type,
                    'amount': amount,
                    'auth_code': result.get('auth_code', 'OK'),
                    'receipt_no': result.get('rrn', tx_id),
                    'card_number': '****', # Gerçek cihaz güvenlik gereği bunu dönmeyebilir
                    'tx_id': tx_id,
                    'message': result.get('message', 'İşlem Başarılı')
                }
            else:
                self.logger.warning(f"İşlem Başarısız: {result['message']}")
                return {
                    'success': False,
                    'method': payment_type,
                    'message': result.get('message', 'Bilinmeyen Hata'),
                    'tx_id': tx_id
                }
                
        except Exception as e:
            self.logger.exception("Kritik Ödeme Hatası")
            return {
                'success': False,
                'message': f'Sistem Hatası: {str(e)}',
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
    Ingenico Move 5000F - Gerçek Cihaz Sürücüsü (EXE/DLL Köprüsü)
    Market bilgisayarındaki veriyi (XML) POS cihazına iletir.
    """
    def __init__(self):
        self.base_path = get_app_path()
        # "libs" klasörü varsa orada ara, yoksa ana dizinde ara
        self.exe_path = os.path.join(self.base_path, "libs", "ixirYazarkasa.exe")
        if not os.path.exists(self.exe_path):
            self.exe_path = os.path.join(self.base_path, "ixirYazarkasa.exe")
            
        self.req_path = os.path.join(self.base_path, "GMP.XML")
        self.res_path = os.path.join(self.base_path, "GMP_RESPONSE.XML")

    def send_transaction(self, amount: float, payment_type: int) -> dict:
        """
        amount: Tutar (Örn: 1.50)
        payment_type: 0 = NAKİT, 1 = KREDİ KARTI
        """
        # 1. Byte Eşleşmesi için Kuruş Hesabı (1.00 TL -> 100 Kuruş)
        # Float hatalarını önlemek için round kullanıyoruz.
        amount_kurus = int(round(amount * 100))

        print(f"🔌 POS Sinyali: {amount:.2f} TL ({amount_kurus} Kuruş) - Tip: {payment_type}")

        # 2. GMP3 XML Oluşturma (Cihazın anladığı dil)
        # ISO-8859-9 (Turkish) encoding kullanıyoruz ki Türkçe karakterler bozulmasın.
        xml_content = f"""<?xml version="1.0" encoding="ISO-8859-9"?>
<GMP3>
    <Transaction>
        <Type>SALE</Type>
        <Amount>{amount_kurus}</Amount>
        <CurrencyCode>949</CurrencyCode>
        <KisimNo>1</KisimNo>
        <PaymentType>{'CASH' if payment_type == 0 else 'CREDIT_CARD'}</PaymentType>
        <InstallmentCount>0</InstallmentCount>
    </Transaction>
</GMP3>"""

        try:
            # Önceki yanıt dosyasını temizle (Çakışmayı önlemek için)
            if os.path.exists(self.res_path):
                os.remove(self.res_path)

            # XML dosyasını yaz
            with open(self.req_path, "w", encoding="ISO-8859-9") as f:
                f.write(xml_content)

            # 3. Exe'yi Tetikle (Cihaza veriyi gönderir)
            if not os.path.exists(self.exe_path):
                return {"success": False, "message": "ixirYazarkasa.exe bulunamadı!"}

            # subprocess ile exe'yi çalıştır ve bekle
            # startupinfo=startupinfo kısmı konsol penceresinin açılıp kapanmasını gizler (Sessiz mod)
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.run([self.exe_path], cwd=os.path.dirname(self.exe_path), 
                                     capture_output=True, text=True, startupinfo=startupinfo, timeout=90)

            # 4. Yanıtı Oku (Cihazdan gelen byte'lar)
            return self._parse_result()

        except subprocess.TimeoutExpired:
            return {"success": False, "message": "POS Zaman Aşımı (Cevap gelmedi)"}
        except Exception as e:
            return {"success": False, "message": f"Sürücü Hatası: {str(e)}"}

    def _parse_result(self):
        """POS cihazından dönen XML dosyasını okur"""
        if not os.path.exists(self.res_path):
            return {"success": False, "message": "Cihazdan yanıt dosyası oluşmadı."}

        try:
            tree = import_xml_etree(self.res_path) # Helper gerekebilir veya direkt ET
            import xml.etree.ElementTree as ET
            tree = ET.parse(self.res_path)
            root = tree.getroot()

            response_code = root.findtext(".//ResponseCode")
            message = root.findtext(".//Message")
            auth_code = root.findtext(".//AuthCode")
            rrn = root.findtext(".//RRN")

            # "00" veya "OK" genellikle başarıdır
            if response_code in ["00", "OK"]:
                return {
                    "success": True,
                    "auth_code": auth_code,
                    "rrn": rrn,
                    "message": message
                }
            else:
                return {
                    "success": False,
                    "message": message or f"Hata Kodu: {response_code}"
                }
        except Exception as e:
            return {"success": False, "message": f"Yanıt okuma hatası: {e}"}
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
    """
    Satış arayüzü ile donanım arasındaki servis katmanı.
    """
    def __init__(self):
        self.logger = logging.getLogger("POSService")
        self.manager = UniversalPOSManager() # Yöneticiyi başlat
    
    def process_sale(self, amount: float, is_cash: bool = False) -> dict:
        """
        Satış işlemi - Thread-Safe
        is_cash: True ise Nakit, False ise Kart
        """
        tx_id = str(uuid.uuid4())[:8]
        self.logger.info(f"TX START | {tx_id} | {amount:.2f} TL")
        
        method = "CASH" if is_cash else "CARD"
        
        try:
            # Yöneticiden işlemi yapmasını iste
            result = self.manager.process_payment(amount, method)
            
            if result['success']:
                return {
                    'success': True,
                    'rc': '00', # Response Code 00 = Başarılı
                    'auth_code': result.get('auth_code', ''),
                    'receipt_no': result.get('receipt_no', ''),
                    'state': 'APPROVED',
                    'tx_id': tx_id,
                    'card_number': result.get('card_number', '')
                }
            else:
                return {
                    'success': False,
                    'rc': 'XX',
                    'msg': result.get('message', 'Reddedildi'),
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
                for cat_name in found_categories:
                    if cat_name: # Boş değilse
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
        w, h = (120, 150) if is_mini else (135, 170)
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
        icon_bg = "#333333"
        text_color = "#e0e0e0"
        icon_text = name[0].upper() if name else "?"
        border_style = "1px solid #3a3a3c"

        if is_all_products:
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
class VoidBrain_Analytic:
    """
    TEK VE MERKEZİ ANALİTİK SINIFI
    Tüm matematiksel hesaplamalar, tahminler ve öneriler burada toplanmıştır.
    """
    def __init__(self, db_path="voidpos.db"):
        self.db_path = db_path
        self.scaler = StandardScaler()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    # ============================================================
    # 1. DİNAMİK FİYATLANDIRMA & MARJ ANALİZİ
    # ============================================================
    def suggest_dynamic_pricing(self):
        """Satış hızına ve marja göre fiyat artırma/azaltma önerileri"""
        try:
            conn = self.get_connection()
            query = """
                SELECT p.name, p.sell_price, p.cost_price, p.stock,
                       COALESCE(SUM(si.quantity), 0) as total_sold,
                       COUNT(DISTINCT si.sale_date) as active_days
                FROM products p
                LEFT JOIN sale_items si ON p.name = si.product_name 
                    AND si.sale_date >= date('now', '-30 days')
                GROUP BY p.id HAVING total_sold > 0
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty: return []

            df['daily_sales'] = df['total_sold'] / (df['active_days'] + 0.1)
            df['turnover_rate'] = df['daily_sales'] / (df['stock'] + 0.1)
            df['margin'] = ((df['sell_price'] - df['cost_price']) / df['sell_price']) * 100
            
            suggestions = []
            for _, row in df.iterrows():
                # Kural 1: Hızlı satılıyor ama marj düşük -> FİYAT ARTIR
                if row['turnover_rate'] > 0.3 and row['margin'] < 25:
                    new_price = row['sell_price'] * 1.10
                    suggestions.append({
                        'product': row['name'],
                        'action': '📈 FİYAT ARTIR',
                        'old': row['sell_price'],
                        'new': round(new_price, 2),
                        'reason': f"Hızlı gidiyor (%{row['margin']:.1f} Marj)"
                    })
                # Kural 2: Yavaş satılıyor ve marj yüksek -> İNDİRİM YAP
                elif row['turnover_rate'] < 0.05 and row['margin'] > 35:
                    new_price = row['sell_price'] * 0.90
                    suggestions.append({
                        'product': row['name'],
                        'action': '📉 İNDİRİM YAP',
                        'old': row['sell_price'],
                        'new': round(new_price, 2),
                        'reason': "Stok erimiyor, marj kurtarıyor"
                    })
            return suggestions[:5]
        except: return []

    # ============================================================
    # 2. CROSS-SELL (PAKET ÖNERİSİ)
    # ============================================================
    def suggest_bundles(self):
        """Birlikte satılan ürünleri bulur"""
        try:
            conn = self.get_connection()
            query = """
                SELECT a.product_name, b.product_name, COUNT(*) as frequency,
                       AVG(a.sell_price) as p1_price, AVG(b.sell_price) as p2_price
                FROM sale_items a
                JOIN sale_items b ON a.sale_id = b.sale_id
                WHERE a.product_name < b.product_name 
                GROUP BY a.product_name, b.product_name
                ORDER BY frequency DESC LIMIT 3
            """
            pairs = conn.execute(query).fetchall()
            conn.close()
            
            bundles = []
            for p1, p2, freq, price1, price2 in pairs:
                if freq < 2: continue
                bundle_price = (price1 + price2) * 0.90 # %10 İndirimli paket
                bundles.append({
                    'bundle': f"{p1} + {p2}",
                    'price': f"{bundle_price:.2f}",
                    'count': freq,
                    'msg': f"📦 **{p1} + {p2} Paketi** yapın! ({freq} kez birlikte satıldı)"
                })
            return bundles
        except: return []

    # ============================================================
    # 3. STOK YATIRIM OPTİMİZASYONU (ROI)
    # ============================================================
    def optimize_stock_investment(self):
        """Hangi ürüne para bağlanmalı?"""
        try:
            conn = self.get_connection()
            # ROI (Yatırım Getirisi) hesaplama
            query = """
                SELECT p.name, (p.stock * p.cost_price) as investment,
                       COALESCE(SUM(si.total_price - (si.cost_price * si.quantity)), 0) as profit_30days
                FROM products p
                LEFT JOIN sale_items si ON p.name = si.product_name 
                    AND si.sale_date >= date('now', '-30 days')
                GROUP BY p.id HAVING p.stock > 0
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if df.empty: return "Veri yok."
            
            df['roi'] = (df['profit_30days'] / (df['investment'] + 1)) * 100
            best = df.sort_values('roi', ascending=False).head(3)
            worst = df.sort_values('roi', ascending=True).head(3)
            
            report = "💰 **YATIRIM TAVSİYESİ:**\n"
            report += "⭐ **Parayı Buna Yatır (Yüksek ROI):**\n"
            for _, r in best.iterrows():
                report += f" • {r['name']} (ROI: %{r['roi']:.0f})\n"
            
            report += "\n⚠️ **Paranı Çek (Ölü Yatırım):**\n"
            for _, r in worst.iterrows():
                if r['roi'] < 5:
                    report += f" • {r['name']} (Yatırım: {r['investment']:.0f}₺, Getiri Yok)\n"
            return report
        except Exception as e: return str(e)

    # ============================================================
    # 4. GELİŞMİŞ TAHMİN (Gradient Boosting)
    # ============================================================
    def predict_next_week_demand(self):
        try:
            conn = self.get_connection()
            query = "SELECT product_name, sale_date, SUM(quantity) as qty FROM sale_items WHERE sale_date >= date('now', '-60 days') GROUP BY product_name, sale_date"
            df = pd.read_sql(query, conn)
            conn.close()
            
            if len(df) < 20: return "Yetersiz veri."
            
            top_products = df.groupby('product_name')['qty'].sum().sort_values(ascending=False).head(5).index
            report = "🔮 **GELECEK HAFTA TAHMİNİ:**\n"
            
            for prod in top_products:
                sub = df[df['product_name'] == prod].copy()
                if len(sub) < 10: continue
                
                sub['sale_date'] = pd.to_datetime(sub['sale_date'])
                sub['ordinal'] = sub['sale_date'].map(datetime.datetime.toordinal)
                
                model = GradientBoostingRegressor(n_estimators=50, random_state=42)
                model.fit(sub[['ordinal']], sub['qty'])
                
                next_week_total = 0
                last_date = sub['sale_date'].max()
                for i in range(1, 8):
                    future_date = last_date + datetime.timedelta(days=i)
                    pred = model.predict([[future_date.toordinal()]])[0]
                    next_week_total += max(0, pred)
                
                report += f"📦 **{prod}:** ~{int(next_week_total)} adet satılacak.\n"
            return report
        except: return "Tahmin hatası."

    # ============================================================
    # 5. ESKİ TEMEL FONKSİYONLAR (Korundu ve Optimize Edildi)
    # ============================================================
    def recommend_next_product(self, current_cart_items):
        if not current_cart_items: return None
        try:
            conn = self.get_connection()
            placeholders = ','.join(['?'] * len(current_cart_items))
            query = f"""
                SELECT s2.product_name, COUNT(*) as frequency
                FROM sale_items s1
                JOIN sale_items s2 ON s1.sale_id = s2.sale_id
                WHERE s1.product_name IN ({placeholders}) AND s2.product_name NOT IN ({placeholders})
                GROUP BY s2.product_name ORDER BY frequency DESC LIMIT 1
            """
            res = conn.execute(query, current_cart_items).fetchone()
            conn.close()
            return res[0] if res else None
        except: return None

    def analyze_busy_hours(self):
        try:
            conn = self.get_connection()
            df = pd.read_sql("SELECT strftime('%H', timestamp) as hour, COUNT(*) as count FROM sales GROUP BY hour", conn)
            conn.close()
            if df.empty: return None
            
            busiest = df.loc[df['count'].idxmax()]
            return f"⏰ En yoğun saat: **{busiest['hour']}:00** ({busiest['count']} işlem)"
        except: return None

    def generate_full_report(self):
        """Tüm analizleri tek metinde topla"""
        report = "📊 **VOID AI KAPSAMLI RAPOR**\n" + "="*30 + "\n\n"
        
        # 1. Fiyat
        pricing = self.suggest_dynamic_pricing()
        if pricing:
            report += "💰 **FİYAT FIRSATLARI:**\n"
            for p in pricing:
                report += f" • {p['product']}: {p['action']} ({p['old']} -> {p['new']})\n"
            report += "\n"
            
        # 2. Paket
        bundles = self.suggest_bundles()
        if bundles:
            report += "📦 **PAKET ÖNERİLERİ:**\n"
            for b in bundles:
                report += f" • {b['bundle']} ({b['price']} TL)\n"
            report += "\n"
            
        # 3. Stok
        report += self.optimize_stock_investment() + "\n\n"
        
        # 4. Tahmin
        report += self.predict_next_week_demand()
        
        return report

class VoidAI_NLP:
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.context = {} 
        self.last_backup = {}

        self.intent_patterns = {
            "ciro": ["ciro", "kazanç", "gelir", "hasılat", "bugün ne kadar", "kasa"],
            "tahmin": ["tahmin", "gelecek", "beklenti"],
            "stok_rapor": ["stok raporu", "stok durumu", "ne kadar stok", "hangi ürünler bitmek üzere"],
            "siparis_oneri": ["ne sipariş", "mal al", "sipariş ver", "tedarik"],
            "satis_trend": ["en çok satan", "popüler", "trend", "çok satılan"],
            "anomali": ["anomali", "hata", "kaçak", "tuhaflık"],
            "yardim": ["yardım", "ne yapabilirsin", "komutlar"],
        }

    # ============================================================
    # 🛠️ YARDIMCI ARAÇLAR
    # ============================================================
    
    def detect_intent(self, user_msg):
        """Kullanıcının genel niyetini algılar"""
        msg_lower = user_msg.lower()
        for intent, keywords in self.intent_patterns.items():
            for kw in keywords:
                if kw in msg_lower:
                    return intent
        return "unknown"

    def extract_number(self, text):
        """
        Gelişmiş Sayı Temizleyici:
        '1.250' -> 1250.0
        '1250' -> 1250.0
        '12,50' -> 12.5
        """
        if not text: return None
        clean_text = re.sub(r'[^\d.,]', '', text)
        
        if not any(char.isdigit() for char in clean_text):
            return None

        # Düz sayı
        if '.' not in clean_text and ',' not in clean_text:
            return float(clean_text)
        val = clean_text.replace('.', '') 
        val = val.replace(',', '.')       
        
        try:
            return float(val)
        except:
            return None

    def find_product_by_barcode(self, barcode):
        """Barkoda göre ürün bilgisi döner"""
        try:
            result = self.db.cursor.execute(
                "SELECT id, name FROM products WHERE barcode=?", 
                (barcode,)
            ).fetchone()
            return result if result else None
        except:
            return None

    def extract_category(self, text):
        """Metinden kategori çıkarır"""
        text_lower = text.lower()
        
        category_patterns = {
            "viski": ["viski", "whisky", "whiskey"],
            "vodka": ["vodka"],
            "rakı": ["rakı", "raki"],
            "bira": ["bira", "beer"],
            "şarap": ["şarap", "wine"],
            "likör": ["likör", "liqueur"],
            "cin": ["cin", "gin"],
            "rom": ["rom", "rum"],
            "tekila": ["tekila", "tequila"],
            "şampanya": ["şampanya", "champagne"],
            "sigara": ["sigara", "cigarette"],
            "içecek": ["içecek", "drink", "meşrubat"],
            "atıştırmalık": ["atıştırmalık", "cips", "gofret"],
        }
        
        for category, keywords in category_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return category.title()
        
        group_match = re.search(r'(\w+)\s+grubuna', text_lower)
        if group_match:
            return group_match.group(1).title()
        
        return None

    # ============================================================
    # 🧠 ANA BEYİN (ROUTER)
    # ============================================================

    def generate_response(self, user_msg):
        """Tüm trafiği yöneten ana fonksiyon"""
        msg_lower = user_msg.lower()

        # 1. GERİ ALMA
        if "geri al" in msg_lower or "iptal et" in msg_lower:
            return self.restore_backup()

        # 2. STOK RAPORU
        intent = self.detect_intent(user_msg)
        if intent == "stok_rapor":
            return self.generate_stock_report()
        
        # 3. SİPARİŞ ÖNERİSİ
        if intent == "siparis_oneri":
            return self.generate_order_suggestion()
        
        # 4. SATIŞ TRENDİ
        if intent == "satis_trend":
            return self.generate_sales_trend()

        # 5. RAPORLAMA
        if "kaç tane sattı" in msg_lower or "ne kadar sattı" in msg_lower:
            return self.process_sales_query(msg_lower)

        # 6. YENİ ÜRÜN EKLEME
        if any(kw in msg_lower for kw in ["yeni ürün", "ürün ekle"]):
            return self.process_new_product(user_msg)

        # 7. KATEGORİ ATAMA
        if "grubuna ekle" in msg_lower or "kategorisi" in msg_lower:
            return self.process_category_assignment(user_msg)

        # 8. KOMPLEKS GÜNCELLEME
        action_keywords = ["yap", "güncelle", "değiştir", "artır", "azalt", "sil", "kaldır", "zam", "indirim", "ekle", "olsun"]
        if any(kw in msg_lower for kw in action_keywords):
            return self.process_complex_update(user_msg)

        # 9. GENEL SORGULAR
        if intent == "ciro":
            return self.handle_ciro_query()
        elif intent == "yardim":
            return self.show_help()
        
        return "🤔 Sadece izliyorum. Bir işlem yapmak istersen komut ver.\n📖 'Yardım' yazarak komutları görebilirsin."

    # ============================================================
    # ⚙️ GÜNCELLEME MOTORU (DÜZELTME İLE)
    # ============================================================

    def process_complex_update(self, text):
        """Metni ürünlere/barkodlara göre parçalar ve komutları uygular"""
        text_lower = text.lower()
        
        # 1. Veritabanından mevcut ürünleri çek
        products = self.db.cursor.execute("SELECT id, name, barcode FROM products").fetchall()
        
        search_items = []
        
        for pid, name, barcode in products:
            # İsim ile arama (uzunluk önemli - "J&B" vs "Jägermeister")
            search_items.append({
                'key': name.lower(), 
                'id': pid, 
                'display': name, 
                'len': len(name),
                'type': 'name'
            })
            
            # Barkod ile arama
            if barcode:
                search_items.append({
                    'key': barcode, 
                    'id': pid, 
                    'display': f"{name}", 
                    'len': len(barcode),
                    'type': 'barcode'
                })

        # UZUN İSİMLERİ ÖNCE BUL (Jägermeister önce, J&B sonra)
        search_items.sort(key=lambda x: x['len'], reverse=True)

        found_matches = []
        temp_text = text_lower

        # 2. TAM EŞLEŞME ARAMASI
        for item in search_items:
            # Kelime sınırlarını kontrol et
            pattern = r'\b' + re.escape(item['key']) + r'\b'
            match = re.search(pattern, temp_text, re.IGNORECASE)
            
            if match:
                idx = match.start()
                found_matches.append({'pos': idx, 'data': item, 'end': match.end()})
                # Bulunan yeri maskele
                temp_text = temp_text[:idx] + "#" * (match.end() - idx) + temp_text[match.end():]

        # 3. FUZZY SEARCH (Eğer hiçbir şey bulunamadıysa)
        if not found_matches:
            words = text_lower.split()
            all_names = {p[1].lower(): (p[0], p[1]) for p in products}
            
            for word in words:
                matches = difflib.get_close_matches(word, all_names.keys(), n=1, cutoff=0.7)
                if matches:
                    matched_key = matches[0]
                    pid, real_name = all_names[matched_key]
                    
                    idx = text_lower.find(word)
                    if idx != -1:
                        found_matches.append({
                            'pos': idx, 
                            'data': {
                                'key': word,
                                'id': pid,
                                'display': real_name,
                                'len': len(word),
                                'type': 'fuzzy'
                            },
                            'end': idx + len(word)
                        })
                        break  # İlk eşleşmeyi al

        if not found_matches:
            return "⚠️ Mesajda kayıtlı bir ürün ismi veya barkod bulamadım."

        # YEDEK AL
        affected_ids = [m['data']['id'] for m in found_matches]
        self.create_backup(affected_ids)

        # Pozisyona göre sırala
        found_matches.sort(key=lambda x: x['pos'])
        
        # 4. HER ÜRÜN İÇİN SADECE KENDİ SEGMENTİNİ İŞLE
        report = "📝 **İşlem Raporu:**\n"
        total_actions = 0

        for i in range(len(found_matches)):
            match = found_matches[i]
            prod_data = match['data']
            
            # Segment başlangıcı: ürün isminin bittiği yer
            start_scope = match['end']
            
            # Segment bitişi: bir sonraki ürün başlangıcı VEYA mesaj sonu
            if i < len(found_matches) - 1:
                end_scope = found_matches[i+1]['pos']
            else:
                end_scope = len(text_lower)

            # Bu ürüne ait segment
            segment = text_lower[start_scope:end_scope]
            
            # Segmenti işle
            result = self.parse_segment_and_execute(prod_data['id'], prod_data['display'], segment)
            
            if result:
                report += f"{result}\n"
                total_actions += 1

        if total_actions > 0:
            return report + "\n💾 *Veritabanı güncellendi. Hata varsa 'Geri al' diyebilirsin.*"
        else:
            return "🤔 Ürünü buldum ama ne yapacağımı anlayamadım."

    def parse_segment_and_execute(self, pid, name, segment):
        changes = []
        
        # --- 1. SİLME ---
        if any(w in segment for w in ["sil", "kaldır", "uçur", "yok et"]):
            self.db.delete_product(pid)
            return f"🗑️ **{name}**: SİLİNDİ."

        # --- 2. YÜZDESEL İŞLEMLER ---
        percent_match = re.search(r'(?:%|yüzde)\s*([\d.,]+)\s*(zam|artır|ekle|indirim|düş|azalt)', segment)
        if percent_match:
            raw_rate = percent_match.group(1)
            rate = self.extract_number(raw_rate)
            action = percent_match.group(2)
            
            if rate is not None:
                curr_price = self.db.cursor.execute("SELECT sell_price FROM products WHERE id=?", (pid,)).fetchone()[0]
                
                if action in ["zam", "artır", "ekle"]:
                    new_price = curr_price * (1 + rate / 100)
                    changes.append(f"Fiyat ➔ {new_price:.2f} ₺ (%{int(rate)} Zam)")
                else:
                    new_price = curr_price * (1 - rate / 100)
                    changes.append(f"Fiyat ➔ {new_price:.2f} ₺ (%{int(rate)} İndirim)")
                    
                self.db.update_product_field(pid, "sell_price", new_price)

        # --- 3. STOK İŞLEMLERİ ---
        stock_patterns = [
            r'(?:stok|stoğu|adet)(?:u)?(?:nu)?\s+([\d.,]+)\s+(yap|olsun|ekle|artır|azalt|çıkar|düş|değiştir)',
            r'(?:stok|stoğu|adet)(?:u)?(?:nu)?\s+([\d.,]+)'
        ]
        
        stock_match = None
        stock_action = "yap"
        
        for pattern in stock_patterns:
            stock_match = re.search(pattern, segment)
            if stock_match:
                # Action kelimesi varsa al
                if len(stock_match.groups()) > 1:
                    stock_action = stock_match.group(2)
                break
        
        if stock_match:
            raw_val = stock_match.group(1)
            val = int(self.extract_number(raw_val))
            
            curr = self.db.cursor.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0]
            new_stock = curr
            
            if stock_action in ["ekle", "artır"]:
                new_stock = curr + val
                changes.append(f"Stok ➔ {new_stock} (+{val})")
            elif stock_action in ["azalt", "çıkar", "düş"]:
                new_stock = curr - val
                changes.append(f"Stok ➔ {new_stock} (-{val})")
            else:  # yap, olsun, değiştir
                new_stock = val
                changes.append(f"Stok ➔ {new_stock} (Ayarlandı)")
                
            self.db.update_product_field(pid, "stock", new_stock)

        # --- 4. FİYAT İŞLEMLERİ (DÜZELTME) ---
        price_patterns = [
            r'(?:fiyat|fiyatı|fiyatını)\s+([\d.,]+)\s*(?:tl|lira|try)?\s*(?:yap|olsun|değiştir)?',
            r'([\d.,]+)\s*(?:tl|lira|try)\s*(?:yap|olsun|değiştir)?',
        ]
        
        final_price = None
        
        for pattern in price_patterns:
            price_match = re.search(pattern, segment)
            if price_match:
                potential_price = self.extract_number(price_match.group(1))
                
                # Bu sayının stok değeri olup olmadığını kontrol et
                is_stock_value = False
                if stock_match:
                    stock_val = self.extract_number(stock_match.group(1))
                    if potential_price == stock_val:
                        is_stock_value = True
                
                if not is_stock_value:
                    final_price = potential_price
                    break

        if final_price is not None:
            self.db.update_product_field(pid, "sell_price", final_price)
            changes.append(f"Fiyat ➔ {final_price:.2f} ₺")

        # --- 5. KRİTİK STOK ---
        crit_match = re.search(r'(?:kritik)\s*(?:stok)?(?:u)?(?:ğu)?\s+([\d.,]+)', segment)
        if crit_match:
            c_val = int(self.extract_number(crit_match.group(1)))
            self.db.update_product_field(pid, "critical_stock", c_val)
            changes.append(f"Kritik Limit ➔ {c_val}")

        # --- 6. MALİYET ---
        cost_match = re.search(r'(?:maliyet|maliyeti|maliyetini)\s+([\d.,]+)', segment)
        if cost_match:
            c_cost = self.extract_number(cost_match.group(1))
            self.db.update_product_field(pid, "cost_price", c_cost)
            changes.append(f"Maliyet ➔ {c_cost:.2f} ₺")

        if changes:
            return f"✅ **{name}**: " + ", ".join(changes)
        return None

    # ============================================================
    # 📊 YENİ ÖZELLİKLER: STOK TAKİP & SİPARİŞ
    # ============================================================

    def generate_stock_report(self):
        """Detaylı stok raporu"""
        try:
            # 1. Kritik stok altındakiler
            critical = self.db.cursor.execute("""
                SELECT name, stock, critical_stock 
                FROM products 
                WHERE stock <= critical_stock
                ORDER BY stock ASC
            """).fetchall()
            
            # 2. Tükenmek üzere olanlar
            low_stock = self.db.cursor.execute("""
                SELECT name, stock, critical_stock 
                FROM products 
                WHERE stock > critical_stock AND stock <= critical_stock * 1.5
                ORDER BY stock ASC
            """).fetchall()
            
            # 3. Bol stoklu ürünler
            high_stock = self.db.cursor.execute("""
                SELECT name, stock, critical_stock 
                FROM products 
                WHERE stock > critical_stock * 3
                ORDER BY stock DESC
                LIMIT 5
            """).fetchall()
            
            report = "📊 **STOK DURUMU RAPORU**\n\n"
            
            # Kritik durum
            if critical:
                report += "🔴 **ACİL SİPARİŞ GEREKLİ:**\n"
                for name, stock, crit in critical:
                    shortage = crit * 2 - stock
                    report += f"   • {name}: {stock} adet (Min: {crit}) → **{shortage} adet sipariş verin**\n"
                report += "\n"
            
            # Düşük stok
            if low_stock:
                report += "🟡 **YAKINDA BİTECEKLER:**\n"
                for name, stock, crit in low_stock:
                    report += f"   • {name}: {stock} adet (Min: {crit})\n"
                report += "\n"
            
            # Bol stok
            if high_stock:
                report += "🟢 **BOL STOKLU ÜRÜNLER:**\n"
                for name, stock, crit in high_stock:
                    report += f"   • {name}: {stock} adet\n"
            
            if not critical and not low_stock:
                report += "✅ Tüm ürünler yeterli stokta!"
            
            return report
            
        except Exception as e:
            return f"Stok raporu hatası: {str(e)}"

    def generate_order_suggestion(self):
        """Satış verilerine göre sipariş önerisi"""
        try:
            # Son 30 günde satılan ürünleri analiz et
            query = """
                SELECT 
                    si.product_name,
                    SUM(si.quantity) as total_sold,
                    p.stock,
                    p.critical_stock
                FROM sale_items si
                JOIN products p ON si.product_name = p.name
                WHERE si.sale_date >= date('now', '-30 days')
                GROUP BY si.product_name
                ORDER BY total_sold DESC
            """
            data = self.db.cursor.execute(query).fetchall()
            
            if not data:
                return "📦 Son 30 günde satış verisi yok."
            
            report = "🛒 **SİPARİŞ ÖNERİLERİ (Son 30 Gün Bazlı):**\n\n"
            
            for name, total_sold, stock, crit in data:
                # Günlük ortalama satış
                daily_avg = total_sold / 30
                
                # Kaç günlük stok kaldı?
                if daily_avg > 0:
                    days_left = stock / daily_avg
                else:
                    days_left = 999
                
                # Önerilen sipariş miktarı (2 haftalık)
                suggested_order = int(daily_avg * 14)
                
                if days_left < 7:
                    urgency = "🔴 ACİL"
                    report += f"{urgency} **{name}**\n"
                    report += f"   • Kalan: {stock} adet (~{int(days_left)} gün)\n"
                    report += f"   • Günlük satış: {daily_avg:.1f} adet\n"
                    report += f"   • **ÖNERİ: {suggested_order} adet sipariş verin**\n\n"
                elif days_left < 14:
                    urgency = "🟡 DİKKAT"
                    report += f"{urgency} **{name}**\n"
                    report += f"   • Kalan: {stock} adet (~{int(days_left)} gün)\n"
                    report += f"   • **ÖNERİ: {suggested_order} adet sipariş verin**\n\n"
            
            return report
            
        except Exception as e:
            return f"Sipariş önerisi hatası: {str(e)}"

    def generate_sales_trend(self, days=30):
        """En çok satan ürünler"""
        try:
            query = f"""
                SELECT 
                    product_name,
                    SUM(quantity) as total_qty,
                    SUM(total_price) as total_revenue,
                    COUNT(DISTINCT sale_id) as transaction_count
                FROM sale_items
                WHERE sale_date >= date('now', '-{days} days')
                GROUP BY product_name
                ORDER BY total_revenue DESC
                LIMIT 10
            """
            data = self.db.cursor.execute(query).fetchall()
            
            if not data:
                return f"📊 Son {days} günde satış verisi yok."
            
            report = f"📈 **EN ÇOK SATAN ÜRÜNLER (Son {days} Gün):**\n\n"
            
            for i, (name, qty, revenue, tx_count) in enumerate(data, 1):
                avg_per_sale = revenue / tx_count if tx_count > 0 else 0
                report += f"{i}. **{name}**\n"
                report += f"   • Satılan: {int(qty)} adet\n"
                report += f"   • Ciro: {revenue:.2f} ₺\n"
                report += f"   • İşlem Sayısı: {tx_count}\n"
                report += f"   • Ortalama: {avg_per_sale:.2f} ₺/işlem\n\n"
            
            return report
            
        except Exception as e:
            return f"Satış trendi hatası: {str(e)}"

    # ============================================================
    # 📦 DİĞER FONKSİYONLAR
    # ============================================================

    def process_category_assignment(self, text):
        """Barkod veya isim ile kategori ataması"""
        try:
            text_lower = text.lower()
            
            category = self.extract_category(text)
            if not category:
                return "⚠️ Hangi kategoriye ekleyeceğinizi belirtmediniz."
            
            products = self.db.cursor.execute("SELECT id, name, barcode FROM products").fetchall()
            target_product = None
            
            # Barkod araması
            barcode_match = re.search(r'\b(\d{8,13})\b', text)
            if barcode_match:
                barcode = barcode_match.group(1)
                result = self.find_product_by_barcode(barcode)
                if result:
                    target_product = result
            
            # İsim araması
            if not target_product:
                all_names = [p[1] for p in products]
                for name in all_names:
                    if name.lower() in text_lower:
                        pid = self.db.cursor.execute("SELECT id FROM products WHERE name=?", (name,)).fetchone()[0]
                        target_product = (pid, name)
                        break
                
                # Fuzzy search
                if not target_product:
                    words = text_lower.split()
                    for word in words:
                        matches = difflib.get_close_matches(word, all_names, n=1, cutoff=0.6)
                        if matches:
                            matched_name = matches[0]
                            pid = self.db.cursor.execute("SELECT id FROM products WHERE name=?", (matched_name,)).fetchone()[0]
                            target_product = (pid, matched_name)
                            break
            
            if target_product:
                pid, name = target_product
                self.db.update_product_field(pid, "category", category)
                return f"✅ **{name}** ➔ **{category}** grubuna eklendi."
            else:
                return "⚠️ Ürün bulunamadı."
                
        except Exception as e:
            return f"Kategori atama hatası: {str(e)}"

    def process_new_product(self, text):
        """Yeni Ürün Ekleme"""
        try:
            text_lower = text.lower()
            
            # Barkod
            barcode_match = re.search(r'(?:barkod|kod)[:\s]*(\d{8,13})', text_lower)
            barcode = barcode_match.group(1) if barcode_match else None
            
            if barcode:
                existing = self.db.cursor.execute("SELECT id FROM products WHERE barcode=?", (barcode,)).fetchone()
                if existing:
                    return f"❌ Bu barkod ({barcode}) zaten kayıtlı!"
            
            # İsim
            name_match = re.search(r'(?:ekle|oluştur|isim)[:\s]+(.*?)(?:,|$|\s(?:fiyat|stok|barkod|kategori|maliyet|kritik))', text_lower)
            if not name_match:
                if barcode:
                    return f"⚠️ Barkod ({barcode}) için bir ürün ismi belirtmediniz."
                return "⚠️ Ürün adını anlayamadım."
            
            name = name_match.group(1).strip().title()
            
            # Fiyat
            price_match = re.search(r'(?:fiyatı|fiyat)[:\s]*([\d.,]+)', text_lower)
            sell_price = self.extract_number(price_match.group(1)) if price_match else 0.0
            
            # Stok
            stock_match = re.search(r'(?:stoğu|stok)[:\s]*([\d.,]+)', text_lower)
            stock = int(self.extract_number(stock_match.group(1))) if stock_match else 0
            
            # Kritik Stok
            crit_match = re.search(r'(?:kritik)\s*(?:stok)?[:\s]*([\d.,]+)', text_lower)
            critical_stock = int(self.extract_number(crit_match.group(1))) if crit_match else 5
            
            # Maliyet
            cost_match = re.search(r'(?:maliyet)[:\s]*([\d.,]+)', text_lower)
            cost_price = self.extract_number(cost_match.group(1)) if cost_match else 0.0
            
            # Kategori
            category = self.extract_category(text_lower) or "Genel"

            self.db.insert_product(
                name, 
                cost_price, 
                sell_price, 
                stock, 
                category, 
                barcode, 
                "",
                critical_stock
            )
            
            result = f"✅ **Eklendi:** {name}\n"
            if barcode:
                result += f"🔢 Barkod: {barcode}\n"
            result += f"📂 Kategori: {category}\n"
            result += f"💰 Fiyat: {sell_price:.2f} ₺\n"
            result += f"💸 Maliyet: {cost_price:.2f} ₺\n"
            result += f"📦 Stok: {stock}\n"
            result += f"⚠️ Kritik Stok: {critical_stock}"
            
            return result
            
        except Exception as e:
            return f"Ekleme hatası: {str(e)}"

    def create_backup(self, product_ids):
        """Değişiklik öncesi verileri yedekle"""
        self.last_backup = {}
        if not product_ids: return
        placeholders = ','.join(['?'] * len(product_ids))
        query = f"SELECT id, sell_price, stock, critical_stock, cost_price, name, category FROM products WHERE id IN ({placeholders})"
        rows = self.db.cursor.execute(query, product_ids).fetchall()
        for row in rows:
            self.last_backup[row[0]] = {
                'sell_price': row[1], 
                'stock': row[2], 
                'critical_stock': row[3], 
                'cost_price': row[4], 
                'name': row[5],
                'category': row[6]
            }

    def restore_backup(self):
        """Son işlemi geri al"""
        if not self.last_backup: 
            return "⚠️ Geri alınacak işlem yok."
        
        names = []
        for pid, data in self.last_backup.items():
            self.db.cursor.execute("""
                UPDATE products 
                SET sell_price=?, stock=?, critical_stock=?, cost_price=?, category=? 
                WHERE id=?
            """, (data['sell_price'], data['stock'], data['critical_stock'], 
                  data['cost_price'], data['category'], pid))
            names.append(data['name'])
        
        self.db.conn.commit()
        self.last_backup = {}
        return f"✅ İşlem geri alındı: {', '.join(names)}"

    def process_sales_query(self, text):
        """Satış Raporu"""
        try:
            products = self.db.cursor.execute("SELECT name FROM products").fetchall()
            all_names = [p[0] for p in products]
            
            target_product = None
            
            for name in all_names:
                if name.lower() in text:
                    target_product = name
                    break
            
            if not target_product:
                words = text.split()
                for word in words:
                    matches = difflib.get_close_matches(word, all_names, n=1, cutoff=0.6)
                    if matches:
                        target_product = matches[0]
                        break
            
            if target_product:
                today = str(datetime.date.today())
                res = self.db.cursor.execute(
                    "SELECT SUM(quantity), SUM(total_price) FROM sale_items WHERE product_name=? AND sale_date=?", 
                    (target_product, today)
                ).fetchone()
                
                qty = res[0] if res[0] else 0
                revenue = res[1] if res[1] else 0.0
                return f"📊 **{target_product}** Bugün Raporu:\n📦 Satılan: {qty} Adet\n💰 Ciro: {revenue:.2f} ₺"
            else:
                return "Hangi ürünün satışını sorduğunu anlayamadım."
        except Exception as e:
            return f"Rapor hatası: {str(e)}"

    def handle_ciro_query(self):
        """Günlük ciro sorgula"""
        today = str(datetime.date.today())
        res = self.db.cursor.execute("SELECT SUM(total_amount) FROM sales WHERE sale_date=?", (today,)).fetchone()
        val = res[0] if res[0] else 0.0
        return f"💰 Bugün Toplam Ciro: **{val:.2f} ₺**"

    def show_help(self):
        """Yardım menüsü"""
        return """
🤖 **Void AI Komutları:**

**📝 Ürün Güncelleme:**
• 'J&B fiyat 1250 yap'
• 'Marlboro stoğu 5 artır'
• '8690504000014 stoğu 10 azalt'
• 'Red Label kritik stoğu 5 yap'
• 'Viski maliyeti 800 yap'

**🆕 Yeni Ürün:**
• 'Yeni ürün ekle: Çikolata fiyat 50 stok 100 barkod 123456789012'

**📂 Kategori:**
• '8690504000014 viski grubuna ekle'

**📊 Raporlar:**
• 'Stok raporu' - Detaylı stok durumu
• 'Ne sipariş vermeliyim' - Sipariş önerileri
• 'En çok satan ürünler' - Satış trendleri
• 'Bugün ne kadar sattık?'

**↩️ Geri Alma:**
• 'Geri al'
        """

class AIChatDialog(QDialog):    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        # NLP'yi başlat (varsa)
        try:
            self.ai_nlp = VoidAI_NLP(db_manager)
        except:
            self.ai_nlp = None
            
        # Yeni Beyni Başlat
        self.brain = VoidBrain_Analytic(db_manager.db_path)
        
        self.setWindowTitle("🧠 Void AI Pro - Analiz Asistanı")
        self.setFixedSize(700, 850)
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        
        layout = QVBoxLayout(self)
        
        # Başlık
        header = QLabel("🧠 Void AI Pro")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #30d158; margin: 10px;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # --- YENİ: HIZLI EYLEM BUTONLARI ---
        quick_actions = QHBoxLayout()
        quick_actions.setSpacing(10)
        
        buttons = [
            ("💰 Fiyat Analizi", self.run_pricing),
            ("📦 Paket Öner", self.run_bundles),
            ("🔮 Gelecek Tahmini", self.run_forecast),
            ("📊 Tam Rapor", self.run_full_report)
        ]
        
        for text, func in buttons:
            btn = QPushButton(text)
            btn.setFixedHeight(45)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a2a; border: 1px solid #444; 
                    border-radius: 8px; font-weight: bold; color: #e0e0e0;
                }
                QPushButton:hover { background-color: #0a84ff; border: 1px solid #0a84ff; color: white; }
            """)
            btn.clicked.connect(func)
            quick_actions.addWidget(btn)
            
        layout.addLayout(quick_actions)

        # Chat Ekranı
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("background-color: #252525; border: none; border-radius: 12px; padding: 15px; font-size: 14px;")
        layout.addWidget(self.chat_history)
        
        # Giriş Alanı
        input_layout = QHBoxLayout()
        self.inp_msg = QLineEdit()
        self.inp_msg.setPlaceholderText("Bir komut yazın (örn: 'ciro', 'stok durumu')...")
        self.inp_msg.setStyleSheet("background-color: #333; color: white; border-radius: 20px; padding: 12px; border: 1px solid #555;")
        self.inp_msg.returnPressed.connect(self.send_message)
        
        btn_send = QPushButton("➤")
        btn_send.setFixedSize(50, 50)
        btn_send.setStyleSheet("background-color: #30d158; border-radius: 25px; font-weight: bold; color: #000;")
        btn_send.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.inp_msg)
        input_layout.addWidget(btn_send)
        layout.addLayout(input_layout)
        
        self.add_message("Void AI", "👋 Merhaba! Kâr artırma motoru devrede. Yukarıdaki butonları kullanarak analiz yapabilirsin.", is_html=True)

    def add_message(self, sender, text, is_html=False):
        align = "left" if sender == "Void AI" else "right"
        bg = "#1e3a2a" if sender == "Void AI" else "#0a84ff"
        color = "#30d158" if sender == "Void AI" else "white"
        
        formatted = text.replace('\n', '<br>') if not is_html else text
        html = f"<div style='text-align:{align}; margin-bottom:10px;'><div style='display:inline-block; background:{bg}; padding:10px; border-radius:10px;'><b style='color:{color}'>{sender}</b><br>{formatted}</div></div>"
        self.chat_history.append(html)
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())

    # --- BUTON FONKSİYONLARI ---
    def run_pricing(self):
        self.add_message("Siz", "Fiyat analizi yap.")
        data = self.brain.suggest_dynamic_pricing()
        if not data:
            self.add_message("Void AI", "Şu an için fiyat önerim yok.")
            return
        msg = "💰 **Fiyat Önerileri:**<br>"
        for d in data:
            msg += f"• <b>{d['product']}</b>: {d['action']} ({d['old']} -> {d['new']})<br><i>Sebebi: {d['reason']}</i><br><br>"
        self.add_message("Void AI", msg, is_html=True)

    def run_bundles(self):
        self.add_message("Siz", "Paket öner.")
        data = self.brain.suggest_bundles()
        if not data:
            self.add_message("Void AI", "Yeterli çapraz satış verisi yok.")
            return
        msg = "📦 **Paket Fırsatları:**<br>"
        for b in data:
            msg += f"• {b['msg']}<br>"
        self.add_message("Void AI", msg, is_html=True)

    def run_forecast(self):
        self.add_message("Siz", "Gelecek tahmini yap.")
        QApplication.processEvents() # Arayüz donmasın
        msg = self.brain.predict_next_week_demand()
        self.add_message("Void AI", msg.replace("\n", "<br>"), is_html=True)

    def run_full_report(self):
        self.add_message("Siz", "Tam rapor hazırla.")
        QApplication.processEvents()
        msg = self.brain.generate_full_report()
        self.add_message("Void AI", msg.replace("\n", "<br>"), is_html=True)

    def send_message(self):
        msg = self.inp_msg.text().strip()
        if not msg: return
        self.add_message("Siz", msg)
        self.inp_msg.clear()
        
        # NLP varsa kullan, yoksa basit cevap ver
        if self.ai_nlp:
            response = self.ai_nlp.generate_response(msg)
            self.add_message("Void AI", response)
        else:
            self.add_message("Void AI", "Şu an sadece buton komutlarını işliyorum.")

class VoidAI_Engine:
    """
    Arka planda çalışan Analiz Motoru
    NOT: Bu motor veritabanına bağlanır, CSV'ye değil!
    """
    def __init__(self, db_path):
        self.db_path = db_path 

    def tum_analizleri_yap(self):
        oneriler = []
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 1. KRİTİK STOK
            cursor.execute("SELECT name, stock, critical_stock FROM products WHERE stock <= critical_stock")
            for name, stock, crit in cursor.fetchall():
                eksik = (crit * 2) - stock 
                oneriler.append({
                    "tur": "KRITIK",
                    "mesaj": f"⚠️ KRİTİK STOK: {name} (Kalan: {stock}) -> {eksik} sipariş ver."
                })

            # 2. ÖLÜ STOK
            query_olu = """
                SELECT name, stock FROM products 
                WHERE stock > 5 
                AND name NOT IN (SELECT DISTINCT product_name FROM sale_items WHERE sale_date >= date('now', '-30 days'))
            """
            cursor.execute(query_olu)
            for name, stock in cursor.fetchall():
                oneriler.append({
                    "tur": "OLU",
                    "mesaj": f"❄️ ÖLÜ STOK: {name} ({stock} adet) satılmıyor. İndirim yap."
                })

            conn.close()
        except Exception as e:
            print(f"Engine Hatası: {e}")
            return []
        return oneriler

class AIWorker(QThread):
    finished = Signal(list)  
    def __init__(self, db_path): # ARTIK DB PATH ALIYOR
        super().__init__()
        self.db_path = db_path

    def run(self):
        if os.path.exists(self.db_path):
            motor = VoidAI_Engine(self.db_path)
            sonuclar = motor.tum_analizleri_yap()
            self.finished.emit(sonuclar)
        else:
            self.finished.emit([])

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
        self.ciro_visible = True 
        self.init_ui()
        self.setWindowTitle("VoidPOS")
        self.resize(1600, 900)
        self.ai = VoidBrain_Analytic("voidpos.db")
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
        main_lay.setContentsMargins(0, 2, 0, 0)
        main_lay.setSpacing(0)
        
        # --- 1. SOL PANEL (AYNI) ---
        left_container = QFrame()
        left_container.setFixedWidth(480) 
        left_container.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(10, 10, 10, 0) 
        left_layout.setSpacing(5)
        
        # Arama
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Ara...")
        self.search_bar.setFixedHeight(45)
        self.search_bar.textChanged.connect(self.on_search_changed)
        left_layout.addWidget(self.search_bar)
        
        # Ürün Grid (Scroll Area)
        self.selection_scroll = QScrollArea()
        self.selection_scroll.setWidgetResizable(True)
        self.selection_scroll.setStyleSheet("border:none; background:transparent;")
        self.selection_cont = QWidget()
        self.selection_lay = QGridLayout(self.selection_cont)
        self.selection_lay.setContentsMargins(0, 2, 0, 0)
        self.selection_lay.setSpacing(15)
        self.selection_scroll.setWidget(self.selection_cont)
        left_layout.addWidget(self.selection_scroll)

        main_lay.addWidget(left_container)

        # --- 2. ORTA PANEL ---
        center_container = QFrame()
        center_container.setObjectName("CenterPanel")        
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(10, 20, 10, 10)
        
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
        # Toplam Tutar
        self.lbl_total = QLabel("0.00 ₺")
        self.lbl_total.setAlignment(Qt.AlignRight)
        self.lbl_total.setStyleSheet("font-size: 70px; font-weight:900; color:white; margin: 20px 0;")
        self.cart_tabs = QTabWidget()
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
        btn_cash.setObjectName("BtnCash")  
        btn_cash.setFixedHeight(90)        
        btn_cash.setCursor(Qt.PointingHandCursor)
        btn_cash.clicked.connect(lambda: self.finish_sale("Nakit"))
        
        # KART BUTONU
        btn_card = QPushButton("KART")
        btn_card.setObjectName("BtnCard")  
        btn_card.setFixedHeight(90)        
        btn_card.setCursor(Qt.PointingHandCursor)
        btn_card.clicked.connect(self.card_payment)
        
        pay_lay.addWidget(btn_cash)
        pay_lay.addWidget(btn_card)
        right_layout.addLayout(pay_lay)
        
        main_lay.addWidget(right_container)
        
        self.load_categories_grid()
        self.table.installEventFilter(self)

    def refresh_after_ai(self):
        print("🔄 AI sonrası sistem yenileniyor...")
        
        # 1. Sepetlerdeki ürünlerin fiyatlarını güncelle
        self.update_cart_prices_live()
        
        # 2. Ürün listesini (Grid) yenile (Eğer bir kategorideyse)
        if self.current_category:
            self.load_products_grid(self.current_category)
        else:
            self.load_categories_grid()
            
        # 3. Ciroyu yenile
        self.update_ciro()

    def update_cart_prices_live(self):
        for i in range(self.cart_tabs.count()):
            table = self.cart_tabs.widget(i)
            
            for row in range(table.rowCount()):
                item_name_widget = table.item(row, 0)
                if not item_name_widget: continue
                
                item_name = item_name_widget.text()
                res = self.db.cursor.execute("SELECT sell_price FROM products WHERE name=?", (item_name,)).fetchone()
                
                if res:
                    new_price = res[0]
                    table.item(row, 1).setText(f"{new_price:.2f}")
            if hasattr(table, 'recalc_total'): # Eğer böyle bir metot varsa
                table.recalc_total()
            elif i == self.cart_tabs.currentIndex(): # Yoksa manuel hesapla
                self.recalc_active_cart_total()

    def open_product_detail_popup(self, product_name):
        dlg = ProductDetailDialog(self.db, product_name, self)
        if dlg.exec():
            if self.current_category != "Tüm Ürünler":
                self.load_products_grid(self.current_category)

    def eventFilter(self, source, event):
        if event.type() == QEvent.KeyPress:
            if self.search_bar.hasFocus():
                if event.key() == Qt.Key_Escape:
                    self.search_bar.clearFocus()
                    if self.table.rowCount() > 0:
                        self.table.setFocus()
                        self.table.selectRow(0)
                    return True
                return super().eventFilter(source, event)
            if event.key() == Qt.Key_Space:
                if self.cart_data:
                    self.finish_sale("Nakit")
                return True 
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                if not self.search_bar.hasFocus():
                    current_row = self.table.currentRow()
                    if current_row >= 0:
                        self.table.removeRow(current_row)
                        self.recalc_active_cart_total()
                        self.selected_row = -1
                    return True
            if source == self.table and event.text().isdigit():
                self.numpad_action(event.text())
                return True
            if event.text().isalnum() and not event.text().isdigit():
                modifiers = QApplication.keyboardModifiers()
                if modifiers == Qt.NoModifier:
                    self.search_bar.setFocus()
                    self.search_bar.setText(self.search_bar.text() + event.text())
                    return True
        return super().eventFilter(source, event)
     
    def set_payment_processing(self, is_processing, btn_type=""):
        btn_cash = self.findChild(QPushButton, "BtnCash") 
        btn_card = self.findChild(QPushButton, "BtnCard") 

        if is_processing:
            if btn_cash: btn_cash.setEnabled(False)
            if btn_card: btn_card.setEnabled(False)
            style_processing = "background-color:#30d158; color:black; border: 4px solid #ffcc00; height: 80px; font-size:18px;"
            style_processing_card = "background-color:#0a84ff; color:white; border: 4px solid #ffcc00; height: 80px; font-size:18px;"

            if btn_type == "NAKİT" and btn_cash:
                btn_cash.setText("⏳ İŞLENİYOR...")
                btn_cash.setStyleSheet(style_processing)
            elif btn_type == "KART" and btn_card:
                btn_card.setText("⏳ POS BEKLENİYOR...")
                btn_card.setStyleSheet(style_processing_card)
                
        else:
            if btn_cash: 
                btn_cash.setEnabled(True)
                btn_cash.setText("NAKİT")
                btn_cash.setStyleSheet("background-color:#30d158; color:black; height: 80px;")
                
            if btn_card: 
                btn_card.setEnabled(True)
                btn_card.setText("KART")
                btn_card.setStyleSheet("background-color:#0a84ff; color:white; height: 80px;")

    def create_cart_table(self):
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["ÜRÜN", "FİYAT", "ADET", " "]) 
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) 
        header.setSectionResizeMode(1, QHeaderView.Fixed)   
        header.setSectionResizeMode(2, QHeaderView.Fixed)   
        header.setSectionResizeMode(3, QHeaderView.Fixed)   
        
        table.setColumnWidth(1, 120) 
        table.setColumnWidth(2, 80) 
        table.setColumnWidth(3, 90)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(60) 
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setShowGrid(False) 
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # CSS
        table.setStyleSheet("""
            QTableWidget { 
                background-color: transparent; 
                border: none; 
                font-size: 18px; 
                font-weight: 600; 
                outline: none;
            }
            QTableWidget::item { 
                padding-left: 10px; 
                border-bottom: 1px solid #333; 
                color: white;
            }
            QTableWidget::item:selected { 
                background-color: #263a4d; 
                color: white; 
            }
            /* Adet düzenleme kutusu */
            QTableWidget QLineEdit {
                background-color: #263a4d;
                color: #ffcc00;
                border: none;
                font-weight: bold;
                font-size: 20px;
            }
        """)

        table.itemChanged.connect(self.on_cart_item_changed)
        table.itemClicked.connect(self.row_selected)
        table.doubleClicked.connect(self.on_table_double_clicked)
        
        return table

    def add_to_cart(self, name, price):
        table = self.get_active_table()
        row = -1

        # 1. Ürün Zaten Var mı?
        found_row = -1
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if item and item.text() == name:
                found_row = r
                break
        
        # --- DURUM A: VARSA (Adet Artır) ---
        if found_row != -1:
            row = found_row
            qty_item = table.item(row, 2)
            try:
                cur_qty = int(qty_item.text())
            except:
                cur_qty = 1
            
            table.blockSignals(True)
            qty_item.setText(str(cur_qty + 1))
            table.blockSignals(False)

        # --- DURUM B: YOKSA (Yeni Ekle) ---
        else:
            row = table.rowCount()
            table.insertRow(row)
            
            font_main = QFont("Segoe UI", 16, QFont.Bold)
            font_qty = QFont("Segoe UI", 18, QFont.Bold)
            
            # 0: İsim (DÜZENLENEMEZ - Sadece Seçilebilir)
            it_name = QTableWidgetItem(str(name))
            it_name.setFont(font_main)
            it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
            table.setItem(row, 0, it_name)
            
            # 1: Fiyat (DÜZENLENEMEZ)
            it_price = QTableWidgetItem(f"{float(price):.2f}")
            it_price.setTextAlignment(Qt.AlignCenter)
            it_price.setFont(font_main)
            it_price.setForeground(QColor("#0a84ff"))
            # DİKKAT: Qt.ItemIsEditable bayrağını buradan da kaldırdım!
            it_price.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
            table.setItem(row, 1, it_price)
            
            # 2: Adet (TEK DÜZENLENEBİLİR ALAN)
            it_qty = QTableWidgetItem("1")
            it_qty.setTextAlignment(Qt.AlignCenter)
            it_qty.setForeground(QColor("#30d158"))
            it_qty.setFont(font_qty)
            # Sadece burası editlenebilir
            it_qty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 2, it_qty)
            
            # 3: Sil Butonu
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0) 
            layout.setAlignment(Qt.AlignCenter)
            btn = QPushButton("Sil 🗑️")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(80, 45)
            btn.setStyleSheet("background-color: #ff453a; color: white; border-radius: 6px; border: none; font-weight: bold;")
            btn.clicked.connect(lambda: self.smart_delete_row(btn))
            layout.addWidget(btn)
            table.setCellWidget(row, 3, container)

        # --- ODAKLANMA BÖLÜMÜ ---
        # Önce seçimi temizle ki karışıklık olmasın
        table.clearSelection()
        
        # Satırı seç
        table.selectRow(row)
        self.selected_row = row
        
        # Adet hücresini (Sütun 2) aktif hücre yap ve odakla
        table.setCurrentCell(row, 2)
        table.setFocus()
        
        # Hücreyi düzenleme moduna al (İmleci yak)
        table.editItem(table.item(row, 2)) 

        self.recalc_active_cart_total()
        
        # AI Kontrolü
        self.check_ai_suggestion(table)

    def check_ai_suggestion(self, table):
        suggestion = None 
        try:
            names = [table.item(r, 0).text() for r in range(table.rowCount()) if table.item(r, 0)]
            suggestion = self.ai.recommend_product(names)
        except: pass

        if suggestion:
            self.search_bar.setPlaceholderText(f"💡 ÖNERİ: '{suggestion}'")
            self.search_bar.setStyleSheet("QLineEdit { background: #2a1a1a; color: #ffcc00; border: 1px solid #ffcc00; }")
        else:
            self.search_bar.setPlaceholderText("🔍 Ürün Ara...")
            self.search_bar.setStyleSheet("QLineEdit { background: #252525; color: white; border: 1px solid #444; }")

    def on_table_double_clicked(self, index):
        table = self.sender()
        row = index.row()
        col = index.column()
        if col == 2:
            table.editItem(table.item(row, 2)) # Manuel olarak düzenlemeyi aç
            return
        item_name_widget = table.item(row, 0)
        
        if item_name_widget:
            item_name = item_name_widget.text()
            
            if hasattr(self, 'db'):
                dlg = ProductDetailDialog(self.db, item_name, self)
                if dlg.exec():
                    self.refresh_after_ai()
                    
    def open_product_detail_popup(self, product_name):
        dlg = ProductDetailDialog(self.db, product_name, self)
        if dlg.exec():
            if self.current_category != "Tüm Ürünler":
                self.load_products_grid(self.current_category)
            else:
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
        self.change_grid.setVerticalSpacing(12) 

        
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
            lbl_res.setProperty("class", "ChangeResultError")
            lbl_res.setStyleSheet("color: #444; font-size: 22px; font-weight: bold; border:none; background:transparent; font-family: 'Consolas', monospace;")
            
            self.change_grid.addWidget(lbl_denom, i, 0)
            self.change_grid.addWidget(lbl_arrow, i, 1)
            self.change_grid.addWidget(lbl_res, i, 2)
            
            self.change_labels[amount] = lbl_res

        layout.addWidget(self.change_grid_widget)
        layout.addStretch() # Altta boşluk bırakıp listeyi yukarı it
        return frame

    def update_change_list(self):
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
        self.search_bar.clear()
        self.load_categories_grid()
        self.update_ciro()

    def clear_selection_area(self):
        while self.selection_lay.count():
            item = self.selection_lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def load_products_grid(self, category_name):
        self.current_category = category_name         
        # Arama placeholder'ını duruma göre ayarla
        if category_name == "Tüm Ürünler":
            self.search_bar.setPlaceholderText("🔍 Kategori Ara...")
        else:
            self.search_bar.setPlaceholderText(f"🔍 {category_name} içinde ürün ara...")
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
        """
        Sol Panel: Kategoriler (Üstte) + Hızlı Erişim (Altta)
        DÜZELTME: Tüm boşluklar (margin/spacing) minimize edildi.
        """
        self.current_category = "Tüm Ürünler"
        self.search_bar.setPlaceholderText("🔍 Tüm ürünlerde ara...")
        
        # Önceki içeriği temizle
        self.clear_selection_area()
        self.selection_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        self.selection_lay.setSpacing(2) 
        
        # ============================================================
        # BÖLÜM 1: KATEGORİLER (ÜSTTE - 3x2 GÖRÜNÜM)
        # ============================================================
        
        lbl_cat = QLabel("KATEGORİLER")
        lbl_cat.setStyleSheet("color: #0a84ff; font-weight: 800; font-size: 14px; margin: 5px 0 2px 5px; letter-spacing: 1px;")
        self.selection_lay.addWidget(lbl_cat, 0, 0, 1, 3)

        # Kategori Scroll Area
        cat_scroll = QScrollArea()
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setStyleSheet("border: none; background: transparent;")
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Yükseklik Ayarı
        cat_scroll.setFixedHeight(220) 
        
        cat_container = QWidget()
        cat_grid = QGridLayout(cat_container)
        cat_grid.setContentsMargins(5, 0, 5, 0) 
        cat_grid.setSpacing(10) 
        cat_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        MAX_CAT_COL = 3 
        c_row = 0
        c_col = 0 

        # 1. TÜM ÜRÜNLER KARTI
        def show_all():
            self.load_products_grid("Tüm Ürünler")
        all_card = CategoryCard("Tüm Ürünler", lambda x: show_all(), is_all_products=True)
        all_card.setFixedSize(135, 90) 
        cat_grid.addWidget(all_card, c_row, c_col)
        c_col += 1

        # 2. DİĞER KATEGORİLER
        categories = self.db.get_all_categories()
        for cat in categories:
            if cat == "Tüm Ürünler": continue
            
            card = CategoryCard(cat, self.load_products_grid, is_add_button=False, db_manager=self.db, refresh_cb=self.refresh_ui)
            card.setFixedSize(135, 90)
            cat_grid.addWidget(card, c_row, c_col)
            
            c_col += 1
            if c_col >= MAX_CAT_COL:
                c_col = 0
                c_row += 1
        
        # 3. EKLEME KARTI
        def trigger_add_cat(_):
            self.add_category()
        add_card = CategoryCard("Kategori Ekle", trigger_add_cat, is_add_button=True)
        add_card.setFixedSize(135, 90)
        cat_grid.addWidget(add_card, c_row, c_col)

        cat_scroll.setWidget(cat_container)
        self.selection_lay.addWidget(cat_scroll, 1, 0, 1, 3)

        # ============================================================
        # BÖLÜM 2: ARA ÇİZGİ
        # ============================================================
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        # --- DÜZELTME 4: Çizgi boşlukları azaltıldı (margin: 5px 0) ---
        line.setStyleSheet("background-color: #333; margin: 5px 0;")
        self.selection_lay.addWidget(line, 2, 0, 1, 3)

        # ============================================================
        # BÖLÜM 3: HIZLI ERİŞİM (ALTTA - 3x3 GÖRÜNÜM + SCROLL)
        # ============================================================
        
        lbl_fav = QLabel("⚡ HIZLI ERİŞİM")
        # --- DÜZELTME 5: Margin azaltıldı ---
        lbl_fav.setStyleSheet("color: #ffcc00; font-weight: 800; font-size: 14px; margin: 2px 0 2px 5px; letter-spacing: 1px;")
        self.selection_lay.addWidget(lbl_fav, 3, 0, 1, 3)

        # Hızlı Erişim Scroll Area
        fav_scroll = QScrollArea()
        fav_scroll.setWidgetResizable(True)
        fav_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #121212; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #444; min-height: 30px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #ffcc00; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        fav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        fav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        fav_container = QWidget()
        fav_grid = QGridLayout(fav_container)
        # --- DÜZELTME 6: Grid iç boşlukları sıkılaştırıldı ---
        fav_grid.setContentsMargins(5, 0, 5, 0) 
        fav_grid.setSpacing(10)
        fav_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        favorites = self.db.get_favorites()
        
        if favorites:
            f_row, f_col = 0, 0
            MAX_FAV_COL = 3 
            
            for pid, name, price, img, fav, stock in favorites:
                def on_click(n, p):
                    self.add_to_cart(n, p)
                
                # Kart oluşturma (Mini mod)
                card = ProductCard(pid, name, price, img, fav, stock, on_click, self.refresh_ui, self.db, is_mini=True)
                card.setFixedSize(135, 160)
                
                fav_grid.addWidget(card, f_row, f_col)
                
                f_col += 1
                if f_col >= MAX_FAV_COL:
                    f_col = 0
                    f_row += 1
            
            fav_scroll.setWidget(fav_container)
            self.selection_lay.addWidget(fav_scroll, 4, 0, 1, 3)
            self.selection_lay.setRowStretch(4, 1) 
            
        else:
            lbl_no_fav = QLabel("Henüz Hızlı Erişim ürünü yok.\nÜrün üzerindeki (⋮) menüden ekleyebilirsiniz.")
            lbl_no_fav.setStyleSheet("color: #666; margin: 20px; font-style: italic; font-size: 13px;")
            lbl_no_fav.setAlignment(Qt.AlignCenter)
            self.selection_lay.addWidget(lbl_no_fav, 4, 0, 1, 3)
            
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
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
                card.setFixedSize(135, 170)
                
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
        
        text = f"Ciro: {daily:.2f} ₺" if self.ciro_visible else "💰"
        
        self.lbl_ciro.setText(text)
        
        self.lbl_ciro.repaint()
        QApplication.processEvents()

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
        row = -1
        
        # 1. Ürün Zaten Var mı Kontrolü
        found_row = -1
        for r in range(table.rowCount()):
            item = table.item(r, 0)
            if item and item.text() == name:
                found_row = r
                break
        
        # --- DURUM A: ÜRÜN VARSA (Adet Artır) ---
        if found_row != -1:
            row = found_row
            qty_item = table.item(row, 2)
            try:
                cur_qty = int(qty_item.text())
            except:
                cur_qty = 1
            
            table.blockSignals(True)
            qty_item.setText(str(cur_qty + 1))
            table.blockSignals(False)

        # --- DURUM B: ÜRÜN YOKSA (Yeni Satır Ekle) ---
        else:
            row = table.rowCount()
            table.insertRow(row)
            
            font_main = QFont("Segoe UI", 16, QFont.Bold)
            font_qty = QFont("Segoe UI", 18, QFont.Bold)
            
            # --- İSİM (DÜZENLENEMEZ - ÇÖZÜM BURADA) ---
            it_name = QTableWidgetItem(str(name))
            it_name.setFont(font_main)
            it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
            table.setItem(row, 0, it_name)
            
            # --- FİYAT (DÜZENLENEMEZ) ---
            it_price = QTableWidgetItem(f"{float(price):.2f}")
            it_price.setTextAlignment(Qt.AlignCenter)
            it_price.setFont(font_main)
            it_price.setForeground(QColor("#0a84ff"))
            it_price.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) 
            table.setItem(row, 1, it_price)
            
            # --- ADET (TEK DÜZENLENEBİLİR ALAN) ---
            it_qty = QTableWidgetItem("1")
            it_qty.setTextAlignment(Qt.AlignCenter)
            it_qty.setForeground(QColor("#30d158"))
            it_qty.setFont(font_qty)
            it_qty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 2, it_qty)
            
            # --- SİL BUTONU ---
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(2, 2, 2, 2) 
            layout.setAlignment(Qt.AlignCenter)
            
            btn = QPushButton("Sil 🗑️")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(80, 30)
            btn.setStyleSheet("""
                QPushButton { 
                    background-color: rgba(255, 69, 58, 0.1); 
                    color: #ff453a; 
                    font-weight: bold; 
                    border: 1px solid #ff453a; 
                    border-radius: 8px; 
                }
                QPushButton:hover { 
                    background-color: #ff453a; 
                    color: white; 
                }
            """)            
            # YENİ SİLME BAĞLANTISI (Lambda yerine direkt fonksiyon)
            btn.clicked.connect(self.smart_delete_row) 
            
            layout.addWidget(btn)
            table.setCellWidget(row, 3, container)

        # --- ODAKLANMA BÖLÜMÜ ---
        # 1. Satırı Seç
        table.selectRow(row)
        self.selected_row = row
        
        # 2. Odağı ADET hücresine (Sütun 2) ver
        table.setCurrentCell(row, 2)
        table.setFocus()
        
        # 3. Hücreyi düzenleme moduna al (İmleç yanıp sönsün)
        table.editItem(table.item(row, 2)) 

        self.recalc_active_cart_total()
        
        # AI Kontrolü
        suggestion = None
        try:
            names = [table.item(r, 0).text() for r in range(table.rowCount()) if table.item(r, 0)]
            suggestion = self.ai.recommend_product(names)
        except: pass

        if suggestion:
            self.search_bar.setPlaceholderText(f"💡 ÖNERİ: '{suggestion}'")
            self.search_bar.setStyleSheet("QLineEdit { background: #2a1a1a; color: #ffcc00; border: 1px solid #ffcc00; }")
        else:
            self.search_bar.setPlaceholderText("🔍 Ürün Ara...")
            self.search_bar.setStyleSheet("QLineEdit { background: #252525; color: white; border: 1px solid #444; }")

    def smart_delete_row(self):
        btn_widget = self.sender() # Tıklanan butonu al
        if not btn_widget: return

        table = self.get_active_table()
        
        # Butonun ekran üzerindeki pozisyonunu bul
        # Bu pozisyonun tablodaki hangi satıra denk geldiğini hesapla
        index = table.indexAt(btn_widget.parent().pos())
        
        if index.isValid():
            row = index.row()
            table.removeRow(row)
            self.recalc_active_cart_total()
            self.selected_row = -1
            
            # Tablo boşaldıysa temizlik yap
            if table.rowCount() == 0:
                self.lbl_total.setText("0.00 ₺")
                self.cart_data = []
                if hasattr(self, 'update_change_list'):
                    self.update_change_list()
                self.search_bar.setFocus()
            else:
                # Hala ürün varsa sonuncuyu seç (Odak kaybolmasın)
                next_row = min(row, table.rowCount() - 1)
                table.selectRow(next_row)
                table.setCurrentCell(next_row, 2)
                table.setFocus()
                
    def on_cart_item_changed(self, item):
        self.recalc_active_cart_total()

    def recalc_active_cart_total(self):
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
        if self.search_bar.hasFocus():
            if e.key() == Qt.Key_Escape:
                self.search_bar.clearFocus()
                if self.table: self.table.setFocus()
            return 

        # 2. SPACE Tuşu -> Nakit Ödeme
        if e.key() == Qt.Key_Space:
            if self.cart_data: 
                self.finish_sale("Nakit")
            return

        # 3. DELETE / BACKSPACE -> Sepetten Sil
        # Artık aramaya odaklanmaz, direkt siler.
        if e.key() == Qt.Key_Delete or e.key() == Qt.Key_Backspace:
            table = self.get_active_table()
            current_row = table.currentRow()
            if current_row >= 0:
                table.removeRow(current_row)
                self.recalc_active_cart_total()
                self.selected_row = -1
            return

        # 4. Rakam Tuşları -> Adet Değiştir (Numpad gibi)
        if e.text().isdigit() and self.table and self.table.hasFocus():
             self.numpad_action(e.text())
             return

        # 5. Harf Tuşları -> Otomatik Arama Çubuğuna Git
        # Sadece harf ise aramaya git (barkod okuyucu veya klavye)
        if e.text().isalnum() and not e.text().isdigit():
            self.search_bar.setFocus()
            self.search_bar.setText(self.search_bar.text() + e.text())


    def get_current_cart(self):
        return self.cart_tabs.currentWidget()

    def update_total_display(self, total):
        if self.sender() == self.get_current_cart():
            self.lbl_total.setText(f"{total:.2f} ₺")
            self.update_change_list()
    
    def on_tab_changed(self):
        cart = self.get_current_cart()
        if cart:
            cart.recalc_total() 

    def numpad_action(self, key):
        cart = self.get_current_cart()
        if not cart: return
        row = cart.currentRow() 
        
        if row < 0: return # Seçili satır yok
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

    # ============================================================
    # 1. NAKİT ÖDEME (Doğrudan Fiş Keser)
    # ============================================================
    def finish_sale(self, method="Nakit"):
        """NAKİT SATIŞ: POS cihazına 'CASH' bilgisi gider, direkt fiş çıkar."""
        if not self.cart_data:
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
        
        # Toplam Tutar
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        
        # Görsel Geri Bildirim
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.set_payment_processing(True, "NAKİT") 
        QApplication.processEvents()
        
        try:
            # --- YENİ SİSTEM ---
            # Aracı servisi çağırıyoruz
            service = POSService()
            # is_cash=True dediğimiz için XML'e 'CASH' yazılacak
            result = service.process_sale(total, is_cash=True)
            # -------------------

            QApplication.restoreOverrideCursor()
            self.set_payment_processing(False)
            
            if result['success']:
                # BAŞARILI: Veritabanına kaydet
                self.db.record_sale(self.cart_data, total, "Nakit")
                
                # Ekranı Temizle
                self.get_active_table().setRowCount(0)
                self.cart_data = []
                self.recalc_active_cart_total()
                self.update_ciro()
                
                # Bilgi ver (Nakit olduğu için kısa mesaj yeterli)
                # İstersen bu mesajı kaldırabilirsin, zaten cihazdan fiş çıkacak.
                # QMessageBox.information(self, "Tamamlandı", "Nakit Fiş Kesildi.")
                
            else:
                # BAŞARISIZ
                err_msg = result.get('msg', 'Bilinmeyen Hata')
                QMessageBox.critical(self, "Hata", f"Yazar Kasa Hatası:\n{err_msg}")

        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.set_payment_processing(False)
            QMessageBox.critical(self, "Sistem Hatası", str(e))

    # ============================================================
    # 2. KREDİ KARTI ÖDEME (Onay Bekler)
    # ============================================================
    def card_payment(self):
        """KARTLI SATIŞ: POS cihazı kart ister ve onay bekler."""
        if not self.cart_data:
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
        
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        
        # Görsel Geri Bildirim (Bekleme Modu)
        self.set_payment_processing(True, "KART")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents() 
        
        try:
            # --- YENİ SİSTEM ---
            service = POSService()
            # is_cash=False dediğimiz için XML'e 'CREDIT_CARD' yazılacak
            # Bu işlem müşteri şifreyi girene kadar programı bekletir (Timeout süresince)
            result = service.process_sale(total, is_cash=False)
            # -------------------
            
            QApplication.restoreOverrideCursor()
            self.set_payment_processing(False)
            
            if result['success']:
                # ONAYLANDI -> Veritabanına kaydet
                self.db.record_sale(self.cart_data, total, "Kredi Kartı")
                
                # Başarılı mesajı ve Onay Kodu
                auth_code = result.get('auth_code', '---')
                msg = f"✅ Ödeme Onaylandı!\nOnay Kodu: {auth_code}"
                QMessageBox.information(self, "Başarılı", msg)
                
                # Ekranı Temizle
                self.get_active_table().setRowCount(0)
                self.cart_data = []
                self.recalc_active_cart_total()
                self.update_ciro()
            else:
                # REDDEDİLDİ
                err_msg = result.get('msg', 'İşlem Reddedildi')
                QMessageBox.warning(self, "Başarısız", f"❌ Kart İşlemi Tamamlanamadı:\n{err_msg}")
                
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.set_payment_processing(False)
            QMessageBox.critical(self, "Sistem Hatası", str(e))

    def on_pos_result(self, result):
        """POS yanıtı geldiğinde çalışır"""
        
        self.set_payment_processing(False)
        
        if result['success']:
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
        print("AI Kontrol Tetiklendi...") # Debug çıktısı
        
        # Dosya yolunu al
        csv_yolu = os.path.join(get_app_path(), "urunler_klasoru", "urunler.csv")
        
        if hasattr(self, 'ai_worker') and self.ai_worker.isRunning():
            print("AI zaten çalışıyor, bu turu atla.")
            return
        self.ai_worker = AIWorker("voidpos.db") 
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
    
    def setup_prod_list(self):
        w = QWidget()
        l = QVBoxLayout(w)
        
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
                    item.setForeground(QColor("#30d158"))
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
        super().__ini__(parent)
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