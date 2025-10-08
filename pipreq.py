import threading
import time
import requests
import asyncio
import  

def get_crypto_data():

    response = requests.get("https://raw.githubusercontent.com/atilsamancioglu/K21-JSONDataSet/master/crypto.json")

    if response.status_code == 200:
        return response.json()

crypto_response = get_crypto_data()
user_input = input("Enter your crpyto currency: ")

for crypto in crypto_response:
    if crypto["currency"] == user_input:
        print(crypto["price"])

class ThreadingDownloader(threading.Thread):
    json_array

    def __init__(self):
        super.__init__()
    def run(self):
        response = requests.get("")
        self.json_array.append(response.json())
        return.response.json()


