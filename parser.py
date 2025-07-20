import requests
from bs4 import BeautifulSoup
import os
import time
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

def download_study_plan(url, output_dir="study_plans"):
    """
    Скачивает учебный план в формате PDF с указанного URL, используя Selenium для имитации клика по кнопке.

    Аргументы:
    url (str): URL страницы, с которой нужно скачать учебный план.
    output_dir (str): Директория для сохранения PDF-файлов.
    """
    print(f"Попытка загрузки учебного плана с: {url} с использованием Selenium.")

    # Настройка опций Chrome
    options = Options()
    options.add_argument("--headless")  # Запуск браузера в фоновом режиме (без графического интерфейса)
    options.add_argument("--no-sandbox") # Необходим для некоторых сред
    options.add_argument("--disable-dev-shm-usage") # Необходим для некоторых сред
    options.add_experimental_option("prefs", {
        "download.default_directory": os.path.abspath(output_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True # Открывать PDF во внешнем приложении, а не в браузере
    })

    # Убедитесь, что chromedriver.exe находится в вашем PATH или укажите полный путь к нему
    # service = Service(executable_path="/path/to/your/chromedriver") # Пример: service = Service("C:/chromedriver/chromedriver.exe")
    driver = None
    try:
        # Инициализация WebDriver
        driver = webdriver.Chrome(options=options) # Если chromedriver в PATH
        # driver = webdriver.Chrome(service=service, options=options) # Если указан путь к chromedriver

        driver.get(url)
        print(f"Страница загружена: {url}")

        # Попытка закрыть возможный баннер с согласием на использование файлов cookie
        try:
            # Ищем кнопку "Принять" или "Согласен" для cookie-баннера
            cookie_accept_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Принять') or contains(., 'Согласен')]"))
            )
            cookie_accept_button.click()
            print("Нажатa кнопка согласия на использование файлов cookie (если была).")
            time.sleep(1) # Даем время баннеру исчезнуть
        except TimeoutException:
            print("Баннер с согласием на использование файлов cookie не найден или не стал кликабельным.")
        except Exception as e:
            print(f"Ошибка при попытке закрыть cookie-баннер: {e}")

        # Ждем, пока кнопка "СКАЧАТЬ УЧЕБНЫЙ ПЛАН" станет кликабельной
        try:
            download_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Скачать учебный план')]"))
            )
            print("Кнопка 'Скачать учебный план' найдена и кликабельна.")
            
            # Прокручиваем элемент в видимую область
            driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
            time.sleep(1) # Даем время на прокрутку

            # Попытка клика
            try:
                download_button.click()
                print("Кнопка нажата стандартным способом.")
            except ElementClickInterceptedException:
                print("Стандартный клик перехвачен. Попытка клика через JavaScript.")
                driver.execute_script("arguments[0].click();", download_button)
                print("Кнопка нажата через JavaScript.")

            print("Ожидание загрузки PDF или открытия новой вкладки.")
            time.sleep(3) 

            # Проверяем, открылась ли новая вкладка/окно с PDF
            pdf_link = None
            original_window = driver.current_window_handle
            for window_handle in driver.window_handles:
                if window_handle != original_window:
                    driver.switch_to.window(window_handle)
                    current_url = driver.current_url
                    if current_url.lower().endswith('.pdf') and "exams" not in current_url.lower():
                        pdf_link = current_url
                        print(f"PDF-файл открылся в новой вкладке: {pdf_link}")
                        driver.close() # Закрываем новую вкладку
                        driver.switch_to.window(original_window) # Возвращаемся к исходной вкладке
                        break
            
            # Если PDF не открылся в новой вкладке, возможно, он скачался напрямую
            # В этом случае Selenium не может напрямую получить URL загруженного файла.
            # Мы можем попытаться найти ссылку на PDF в HTML после клика, если она появилась динамически.
            if not pdf_link:
                # Повторно парсим страницу после клика, чтобы найти потенциально динамически появившуюся ссылку
                updated_soup = BeautifulSoup(driver.page_source, 'html.parser')
                for a_tag in updated_soup.find_all('a', href=True):
                    potential_pdf_link = urljoin(url, a_tag['href'])
                    if potential_pdf_link.lower().endswith('.pdf') and "exams" not in potential_pdf_link.lower():
                        pdf_link = potential_pdf_link
                        print(f"Найдена PDF ссылка на обновленной странице: {pdf_link}")
                        break

            if pdf_link:
                # Создаем директорию, если ее нет
                os.makedirs(output_dir, exist_ok=True)

                # Определяем имя файла из URL, удаляя параметры запроса
                file_name = pdf_link.split('/')[-1]
                if '?' in file_name:
                    file_name = file_name.split('?')[0]
                
                file_path = os.path.join(output_dir, file_name)

                # Скачиваем PDF-файл с помощью requests (более надежно для больших файлов)
                pdf_response = requests.get(pdf_link, stream=True)
                pdf_response.raise_for_status()

                with open(file_path, 'wb') as f:
                    for chunk in pdf_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Учебный план успешно скачан и сохранен как: {file_path}")
                return file_path
            else:
                print(f"PDF ссылка на учебный план не найдена после клика по кнопке на странице: {url}")
                return None

        except TimeoutException:
            print(f"Таймаут: Кнопка 'Скачать учебный план' не найдена или не стала кликабельной на странице: {url}")
            return None
        except NoSuchElementException:
            print(f"Элемент не найден: Кнопка 'Скачать учебный план' не найдена на странице: {url}")
            return None

    except Exception as e:
        print(f"Произошла непредвиденная ошибка при использовании Selenium: {e}")
        return None
    finally:
        if driver:
            driver.quit() # Всегда закрываем браузер

if __name__ == "__main__":
    # URL-ы магистерских программ
    program_urls = [
        "https://abit.itmo.ru/program/master/ai",
        "https://abit.itmo.ru/program/master/ai_product"
    ]

    downloaded_files = []
    for url in program_urls:
        file = download_study_plan(url)
        if file:
            downloaded_files.append(file)

    if downloaded_files:
        print("\nВсе учебные планы, которые удалось скачать:")
        for f in downloaded_files:
            print(f)
    else:
        print("\nНе удалось скачать ни один учебный план.")
