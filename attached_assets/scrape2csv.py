from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import argparse
import time

# Argument parser for limit parameter
parser = argparse.ArgumentParser(description="Scrape company data with a limit.")
parser.add_argument('--limit', type=int, default=100, help='Maximum number of companies to scrape.')
args = parser.parse_args()
limit = args.limit

# Set up Selenium WebDriver
driver = webdriver.Chrome()

# Open the webpage
url = "https://www.mintos.com/en/lending-companies/"
driver.get(url)

# Accept cookie consent
try:
    cookie_button = WebDriverWait(driver, 3).until(
        EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
    )
    cookie_button.click()
except Exception as e:
    print("Cookie consent button not found or clickable:", e)

# Wait for the page to load
time.sleep(2)

# Select rows with clickable company links
company_rows = driver.find_elements(By.XPATH, '//div[@id="loan-originators-overview-wrapper"]//table/tbody/tr')[:limit]

# Store the original window handle
original_window = driver.current_window_handle

# List to collect all extracted data
company_data = []

# Loop through each row
for row in company_rows:
    try:
        # Click on the company link
        company_link = row.find_element(By.XPATH, './/td[1]/span/div/img')
        company_link.click()
        
        # Wait for the new tab to open and switch to it
        WebDriverWait(driver, 3).until(EC.number_of_windows_to_be(2))
        new_window = [window for window in driver.window_handles if window != original_window][0]
        driver.switch_to.window(new_window)
        
        # Wait for the page content to load
        time.sleep(2)

        # Scrape data from the company page
        try:
            header = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//div[@class="loan-originator-header-header"]/h1[1]'))
            )
            header_text = header.text.replace("\n", " ")  # Replace line breaks with spaces
        except:
            header_text = "Header not found."

        try:
            section_1 = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//div[@class="loan-originator-files clearfix horizontal-block-right"]/div[1]'))
            )
            section_1_text = section_1.text.replace("\n", " ")  # Replace line breaks with spaces
        except:
            section_1_text = "Section 1 not found."

        try:
            section_2 = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//div[@class="loan-originator-files clearfix horizontal-block-right"]/div[2]'))
            )
            section_2_text = section_2.text.replace("\n", " ")  # Replace line breaks with spaces
        except:
            section_2_text = "Section 2 not found."

        try:
            section_3 = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//div[@class="loan-originator-files clearfix horizontal-block-right"]/div[3]'))
            )
            section_3_text = section_3.text.replace("\n", " ")  # Replace line breaks with spaces
        except:
            section_3_text = "Section 3 not found."

        try:
            last_updated = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, '//td[@data-label="Last Updated"]'))
            )
            last_updated_text = last_updated.text.replace("\n", " ")  # Replace line breaks with spaces
        except:
            last_updated_text = "Last Updated not found."

        # Get the current page URL
        page_url = driver.current_url

        # Append data to the list
        company_data.append({
            "url": page_url,
            "header": header_text,
            "section_1": section_1_text,
            "section_2": section_2_text,
            "section_3": section_3_text,
            "last_updated": f"Basic information updated on: {last_updated_text}",
        })

        print(f"Scraped: {header_text} | Last Updated: {last_updated_text}")

        # Close the new tab and switch back to the original window
        driver.close()
        driver.switch_to.window(original_window)
        time.sleep(2)

    except Exception as e:
        print("An error occurred:", e)

# After collecting data
df = pd.DataFrame(company_data)
csv_filename = r"lo_finance_page\scraped_data.csv"
df.to_csv(csv_filename, index=False)

print(f"Data saved to {csv_filename}")

# Close the WebDriver
driver.quit()
