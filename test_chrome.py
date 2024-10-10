from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

# Test if Chrome opens with a simple script
try:
    options = webdriver.ChromeOptions()
    # Remove headless mode to see the browser
    # options.add_argument('--headless')

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.get("https://www.google.com")  # Open Google to test
    print("Chrome opened successfully and navigated to Google!")

    # Keep the browser open for 10 seconds before closing
    time.sleep(10)  # This keeps the browser open for 10 seconds
except Exception as e:
    print(f"Error opening Chrome: {str(e)}")
finally:
    # Comment out the quit to keep the browser open
    # driver.quit()
    pass
