from flask import Flask, render_template, request, jsonify
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import os
import sqlite3
from datetime import datetime
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import json
import time
import re
import csv

app = Flask(__name__)

# SQLite database setup
DB_PATH = 'scraping_data.db'

def init_db():
    """Initialize SQLite database and create tables if they don't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS scraping_summary (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            date TEXT,
                            country TEXT,
                            city TEXT,
                            job_count INTEGER,
                            file_path TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS exclusion_settings (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            attribute TEXT,
                            keywords TEXT)''')
        conn.commit()

# Initialize database when the app starts
init_db()

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
    return jsonify(scraping_status)

def save_scraping_summary(country, city, job_count, file_path):
    today = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO scraping_summary (date, country, city, job_count, file_path) VALUES (?, ?, ?, ?, ?)",
                       (today, country, city, job_count, file_path))
        conn.commit()


@app.route('/get_scraping_summary', methods=['GET'])
def get_scraping_summary():
    date = request.args.get('date', datetime.now().strftime("%Y-%m-%d"))
    data = []
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date, country, city, job_count, file_path FROM scraping_summary WHERE date = ?", (date,))
        rows = cursor.fetchall()
        for row in rows:
            file_path = row[4]
            if os.path.exists(file_path):  # Only add records if the file exists
                data.append({
                    "Date": row[0],
                    "Country": row[1],
                    "City": row[2],
                    "Job Count": row[3],
                    "FilePath": file_path
                })
            else:
                # Optionally, delete the record if the file no longer exists
                cursor.execute("DELETE FROM scraping_summary WHERE file_path = ?", (file_path,))
                conn.commit()
    return jsonify(data)

def fetch_exclusions_from_db():
    exclusions = {
        "Title": [],
        "Company": [],
        "Location": [],
        "Salary": [],
        "Type": [],
        "Description": []
    }
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT attribute, keywords FROM exclusion_settings")
        rows = cursor.fetchall()
        for row in rows:
            attribute, keywords = row
            if attribute in exclusions:
                exclusions[attribute].extend(keywords.split(','))
    print("Exclusions loaded from DB:", exclusions)  # Debugging log
    return exclusions

@app.route('/save_exclusions', methods=['POST'])
def save_exclusions():
    new_exclusions = request.json
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM exclusion_settings")
            for attribute, keywords in new_exclusions.items():
                keywords_set = set(k.strip() for k in keywords if k.strip())
                if keywords_set:
                    keywords_str = ','.join(keywords_set)
                    cursor.execute("INSERT INTO exclusion_settings (attribute, keywords) VALUES (?, ?)",
                                   (attribute, keywords_str))
            conn.commit()
        return jsonify({"message": "Exclusions saved successfully!"})
    except Exception as e:
        print("Error saving exclusions:", e)
        return jsonify({"message": "Error saving exclusions"}), 500

@app.route('/get_exclusions', methods=['GET'])
def get_exclusions():
    return jsonify(fetch_exclusions_from_db())

@app.route('/scrape_jobs', methods=['POST'])
def scrape_jobs():
    country_id = int(request.form['country_id'])
    selected_city = request.form['city']
    num_jobs = int(request.form['num_jobs'])

    scraping_status["total"] = num_jobs
    scraping_status["completed"] = 0

    entry = next((entry for entry in entries if entry['id'] == country_id), None)
    if entry:
        exclusions = fetch_exclusions_from_db()  # Fetch exclusions before starting scraping
        link = entry['link'] + selected_city
        threading.Thread(target=run_scraping, args=(link, num_jobs, entry["country"], selected_city, exclusions)).start()
        return jsonify({"message": "Scraping has started!"})
    return jsonify({"message": "Country or city not found"}), 404

def run_scraping(link, num_jobs, country, city, exclusions):
    global scraping_status
    chrome_driver_path = '/opt/homebrew/bin/chromedriver'
    service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=service)

    scraping_status["total"] = num_jobs
    scraping_status["completed"] = 0

    try:
        print(f"Navigating to {link}")
        driver.get(link)
        time.sleep(2)

        jobs = []

        for i in range(num_jobs):
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CLASS_NAME, "job_seen_beacon")))
                job_listings = driver.find_elements(By.CLASS_NAME, "job_seen_beacon")

                if i >= len(job_listings):
                    print("Fewer job listings than expected.")
                    break

                job = job_listings[i]
                title = WebDriverWait(job, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2.jobTitle"))).text
                job_link = WebDriverWait(job, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2.jobTitle a"))).get_attribute('href')

                # Clean title by removing excluded words
                for word in exclusions.get("Title", []):
                    title = re.sub(rf"{re.escape(word)}", "", title, flags=re.IGNORECASE).strip()

                driver.execute_script("window.open(arguments[0], '_blank');", job_link)
                driver.switch_to.window(driver.window_handles[1])

                job_description = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#jobDescriptionText"))
                ).get_attribute('innerHTML')
                
                company = driver.find_element(By.CSS_SELECTOR, "div.css-hon9z8 a").text
                # Clean company by removing excluded words
                for word in exclusions.get("Company", []):
                    company = re.sub(rf"{re.escape(word)}", "", company, flags=re.IGNORECASE).strip()

                # Location exclusion check
                try:
                    location = driver.find_element(By.CSS_SELECTOR, "div[data-testid='job-location']").text
                    for word in exclusions.get("Location", []):
                        location = re.sub(rf"{re.escape(word)}", "", location, flags=re.IGNORECASE).strip()
                except NoSuchElementException:
                    location = "Location not found"

                # Salary and Type exclusion checks
                try:
                    salary = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType span").text
                    job_type = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType span:nth-child(2)").text

                    # Remove excluded salary keywords like "£"
                    for word in exclusions.get("Salary", []):
                        salary = re.sub(rf"{re.escape(word)}", "", salary, flags=re.IGNORECASE).strip()

                    # Job type exclusion based on user-provided exclusions
                    for word in exclusions.get("Type", []):
                        job_type = re.sub(rf"{re.escape(word)}", "", job_type, flags=re.IGNORECASE).strip()
                except NoSuchElementException:
                    salary = "N/A"
                    job_type = "N/A"

                # Description exclusion check
                for word in exclusions.get("Description", []):
                    job_description = re.sub(rf"{re.escape(word)}", "", job_description, flags=re.IGNORECASE).strip()

                # Add job details to the jobs list
                jobs.append({
                    "Title": title,
                    "Company": company,
                    "Location": location,
                    "Salary": salary,
                    "Type": job_type,
                    "Description": job_description,
                    "Link": job_link
                })

                driver.close()
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(2)

                scraping_status["completed"] += 1

            except (NoSuchElementException, TimeoutException) as e:
                print(f"Error extracting job data for job {i + 1}: {e}")

        driver.quit()

        # Save job data if jobs were scraped successfully
        if jobs:
            today_date = datetime.now().strftime("%Y-%m-%d")
            dir_path = os.path.join("scrap_jobs", country, today_date)
            os.makedirs(dir_path, exist_ok=True)
            file_name = f"jobs_{city}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
            output_path = os.path.join(dir_path, file_name)

            jobs_df = pd.DataFrame(jobs)
            jobs_df.to_csv(output_path, index=False)
            print(f"Job data saved to {output_path}")

            # Save scraping summary
            save_scraping_summary(country, city, len(jobs), output_path)

    except Exception as e:
        print(f"Scraping failed: {e}")
        driver.quit()


@app.route('/view_file', methods=['GET'])
def view_file():
    """Serve the CSV file for viewing in a formatted table."""
    file_path = request.args.get('file_path')

    # Ensure the file path is absolute
    abs_file_path = os.path.abspath(file_path)
    
    # Check if the file exists
    if abs_file_path and os.path.exists(abs_file_path):
        # Parse CSV content into a list of rows
        with open(abs_file_path, 'r') as file:
            csv_reader = csv.reader(file)
            headers = next(csv_reader)  # Get headers from the first row
            rows = [row for row in csv_reader]  # Remaining rows are data
        return render_template('view_file.html', headers=headers, rows=rows)
    else:
        return "File not found", 404

if __name__ == '__main__':
    app.run(debug=True, port=5001)
