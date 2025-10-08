from tkinter import *
from tkinter import messagebox, Entry

window = Tk()
window.title("Secret Notes")
window.minsize(300,420)
window.maxsize(400, 400)

#photo = PhotoImage(file="sqiurrel cropped.jpg")
#photo_label = Label(window, image=photo)
#photo_label.pack()

def save_notes():
    title = my_entry.get()
    message = my_entry_2.get()
    master_secret = my_entry_3.get()

    if len(title) == 0 or len(message) == 0 or len(master_secret) == 0:
        messagebox.showinfo(title="Error", message="Please enter all info")

    else:                                         #dosyalar "with open()" ile açılır
        with open("mysecret.txt","w") as data_file:
            data_file.write(f"\n{title}\n{message}\n{master_secret}")


my_label = Label(window, text="Please enter your title",font=("Arial",15))
my_label.pack()

my_entry = Entry(window,width=20)
my_entry.pack()

my_label_2 = Label(window, text="Please enter your secret",font=("Arial",15))
my_label_2.pack()

my_entry_2 = Entry(window,width=20)
my_entry_2.pack()

my_label_3 = Label(window,text="Please enter your master key",font=("Arial",15))
my_label_3.pack()

my_entry_3 = Entry(window,width=25)
my_entry_3.pack()

my_save_button = Button(window, text="Save & Encrypt",command=save_notes)
my_save_button.pack()

my_decrypt_button = Button(window, text="Decrypt")
my_decrypt_button.pack()

window.mainloop()