import pandas as pd
import os
import time
from datetime import date, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Configuration for Selenium WebDriver ---
# Use Chrome
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# Optional: To run without a visible browser window (headless mode)
# chrome_options = webdriver.ChromeOptions()
# chrome_options.add_argument("--headless")
# chrome_options.add_argument("--disable-gpu")
# chrome_options.add_argument("--window-size=1920,1080")
# driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)

# To run with a visible browser window
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))


# --- URL Template ---
BASE_URL_TEMPLATE = "https://racing.hkjc.com/racing/information/English/racing/LocalResults.aspx?RaceDate={date}"

# --- DYNAMIC DATE RANGE ---
# The script will iterate through all dates from START_DATE to END_DATE.
# Format: YYYY, M, D
START_DATE = date(2019, 1, 1)
END_DATE = date(2024, 12, 31)


# --- Helper Functions ---
def daterange(start_date, end_date):
    """Generator function to iterate through a range of dates."""
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)

def get_safe_text(element, by, value, default="N/A"):
    """Safely extracts text from an element, returning default if not found."""
    try:
        return element.find_element(by, value).text.strip()
    except NoSuchElementException:
        return default

def extract_horse_jockey_trainer_info(cell_element):
    """Extracts name and link for Horse, Jockey, or Trainer from a table cell."""
    name, link = "N/A", "N/A"
    try:
        link_element = cell_element.find_element(By.TAG_NAME, "a")
        name = link_element.text.strip()
        link = link_element.get_attribute("href")
    except NoSuchElementException:
        name = cell_element.text.strip()
    return name, link


# --- Main Scraping Logic ---
all_meets_data = []

# Iterate through each date in the specified range
for single_date in daterange(START_DATE, END_DATE):
    # Format the date as DD/MM/YYYY for the URL
    meet_date = single_date.strftime("%d/%m/%Y")
    print(f"\n--- Checking date: {meet_date} ---")

    # Generate a unique filename for the CSV, e.g., races_2019-12-29.csv
    formatted_date_for_filename = single_date.strftime("%Y-%m-%d")
    output_filename = f"races_{formatted_date_for_filename}.csv"

    if os.path.exists(output_filename):
        print(f"File {output_filename} already exists. Skipping this date.")
        continue

    initial_url = BASE_URL_TEMPLATE.format(date=meet_date)
    
    try:
        driver.get(initial_url)
        # Wait for either the race links or the 'no race' message to appear
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH, "//div[contains(@class, 'top_races')]//table | //div[contains(text(), 'No race meeting.')]"
            ))
        )
    except TimeoutException:
        print(f"Timeout loading page for {meet_date}. It might be a non-race day or a server issue. Skipping.")
        continue
    except Exception as e:
        print(f"An unexpected error occurred loading {initial_url}: {e}")
        continue

    # *** Check if the date is a non-race day ***
    try:
        no_race_meeting_div = driver.find_element(By.XPATH, "//div[contains(text(), 'No race meeting.')]")
        if no_race_meeting_div:
            print(f"No races on this date. Skipping.")
            time.sleep(1) # Brief pause
            continue
    except NoSuchElementException:
        # This is expected on a race day, so we proceed
        print(f"Race day confirmed. Proceeding with scraping...")
        pass

    # --- Start scraping if it is a race day ---
    meet_data_for_csv = []
    
    # Get links for all individual races on this meet date
    race_links_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'top_races')]//table//td/a[contains(@href, 'LocalResults.aspx')]")
    
    race_page_urls = {initial_url} # Start with the current page for the first race
    for elem in race_links_elements:
        href = elem.get_attribute("href")
        if href and "LocalResults.aspx" in href and "ResultsAll.aspx" not in href:
            race_page_urls.add(href)
    
    # *** CORRECTED SORTING: Sort URLs numerically by RaceNo ***
    sorted_race_urls = sorted(
        list(race_page_urls),
        key=lambda url: int(url.split("RaceNo=")[-1]) if "RaceNo=" in url and url.split("RaceNo=")[-1].isdigit() else 0
    )

    print(f"Found {len(sorted_race_urls)} race URLs for meet {meet_date}:")

    for race_url in sorted_race_urls:
        print(f"\nScraping Race URL: {race_url}")
        try:
            driver.get(race_url)
            performance_table_locator = (By.XPATH, "//div[@class='performance']/table[contains(@class, 'draggable')]")
            WebDriverWait(driver, 20).until(EC.presence_of_element_located(performance_table_locator))
        except TimeoutException:
            print(f"Timeout loading race page: {race_url}. Skipping this race.")
            continue

        # Extract general race information
        race_header_full, race_details_text, race_specific_name, race_going, race_course = ("N/A",) * 5
        try:
            race_info_element = driver.find_element(By.XPATH, "//div[contains(@class, 'race_tab')]/table")
            race_header_full = get_safe_text(race_info_element, By.XPATH, ".//thead/tr/td[1]")
            race_details_text = get_safe_text(race_info_element, By.XPATH, ".//tbody/tr[2]/td[1]")
            race_specific_name = get_safe_text(race_info_element, By.XPATH, ".//tbody/tr[3]/td[1]")
            race_going = get_safe_text(race_info_element, By.XPATH, ".//tbody/tr[2]/td[3]")
            race_course = get_safe_text(race_info_element, By.XPATH, ".//tbody/tr[3]/td[3]")
            print(f"  Race Header: {race_header_full}, Going: {race_going}, Course: {race_course}")
        except NoSuchElementException:
            print(f"Could not find general race info for {race_url}")

        # Extract horse results from the performance table
        try:
            performance_table = driver.find_element(*performance_table_locator)
            body_rows = performance_table.find_elements(By.XPATH, "./tbody/tr")
            
            for row in body_rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 12: continue

                placing = cols[0].text.strip()
                horse_name, horse_link = extract_horse_jockey_trainer_info(cols[2])
                
                # Combine all data into a dictionary
                horse_data = {
                    "MeetDate": meet_date,
                    "RaceURL": race_url,
                    "RaceHeader": race_header_full,
                    "RaceDetails": race_details_text,
                    "RaceSpecificName": race_specific_name,
                    "RaceGoing": race_going,
                    "RaceCourse": race_course,
                    "Placing": placing,
                    "HorseNo": cols[1].text.strip(),
                    "HorseName": horse_name,
                    "HorseLink": horse_link,
                    "JockeyName": extract_horse_jockey_trainer_info(cols[3])[0],
                    "JockeyLink": extract_horse_jockey_trainer_info(cols[3])[1],
                    "TrainerName": extract_horse_jockey_trainer_info(cols[4])[0],
                    "TrainerLink": extract_horse_jockey_trainer_info(cols[4])[1],
                    "ActualWt": cols[5].text.strip(),
                    "DeclarHorseWt": cols[6].text.strip(),
                    "Draw": cols[7].text.strip(),
                    "LBW": cols[8].text.strip(),
                    "RunningPosition": " ".join([rp.text.strip() for rp in cols[9].find_elements(By.XPATH, ".//div/div") if rp.text.strip()]),
                    "FinishTime": cols[10].text.strip(),
                    "WinOdds": cols[11].text.strip(),
                }
                meet_data_for_csv.append(horse_data)

            print(f"  Scraped {len(body_rows)} horses for this race.")
        except Exception as e:
            print(f"  Error scraping performance table for {race_url}: {e}")
        
        time.sleep(1) # Polite delay

    if meet_data_for_csv:
        df_meet = pd.DataFrame(meet_data_for_csv)
        df_meet.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"\nSuccessfully saved data for meet {meet_date} to {output_filename}")
        all_meets_data.extend(meet_data_for_csv)
    else:
        print(f"\nNo data was collected for meet {meet_date}, although it appeared to be a race day.")

# --- Cleanup ---
driver.quit()
print("\n--- Scraping process completed for the entire date range. ---")

# Optional: Create one large file with all results at the end
if all_meets_data:
    print("\nCreating a combined CSV file for all scraped dates...")
    df_all = pd.DataFrame(all_meets_data)
    df_all.to_csv("all_races_2019_to_2024.csv", index=False, encoding='utf-8-sig')
    print("Successfully saved all combined data to csv")