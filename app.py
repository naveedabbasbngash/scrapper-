import requests
from bs4 import BeautifulSoup

# Specify the Indeed URL you want to scrape
url = "https://uk.indeed.com/jobs?q=&l=London%2C+Greater+London&from=searchOnHP&vjk=ce8512cce44fb7d5"

# Function to scrape job data from the page
def scrape_indeed_jobs(url):
    # Send a request to the webpage
    response = requests.get(url)
    
    # Check if request was successful
    if response.status_code == 200:
        # Parse the page content
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find the job listings
        job_listings = soup.find_all("div", class_="job_seen_beacon")
        
        jobs = []
        
        for job in job_listings:
            title = job.find("h2", class_="jobTitle").text.strip() if job.find("h2", class_="jobTitle") else "N/A"
            company = job.find("span", class_="companyName").text.strip() if job.find("span", class_="companyName") else "N/A"
            location = job.find("div", class_="companyLocation").text.strip() if job.find("div", class_="companyLocation") else "N/A"
            summary = job.find("div", class_="job-snippet").text.strip() if job.find("div", class_="job-snippet") else "N/A"
            
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "summary": summary
            })
        
        return jobs
    else:
        return None

# Run the function
job_data = scrape_indeed_jobs(url)

if job_data:
    for job in job_data:
        print(f"Title: {job['title']}\nCompany: {job['company']}\nLocation: {job['location']}\nSummary: {job['summary']}\n\n")
else:
    print("Failed to retrieve data")
