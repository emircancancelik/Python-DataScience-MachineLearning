from rembg import remove
from PIL import Image


import datetime

class VoidPOS_AI:
    def __init__(self):
        # Simüle edilmiş veritabanı (Normalde SQL'den gelecek)
        self.urunler = [
            {"id": 101, "ad": "Yarım Yağlı Süt", "stok": 15, "satis_hizi": "YUKSEK", "skt": "2026-02-01", "fiyat": 30.0},
            {"id": 102, "ad": "Çikolatalı Gofret", "stok": 500, "satis_hizi": "DUSUK", "skt": "2026-10-15", "fiyat": 10.0},
            {"id": 103, "ad": "Organik Yumurta", "stok": 8, "satis_hizi": "NORMAL", "skt": "2026-01-31", "fiyat": 60.0}
        ]
        self.bugun = datetime.datetime.strptime("2026-01-29", "%Y-%m-%d").date() # Örnek tarih

    # --- FAZ 1: Stok ve Sipariş Analizi ---
    def siparis_analizi_yap(self):
        oneriler = []
        print("\n--- [AI] Stok Analizi Çalışıyor ---")
        
        for urun in self.urunler:
            # Mantık: Stok 20'nin altındaysa VE satış hızı YÜKSEK ise
            if urun["stok"] < 20 and urun["satis_hizi"] == "YUKSEK":
                # AI, geçmiş veriye bakarak "20 koli fazla" öneriyor (Simülasyon)
                onerilen_miktar = 50 + 20 
                
                oneri = {
                    "tip": "SIPARIS",
                    "mesaj": f"DİKKAT: {urun['ad']} stokları eriyor! Normalden 20 koli fazla sipariş geçilmeli.",
                    "detay": {"urun_id": urun["id"], "miktar": onerilen_miktar},
                    "oncelik": "YÜKSEK"
                }
                oneriler.append(oneri)
        return oneriler

    # --- FAZ 2: SKT ve Fiyatlandırma Analizi ---
    def skt_analizi_yap(self):
        oneriler = []
        print("\n--- [AI] SKT Taraması Çalışıyor ---")
        
        for urun in self.urunler:
            urun_skt = datetime.datetime.strptime(urun["skt"], "%Y-%m-%d").date()
            kalan_gun = (urun_skt - self.bugun).days

            if 0 < kalan_gun <= 3: # Son 3 gün kalmışsa
                oneri = {
                    "tip": "FIYAT_KIRMA",
                    "mesaj": f"UYARI: {urun['ad']} SKT'sine {kalan_gun} gün kaldı. %10 İndirim uygulayalım mı?",
                    "detay": {"urun_id": urun["id"], "yeni_fiyat": urun["fiyat"] * 0.90},
                    "oncelik": "ACİL"
                }
                oneriler.append(oneri)
            elif kalan_gun <= 0:
                oneri = {
                    "tip": "IMHA",
                    "mesaj": f"KRİTİK: {urun['ad']} SKT'si dolmuş! Satıştan kaldırılmalı.",
                    "detay": {"urun_id": urun["id"], "aksiyon": "Stoktan Düş"},
                    "oncelik": "KRİTİK"
                }
                oneriler.append(oneri)
                
        return oneriler

    # --- FAZ 3: UI ile Konuşma ve Onay Mekanizması ---
    def kasiyer_arayuz_simulasyonu(self, oneriler):
        print(f"\n📢 EKRANA DÜŞEN BİLDİRİMLER ({len(oneriler)} Adet)")
        
        for i, oneri in enumerate(oneriler, 1):
            print(f"\n[{i}] {oneri['oncelik']} - {oneri['tip']}")
            print(f"    AI Mesajı: \"{oneri['mesaj']}\"")
            
            # Burada UI üzerinden kasiyerin butonuna basmasını simüle ediyoruz
            cevap = input(f"    >>> Kasiyer Onayı (E/H): ").upper()
            
            if cevap == "E":
                self.aksiyonu_gerceklestir(oneri)
            else:
                print("    ❌ Kasiyer reddetti. İşlem iptal edildi.")

    def aksiyonu_gerceklestir(self, oneri):
        if oneri["tip"] == "FIYAT_KIRMA":
            yeni_fiyat = oneri["detay"]["yeni_fiyat"]
            print(f"    ✅ ONAYLANDI: Fiyat {yeni_fiyat} TL olarak güncellendi ve etiket basıldı.")
            # Veritabanı update kodu burada çalışır
            
        elif oneri["tip"] == "SIPARIS":
            miktar = oneri["detay"]["miktar"]
            print(f"    ✅ ONAYLANDI: Tedarikçiye {miktar} adetlik sipariş maili gönderildi.")
            # Sipariş API'si burada çağrılır

# --- SİSTEMİ ÇALIŞTIRALIM ---
if __name__ == "__main__":
    sistem = VoidPOS_AI()
    
    # 1. Analizleri topla
    stok_onerileri = sistem.siparis_analizi_yap()
    skt_onerileri = sistem.skt_analizi_yap()
    
    tum_oneriler = stok_onerileri + skt_onerileri
    
    # 2. Kasiyere Sun
    if tum_oneriler:
        sistem.kasiyer_arayuz_simulasyonu(tum_oneriler)
    else:
        print("Sistem stabil, AI önerisi yok.")

        import sqlite3
import datetime

class VoidAI_Engine:
    def __init__(self, db_path="voidpos.db"):
        self.db_path = db_path

    def baglanti_kur(self):
        """Veritabanı bağlantısını açar."""
        return sqlite3.connect(self.db_path)

    # --- GERÇEK STOK ANALİZİ ---
    def stoklari_tarama(self):
        conn = self.baglanti_kur()
        cursor = conn.cursor()
        
        # Kritik stok seviyesinin altına düşen VE çok satan ürünleri SQL ile çekiyoruz
        # (Burada SQL'in gücünü kullanıyoruz)
        sorgu = """
            SELECT urun_id, urun_adi, stok_adedi, satis_hizi 
            FROM urunler 
            WHERE stok_adedi < kritik_seviye 
            AND satis_hizi = 'YUKSEK'
        """
        cursor.execute(sorgu)
        kritik_urunler = cursor.fetchall()
        
        oneriler = []
        for urun in kritik_urunler:
            # (id, ad, stok, hız) döner
            oneri = {
                "tur": "SIPARIS_ONERISI",
                "baslik": "Stok Alarmı",
                "mesaj": f"Patron, {urun[1]} peynir ekmek gibi gidiyor ama depoda {urun[2]} tane kaldı. 50 koli sipariş geçelim mi?",
                "aksiyon_verisi": {"id": urun[0], "miktar": 50, "islem": "tedarikci_mail"}
            }
            oneriler.append(oneri)
            
        conn.close()
        return oneriler

    # --- GERÇEK SKT ANALİZİ ---
    def skt_kontrol(self):
        conn = self.baglanti_kur()
        cursor = conn.cursor()
        
        # Bugünden itibaren 3 gün içinde SKT'si dolacak ürünleri bul
        bugun = datetime.date.today()
        limit_tarih = bugun + datetime.timedelta(days=3)
        
        sorgu = """
            SELECT urun_id, urun_adi, skt_tarihi, satis_fiyati 
            FROM urunler 
            WHERE skt_tarihi BETWEEN ? AND ?
        """
        cursor.execute(sorgu, (bugun, limit_tarih))
        riskli_urunler = cursor.fetchall()
        
        oneriler = []
        for urun in riskli_urunler:
            eski_fiyat = urun[3]
            yeni_fiyat = eski_fiyat * 0.90 # %10 İndirim
            
            oneri = {
                "tur": "FIYAT_INDIRIMI",
                "baslik": "İsraf Uyarısı",
                "mesaj": f"{urun[1]} ürününün tarihi yaklaşıyor. Çöpe gitmemesi için fiyatı {eski_fiyat}'den {yeni_fiyat}'ye çekelim mi?",
                "aksiyon_verisi": {"id": urun[0], "yeni_fiyat": yeni_fiyat, "islem": "fiyat_guncelle"}
            }
            oneriler.append(oneri)
            
        conn.close()
        return oneriler

    # --- AKSİYON (GERÇEK DÜNYA MÜDAHALESİ) ---
    def aksiyonu_uygula(self, aksiyon_verisi):
        conn = self.baglanti_kur()
        cursor = conn.cursor()
        
        if aksiyon_verisi["islem"] == "fiyat_guncelle":
            # Veritabanında fiyatı gerçekten değiştiriyoruz
            cursor.execute("UPDATE urunler SET satis_fiyati = ? WHERE urun_id = ?", 
                           (aksiyon_verisi["yeni_fiyat"], aksiyon_verisi["id"]))
            conn.commit()
            durum = f"Veritabanı güncellendi: Ürün {aksiyon_verisi['id']} yeni fiyatı {aksiyon_verisi['yeni_fiyat']} TL oldu."
            
        elif aksiyon_verisi["islem"] == "tedarikci_mail":
            # Burada gerçekten mail atma fonksiyonunu çağırabilirsin
            # send_mail_to_supplier(...)
            durum = f"Tedarikçiye {aksiyon_verisi['miktar']} adetlik sipariş maili gönderildi."
            
        conn.close()
        return durum