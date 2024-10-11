Job Scraping Tool

A Flask-based web application for scraping job listings, with configurable exclusion criteria for job attributes like title, company, location, salary, type, and description. This tool uses Selenium for web scraping and SQLite for data storage, offering a user-friendly HTML dashboard to manage country and city entries, exclusion settings, and daily scraping summaries.

Key Features

	•	Job Exclusion Settings: Define specific words or phrases for exclusion across job attributes to filter out unwanted data.
	•	Country & City Management: Manage target countries and cities for job scraping via a streamlined dashboard.
	•	Scraping Summary: View daily summaries of jobs scraped by country and city, with file view and delete options.
	•	Data Storage: Stores job data in SQLite with CSV export for easy data handling and analysis.

Tech Stack

	•	Backend: Flask, SQLite
	•	Scraping: Selenium
	•	Frontend: HTML, JavaScript (jQuery)

Setup

	1.	Clone the repository.
	2.	Install dependencies from requirements.txt.
	3.	Run the Flask application.

Usage

	1.	Open the dashboard in a browser.
	2.	Set exclusions and start a scraping job.
	3.	View and manage scraped job listings with ease.