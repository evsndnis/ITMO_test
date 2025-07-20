import os
import PyPDF2
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Извлекает весь текст из PDF-файла.

    Аргументы:
    pdf_path (str): Путь к PDF-файлу.

    Возвращает:
    str: Весь извлеченный текст из PDF.
    """
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = len(reader.pages)
            for page_num in range(num_pages):
                page = reader.pages[page_num]
                text += page.extract_text()
        logger.info(f"Текст успешно извлечен из {pdf_path}")
    except FileNotFoundError:
        logger.error(f"Ошибка: Файл не найден по пути {pdf_path}")
    except Exception as e:
        logger.error(f"Ошибка при извлечении текста из {pdf_path}: {e}")
    return text

def process_study_plans(pdf_dir="study_plans") -> dict:
    """
    Обрабатывает все PDF-файлы в указанной директории и извлекает из них текст.

    Аргументы:
    pdf_dir (str): Директория, содержащая PDF-файлы учебных планов.

    Возвращает:
    dict: Словарь, где ключами являются имена файлов PDF, а значениями - извлеченный текст.
    """
    extracted_texts = {}
    if not os.path.exists(pdf_dir):
        logger.warning(f"Директория {pdf_dir} не найдена. Убедитесь, что PDF-файлы скачаны.")
        return extracted_texts

    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(pdf_dir, filename)
            logger.info(f"Обработка файла: {pdf_path}")
            text = extract_text_from_pdf(pdf_path)
            if text:
                extracted_texts[filename] = text
            else:
                logger.warning(f"Не удалось извлечь текст из файла: {filename}")
    return extracted_texts

if __name__ == "__main__":
    # Убедитесь, что папка 'study_plans' существует и содержит скачанные PDF
    # Если вы запускаете этот скрипт отдельно, убедитесь, что parser.py уже скачал файлы.
    
    print("Начинаем извлечение текста из PDF-файлов...")
    study_plan_texts = process_study_plans()

    if study_plan_texts:
        print("\nТекст успешно извлечен из следующих файлов:")
        for filename, text_content in study_plan_texts.items():
            print(f"- {filename} (длина текста: {len(text_content)} символов)")
            # Для демонстрации вы можете распечатать часть текста
            # print("--- Начало текста ---")
            # print(text_content[:500]) # Печатаем первые 500 символов
            # print("--- Конец текста ---")
    else:
        print("\nНе удалось извлечь текст ни из одного PDF-файла. Проверьте директорию и файлы.")

