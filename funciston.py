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
                               QDoubleSpinBox)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QCursor, QPixmap, QColor

# =====================================================
# AYARLAR
# =====================================================
TEST_MODE = False  # ✅ GERÇEK POS MODU
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
        border-radius: 8px; font-weight: bold; font-size: 18px; padding: 0 15px; 
    }
    QLabel#CiroBox:hover { 
        border: 1px solid #30d158; cursor: pointer;
    }

    /* ÜST BAR BUTONLARI */
    QPushButton.TopBarBtn { background-color: #252525; color: #e0e0e0; border: 1px solid #333; border-radius: 8px; font-weight: bold; font-size: 13px; padding: 0 15px; height: 45px; }
    
    /* BAŞLIKLAR */
    QLabel#SectionTitle { color: #808080; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; margin: 5px; }
    
    /* NUMPAD */
    QWidget#NumpadContainer { background-color: #252525; border-radius: 12px; border: 1px solid #333; }
    QPushButton.NumBtn { background-color: transparent; color: white; font-size: 26px; font-weight: 400; border: 0.5px solid #333; border-radius: 0px; height: 65px; }
    QPushButton.NumBtn:hover { background-color: #353535; }
    QPushButton.NumBtn:pressed { background-color: #0a84ff; color: white; }
    
    /* ÖDEME BUTONLARI */
    QPushButton.PayBtn { border-radius: 12px; font-size: 22px; font-weight: 800; color: white; }
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
        
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Tüm Ürünler', 0)")
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Sigara', 1)")
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Viski', 2)")
        self.cursor.execute("INSERT OR IGNORE INTO categories (name, sort_order) VALUES ('Rakı', 3)")
        
        self.conn.commit()
    
    def get_all_categories(self):
        self.cursor.execute("SELECT name FROM categories ORDER BY sort_order ASC")
        return [r[0] for r in self.cursor.fetchall()]
    
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
        
        if is_mini:
            self.setFixedSize(95, 120)
            icon_size = 60
            font_sz = 15
            font_p_sz = 15
        else:
            self.setFixedSize(140, 195)
            icon_size = 60
            font_sz = 12
            font_p_sz = 20
        
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background-color: #252525; border-radius: 14px; border: 1px solid {'#ff453a' if stock <= 5 else '#353535'}; }}
            QFrame:hover {{ background-color: #303030; border: 1px solid #0a84ff; }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addStretch()
        
        if not is_mini:
            self.btn_menu = QPushButton("⋮")
            self.btn_menu.setFixedSize(20, 20)
            self.btn_menu.setProperty("class", "CardMenuBtn")
            self.btn_menu.setCursor(Qt.PointingHandCursor)
            self.btn_menu.clicked.connect(self.show_options_menu)
            top_bar.addWidget(self.btn_menu)
        
        layout.addLayout(top_bar)
        
        icon_cont = QWidget()
        ic_lay = QVBoxLayout(icon_cont)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        icon = QLabel(name[0].upper() if name else "?")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(icon_size, icon_size)
        icon.setFont(QFont("Segoe UI", icon_size // 2.5, QFont.Bold))
        icon.setStyleSheet(f"background:#303030; color:#0a84ff; border-radius:{icon_size // 2}px;")
        
        if img_path and os.path.exists(img_path):
            icon.setPixmap(QPixmap(img_path).scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        ic_lay.addWidget(icon, 0, Qt.AlignCenter)
        layout.addWidget(icon_cont)
        
        name_lbl = QLabel(name)
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(f"color:#e0e0e0; font-weight:600; font-size:{font_sz}px; border:none; background-color: #252525;")
        layout.addWidget(name_lbl)
        
        price_lbl = QLabel(f"{price:.2f} ₺")
        price_lbl.setAlignment(Qt.AlignCenter)
        price_lbl.setStyleSheet(f"color: #30d158; font-weight: 800; font-size: {font_p_sz}px; background-color: rgba(48, 209, 88, 0.1); border-radius: 6px; padding: 2px 5px;")
        layout.addWidget(price_lbl)
        
        if not is_mini:
            stock_lbl = QLabel(f"Stok: {stock}")
            stock_lbl.setAlignment(Qt.AlignCenter)
            stock_lbl.setStyleSheet("color: #888; font-size: 11px; margin-top: 2px; background-color: #252525;")
            layout.addWidget(stock_lbl)
        
        layout.addStretch()
    
    def mousePressEvent(self, e):
        child = self.childAt(e.pos())
        if child != getattr(self, "btn_menu", None):
            if e.button() == Qt.LeftButton:
                self.cb(self.name_val, self.price_val)
    
    def show_options_menu(self):
        menu = QMenu(self)
        act_fav = menu.addAction("Hızlı Erişimden Kaldır" if self.fav else "Hızlı Erişime Ekle")
        act_fav.triggered.connect(lambda: self.toggle_fav())
        menu.addSeparator()
        act_price = menu.addAction("Fiyat Değiştir")
        act_price.triggered.connect(self.change_price)
        act_stock = menu.addAction("Stok Sayım/Düzenle")
        act_stock.triggered.connect(self.change_stock)
        act_cost = menu.addAction("Maliyet Değiştir")
        act_cost.triggered.connect(self.change_cost)
        menu.addSeparator()
        cat_menu = menu.addMenu("Kategoriye Taşı")
        for cat in self.db.get_all_categories():
            if cat == "Tüm Ürünler":
                continue
            cat_menu.addAction(cat, lambda c=cat: self.move_to_category(c))
        menu.exec(QCursor.pos())
    
    def toggle_fav(self):
        self.db.toggle_favorite(self.pid, 0 if self.fav else 1)
        self.update_cb()
    
    def change_price(self):
        val, ok = QInputDialog.getDouble(self, "Fiyat", "Yeni Satış Fiyatı:", self.price_val, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "sell_price", val)
            self.update_cb()
    
    def change_stock(self):
        val, ok = QInputDialog.getInt(self, "Stok", "Yeni Stok Adedi:", self.stock_val, -1000, 100000, 1)
        if ok:
            self.db.update_product_field(self.pid, "stock", val)
            self.update_cb()
    
    def change_cost(self):
        current_cost = self.db.get_cost(self.name_val)
        val, ok = QInputDialog.getDouble(self, "Maliyet", "Yeni Maliyet:", current_cost, 0, 100000, 2)
        if ok:
            self.db.update_product_field(self.pid, "cost_price", val)
            self.update_cb()
    
    def move_to_category(self, cat_name):
        self.db.update_product_field(self.pid, "category", cat_name)
        self.update_cb()
        QMessageBox.information(self, "Taşındı", f"Ürün '{cat_name}' kategorisine taşındı.")


class CategoryCard(QFrame):
    def __init__(self, name, click_cb):
        super().__init__()
        self.setFixedSize(140, 140)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame { background-color: #252525; border-radius: 16px; border: 1px solid #353535; }
            QFrame:hover { background-color: #303030; border: 1px solid #0a84ff; }
        """)
        l = QVBoxLayout(self)
        l.setAlignment(Qt.AlignCenter)
        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: white; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        l.addWidget(lbl)
        self.mousePressEvent = lambda e: click_cb(name)


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
            btn.setFixedHeight(50)
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
    def __init__(self, name, click_cb):
        super().__init__()
        self.setFixedSize(130, 100) # Kutucuk boyutu
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame { 
                background-color: #333; 
                border-radius: 12px; 
                border: 1px solid #444; 
            }
            QFrame:hover { 
                background-color: #404040; 
                border: 1px solid #0a84ff; 
            }
        """)
        
        l = QVBoxLayout(self)
        l.setSpacing(5)
        l.setAlignment(Qt.AlignCenter)
        
        # İkon veya Harf
        icon_lbl = QLabel(name[0].upper())
        icon_lbl.setStyleSheet("color: #0a84ff; font-size: 24px; font-weight: bold; border:none; background:transparent;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        
        # İsim
        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: white; font-size: 14px; font-weight: 600; border: none; background: transparent;")
        
        l.addWidget(icon_lbl)
        l.addWidget(lbl)
        
        self.mousePressEvent = lambda e: click_cb(name)

# --- ANA UYGULAMA ---
class NexusPOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.cart_data = []
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
        
        # ANA LAYOUT
        main_lay = QHBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        
        # =================================================
        # 1. SOL PANEL (ARAMA + KATEGORİLER/ÜRÜNLER)
        # =================================================
        left_container = QFrame()
        left_container.setFixedWidth(550) # Izgara için genişlettik
        left_container.setStyleSheet("background:#181818; border-right:1px solid #252525;")
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)

        # --- ARAMA KUTUSU ---
        search_cont = QWidget()
        search_lay = QHBoxLayout(search_cont)
        search_lay.setContentsMargins(0,0,0,0)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Ürün Ara (İsim veya Barkod)...")
        self.search_bar.setFixedHeight(50)
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: #252525;
                color: white;
                border: 1px solid #333;
                border-radius: 10px;
                padding-left: 15px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border: 1px solid #0a84ff;
                background-color: #2a2a2a;
            }
        """)
        self.search_bar.textChanged.connect(self.on_search_changed)
        
        # Sanal klavye açılmaması için focus policy ayarı (opsiyonel)
        # self.search_bar.setFocusPolicy(Qt.ClickFocus) 
        
        search_lay.addWidget(self.search_bar)
        left_layout.addWidget(search_cont)

        # --- DİNAMİK ALAN (Kategoriler veya Ürünler buraya gelecek) ---
        self.selection_scroll = QScrollArea()
        self.selection_scroll.setWidgetResizable(True)
        self.selection_scroll.setStyleSheet("border:none; background:transparent;")
        
        self.selection_cont = QWidget()
        # Grid Layout kullanıyoruz ki kutucuklar yan yana dizilsin
        self.selection_lay = QGridLayout(self.selection_cont) 
        self.selection_lay.setSpacing(10)
        self.selection_lay.setAlignment(Qt.AlignTop)
        
        self.selection_scroll.setWidget(self.selection_cont)
        left_layout.addWidget(self.selection_scroll)
        
        main_lay.addWidget(left_container)

        # =================================================
        # 2. ORTA PANEL: CİRO + SEPET (Aynı Kalıyor)
        # =================================================
        center_container = QFrame()
        center_container.setStyleSheet("background:#1a1a1a; border-right:1px solid #333;")
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(20, 20, 20, 20)
        
        # Üst Bar
        top_bar = QHBoxLayout()
        self.lbl_ciro = ClickableLabel(f"Ciro: {self.db.get_daily_turnover():.2f} ₺")
        self.lbl_ciro.setObjectName("CiroBox")
        self.lbl_ciro.setCursor(Qt.PointingHandCursor)
        self.lbl_ciro.clicked.connect(self.toggle_ciro_visibility)
        top_bar.addWidget(self.lbl_ciro)
        top_bar.addStretch()
        btn_admin = QPushButton("YÖNETİM PANELİ")
        btn_admin.setProperty("class", "TopBarBtn")
        btn_admin.clicked.connect(self.open_admin)
        top_bar.addWidget(btn_admin)
        center_layout.addLayout(top_bar)
        
        # Sepet Tablosu
        center_layout.addSpacing(15)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ÜRÜN", "FİYAT", "ADET"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 80)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.itemClicked.connect(self.row_selected)
        center_layout.addWidget(self.table)
        
        # Toplam Tutar
        self.lbl_total = QLabel("0.00 ₺")
        self.lbl_total.setAlignment(Qt.AlignRight)
        self.lbl_total.setStyleSheet("font-size: 64px; font-weight:900; color:white; margin-top:10px;")
        center_layout.addWidget(self.lbl_total)
        
        main_lay.addWidget(center_container, stretch=1)

        # =================================================
        # 3. SAĞ PANEL (NUMPAD - Aynı Kalıyor)
        # =================================================
        right_container = QFrame()
        right_container.setFixedWidth(360)
        right_container.setStyleSheet("background:#161616;")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(15, 20, 15, 30)
        right_layout.setSpacing(20)
        
        right_layout.addStretch()
        self.numpad = MergedNumpad(self.numpad_action)
        right_layout.addWidget(self.numpad)
        
        pay_lay = QHBoxLayout()
        pay_lay.setSpacing(10)
        btn_cash = QPushButton("NAKİT")
        btn_cash.setFixedHeight(80)
        btn_cash.setProperty("class", "PayBtn")
        btn_cash.setStyleSheet("background-color:#30d158; color:black;")
        btn_cash.clicked.connect(lambda: self.finish_sale("Nakit"))
        
        btn_card = QPushButton("KART")
        btn_card.setFixedHeight(80)
        btn_card.setProperty("class", "PayBtn")
        btn_card.setStyleSheet("background-color:#0a84ff; color:white;")
        btn_card.clicked.connect(self.card_payment)
        
        pay_lay.addWidget(btn_cash)
        pay_lay.addWidget(btn_card)
        right_layout.addLayout(pay_lay)
        
        main_lay.addWidget(right_container)
        
        # Başlangıçta kategorileri yükle
        self.load_categories_grid()
    
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
        """Seçilen kategorideki ürünleri getirir"""
        self.clear_selection_area()
        
        # Grid ayarlarını ürünler için düzenle
        self.selection_lay.setAlignment(Qt.AlignTop)
        
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
        
        # Ana hizalamayı yukarı sabitle
        self.selection_lay.setAlignment(Qt.AlignTop)
        self.selection_lay.setSpacing(10)

        # Temizlik: Satır esnemelerini sıfırla
        for r in range(self.selection_lay.rowCount()):
            self.selection_lay.setRowStretch(r, 0)

        # ==========================================
        # SATIR 0: KATEGORİ BAŞLIĞI
        # ==========================================
        lbl_cat = QLabel("KATEGORİLER")
        lbl_cat.setStyleSheet("color: #0a84ff; font-weight: 800; font-size: 14px; margin-left: 5px;")
        self.selection_lay.addWidget(lbl_cat, 0, 0)

        # ==========================================
        # SATIR 1: KATEGORİ IZGARASI (3 SÜTUNLU)
        # ==========================================
        cat_container = QWidget()
        cat_grid = QGridLayout(cat_container)
        cat_grid.setContentsMargins(0, 5, 0, 5)
        cat_grid.setSpacing(10)
        cat_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        categories = self.db.get_all_categories()
        
        # "Tüm Ürünler" Butonu
        def show_all():
            self.load_products_grid("Tüm Ürünler")
            
        all_card = CategoryCard("Tüm Ürünler", lambda x: show_all())
        all_card.setStyleSheet(all_card.styleSheet() + "QFrame { border: 1px dashed #555; }")
        cat_grid.addWidget(all_card, 0, 0)

        # Diğer Kategoriler
        c_row = 0
        c_col = 1 
        max_cat_col = 3 # KATEGORİLER 3 YAN YANA

        for cat in categories:
            if cat == "Tüm Ürünler": continue
            
            card = CategoryCard(cat, self.load_products_grid)
            cat_grid.addWidget(card, c_row, c_col)
            
            c_col += 1
            if c_col >= max_cat_col:
                c_col = 0
                c_row += 1
        
        self.selection_lay.addWidget(cat_container, 1, 0)

        # ==========================================
        # SATIR 2: ARA ÇİZGİ
        # ==========================================
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333; margin-top: 15px; margin-bottom: 15px;")
        self.selection_lay.addWidget(line, 2, 0)

        # ==========================================
        # SATIR 3: HIZLI ERİŞİM BAŞLIĞI
        # ==========================================
        lbl_fav = QLabel("HIZLI ERİŞİM")
        lbl_fav.setStyleSheet("color: #ffcc00; font-weight: 800; font-size: 14px; margin-left: 5px;")
        self.selection_lay.addWidget(lbl_fav, 3, 0)

        # ==========================================
        # SATIR 4: HIZLI ERİŞİM IZGARASI (4 SÜTUNLU)
        # ==========================================
        fav_container = QWidget()
        fav_grid = QGridLayout(fav_container)
        fav_grid.setContentsMargins(0, 5, 0, 5)
        fav_grid.setSpacing(10)
        fav_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        favorites = self.db.get_favorites()
        
        if favorites:
            f_row = 0
            f_col = 0
            max_fav_col = 4 # HIZLI ERİŞİM 4 YAN YANA

            for pid, name, price, img, fav, stock in favorites:
                def on_click(n, p):
                    self.add_to_cart(n, p)
                
                card = ProductCard(pid, name, price, img, fav, stock, on_click, self.refresh_ui, self.db, is_mini=True)
                card.setFixedSize(130, 150)
                
                fav_grid.addWidget(card, f_row, f_col)
                
                f_col += 1
                if f_col >= max_fav_col:
                    f_col = 0
                    f_row += 1
            
            self.selection_lay.addWidget(fav_container, 4, 0)
        else:
            lbl_empty = QLabel("Henüz favori ürün yok.")
            lbl_empty.setStyleSheet("color: #555; font-style: italic; margin-left: 10px;")
            self.selection_lay.addWidget(lbl_empty, 4, 0)

        # ==========================================
        # SATIR 5: BOŞLUK DOLDURUCU (SPACER)
        # ==========================================
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        
        # HATA BURADAYDI: 'row' yerine '5' yazdık.
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

    def load_cats_sidebar(self):
        while self.cat_lay.count():
            i = self.cat_lay.takeAt(0)
            if i.widget(): i.widget().deleteLater()
        
        # Tüm Ürünler
        btn_all = QPushButton("TÜM ÜRÜNLER")
        btn_all.setProperty("class", "CatBoxBtn")
        btn_all.setStyleSheet("border: 1px solid #0a84ff; color: #0a84ff;")
        btn_all.clicked.connect(lambda: self.show_products_popup("Tüm Ürünler"))
        self.cat_lay.addWidget(btn_all)
        
        categories = self.db.get_all_categories()
        for c in categories:
            if c == "Tüm Ürünler": continue
            btn = QPushButton(c)
            btn.setProperty("class", "CatBoxBtn")
            btn.clicked.connect(lambda _, x=c: self.show_products_popup(x))
            self.cat_lay.addWidget(btn)
        self.cat_lay.addStretch()

    def load_quick_access(self): # hızlı erişim bölümü
        while self.fav_lay.count():
            i = self.fav_lay.takeAt(0)
            if i.widget(): i.widget().deleteLater()
            
        favorites = self.db.get_favorites()
        if not favorites: return

        # 4 Sütunlu Mantık
        max_col = 4
        
        for i, (pid, name, price, img, is_fav, stock) in enumerate(favorites):
            row = i // max_col
            col = i % max_col
            
            card = ProductCard(pid, name, price, img, is_fav, stock, self.add_to_cart, self.refresh_ui, self.db, is_mini=True)
            card.setFixedSize(120, 130) # hızlı erişim ürün boyutları
            
            self.fav_lay.addWidget(card, row, col)

    def show_products_popup(self, cat): # hızlı erişim ürünleri
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{cat}")
        dlg.resize(1000, 700)
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

    def add_to_cart(self, name, price):
        found = False
        target_index = -1
        
        # Ürün zaten sepette mi kontrol et
        for i, item in enumerate(self.cart_data):
            if item['name'] == name:
                item['qty'] += 1
                found = True
                target_index = i
                break
        
        # Yoksa yeni ekle
        if not found:
            self.cart_data.append({
                'name': name, 
                'price': float(price), # Fiyatın sayı olduğundan emin oluyoruz
                'qty': 1
            })
            target_index = len(self.cart_data) - 1
            
        # Ekranı Yenile
        self.render_cart()
        
        # Eklenen satıra odaklan (Otomatik kaydırma)
        if target_index != -1:
            self.table.selectRow(target_index)
            self.selected_row = target_index
            self.table.scrollToItem(self.table.item(target_index, 0))

    def render_cart(self):
        """Sepeti ekrana çizer ve toplamı günceller"""
        self.table.setRowCount(0) # Tabloyu temizle
        total = 0.0
        
        for i, item in enumerate(self.cart_data):
            self.table.insertRow(i)
            
            # 1. Sütun: Ürün Adı
            item_name = QTableWidgetItem(str(item['name']))
            item_name.setFont(QFont("Segoe UI", 14, QFont.Bold))
            self.table.setItem(i, 0, item_name)
            
            # 2. Sütun: Fiyat
            item_price = QTableWidgetItem(f"{item['price']:.2f}")
            item_price.setFont(QFont("Segoe UI", 14))
            self.table.setItem(i, 1, item_price)
            
            # 3. Sütun: Adet (BURASI SORUNLUYDU)
            qty_val = item['qty']
            item_qty = QTableWidgetItem(str(qty_val)) # Mutlaka str() olmalı
            item_qty.setTextAlignment(Qt.AlignCenter)
            item_qty.setFont(QFont("Segoe UI", 16, QFont.Bold))
            item_qty.setForeground(QColor("#30d158")) # Yeşil renk
            self.table.setItem(i, 2, item_qty)
            
            # Toplam Hesapla
            total += item['price'] * item['qty']
        
        # Genel Toplam Etiketini Güncelle
        self.lbl_total.setText(f"{total:.2f} ₺")

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

    def numpad_action(self, key):
        """Hem Numpad hem Klavye burayı tetikler"""
        if self.selected_row == -1 and self.cart_data:
            self.selected_row = len(self.cart_data) - 1
            self.table.selectRow(self.selected_row)
            
        if self.selected_row == -1: return
            
        item = self.cart_data[self.selected_row]
        cur_s = str(item['qty'])
        
        if key == 'C':
            self.cart_data.pop(self.selected_row)
            self.selected_row = -1
            if self.cart_data: self.selected_row = len(self.cart_data) - 1
        elif key == '⌫':
            if len(cur_s) > 1:
                item['qty'] = int(cur_s[:-1])
            else:
                self.cart_data.pop(self.selected_row)
                self.selected_row = -1
                if self.cart_data: self.selected_row = len(self.cart_data) - 1
        else:
            # Yeni sayı girişi
            if item['qty'] == 1 and len(cur_s) == 1:
                 # Adet 1 ise ve tek haneli sayı giriliyorsa üzerine yaz (15 olmasın, 5 olsun)
                 item['qty'] = int(key)
            else:
                 item['qty'] = int(cur_s + key)
                 
        self.render_cart()
        
        # Seçimi koru
        if self.selected_row != -1 and self.selected_row < self.table.rowCount():
            self.table.selectRow(self.selected_row)
            self.table.setCurrentCell(self.selected_row, 2)

    # ... Diğer metodlar aynı (finish_sale, card_payment, on_pos_result, etc.) ...
    # Kodu kısaltmak için değişmeyen fonksiyonları tekrar yazmıyorum, 
    # önceki kodunuzdaki finish_sale, card_payment, mark_pending, add_category, open_admin, process_barcode_scan fonksiyonlarını aynen kullanın.
    
    def finish_sale(self, method):
       if not self.cart_data: return
       total = sum([x['price'] * x['qty'] for x in self.cart_data])
       try:
           alerts = self.db.record_sale(self.cart_data, total, method)
           if alerts: QMessageBox.warning(self, "Kritik Stok", "\n".join(alerts))
           self.cart_data = []
           self.render_cart()
           self.update_ciro()
           QMessageBox.information(self, "Başarılı", "Satış tamamlandı!")
       except Exception as e:
           QMessageBox.critical(self, "Hata", str(e))

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
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Yönetim Paneli")
        self.resize(1000, 800)
        self.setStyleSheet("background:#1a1a1a; color:white;")
        
        layout = QVBoxLayout(self)
        
        # Sekmeler
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.on_tab_change)
        layout.addWidget(self.tabs)
        
        self.editing_pid = None
        self.filter_mode = 'day'
        self.last_tab_index = 0
        
        # --- SEKMELERİ KUR ---
        self.setup_finances()             # 1. Finansal Rapor
        self.setup_sales_history()        # 2. Satış Geçmişi
        self.setup_prod_list()            # 3. Ürün Listesi
        self.setup_add_prod()             # 4. Ürün Ekle
        self.setup_stock_tracking()       # 5. Stok Takip
        self.setup_pending_transactions() # 6. Bekleyen İşlemler (EKSİK OLAN BUYDU)
        self.setup_bulk_operations()      # 7. Toplu İşlemler

    def on_tab_change(self, index):
        self.last_tab_index = index
        # 4. İndeks (Stok Takip) ise verileri yenile
        if index == 4: 
            self.load_stock_data()
        # 5. İndeks (Bekleyenler) ise yenile
        elif index == 5:
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
        
        self.load_finance_data()
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
        
        self.hist_table = QTableWidget()
        self.hist_table.setColumnCount(6)
        self.hist_table.setHorizontalHeaderLabels(["ID", "Tarih/Saat", "Fiş No", "Satış İçeriği", "Ödeme", "Tutar"])
        self.hist_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hist_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self.hist_table.setStyleSheet("QTableWidget { background:#252525; border:none; }")
        self.hist_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist_table.doubleClicked.connect(self.show_receipt_detail)
        
        data = self.db.get_sales_history_extended()
        self.hist_table.setRowCount(0)
        for r_idx, row in enumerate(data):
            self.hist_table.insertRow(r_idx)
            self.hist_table.setItem(r_idx, 0, QTableWidgetItem(str(row[0])))
            self.hist_table.setItem(r_idx, 1, QTableWidgetItem(str(row[3])))
            self.hist_table.setItem(r_idx, 2, QTableWidgetItem(str(row[1])))
            
            prod_info = str(row[6]) if row[6] else "Ürün Yok"
            self.hist_table.setItem(r_idx, 3, QTableWidgetItem(f"{prod_info}..."))
            
            self.hist_table.setItem(r_idx, 4, QTableWidgetItem(str(row[4])))
            self.hist_table.setItem(r_idx, 5, QTableWidgetItem(f"{row[5]:.2f} ₺"))
            
        l.addWidget(self.hist_table)
        l.addWidget(QLabel("* Fiş detayını görmek için satıra çift tıklayın."))
        self.tabs.addTab(w, "Satış Geçmişi")

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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "AD", "FİYAT", "STOK", "BARKOD", "KRİTİK"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("QTableWidget { background:#252525; border:none; gridline-color:#333; }")
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.start_edit)
        
        l.addWidget(self.table)
        l.addWidget(QLabel("* Düzenlemek için çift tıklayın."))
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
            
        self.table.setRowCount(0)
        for r_idx, row in enumerate(data):
            self.table.insertRow(r_idx)
            for c_idx, val in enumerate(row):
                self.table.setItem(r_idx, c_idx, QTableWidgetItem(str(val if val is not None else "")))

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
        l = QVBoxLayout(w)
        l.setSpacing(15)
        l.setContentsMargins(50, 30, 50, 30)
        
        l.addWidget(QLabel("YENİ ÜRÜN EKLE", styleSheet="font-size:18px; font-weight:bold; color:#0a84ff;"))
        
        self.inp_name = QLineEdit(placeholderText="Ürün Adı")
        self.inp_code = QLineEdit(placeholderText="Barkod")
        
        r1 = QHBoxLayout()
        self.inp_cost = QLineEdit(placeholderText="Maliyet")
        self.inp_sell = QLineEdit(placeholderText="Satış Fiyatı")
        r1.addWidget(self.inp_cost)
        r1.addWidget(self.inp_sell)
        
        r2 = QHBoxLayout()
        self.inp_stok = QLineEdit(placeholderText="Stok")
        self.inp_crit = QLineEdit(placeholderText="Kritik Stok")
        r2.addWidget(self.inp_stok)
        r2.addWidget(self.inp_crit)
        
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItems(self.db.get_all_categories())
        self.cmb_cat.setStyleSheet("padding:10px; border:1px solid #404040; border-radius:8px; background:#252525; color:white;")
        
        self.btn_save = QPushButton("KAYDET")
        self.btn_save.setFixedHeight(50)
        self.btn_save.setStyleSheet("background:#30d158; color:black; font-weight:bold; border-radius:10px; font-size:16px;")
        self.btn_save.clicked.connect(self.save_product)
        
        btn_clear = QPushButton("Temizle")
        btn_clear.setStyleSheet("color:#ff453a; background:transparent;")
        btn_clear.clicked.connect(self.clear_form)
        
        l.addWidget(self.inp_code)
        l.addWidget(self.inp_name)
        l.addLayout(r1)
        l.addLayout(r2)
        l.addWidget(self.cmb_cat)
        l.addWidget(self.btn_save)
        l.addWidget(btn_clear)
        l.addStretch()
        
        self.tabs.addTab(w, "Ürün Ekle / Düzenle")

    def save_product(self):
        inputs = [self.inp_name, self.inp_code, self.inp_cost, self.inp_sell, self.inp_stok]
        error = False
        
        for i in inputs: 
            if not i.text().strip(): 
                i.setProperty("class", "Error")
                i.style().unpolish(i)
                i.style().polish(i)
                error = True
            else: 
                i.setProperty("class", "")
                i.style().unpolish(i)
                i.style().polish(i)
        
        if error: 
            QMessageBox.warning(self, "Hata", "Zorunlu alanları doldurun!")
            return
        
        try:
            crit = int(self.inp_crit.text()) if self.inp_crit.text() else 5
            
            if self.editing_pid:
                self.db.update_product_fully(
                    self.editing_pid, 
                    self.inp_name.text(), 
                    float(self.inp_cost.text()), 
                    float(self.inp_sell.text()), 
                    int(self.inp_stok.text()), 
                    self.cmb_cat.currentText(), 
                    self.inp_code.text(), 
                    None, 
                    crit
                )
                QMessageBox.information(self, "Bilgi", "Güncellendi.")
            else:
                if self.db.get_product_by_barcode(self.inp_code.text()): 
                    QMessageBox.warning(self, "Hata", "Barkod kullanılıyor!")
                    return
                    
                self.db.insert_product(
                    self.inp_name.text(), 
                    float(self.inp_cost.text()), 
                    float(self.inp_sell.text()), 
                    int(self.inp_stok.text()), 
                    self.cmb_cat.currentText(), 
                    self.inp_code.text(), 
                    None, 
                    crit
                )
                QMessageBox.information(self, "Bilgi", "Eklendi.")
            
            self.clear_form()
            self.load_table_data()
            self.load_stock_data()
            
        except Exception as e: 
            QMessageBox.critical(self, "Hata", str(e))

    def clear_form(self):
        self.editing_pid = None
        self.inp_name.clear()
        self.inp_code.clear()
        self.inp_cost.clear()
        self.inp_sell.clear()
        self.inp_stok.clear()
        self.inp_crit.clear()
        self.btn_save.setText("KAYDET")
        self.btn_save.setStyleSheet("background:#30d158; color:black; font-weight:bold; border-radius:10px; font-size:16px;")
        
        for i in [self.inp_name, self.inp_code, self.inp_cost, self.inp_sell, self.inp_stok]: 
            i.setProperty("class", "")
            i.style().unpolish(i)
            i.style().polish(i)

    # --- 5. STOK TAKİP ---
    def setup_stock_tracking(self):
        w = QWidget()
        l = QVBoxLayout(w)
        
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(4)
        self.stock_table.setHorizontalHeaderLabels(["ID", "Ürün Adı", "Güncel Stok", "İşlem"])
        self.stock_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stock_table.setStyleSheet("QTableWidget { background:#252525; border:none; gridline-color:#333; }")
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stock_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        l.addWidget(self.stock_table)
        self.load_stock_data()
        self.tabs.addTab(w, "Stok Takip")

    def load_stock_data(self):
        data = self.db.get_all_products_stock()
        self.stock_table.setRowCount(0)
        
        for i, (pid, name, stock) in enumerate(data):
            self.stock_table.insertRow(i)
            self.stock_table.setItem(i, 0, QTableWidgetItem(str(pid)))
            self.stock_table.setItem(i, 1, QTableWidgetItem(name))
            self.stock_table.setItem(i, 2, QTableWidgetItem(str(stock)))
            
            btn = QPushButton("Stok Değiştir")
            btn.setProperty("class", "StockChangeBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, p=pid, s=stock: self.update_stock_direct(p, s))
            
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(5,5,5,5)
            layout.addWidget(btn)
            self.stock_table.setCellWidget(i, 3, container)

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
        
        self.load_pending_data()
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
        btn_apply = QPushButton("UYGULA")
        btn_apply.setFixedHeight(60)
        btn_apply.setStyleSheet("""
            QPushButton { background-color: #ff9f0a; color: black; font-weight: bold; font-size: 18px; border-radius: 10px; } 
            QPushButton:hover { background-color: #ffb340; }
        """)
        btn_apply.clicked.connect(self.run_bulk_update)
        l.addWidget(btn_apply)
        
        # Ayırıcı Çizgi
        l.addSpacing(20)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #333;")
        l.addWidget(line)
        l.addSpacing(20)
        
        # Yedekle Butonu
        btn_backup = QPushButton("VERİTABANI YEDEKLE")
        btn_backup.setFixedHeight(50)
        btn_backup.setStyleSheet("""
            QPushButton { background-color: #0a84ff; color: white; font-weight: bold; font-size: 16px; border-radius: 10px; } 
            QPushButton:hover { background-color: #007aff; }
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