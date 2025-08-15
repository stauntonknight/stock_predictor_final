"""Morningstar Crawler for Monthly Newsletters"""

import os
import time
from enum import Enum

import google.generativeai as genai
from selenium.webdriver.common.keys import Keys
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# It's a good practice to load environment variables for API keys
load_dotenv()

# Configure the Gemini API
# Make sure you have GOOGLE_API_KEY in your .env file or set as an environment variable
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError(
        "GOOGLE_API_KEY not found. Please set it in your environment or a .env file."
    )
genai.configure(api_key=GEMINI_API_KEY)


class MorningstarCrawler:
    """Crawler for fetching stock newsletters from Morningstar."""

    class URLType(Enum):
        """Enumeration for URL types."""

        OPEN = 1
        CLICK = 2
        UNSUPPORTED = 3

    STOCK_LINK = "https://research-morningstar-com.ezproxy.sfpl.org/collections/767/stock-investor-publications"

    def __init__(self):
        """Initialize the crawler."""
        self.download_path = "/tmp/downloads"
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)
        options = Options()
        options.add_argument("--headless=new")  # Run in headless mode for automation
        options.add_argument("--no-sandbox")  # Disable GPU acceleration
        options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": self.download_path,
                "savefile.default_directory": self.download_path,
            },
        )
        self.driver = webdriver.Chrome(options=options)

    def login(self):
        """Logs into Morningstar using credentials from environment variables."""
        url = os.getenv("MORNINGSTAR_URL")
        print(url)
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "barcode"))
        )
        barcode_elem = self.driver.find_element(By.ID, "barcode")
        password_elem = self.driver.find_element(By.ID, "pin")
        barcode_elem.send_keys(os.getenv("MORNINGSTAR_LOGIN"))
        password_elem.send_keys(os.getenv("MORNINGSTAR_PASSWORD"))
        password_elem.send_keys(Keys.RETURN)
        print("Waiting for login...")
        _ = WebDriverWait(self.driver, 20).until(
            EC.presence_of_all_elements_located((By.ID, "site-nav__home"))
        )
        print("Logged in successfully.")

    def get_all_stocks(self):
        """Fetches all stocks from Morningstar."""
        url = "https://research-morningstar-com.ezproxy.sfpl.org/stocks"
        self._get_stocks(url)

    def _get_stocks(self, base_url) -> None:
        """Fetches stocks from Morningstar's model portfolios."""
        self.driver.get(base_url)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "investment-ideas__section-header")
            )
        )
        elements = self.driver.find_elements(By.CLASS_NAME, "mdc-investment-list-card")
        urls = []
        for element in elements:
            try:
                element = element.find_element(By.CLASS_NAME, "mdc-card__title")
                href = element.get_attribute("href")
                urls.append(href)
            except NoSuchElementException as e:
                print(f"Error finding element: {e}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
        url_types = list(map(self._analyze_url, urls))
        follow_up: list[str] = []
        print(urls, url_types)
        for each_url, url_type in zip(urls, url_types):
            if url_type == MorningstarCrawler.URLType.OPEN:
                self.driver.get(each_url)
                self._get_stock_details(class_name="pick-list__table-container")
            elif url_type == MorningstarCrawler.URLType.CLICK:
                follow_up.append(each_url)
            else:
                print(f"Unsupported URL {each_url}")

        self.click_all(base_url, follow_up)

    def click_all(self, base_url: str, urls: list[str]):
        """Click all URLs and get stock details."""

        def _internal_click(actual_url):
            elements = self.driver.find_elements(
                By.CLASS_NAME, "mdc-investment-list-card"
            )
            for element in elements:
                try:
                    element = element.find_element(By.CLASS_NAME, "mdc-card__title")
                    href = element.get_attribute("href")
                    if href == actual_url:
                        WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable(element))
                        element.send_keys(Keys.RETURN)
                        self._get_stock_details(
                            class_name="model-portfolio__table-container"
                        )
                        break
                except Exception as e:
                    print(f"Exception raised in internal_click {e}")
                    continue

        for url in urls:
            self.driver.get(base_url)
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "investment-ideas__section-header")
                )
            )
            # close the left panel to make it easier to navigate.
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "mds-navigation-panel-toggle-button"))
            )
            button = self.driver.find_element(By.ID,"mds-navigation-panel-toggle-button")
            button.click()
            # scroll the header into view.
            section_headers = self.driver.find_elements(By.CLASS_NAME,"investment-ideas__section-header")
            if len(section_headers) >= 2:
                print("Scrolling into view")
                self.driver.execute_script(
                    "arguments[0].scrollIntoView(true);", section_headers[1]
                )
            time.sleep(10)
            print(f"Looking up URL: {url}")
            _internal_click(url)

    def _analyze_url(self, url) -> URLType:
        if "pick-list" in url:
            return MorningstarCrawler.URLType.OPEN
        if "model-portfolio" in url:
            return MorningstarCrawler.URLType.CLICK
        return MorningstarCrawler.URLType.UNSUPPORTED

    def _get_stock_details(self, class_name: str = ""):
        """Fetches details of stocks from the current page."""
        try:
            print("Waiting for element with class:", class_name)
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, class_name))
            )
            print("Found element with class:", class_name)
            time.sleep(10)
            elem = self.driver.find_element(By.CLASS_NAME, class_name)
            thead = elem.find_element(By.TAG_NAME, "thead")
            ths = thead.find_elements(By.TAG_NAME, "th")
            interesting_indexes = {}
            filter_indexes = {}
            interesting_columns = set(
                ["Name", "Ticker", "Fair Value", "Price/Fair Value"]
            )
            # filter criteria for every column name and the values it can accept.
            filter_criteria: dict[str, set[str]] = {"Base Currency": set(["US Dollar"])}

            for i, th in enumerate(ths):
                if th.text.strip() in interesting_columns:
                    interesting_indexes[th.text.strip()] = i
                if th.text.strip() in filter_criteria:
                    filter_indexes[i] = th.text.strip()

            tbodies = elem.find_elements(By.TAG_NAME, "tbody")
            for tbody in tbodies:
                rows = tbody.find_elements(By.TAG_NAME, "tr")
                print(interesting_indexes)
                for row in rows:
                    tds = row.find_elements(By.CLASS_NAME, "mdc-table-cell")
                    if len(tds) != len(ths):
                        continue
                    filtered = False
                    for index, value in filter_indexes.items():
                        current_value = tds[index].text.strip()
                        if current_value not in filter_criteria[value]:
                            filtered = True
                            break
                    if filtered:
                        continue
                    stock_info = {}
                    for value, index in interesting_indexes.items():
                        if index < len(tds):
                            stock_info[value] = tds[index].text.strip()
                    print(stock_info)
        except Exception as e:
            print(f"An error occurred in stock fetching: {e}")

    def get_stock_newsletters(self):
        """Fetches stock newsletters."""
        self.driver.get(MorningstarCrawler.STOCK_LINK)
        WebDriverWait(self.driver, 10).until(EC.title_contains("Stock Investor"))
        elements = self.driver.find_elements(By.CLASS_NAME, "mdc-heading")
        print("Found elements:", len(elements))
        arr = []
        for element in elements:
            try:
                url = element.find_element(By.TAG_NAME, "a").get_attribute("href")
                text = element.text.strip()
                arr.append((url, text))
            except NoSuchElementException as _:
                pass
        downloads = []
        for url, text in arr:
            file_name = self._get_file_name(text) + ".pdf"
            print("searching for:", file_name)
            if os.path.exists(os.path.join(self.download_path, file_name)):
                print(f"File {file_name} already exists, skipping download.")
                continue
            self._download(url)
            downloads.append(self._rename_file(text + ".pdf", file_name))
        return downloads

    def _download(self, url):
        """Downloads the file from the given URL."""
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "article__article-download"))
        )
        print("Loaded page")
        elem = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "article__article-download"))
        )
        print("Element clickable")
        elem.click()
        print("downloaded")
        time.sleep(7)  # Wait for the download to complete

    def _rename_file(self, filename: str, new_filename: str):
        """Renames downloaded files based on their content."""
        original_path = os.path.join(self.download_path, filename)
        if not os.path.exists(original_path):
            original_path = os.path.join(self.download_path, filename.replace("-", ""))
        if not os.path.exists(original_path):
            print(f"File name mismatch expected {filename} but not found")
        os.rename(
            original_path,
            os.path.join(self.download_path, new_filename),
        )
        return new_filename

    def _get_file_name(self, text):
        """Generates a file name based on the text."""
        return "".join(text.split(" ")[-2:])


def main():
    """Main function to orchestrate the process."""

    morning_star = MorningstarCrawler()
    try:
        morning_star.login()
        morning_star.get_all_stocks()
        # downloads = morning_star.get_stock_newsletters()
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        morning_star.driver.quit()


if __name__ == "__main__":
    main()
