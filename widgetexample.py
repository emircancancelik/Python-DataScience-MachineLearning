from tkinter import *
from tkinter import Radiobutton

window = Tk()
window.title("Tkinter Python")
window.minsize(400, 400)

my_label = Label(window, text="Label Text")
my_label.config(bg="black")
my_label.config(fg="white")
my_label.config(padx=5, pady=5)
my_label.pack()

def button_clicked(text=None):
    print("Button clicked")
    print(my_text.get("2.0",END))

my_button = Button(text="button", command=button_clicked)
my_button.config(padx=10, pady=10)
my_button.pack()

my_entry = Entry(window, width=25)
my_entry.focus()
my_entry.pack()

my_text = Text(width=25, height=5)
my_text.pack()

#scale
def scale_selected(value):
    print(value)
my_scale = Scale(from_=0, to=50,command=scale_selected, orient=HORIZONTAL)
my_scale.pack()

#spinbox
def spinbox_selected(value):
    print(value)
my_spinbox = Spinbox(from_=0, to=100,command=spinbox_selected)
my_spinbox.pack()

#checkButton
def check_button_selected():
    print(check_state.get())

check_state = IntVar()
my_checkbutton = Checkbutton(text="Checkbutton", variable=check_state,command=check_button_selected)
my_checkbutton.pack()

#radiobutton
def radio_selected():
    print(radio_checked_state.get())


radio_checked_state = IntVar()
my_radiobutton = Radiobutton(window, text="1. option", variable=check_state, value=10)
my_radiobutton_2 = Radiobutton(window, text="2. option", variable=check_state, value=20)
my_radiobutton.pack()
my_radiobutton_2.pack()

#listbox

def listbox_selected(event):
    print(my_listbox.get(my_listbox.curselection()))

my_listbox = Listbox(window)
name_list = ["atil", "abc", "def"]
for i in range(len(name_list)):
    my_listbox.insert(i, name_list[i])
    my_listbox.bind('<<ListboxSelect>>', listbox_selected)
my_listbox.pack()




window.mainloop()