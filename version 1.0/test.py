from flask import Flask, render_template, request, jsonify
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import os
from selenium.common.exceptions import NoSuchElementException, TimeoutException

app = Flask(__name__)

# Sample data for countries and cities
entries = [
    {"id": 1, "country": "United Kingdom", "cities": ["London", "Manchester", "Birmingham"], "link": "https://uk.indeed.com/jobs?q=&l="},
    {"id": 2, "country": "Canada", "cities": ["Toronto", "Vancouver", "Montreal"], "link": "https://ca.indeed.com/jobs?q=&l="},
]

# Global variable to track scraping progress
scraping_status = {"total": 0, "completed": 0}

@app.route('/')
def index():
    return render_template('index.html', entries=entries)

@app.route('/scraping_progress')
def scraping_progress():
    """Endpoint for AJAX polling to get scraping progress."""
    return jsonify(scraping_status)

def run_scraping(link, num_jobs):
    global scraping_status
    chrome_driver_path = '/opt/homebrew/bin/chromedriver'  # Adjust path as needed
    service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=service)

    # Reset progress at the start of scraping
    scraping_status["total"] = num_jobs
    scraping_status["completed"] = 0

    try:
        print(f"Navigating to {link}")
        driver.get(link)
        time.sleep(2)

        jobs = []

        for i in range(num_jobs):
            try:
                # Wait for job listings to load
                WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CLASS_NAME, "job_seen_beacon")))
                job_listings = driver.find_elements(By.CLASS_NAME, "job_seen_beacon")

                if i >= len(job_listings):
                    print("Fewer job listings than expected.")
                    break

                job = job_listings[i]

                # Extract job details with explicit waits
                title = WebDriverWait(job, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2.jobTitle"))).text
                job_link = WebDriverWait(job, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2.jobTitle a"))).get_attribute('href')

                # Open job link in a new tab
                driver.execute_script("window.open(arguments[0], '_blank');", job_link)
                driver.switch_to.window(driver.window_handles[1])

                # Wait for job description to load
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div#jobDescriptionText")))

                job_description = driver.find_element(By.CSS_SELECTOR, "div#jobDescriptionText").get_attribute('innerHTML')
                company = driver.find_element(By.CSS_SELECTOR, "div.css-hon9z8 a").text

                try:
                    location = driver.find_element(By.CSS_SELECTOR, "div[data-testid='job-location']").text
                except NoSuchElementException:
                    print(f"Warning: Unable to locate 'job-location' for job {i+1}. Using alternative selector.")
                    location = "Location not found"

                try:
                    salary = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType span").text
                    job_type = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType span:nth-child(2)").text
                except NoSuchElementException:
                    salary = "N/A"
                    job_type = "N/A"

                # Save job data
                jobs.append({
                    "Title": title,
                    "Company": company,
                    "Location": location,
                    "Salary": salary,
                    "Type": job_type,
                    "Description": job_description,
                    "Link": job_link
                })

                # Close the current tab and switch back to the main tab
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(2)

                # Update progress after each job is completed
                scraping_status["completed"] += 1

            except (NoSuchElementException, TimeoutException) as e:
                print(f"Error extracting job data for job {i + 1}: {e}")

        driver.quit()

        # Save results to CSV if jobs were scraped
        if jobs:
            print("Saving job data to CSV...")
            jobs_df = pd.DataFrame(jobs)
            output_path = os.path.join(os.getcwd(), 'scraped_jobs.csv')
            jobs_df.to_csv(output_path, index=False)
            print(f"Job data saved to {output_path}")
        else:
            print("No jobs were scraped.")

        # Reset scraping status after completing scraping
        scraping_status["completed"] = scraping_status["total"]

    except Exception as e:
        print(f"Scraping failed: {e}")
        driver.quit()

@app.route('/scrape_jobs', methods=['POST'])
def scrape_jobs():
    country_id = int(request.form['country_id'])
    selected_city = request.form['city']
    num_jobs = int(request.form['num_jobs'])

    # Reset scraping status at the beginning of each job
    scraping_status["total"] = num_jobs
    scraping_status["completed"] = 0

    # Retrieve base link for the selected country
    entry = next((entry for entry in entries if entry['id'] == country_id), None)
    if entry:
        link = entry['link'] + selected_city  # Append city to the base link
        # Start scraping in a new thread and reset progress
        threading.Thread(target=run_scraping, args=(link, num_jobs)).start()
        return jsonify({"message": "Scraping has started!"})
    return jsonify({"message": "Country or city not found"}), 404

if __name__ == '__main__':
    app.run(debug=True)
