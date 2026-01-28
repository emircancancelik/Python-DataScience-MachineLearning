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
                               QDoubleSpinBox, QFileDialog,QStackedWidget)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QCursor, QPixmap, QColor

# =====================================================
# AYARLAR
# =====================================================
TEST_MODE = False  
POS_IP = "192.168.1.157"
POS_PORT = 6420
SHOP_NAME = "BAYİÇ ALCOHOL CENTER"
ADMIN_USER = "admin"
ADMIN_PASS = "123456"

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


class IngenicoMove5000F:
    """
    Ingenico Move 5000F POS Terminal
    GÖSB Protokolü ile TCP/IP Bağlantısı
    """
    ACK = 0x06
    NAK = 0x15
    STX = 0x02
    ETX = 0x03
    FS = 0x1C
    
    def __init__(self, ip: str = "192.168.1.157", port: int = 6420):
        self.ip = ip
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.logger = logging.getLogger("IngenicoMove5000F")
        
        self.connection_timeout = 10
        self.transaction_timeout = 120
        
        self.terminal_id = None
        self.merchant_id = None
    
    def connect(self) -> bool:
        """POS terminaline bağlan"""
        try:
            self.logger.info(f"POS'a bağlanılıyor: {self.ip}:{self.port}")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.connection_timeout)
            self.socket.connect((self.ip, self.port))
            
            self.logger.info("✅ POS bağlantısı başarılı")
            self._get_terminal_info()
            
            return True
            
        except socket.timeout:
            self.logger.error("❌ Bağlantı zaman aşımı")
            return False
        except ConnectionRefusedError:
            self.logger.error("❌ Bağlantı reddedildi")
            return False
        except Exception as e:
            self.logger.error(f"❌ Bağlantı hatası: {e}")
            return False
    
    def disconnect(self):
        """Bağlantıyı kapat"""
        if self.socket:
            try:
                self.socket.close()
                self.logger.info("POS bağlantısı kapatıldı")
            except:
                pass
            finally:
                self.socket = None
    
    def _get_terminal_info(self) -> bool:
        """Terminal bilgilerini al"""
        try:
            message = self._build_message(GOSBMessageType.STATUS, {})
            self._send_message(message)
            response = self._receive_message(timeout=10)
            
            if response:
                parsed = self._parse_response(response)
                self.terminal_id = parsed.get('terminal_id')
                self.merchant_id = parsed.get('merchant_id')
                self.logger.info(f"Terminal ID: {self.terminal_id}")
                return True
            return False
        except:
            return False
    
    def _build_message(self, msg_type: GOSBMessageType, fields: dict) -> bytes:
        """GÖSB mesajı oluştur"""
        payload = bytes([msg_type.value])
        
        for field_id, value in fields.items():
            if value is not None:
                field_data = str(value).encode('ascii')
                field_length = len(field_data)
                
                payload += struct.pack('!H', field_id)
                payload += struct.pack('!I', field_length)[1:]
                payload += field_data
        
        length = len(payload)
        
        frame = bytes([self.STX])
        frame += struct.pack('!H', length)
        frame += payload
        frame += bytes([self.ETX])
        
        lrc = 0
        for byte in frame[1:]:
            lrc ^= byte
        
        frame += bytes([lrc])
        
        return frame
    
    def _send_message(self, message: bytes):
        """Mesaj gönder"""
        if not self.socket:
            raise Exception("POS bağlı değil")
        
        self.logger.debug(f"Gönderilen: {message.hex()}")
        self.socket.sendall(message)
    
    def _receive_message(self, timeout: Optional[int] = None) -> Optional[bytes]:
        """Mesaj al - DÜZELTİLMİŞ VE TAM VERSİYON"""
        if not self.socket:
            raise Exception("POS bağlı değil")
        
        old_timeout = self.socket.gettimeout()
        
        try:
            if timeout:
                self.socket.settimeout(timeout)
            
            # 1. STX Oku
            stx = self.socket.recv(1)
            if not stx or stx[0] != self.STX:
                return None
            
            # 2. Uzunluk Oku (2 byte)
            length_bytes = self.socket.recv(2)
            if len(length_bytes) != 2:
                return None
            
            length = struct.unpack('!H', length_bytes)[0]
            
            # 3. Payload Oku
            payload = self.socket.recv(length)
            if len(payload) != length:
                return None
            
            # 4. ETX Oku
            etx = self.socket.recv(1)
            if not etx or etx[0] != self.ETX:
                return None
            
            # 5. LRC Oku
            lrc_received = self.socket.recv(1)
            if not lrc_received:
                return None
            
            # 6. Frame Oluştur ve LRC Doğrula
            frame = stx + length_bytes + payload + etx
            lrc_calculated = 0
            for byte in frame[1:]:
                lrc_calculated ^= byte
            
            if lrc_calculated != lrc_received[0]:
                self.logger.error("LRC hatası!")
                # Hata durumunda NAK gönder
                self.socket.send(bytes([self.NAK])) 
                return None
            
            # Başarılıysa ACK gönder
            self.socket.send(bytes([self.ACK])) 
            
            self.logger.debug(f"Alınan: {frame.hex()}")
            
            return payload
            
        except socket.timeout:
            self.logger.error("Yanıt zaman aşımı")
            return None
        except Exception as e:
            self.logger.error(f"Okuma hatası: {e}")
            return None
        finally:
            if timeout:
                self.socket.settimeout(old_timeout)
    
    def _parse_response(self, payload: bytes) -> dict:
        """GÖSB yanıtını parse et"""
        result = {
            'raw': payload.hex(),
            'message_type': payload[0]
        }
        
        offset = 1
        
        while offset < len(payload):
            if offset + 5 > len(payload):
                break
            
            field_id = struct.unpack('!H', payload[offset:offset+2])[0]
            offset += 2
            
            length_bytes = b'\x00' + payload[offset:offset+3]
            field_length = struct.unpack('!I', length_bytes)[0]
            offset += 3
            
            if offset + field_length > len(payload):
                break
            
            field_data = payload[offset:offset+field_length].decode('ascii', errors='ignore')
            offset += field_length
            
            if field_id == 1:
                result['response_code'] = field_data
            elif field_id == 2:
                result['auth_code'] = field_data
            elif field_id == 3:
                result['terminal_id'] = field_data
            elif field_id == 4:
                result['merchant_id'] = field_data
            elif field_id == 5:
                result['card_number'] = field_data
            elif field_id == 6:
                result['amount'] = field_data
            elif field_id == 7:
                result['stan'] = field_data
            elif field_id == 8:
                result['rrn'] = field_data
        
        return result
    
    def sale(self, amount: float) -> dict:
        """Satış işlemi"""
        tx_id = str(uuid.uuid4())[:8]
        
        self.logger.info(f"🔄 SATIŞ | TX:{tx_id} | {amount:.2f} TL")
        
        if not self.socket:
            if not self.connect():
                return {
                    'success': False,
                    'message': 'POS bağlantı hatası'
                }
        
        try:
            amount_krs = int(amount * 100)
            
            message = self._build_message(
                msg_type=GOSBMessageType.SALE,
                fields={
                    6: amount_krs,
                    12: datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
                    99: tx_id
                }
            )
            
            self.logger.info("📤 Kart bekleniyor...")
            self._send_message(message)
            
            response = self._receive_message(timeout=self.transaction_timeout)
            
            if not response:
                self.logger.error("❌ POS yanıt vermedi!")
                return {
                    'success': False,
                    'message': 'POS yanıt vermedi',
                    'timeout': True
                }
            
            parsed = self._parse_response(response)
            response_code = parsed.get('response_code', 'XX')
            
            if response_code == '00':
                self.logger.info(f"✅ ONAYLANDI | Auth:{parsed.get('auth_code')}")
                
                return {
                    'success': True,
                    'response_code': response_code,
                    'auth_code': parsed.get('auth_code', ''),
                    'card_number': self._mask_card(parsed.get('card_number', '')),
                    'amount': amount,
                    'stan': parsed.get('stan', ''),
                    'rrn': parsed.get('rrn', ''),
                    'message': 'İşlem Onaylandı',
                    'tx_id': tx_id
                }
            else:
                msg = self._get_response_message(response_code)
                self.logger.warning(f"❌ REDDEDİLDİ | {response_code} | {msg}")
                
                return {
                    'success': False,
                    'response_code': response_code,
                    'message': msg,
                    'tx_id': tx_id
                }
        
        except Exception as e:
            self.logger.exception(f"Satış hatası")
            return {
                'success': False,
                'message': f'Hata: {str(e)}'
            }
    
    def _mask_card(self, card_number: str) -> str:
        """Kart maskele"""
        if not card_number or len(card_number) < 10:
            return "****"
        return f"{card_number[:6]}{'*' * (len(card_number) - 10)}{card_number[-4:]}"
    
    def _get_response_message(self, code: str) -> str:
        """Response mesajı"""
        messages = {
            '00': 'İşlem Onaylandı',
            '05': 'İşlem Reddedildi',
            '51': 'Yetersiz Bakiye',
            '54': 'Kartın Süresi Dolmuş',
            '55': 'Hatalı PIN',
            '57': 'İşlem İzni Yok',
            '91': 'Banka Yanıt Vermiyor',
            '96': 'Sistem Hatası'
        }
        return messages.get(code, f'Kod: {code}')


# =====================================================
# POS SERVİSİ
# =====================================================

class POSService:
    def __init__(self):
        self.client = IngenicoMove5000F(POS_IP, POS_PORT)
        self.logger = logging.getLogger("POSService")
    
    def process_sale(self, amount: float) -> dict:
        """Satış işlemi"""
        tx_id = str(uuid.uuid4())[:8]
        state = TxState.INIT
        
        self.logger.info(f"TX START | {tx_id} | {amount:.2f} TL")
        
        try:
            state = TxState.SENT
            result = self.client.sale(amount)
            
            if result['success']:
                state = TxState.APPROVED
                return {
                    'success': True,
                    'rc': result['response_code'],
                    'auth_code': result['auth_code'],
                    'receipt_no': result['rrn'],
                    'state': state.value,
                    'tx_id': tx_id,
                    'card_number': result.get('card_number', '')
                }
            else:
                if result.get('timeout'):
                    state = TxState.TIMEOUT
                    return {
                        'success': False,
                        'msg': 'POS zaman aşımı',
                        'state': state.value,
                        'tx_id': tx_id,
                        'pending': True
                    }
                else:
                    state = TxState.DECLINED
                    return {
                        'success': False,
                        'rc': result.get('response_code', 'XX'),
                        'msg': result['message'],
                        'state': state.value,
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
    finished = Signal(dict)
    
    def __init__(self, amount: float):
        super().__init__()
        self.amount = amount
        self.service = POSService()
    
    def run(self):
        result = self.service.process_sale(self.amount)
        self.finished.emit(result)


#CSS
STYLESHEET = """
    QMainWindow { background-color: #121212; }
    QWidget { font-family: 'Segoe UI', sans-serif; color: #e0e0e0; outline: none; }
    
    /* SCROLLBAR */
    QScrollBar:vertical { background: #252525; width: 8px; margin: 0; border-radius: 4px; }
    QScrollBar::handle:vertical { background: #404040; min-height: 30px; border-radius: 4px; }
    
    /* TABLO (SEPET) - DAHA BÜYÜK VE MODERN */
    QTableWidget { 
        background-color: #1e1e1e; 
        border-radius: 12px; 
        border: none; 
        color: #fff; 
        gridline-color: #303030; 
        font-size: 18px; /* Font büyütüldü */
        padding: 5px; 
    }
    QTableWidget::item { 
        padding: 15px; /* Satır aralığı açıldı */
        border-bottom: 1px solid #303030; 
    }
    QTableWidget::item:selected { 
        background-color: #0a84ff; 
        color: #fff; 
        border-radius: 8px;
    }
    QHeaderView::section { 
        background-color: #1e1e1e; 
        color: #888; 
        border: none; 
        border-bottom: 2px solid #404040; 
        padding: 10px; 
        font-weight: bold; 
        font-size: 14px; 
    }
    
    /* SPLITTER (AYIRAÇ) */
    QSplitter::handle { 
        background-color: #333; 
        height: 4px; /* Tutamaç kalınlaştırıldı */
        margin: 2px;
    }
    QSplitter::handle:hover { 
        background-color: #0a84ff; 
    }

    /* KATEGORİ KUTULARI */
    QPushButton.CatBoxBtn { 
        background-color: #252525; color: #e0e0e0; border: 1px solid #333; 
        border-radius: 12px; font-size: 16px; font-weight: bold; margin: 4px; 
        min-height: 70px; 
    }
    QPushButton.CatBoxBtn:hover { background-color: #333; border: 1px solid #555; }
    QPushButton.CatBoxBtn:pressed { background-color: #0a84ff; color: white; border: 1px solid #0a84ff; }

    /* CİRO KUTUSU (TIKLANABİLİR) */
    QLabel#CiroBox {
        background-color: #252525; color: #30d158; border: 1px solid #333;
        border-radius: 16px; font-weight: bold; font-size: 18px; padding: 8px 15px;
    }
    QLabel#CiroBox:hover { 
        border: 1px solid #30d158; cursor: pointer;
    }

    /* ÜST BAR BUTONLARI */
    QPushButton.TopBarBtn { background-color: #252525; color: #e0e0e0; border: 1px solid #333; border-radius: 16px; font-weight: bold; font-size: 13px; padding: 0 15px; height: 45px; }    
    /* BAŞLIKLAR */
    QLabel#SectionTitle { color: #808080; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin: 5px; }
    
    /* NUMPAD */
    QWidget#NumpadContainer { background-color: #252525; border-radius: 12px; border: 1px solid #333; }
    QPushButton.NumBtn { background-color: transparent; color: white; font-size: 26px; font-weight: 400; border: 0.5px solid #333; border-radius: 0px; height: 65px; }
    QPushButton.NumBtn:hover { background-color: #353535; }
    QPushButton.NumBtn:pressed { background-color: #0a84ff; color: white; }
    
    /* ÖDEME BUTONLARI */
    QPushButton.PayBtn { border-radius: 12px; font-size: 22px; font-weight: 800; color: white; }

    /* SAĞ PANEL - PARA ÜSTÜ LİSTESİ */
    QLabel.ChangeDenom {
        color: #aaaaaa;
        font-size: 16px;
        font-weight: bold;
        font-family: 'Consolas', 'Courier New', monospace;
    }
    QLabel.ChangeArrow {
        color: #555555;
        font-size: 16px;
        font-weight: bold;
    }
    QLabel.ChangeResult {
        color: #30d158; /* Yeşil Sonuç */
        font-size: 22px;
        font-weight: 900;
        font-family: 'Consolas', 'Courier New', monospace;
    }
    QLabel.ChangeResultError {
        color: #444; /* Sönük */
        font-size: 16px;
        font-style: italic;
        font-family: 'Consolas', 'Courier New', monospace;
    }
    QFrame#ChangeFrame {
        background-color: #202020;
        border-radius: 12px;
        border: 1px solid #333;
    }
"""

# --- VERİTABANI ---
class DatabaseManager:
    def __init__(self, db_name="voidpos.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
        self.db_name = db_name

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

    def import_products_from_csv(self, filename):
        """CSV dosyasından ürünleri günceller"""
        try:
            with open(filename, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    pid = row.get('id')
                    if not pid: continue
                    
                    # Veritabanını güncelle
                    self.cursor.execute("""
                        UPDATE products SET 
                        name=?, cost_price=?, sell_price=?, stock=?, 
                        critical_stock=?, category=?, barcode=?, image_path=?
                        WHERE id=?
                    """, (
                        row['name'], row['cost_price'], row['sell_price'], row['stock'],
                        row['critical_stock'], row['category'], row['barcode'], row['image_path'],
                        pid
                    ))
                    count += 1
                
            self.conn.commit()
            return True, f"{count} ürün güncellendi."
        except Exception as e:
            return False, str(e)
        
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
            self.setFixedSize(95, 120)
            icon_size = 60
            font_sz = 13
            font_p_sz = 14
        else:
            self.setFixedSize(165, 195)
            icon_size = 60
            font_sz = 12
            font_p_sz = 20
        
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background-color: #252525; border-radius: 20px; border: 1px solid {'#ff453a' if stock <= 5 else '#353535'}; }}
            QFrame:hover {{ background-color: #303030; border: 1px solid #0a84ff; }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # --- Üst Bar (Menü Butonu) ---
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch()
        
        self.btn_menu = QPushButton("⋮")
        self.btn_menu.setFixedSize(20, 20)
        self.btn_menu.setStyleSheet("background:transparent; color:#888; font-weight:bold; border:none;")
        self.btn_menu.setCursor(Qt.PointingHandCursor)
        self.btn_menu.clicked.connect(self.show_options_menu)
        top_bar.addWidget(self.btn_menu)
        
        layout.addLayout(top_bar)
        
        # --- İkon ---
        icon_cont = QWidget()
        ic_lay = QVBoxLayout(icon_cont)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        
        # Resim yoksa baş harfi göster
        icon = QLabel(name[0].upper() if name else "?")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(icon_size, icon_size)
        icon.setFont(QFont("Segoe UI", icon_size // 2.5, QFont.Bold))
        icon.setStyleSheet(f"background:#303030; color:#0a84ff; border-radius:{icon_size // 2}px;")
        
        if img_path and os.path.exists(img_path):
            icon.setPixmap(QPixmap(img_path).scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        ic_lay.addWidget(icon, 0, Qt.AlignCenter)
        layout.addWidget(icon_cont)
        
        # --- İsim ve Fiyat ---
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

    # --- Tıklama Olayı (Tek ve Düzgün Hali) ---
    def mousePressEvent(self, e):
        # Eğer tıklanan yer menü butonu ise kartın click eventini çalıştırma
        child = self.childAt(e.pos())
        if child == self.btn_menu:
            return
            
        if e.button() == Qt.LeftButton:
            # Buradaki callback'in parametreleri __init__ içinde gelen yapıya uygun olmalı
            self.cb(self.name_val, self.price_val)
    
    # --- Sağ Tık / Menü Butonu Menüsü ---
    def show_options_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #252525; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #0a84ff; }")
        
        # Hızlı Erişim
        act_fav = menu.addAction("⭐ Hızlı Erişimden Kaldır" if self.fav else "⭐ Hızlı Erişime Ekle")
        act_fav.triggered.connect(self.toggle_fav)
        
        menu.addSeparator()
        
        # Fiyat Değiştir
        act_price = menu.addAction("💰 Fiyat Değiştir")
        act_price.triggered.connect(self.change_price)
        
        # İsim Değiştir (Yarım kalan fonksiyon düzeltildi)
        act_name = menu.addAction("✏️ İsim Değiştir")
        act_name.triggered.connect(self.change_name)

        # Stok İşlemleri
        act_stock = menu.addAction("📦 Stok Sayım/Düzenle")
        act_stock.triggered.connect(self.change_stock)
        
        # Kritik Stok
        act_crit = menu.addAction("⚠️ Kritik Stok Limiti")
        act_crit.triggered.connect(self.change_critical_stock)
        
        # Maliyet
        act_cost = menu.addAction("📉 Maliyet Değiştir")
        act_cost.triggered.connect(self.change_cost)
        
        menu.addSeparator()
        
        # Kategori Taşıma
        cat_menu = menu.addMenu("📂 Kategoriye Taşı")
        cat_menu.setStyleSheet("QMenu { background-color: #252525; color: white; border: 1px solid #444; }")
        
        # DB'den kategorileri çekiyoruz
        categories = self.db.get_all_categories() if hasattr(self.db, 'get_all_categories') else []
        for cat in categories:
            if cat == "Tüm Ürünler": continue
            cat_menu.addAction(cat, lambda c=cat: self.move_to_category(c))
            
        menu.exec(QCursor.pos())

    # --- İşlev Fonksiyonları ---

    def toggle_fav(self):
        self.db.toggle_favorite(self.pid, 0 if self.fav else 1)
        self.update_cb()

    def change_price(self):
        val, ok = QInputDialog.getDouble(self, "Fiyat", "Yeni Satış Fiyatı:", self.price_val, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "sell_price", val)
            self.update_cb()
            
    def change_name(self):
        text, ok = QInputDialog.getText(self, "İsim Değiştir", "Yeni Ürün Adı:", text=self.name_val)
        if ok and text:
            self.db.update_product_field(self.pid, "name", text)
            self.update_cb()

    def change_stock(self):
        val, ok = QInputDialog.getInt(self, "Stok", "Yeni Stok Adedi:", self.stock_val, -1000, 100000, 1)
        if ok:
            self.db.update_product_field(self.pid, "stock", val)
            self.update_cb()

    def change_critical_stock(self):
        # Mevcut kritik stoğu çekmeye çalış, yoksa varsayılan 5
        # Not: DB yapınıza göre get_product_by_id dönüşü değişebilir.
        curr = 5 
        try:
            prod_data = self.db.get_product_by_id(self.pid)
            if prod_data and len(prod_data) > 5:
                curr = prod_data[5] # 5. indexin kritik stok olduğunu varsayıyoruz
        except:
            pass
            
        val, ok = QInputDialog.getInt(self, "Kritik Stok", "Uyarı verilecek stok limiti:", curr, 0, 1000, 1)
        if ok:
            self.db.update_product_field(self.pid, "critical_stock", val)
            self.update_cb()

    def change_cost(self):
        # get_cost fonksiyonu isme göre değil ID'ye göre çalışsa daha güvenli olur ama mevcut yapıyı korudum
        current_cost = 0.0
        if hasattr(self.db, 'get_cost'):
             current_cost = self.db.get_cost(self.name_val)
             
        val, ok = QInputDialog.getDouble(self, "Maliyet", "Yeni Maliyet:", current_cost, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "cost_price", val)
            self.update_cb()

    def move_to_category(self, cat_name):
        self.db.update_product_field(self.pid, "category", cat_name)
        self.update_cb()
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
    def __init__(self, name, click_cb, is_add_button=False, db_manager=None, refresh_cb=None):
        super().__init__()
        self.setFixedSize(150, 100)
        self.setCursor(Qt.PointingHandCursor)
        self.name = name
        self.db = db_manager
        self.refresh_cb = refresh_cb
        self.cb = click_cb
        
        if is_add_button:
            # Ekleme Butonu 
            self.setStyleSheet("""
                QFrame { background-color: rgba(48, 209, 88, 0.1); border-radius: 24px; border: 1px dashed #30d158; }
                QFrame:hover { background-color: rgba(48, 209, 88, 0.2); }
            """)
            lbl_color = "#414e44"
            icon_text = "+"
            font_size = "32px"
        else:
            # Normal Kategori 
            self.setStyleSheet("""
                QFrame { background-color: #252525; border-radius: 24px; border: 1px solid #333; }
                QFrame:hover { background-color: #303030; border: 1px solid #0a84ff; }
            """)
            lbl_color = "#45525e"
            icon_text = name[0].upper() if name else "?"
            font_size = "24px"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(2)

        # --- Üst Bar (Menü Butonu) ---
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        
        # Sadece normal kategorilerde ve "Tüm Ürünler" değilse menü göster
        if not is_add_button and name != "Tüm Ürünler":
            self.btn_menu = QPushButton("⋮")
            self.btn_menu.setFixedSize(20, 20)
            self.btn_menu.setStyleSheet("background:transparent; color:#888; font-weight:bold; border:none;")
            self.btn_menu.setCursor(Qt.PointingHandCursor)
            self.btn_menu.clicked.connect(self.show_options)
            top_bar.addWidget(self.btn_menu)
        
        layout.addLayout(top_bar)

        # --- İçerik (İkon + İsim) ---
        content_lay = QVBoxLayout()
        content_lay.setSpacing(5)
        
        icon_lbl = QLabel(icon_text)
        icon_lbl.setStyleSheet(f"color: {lbl_color}; font-size: {font_size}; font-weight: bold; border:none; background:transparent;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        
        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 600; border: none; background: transparent;")
        
        content_lay.addWidget(icon_lbl)
        content_lay.addWidget(lbl)
        layout.addLayout(content_lay)
        layout.addStretch()

    def mousePressEvent(self, e):
        # Menü butonuna basıldıysa kart tıklamasını engelle
        child = self.childAt(e.pos())
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
            else:
                QMessageBox.warning(self, "Hata", "Bu isimde bir kategori zaten var!")

# --- ANA UYGULAMA ---
class NexusPOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.selected_row = -1
        self.barcode_buffer = ""
        self.ciro_visible = True # Ciro görünürlük durumu
        
        self.init_ui()
        self.setWindowTitle("VoidPOS")
        self.resize(1600, 900)
        self.setStyleSheet(STYLESHEET)
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QHBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        
        # --- 1. SOL PANEL (AYNI) ---
        left_container = QFrame()
        left_container.setFixedWidth(520)
        left_container.setStyleSheet("background:#181818; border-right:1px solid #252525;")
        left_layout = QVBoxLayout(left_container)
        
        # Arama
        search_cont = QWidget()
        search_lay = QHBoxLayout(search_cont)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Ürün Ara...")
        self.search_bar.setFixedHeight(40)
        self.search_bar.setStyleSheet("background:#252525; color:white; border:1px solid #333; border-radius:20px; padding-left:15px;")
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
        center_container.setStyleSheet("background:#1a1a1a; border-right:1px solid #333;")
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
        right_container.setStyleSheet("background:#161616;")
        right_layout = QVBoxLayout(right_container)
        
        self.change_panel = self.create_change_list_panel()
        right_layout.addWidget(self.change_panel, stretch=1)
        
        self.numpad = MergedNumpad(self.numpad_action)
        right_layout.addWidget(self.numpad, stretch=0)
        
        pay_lay = QHBoxLayout()
        btn_cash = QPushButton("NAKİT")
        btn_cash.setProperty("class", "PayBtn")
        btn_cash.setStyleSheet("background-color:#30d158; color:black; height: 80px;")
        btn_cash.clicked.connect(lambda: self.finish_sale("Nakit"))
        
        btn_card = QPushButton("KART")
        btn_card.setProperty("class", "PayBtn")
        btn_card.setStyleSheet("background-color:#0a84ff; color:white; height: 80px;")
        btn_card.clicked.connect(self.card_payment)
        
        pay_lay.addWidget(btn_cash)
        pay_lay.addWidget(btn_card)
        right_layout.addLayout(pay_lay)
        
        main_lay.addWidget(right_container)
        
        self.load_categories_grid()

    # NexusPOS sınıfı içinde:

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
        table.setStyleSheet("""
            QTableWidget { background-color: transparent; border: none; color: #ddd; font-size: 16px; }
            QTableWidget::item { padding: 12px 5px; border-bottom: 1px solid #2a2a2a; } /* Hafif satır çizgisi */
            QTableWidget::item:selected { background-color: #252525; color: #fff; border-radius: 5px; }
            QHeaderView::section { background-color: transparent; color: #666; border: none; border-bottom: 2px solid #333; font-weight: bold; font-size: 13px; }
            QLineEdit { background: #333; color: white; border: 1px solid #0a84ff; border-radius: 5px; }
        """)

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
            
            # ProductCard oluştur
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
        
        # ANA LAYOUT AYARLARI
        self.selection_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.selection_lay.setSpacing(0)
        self.selection_lay.setContentsMargins(0, 0, 0, 0)
        
        self.selection_scroll.setMaximumHeight(16777215)
        self.selection_scroll.setWidgetResizable(True)

        # 1. KATEGORİ BAŞLIĞI
        lbl_cat = QLabel("KATEGORİLER")
        lbl_cat.setStyleSheet("color: #0a84ff; font-weight: 800; font-size: 14px; margin: 10px 0 5px 10px;")
        self.selection_lay.addWidget(lbl_cat, 0, 0, 1, 3)

        # 2. KATEGORİ SCROLL (SABİT YÜKSEKLİK)
        cat_scroll = QScrollArea()
        cat_scroll.setFixedHeight(250)
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cat_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background: #121212; width: 0px; } /* Scrollbar'ı gizledik */
        """)
        
        cat_container = QWidget()
        cat_container.setStyleSheet("background: transparent;")
        cat_grid = QGridLayout(cat_container)
        cat_grid.setContentsMargins(5, 0, 5, 0) 
        cat_grid.setSpacing(10)
        cat_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # KARTLARI DİZME
        categories = self.db.get_all_categories()
        
        def show_all():
            self.load_products_grid("Tüm Ürünler")
            
        all_card = CategoryCard("Tüm Ürünler", lambda x: show_all())
        all_card.setStyleSheet(all_card.styleSheet() + "QFrame { border: 1px dashed #555; }")
        cat_grid.addWidget(all_card, 0, 0)

        c_row = 0
        c_col = 1 
        max_cat_col = 3 

        for cat in categories:
            if cat == "Tüm Ürünler": continue
            # CategoryCard'ı parametrelerle çağırıyoruz
            card = CategoryCard(cat, self.load_products_grid, is_add_button=False, db_manager=self.db, refresh_cb=self.refresh_ui)
            cat_grid.addWidget(card, c_row, c_col)
            
            c_col += 1
            if c_col >= max_cat_col:
                c_col = 0
                c_row += 1
        
        # (+) Yeni Kategori Butonu
        def trigger_add_cat(_):
            self.add_category()
            
        add_card = CategoryCard("Yeni Kategori", trigger_add_cat, is_add_button=True)
        cat_grid.addWidget(add_card, c_row, c_col)

        cat_scroll.setWidget(cat_container)
        self.selection_lay.addWidget(cat_scroll, 1, 0, 1, 3)

        # 3. ARA ÇİZGİ
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333; margin: 15px 0;")
        self.selection_lay.addWidget(line, 2, 0, 1, 3)

        # 4. HIZLI ERİŞİM
        lbl_fav = QLabel("HIZLI ERİŞİM")
        lbl_fav.setStyleSheet("color: #ffcc00; font-weight: 800; font-size: 14px; margin-left: 10px;")
        self.selection_lay.addWidget(lbl_fav, 3, 0, 1, 3)

        fav_container = QWidget()
        fav_grid = QGridLayout(fav_container)
        fav_grid.setContentsMargins(5, 5, 5, 5)
        fav_grid.setSpacing(10)
        fav_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        favorites = self.db.get_favorites()
        if favorites:
            f_row = 0
            f_col = 0
            max_fav_col = 4 
            
            for pid, name, price, img, fav, stock in favorites:
                card = ProductCard(pid, name, price, img, fav, stock, self.add_to_cart, self.refresh_ui, self.db, is_mini=True)
                card.setFixedSize(120, 150)
                fav_grid.addWidget(card, f_row, f_col)
                
                f_col += 1
                if f_col >= max_fav_col:
                    f_col = 0
                    f_row += 1
            
            self.selection_lay.addWidget(fav_container, 4, 0, 1, 3)
        else:
            lbl_empty = QLabel("Henüz favori ürün yok.")
            lbl_empty.setStyleSheet("color: #555; font-style: italic; margin-left: 10px;")
            self.selection_lay.addWidget(lbl_empty, 4, 0, 1, 3)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.selection_lay.addWidget(spacer, 5, 0)
        self.selection_lay.setRowStretch(5, 1)

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
        
        found_row = -1
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.text() == name:
                found_row = row
                break
        
        if found_row != -1:
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
            row = table.rowCount()
            table.insertRow(row)
            
            # Ürün Adı (Çizgisiz, sade)
            it_name = QTableWidgetItem(str(name))
            it_name.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 0, it_name)
            
            # Fiyat (Bunu belirgin yapıyoruz)
            it_price = QTableWidgetItem(f"{float(price):.2f}")
            it_price.setTextAlignment(Qt.AlignCenter)
            # Fiyatı düzenlenebilir yapıyoruz
            it_price.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 1, it_price)
            
            # Adet
            it_qty = QTableWidgetItem("1")
            it_qty.setTextAlignment(Qt.AlignCenter)
            it_qty.setForeground(QColor("#30d158"))
            it_qty.setFont(QFont("Segoe UI", 14, QFont.Bold))
            it_qty.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            table.setItem(row, 2, it_qty)
            
            # Sil Butonu (Sadeleştirildi)
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


    def card_payment(self):
        if not self.cart_data: 
            QMessageBox.warning(self, "Uyarı", "Sepet boş!")
            return
            
        # POS bağlantı testi
        test_pos = IngenicoMove5000F(POS_IP, POS_PORT)
        if not test_pos.connect():
            reply = QMessageBox.question(
                self, 
                "POS Bağlantı Hatası", 
                "POS cihazına bağlanılamadı!\n\nNakit ödeme ile devam etmek ister misiniz?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.finish_sale("Nakit")
            return
        test_pos.disconnect()
    
    # Bağlantı başarılı, işleme devam et
        self.pd = QProgressDialog(
            "🔄 POS'a Bağlanılıyor...\n\n⏳ Lütfen Kartı Okutunuz", 
            "İptal", 0, 0, self
        )
        self.pd.setWindowModality(Qt.WindowModal)
        self.pd.setWindowTitle("POS İşlemi")
        self.pd.setMinimumDuration(0)
        self.pd.show()
        
        total = sum([x['price'] * x['qty'] for x in self.cart_data])
        self.worker = PaymentWorker(total)
        self.worker.finished.connect(self.on_pos_result)
        self.worker.start()
    def add_customer_tab(self, name):
        tab = CustomerCartTab()
        tab.totalChanged.connect(self.update_total_display)
        self.cart_tabs.addTab(tab, name)

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
        cart = self.get_current_cart()
        if not cart or not cart.cart_data: return
        
        total = sum([x['price'] * x['qty'] for x in cart.cart_data])
        
        try:
            # Satışı kaydet
            alerts = self.db.record_sale(cart.cart_data, total, method)
            if alerts: QMessageBox.warning(self, "Stok Uyarısı", "\n".join(alerts))
            
            # Sepeti Temizle (Satırları sil)
            cart.table.setRowCount(0)
            cart.recalc_total()
            
            self.update_ciro()
            QMessageBox.information(self, "Başarılı", f"{method} satışı tamamlandı!")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def on_pos_result(self, result):
       self.pd.close()
       if result.get('state') == 'APPROVED':
           auth = result.get('auth_code', '')
           rrn = result.get('receipt_no', '')
           QMessageBox.information(self, "✅ Ödeme Onaylandı", f"İşlem başarılı!\nAuth:{auth}\nRRN:{rrn}")
           self.finish_sale("Kredi Kartı")
       elif result.get('pending'):
           QMessageBox.warning(self, "⚠️ İşlem Beklemede", "POS yanıt vermedi. İşlem askıya alındı.")
           self.mark_pending(result)
       else:
           QMessageBox.critical(self, "❌ POS Hatası", result.get('msg', 'Bilinmeyen Hata'))

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
#yönetim paneli
# ==========================================
# YÖNETİM PANELİ
# ==========================================
class AdminDialog(QDialog):
    # AdminDialog sınıfının __init__ metodunu şu şekilde sadeleştirin:
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Yönetim Paneli")
        self.resize(1200, 800) # Biraz daha genişletelim
        self.setStyleSheet("background:#1a1a1a; color:white;")
        
        layout = QVBoxLayout(self)
        
        # Sekmeler
        self.tabs = QTabWidget()
        # Sekme değişince veriyi yükle diyeceğiz
        self.tabs.currentChanged.connect(self.on_tab_change) 
        layout.addWidget(self.tabs)
        
        self.editing_pid = None
        self.filter_mode = 'day'
        self.last_tab_index = 0
        
        # ARAYÜZLERİ KURUYORUZ AMA VERİLERİ HENÜZ YÜKLEMİYORUZ!
        self.setup_finances()             # Tab 0
        self.setup_sales_history()        # Tab 1
        self.setup_prod_list()            # Tab 2
        self.setup_add_prod()             # Tab 3
        self.setup_stock_tracking()       # Tab 4
        self.setup_pending_transactions() # Tab 5
        self.setup_bulk_operations()      # Tab 6
        self.load_finance_data()

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
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #ff9f0a; color: black; font-weight: bold; font-size: 16px; border-radius: 10px; }
            QPushButton:hover { background-color: #e08e0b; }
        """)
        
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
        # Dosya açma penceresi aç
        path, _ = QFileDialog.getOpenFileName(self, "CSV Dosyası Seç", "", "CSV Dosyaları (*.csv)")
        if path:
            reply = QMessageBox.question(self, "Onay", "Veritabanı bu dosyadan güncellenecek.\nBu işlem geri alınamaz!\nDevam edilsin mi?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                success, msg = self.db.import_products_from_csv(path)
                if success:
                    QMessageBox.information(self, "Başarılı", msg)
                    # Listeyi yenile ki değişiklikleri görelim
                    if hasattr(self, 'load_table_data'):
                        self.load_table_data() 
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
        
        h = QHBoxLayout()
        self.cmb_filter = QComboBox()
        self.cmb_filter.addItems(["Tüm Ürünler"] + self.db.get_all_categories())
        self.cmb_filter.setStyleSheet("padding:8px; background:#252525; border:1px solid #404040; color:white;")
        self.cmb_filter.currentTextChanged.connect(self.load_table_data)
        
        h.addWidget(QLabel("Kategori:"))
        h.addWidget(self.cmb_filter)
        h.addStretch()
        l.addLayout(h)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7) # ID, AD, FİYAT, STOK, BARKOD, KRİTİK, SİL
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setHorizontalHeaderLabels(["ID", "AD", "FİYAT", "STOK", "BARKOD", "KRİTİK", "İŞLEM"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed) # Sil butonu sabit
        self.table.setColumnWidth(6, 100)
        self.table.setStyleSheet("""
            QTableWidget { background:#252525; border:none; gridline-color:#333; color: white; font-size:14px; }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background:#0a84ff; }
            QLineEdit { background: #333; color: white; border: 1px solid #0a84ff; }
        """)
        
        # --- Yerinde Düzenleme Sinyali ---
        self.table.itemChanged.connect(self.on_prod_cell_changed)
        
        l.addWidget(self.table)
        l.addWidget(QLabel("* Hücrelere çift tıklayarak düzenleyebilirsiniz. 'Sil' butonu kalıcı olarak siler."))
        self.tabs.addTab(w, "Ürün Listesi")
        self.load_table_data()

    def load_table_data(self):
        cat = self.cmb_filter.currentText()
        if cat != "Tüm Ürünler":
            q = "SELECT id, name, sell_price, stock, barcode, critical_stock FROM products WHERE category=?"
            data = self.db.cursor.execute(q, (cat,)).fetchall()
        else:
            q = "SELECT id, name, sell_price, stock, barcode, critical_stock FROM products"
            data = self.db.cursor.execute(q).fetchall()
            
        self.table.blockSignals(True) # Yüklerken sinyalleri kapat (döngüye girmesin)
        self.table.setRowCount(0)
        
        for r_idx, row in enumerate(data):
            self.table.insertRow(r_idx)
            
            # ID (Düzenlenemez)
            item_id = QTableWidgetItem(str(row[0]))
            item_id.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(r_idx, 0, item_id)
            
            # Diğer kolonlar (Düzenlenebilir)
            for c_idx, val in enumerate(row[1:], 1): # 1'den başla çünkü ID'yi koyduk
                item = QTableWidgetItem(str(val if val is not None else ""))
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.table.setItem(r_idx, c_idx, item)
            
            # Sil Butonu
            btn_del = QPushButton("SİL")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("background-color: #ff453a; color: white; font-weight: bold; border-radius: 4px;")
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

    # --- 6. BEKLEYEN İŞLEMLER (DÜZELTİLDİ VE EKLENDİ) ---
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
    
    # macOS için sistem fontunu kullanalım
    font = QFont(".AppleSystemUIFont", 13) 
    # Veya manuel olarak: font = QFont("Helvetica Neue", 13)
    
    app.setFont(font)    
    window = NexusPOS()
    window.show()
    sys.exit(app.exec())