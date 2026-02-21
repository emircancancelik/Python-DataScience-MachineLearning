from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
driver.maximize_window() #otomasyon yazarken chrome'u açmaya gerek yok.

#get ile sadece url alınır. o siteye gidilir.
driver.get("https://google.com")

#find_element ile bulunmak istenen yerler html kodundan
#class veya name ile çekilir. name tercihtir.

WebDriverWait(driver, 4).until(expected_conditions.visibility_of_all_elements_located((By.NAME, "q"))) 
input_element_by_name = driver.find_element(By.NAME, "q")

#time.sleep(4) yerine webdriverwait kullanmak daha mantıklı.
#işlem için maximum 4 saniye bekle eğer işlem 0.1 saniyede gerçekleşirse işlemi geçmesini söyleriz.
#timesleep(4) ise işlem 0.01 saniyede gerçekleşse bile 4 saniye işlemi bekletir.


# print(driver.find_element(By.NAME, "q")) -> q ile html kodu çekilir.

input_element_by_name.get("kahve kültürü nedir?")

WebDriverWait(driver, 4).until(expected_conditions.visibility_of_all_elements_located((By.NAME, "btnK"))) 
search_button = driver.find_element(By.NAME,"btnK")

WebDriverWait(driver, 4).until(expected_conditions.visibility_of_all_elements_located((By.NAME, "btnK"))) 
search_button.click()

while True:
    continue