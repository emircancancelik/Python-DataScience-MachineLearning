import time


led_state = 0  # 0: kapalı, 1: açık

print("Python ile PICSimLab LED Simülasyonu")
print("Komutlar: 1 -> LED aç, 0 -> LED kapat, q -> çıkış")

while True:
    cmd = input("Komut gir (1/0/q): ").strip()

    if cmd == "1":
        led_state = 1
        print("[PICSimLab] LED Yandı!")
    elif cmd == "0":
        led_state = 0
        print("[PICSimLab] LED Söndü!")
    elif cmd.lower() == "q":
        print("Program sonlandırıldı.")
        break
    else:
        print("Geçersiz komut!")


    print(f"LED Durumu: {'ON' if led_state else 'OFF'}\n")
    time.sleep(0.1)
