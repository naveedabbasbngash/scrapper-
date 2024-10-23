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
import re
import logging
import sqlite3
from flask import Flask, jsonify, request

from webdriver_manager.chrome import ChromeDriverManager  # Import WebDriverManager


app = Flask(__name__)

# SQLite database setup
DB_PATH = 'scraping_data.db'

def init_db():
    """Initialize SQLite database and create tables if they don't exist."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Table for storing scraping summaries
        cursor.execute('''CREATE TABLE IF NOT EXISTS scraping_summary (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            date TEXT,
                            country TEXT,
                            city TEXT,
                            job_count INTEGER,
                            file_path TEXT)''')
        
        # Updated exclusion_settings table with separate remove and replace columns
        cursor.execute('''CREATE TABLE IF NOT EXISTS exclusion_settings (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            attribute TEXT,
                            remove_word TEXT,
                            replace_word TEXT)''')
        
        conn.commit()
# Initialize database when the app starts
init_db()

def reset_exclusion_settings_table():
    """Drops and recreates the exclusion_settings table with the updated schema."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Drop the existing table if it exists
        cursor.execute("DROP TABLE IF EXISTS exclusion_settings")
        
        # Recreate the table with updated columns
        cursor.execute('''CREATE TABLE IF NOT EXISTS exclusion_settings (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            attribute TEXT,
                            remove_word TEXT,
                            replace_word TEXT)''')
        
        conn.commit()

# Run this function once to reset the table
# reset_exclusion_settings_table()

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
    """Saves the scraping summary in the database."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO scraping_summary (date, country, city, job_count, file_path) VALUES (?, ?, ?, ?, ?)",
                           (today, country, city, job_count, file_path))
            conn.commit()
        print("Scraping summary saved to database with file path:", file_path)
    except Exception as e:
        print(f"Failed to save scraping summary: {e}")

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

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT attribute, remove_word, replace_word FROM exclusion_settings")
            rows = cursor.fetchall()

            if rows:
                print(f"Exclusions fetched from DB: {rows}")
            else:
                print("No exclusions found in the database.")

            for attribute, remove_word, replace_word in rows:
                attribute_key = attribute.capitalize()  # Capitalize to match dictionary keys (e.g., "Title", "Company")
                if attribute_key in exclusions:
                    exclusions[attribute_key].append({"remove": remove_word, "replace": replace_word})
            
            # Deduplicate entries after fetching them from the database
            for attribute in exclusions:
                exclusions[attribute] = deduplicate_entries(exclusions[attribute])

        logging.info("Exclusions loaded from DB: %s", exclusions)
        return exclusions

    except Exception as e:
        logging.error(f"Error fetching exclusions from database: {e}")
        return exclusions  # Return the empty exclusion structure in case of error
    
    
@app.route('/save_exclusions', methods=['POST'])
def save_exclusions():
    new_exclusions = request.json

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM exclusion_settings")  # Clear old entries

            for attribute, entries in new_exclusions.items():
                deduped_entries = deduplicate_entries(entries)  # Deduplicate here

                for entry in deduped_entries:
                    # Ensure `remove_word` and `replace_word` are strings, or assign empty strings
                    remove_word = entry.get("remove", "")
                    replace_word = entry.get("replace", "")

                    # If `remove_word` or `replace_word` is None, make it an empty string
                    remove_word = remove_word.strip() if isinstance(remove_word, str) else ""
                    replace_word = replace_word.strip() if isinstance(replace_word, str) else ""

                    # Only save if `remove_word` is non-empty
                    if remove_word:
                        cursor.execute(
                            "INSERT INTO exclusion_settings (attribute, remove_word, replace_word) VALUES (?, ?, ?)",
                            (attribute, remove_word, replace_word)
                        )

            conn.commit()
            logging.info("Exclusions saved successfully.")
        return jsonify({"message": "Exclusions saved successfully!"})

    except Exception as e:
        logging.error("Error saving exclusions: %s", e)
        return jsonify({"message": "Error saving exclusions"}), 500
    

@app.route('/get_settings', methods=['GET'])
def get_exclusions():
    logging.info("Fetching exclusions from the database.")
    exclusions = {
        "title": [],
        "company": [],
        "location": [],
        "salary": [],
        "type": [],
        "description": []
    }
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT attribute, remove_word, replace_word FROM exclusion_settings")
        rows = cursor.fetchall()
        for attribute, remove_word, replace_word in rows:
            if attribute.lower() in exclusions:
                exclusions[attribute.lower()].append({"remove": remove_word, "replace": replace_word})
    
    logging.info("Exclusions loaded:", exclusions)
    return jsonify(exclusions)



@app.route('/scrape_jobs', methods=['POST'])
def scrape_jobs():
    try:
        country_id = int(request.form['country_id'])
        selected_city = request.form['city']
        num_jobs = int(request.form['num_jobs'])

        scraping_status["total"] = num_jobs
        scraping_status["completed"] = 0

        entry = next((entry for entry in entries if entry['id'] == country_id), None)
        if entry:
            # Fetch exclusions before starting scraping
            exclusions = fetch_exclusions_from_db()
            print("Exclusions loaded before scraping:", exclusions)  # Log exclusions for verification
            
            link = entry['link'] + selected_city
            
            # Wrap the function call in a thread
            scraping_thread = threading.Thread(target=run_scraping, args=(link, num_jobs, entry["country"], selected_city, exclusions))
            scraping_thread.start()
            
            return jsonify({"message": "Scraping has started!"})

    except Exception as e:
        print(f"Error starting scraping: {e}")
        return jsonify({"message": "Error starting scraping"}), 500

def apply_exclusions(text, exclusions):
    """Apply remove and replace logic to a given text based on exclusions."""
    original_text = text  # Keep the original text for comparison in logs
    for exclusion in exclusions:
        remove_word = exclusion.get("remove", "").strip()
        replace_word = exclusion.get("replace", "").strip()
        
        if remove_word:
            # Log each exclusion attempt
            print(f"Attempting to remove '{remove_word}' and replace with '{replace_word}' in '{text}'")
            # Use regex substitution to replace/remove case-insensitively
            # Apply replacement only if `remove_word` is found
            text = re.sub(rf"{re.escape(remove_word)}", replace_word, text, flags=re.IGNORECASE)
            print(f"Applied exclusion: '{remove_word}' -> '{replace_word}' | Result: '{text}'")
    
    print(f"Final processed text: '{text}' | Original text: '{original_text}'")
    return text




def run_scraping(link, num_jobs, country, city, exclusions):
    driver = None
    jobs = []  # Ensure jobs is initialized even if driver fails
    try:
        global scraping_status
        print("Exclusions to apply:", exclusions)  # Log the exclusions dictionary structure

        # Automatically download the correct ChromeDriver version
        chrome_driver_path = ChromeDriverManager().install()
        service = Service(chrome_driver_path)

        # Initialize WebDriver
        driver = webdriver.Chrome(service=service)

        scraping_status["total"] = num_jobs
        scraping_status["completed"] = 0

        print(f"Navigating to {link}")
        driver.get(link)
        time.sleep(2)

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

                # Log original title before applying exclusions
                print(f"Original Title: '{title}'")
                title = apply_exclusions(title, exclusions.get("Title", []))
                print(f"Processed Title: '{title}'")

                driver.execute_script("window.open(arguments[0], '_blank');", job_link)
                driver.switch_to.window(driver.window_handles[1])

                job_description = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#jobDescriptionText"))
                ).get_attribute('innerHTML')

                company = driver.find_element(By.CSS_SELECTOR, "div.css-hon9z8 a").text
                print(f"Original Company: '{company}'")
                company = apply_exclusions(company, exclusions.get("Company", []))
                print(f"Processed Company: '{company}'")

                try:
                    location = driver.find_element(By.CSS_SELECTOR, "div[data-testid='job-location']").text
                    print(f"Original Location: '{location}'")
                    location = apply_exclusions(location, exclusions.get("Location", []))
                    print(f"Processed Location: '{location}'")
                except NoSuchElementException:
                    location = "Location not found"

                try:
                    salary = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType span").text
                    job_type = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType span:nth-child(2)").text
                    print(f"Original Salary: '{salary}' | Original Type: '{job_type}'")
                    salary = apply_exclusions(salary, exclusions.get("Salary", []))
                    job_type = apply_exclusions(job_type, exclusions.get("Type", []))
                    print(f"Processed Salary: '{salary}' | Processed Type: '{job_type}'")
                except NoSuchElementException:
                    salary = "N/A"
                    job_type = "N/A"

                # Apply exclusions to job description
                print(f"Original Description: '{job_description[:50]}...'")  # Truncate for readability
                job_description = apply_exclusions(job_description, exclusions.get("Description", []))
                print(f"Processed Description: '{job_description[:50]}...'")

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
                print(f"Scraping progress: {scraping_status['completed']}/{scraping_status['total']}")

            except (NoSuchElementException, TimeoutException) as e:
                print(f"Error extracting job data for job {i + 1}: {e}")

    except Exception as e:
        print(f"Scraping failed in run_scraping: {e}")
    
    finally:
        # Ensure driver quits only if it was successfully initialized
        if driver:
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




def deduplicate_entries(entries):
    """Remove duplicate exclusion entries based on `remove_word` and `replace_word`."""
    unique_entries = []
    seen = set()
    for entry in entries:
        entry_tuple = (entry['remove'], entry['replace'])
        if entry_tuple not in seen:
            unique_entries.append(entry)
            seen.add(entry_tuple)
    return unique_entries

if __name__ == '__main__':
    app.run(debug=True, port=5001)
