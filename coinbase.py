from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# tarayıcının kapanmaması için ayar yapıyoruz
chrome_options = Options()
chrome_options.add_experimental_option("detach", True)

#  servisi ve opsiyonları driver'a tanıtıyoruz
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

driver.maximize_window()
driver.get("https://www.coinbase.com/explore")

