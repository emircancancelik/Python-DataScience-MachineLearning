import tkinter as tk


led_state = 0


def led_on():
    global led_state
    led_state = 1
    led_label.config(text="LED Durumu: ON", bg="yellow")
    print("[PICSimLab] LED Yandı!")

def led_off():
    global led_state
    led_state = 0
    led_label.config(text="LED Durumu: OFF", bg="grey")
    print("[PICSimLab] LED Söndü!")

root = tk.Tk()
root.title("Python + PICSimLab LED Kontrolü")
root.geometry("300x150")

#label
led_label = tk.Label(root, text="LED Durumu: OFF", bg="grey", font=("Arial", 14))
led_label.pack(pady=10)

#Button
on_button = tk.Button(root, text="LED Aç", command=led_on, width=10, bg="green", fg="white")
on_button.pack(pady=5)

off_button = tk.Button(root, text="LED Kapat", command=led_off, width=10, bg="red", fg="white")
off_button.pack(pady=5)

quit_button = tk.Button(root, text="Çıkış", command=root.destroy, width=10)
quit_button.pack(pady=5)


root.mainloop()
