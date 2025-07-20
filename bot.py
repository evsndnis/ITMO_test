import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv # Для загрузки переменных окружения из .env
import requests # Для HTTP-запросов к Gemini API
import json # Для работы с JSON-ответами
import PyPDF2 # Для извлечения текста из PDF

# Включите логирование для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
# Установите более низкий уровень логирования для httpx, чтобы избежать слишком большого количества сообщений
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Максимальная длина сообщения для Telegram (4096 символов), оставляем небольшой запас
TELEGRAM_MAX_MESSAGE_LENGTH = 4000 

# --- Функции для извлечения текста из PDF ---
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
# --- Конец функций для извлечения текста из PDF ---

# --- Вспомогательная функция для разделения длинных сообщений ---
async def send_long_message(update: Update, text: str) -> None:
    """
    Разделяет длинный текст на части и отправляет их как отдельные сообщения.
    """
    if len(text) <= TELEGRAM_MAX_MESSAGE_LENGTH:
        await update.message.reply_text(text)
        return

    chunks = []
    current_chunk = ""
    # Разделяем по абзацам или предложениям для сохранения смысла
    paragraphs = text.split('\n\n') 
    
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= TELEGRAM_MAX_MESSAGE_LENGTH: # +2 для \n\n
            current_chunk += (para + '\n\n')
        else:
            if current_chunk: # Добавляем предыдущий заполненный кусок
                chunks.append(current_chunk.strip())
            current_chunk = para + '\n\n' # Начинаем новый кусок
    
    if current_chunk: # Добавляем последний кусок
        chunks.append(current_chunk.strip())

    # Если абзацы слишком длинные, чтобы поместиться даже в один чанк,
    # то разбиваем их посимвольно
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > TELEGRAM_MAX_MESSAGE_LENGTH:
            # Разбиваем слишком длинные абзацы посимвольно
            for i in range(0, len(chunk), TELEGRAM_MAX_MESSAGE_LENGTH):
                final_chunks.append(chunk[i:i + TELEGRAM_MAX_MESSAGE_LENGTH])
        else:
            final_chunks.append(chunk)

    for i, chunk in enumerate(final_chunks):
        await update.message.reply_text(f"Часть {i+1}/{len(final_chunks)}:\n{chunk}")
        time.sleep(0.5) # Небольшая задержка между сообщениями, чтобы избежать флуда

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при получении команды /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Привет, {user.mention_html()}! Я чат-бот, который поможет тебе разобраться с магистерскими программами ИТМО. "
        "Задай мне вопрос по учебным планам или программам.",
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет сообщение с помощью при получении команды /help."""
    await update.message.reply_text("Я могу отвечать на вопросы по учебным планам и программам магистратуры ИТМО. Просто напиши свой вопрос.")

# --- Обработчик текстовых сообщений ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает текстовое сообщение пользователя, использует LLM для генерации ответа
    на основе содержимого учебных планов.
    """
    user_message = update.message.text
    logger.info(f"Получено сообщение от {update.effective_user.first_name}: {user_message}")

    # Получаем извлеченные тексты из bot_data
    study_plan_texts = context.bot_data.get('study_plan_texts', {})
    
    if not study_plan_texts:
        await update.message.reply_text("У меня пока нет информации об учебных планах. Пожалуйста, убедитесь, что PDF-файлы обработаны.")
        return

    # Объединяем все тексты учебных планов в одну строку для контекста LLM
    # В реальном приложении, если тексты очень большие, может потребоваться
    # более сложная логика для выбора релевантных частей текста (например, с помощью векторизации).
    full_context = "\n\n".join(study_plan_texts.values())

    # Формируем промпт для LLM
    # Важно: проинструктировать LLM отвечать только на основе предоставленного контекста
    prompt = (
        f"Ты чат-бот, который помогает абитуриентам разобраться в магистерских программах ИТМО. "
        f"Отвечай на вопросы только на основе предоставленного ниже текста учебных планов. "
        f"Если информация отсутствует в тексте, так и скажи, что не можешь ответить на этот вопрос на основе имеющихся данных. "
        f"Вот контекст из учебных планов:\n\n{full_context}\n\n"
        f"Вопрос абитуриента: {user_message}"
    )

    # Получаем API ключ Gemini из контекста
    gemini_api_key = context.bot_data.get('gemini_api_key')
    if not gemini_api_key:
        await update.message.reply_text("Ошибка: API ключ Gemini не настроен. Пожалуйста, обратитесь к администратору бота.")
        logger.error("API ключ Gemini не найден в bot_data.")
        return

    # Вызов Gemini API
    # Используем модель gemini-2.0-flash, как указано в инструкциях
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_api_key}"
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }

    response_text = "Извините, произошла ошибка при получении ответа от AI."
    try:
        logger.info(f"Отправка запроса к Gemini API. Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}") # Логируем payload
        # Используем requests для вызова API
        api_response = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        api_response.raise_for_status() # Вызывает исключение для ошибок HTTP (4xx или 5xx)
        
        result = api_response.json()
        
        # Проверяем структуру ответа от Gemini API
        if result and result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
            response_text = result['candidates'][0]['content']['parts'][0]['text']
        else:
            logger.warning(f"Неожиданная структура ответа от Gemini API: {result}")
            response_text = "Извините, я получил некорректный ответ от AI."

    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к Gemini API: {e}")
        if api_response is not None: # Проверяем, что api_response был получен
            logger.error(f"Текст ответа от API: {api_response.text}") # Логируем текст ответа
        response_text = "Извините, не удалось связаться с AI для получения ответа. Проверьте ваше интернет-соединение или API ключ."
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка при парсинге JSON ответа от Gemini API: {e}")
        response_text = "Извините, не удалось обработать ответ от AI. Возможно, проблема с форматом данных."
    except Exception as e:
        logger.error(f"Произошла непредвиденная ошибка при обработке сообщения: {e}")
        response_text = "Извините, произошла внутренняя ошибка."

    # Отправляем ответ, разделяя его на части, если он слишком длинный
    await send_long_message(update, response_text)

# --- Основная функция запуска бота ---

def main() -> None:
    """Запускает бота."""
    load_dotenv() # Загружаем переменные окружения из .env файла

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не установлена. Пожалуйста, установите ее в .env файле.")
        print("ОШИБКА: TELEGRAM_BOT_TOKEN не установлен. Бот не может быть запущен.")
        return
    
    if not GEMINI_API_KEY:
        logger.error("Переменная окружения GEMINI_API_KEY не установлена. Пожалуйста, установите ее в .env файле.")
        print("ОШИБКА: GEMINI_API_KEY не установлен. Бот не может быть запущен.")
        return

    # Создаем объект Application и передаем токен бота
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Загружаем извлеченные тексты из PDF при запуске бота
    print("Загрузка учебных планов...")
    study_plan_texts = process_study_plans()
    if not study_plan_texts:
        logger.warning("Не удалось загрузить учебные планы. Бот будет работать без контекста PDF.")
        print("ВНИМАНИЕ: Не удалось загрузить учебные планы. Бот не сможет отвечать на вопросы по ним.")
    else:
        print(f"Успешно загружено {len(study_plan_texts)} учебных планов.")
    
    # Сохраняем извлеченные тексты и API ключ в bot_data, чтобы они были доступны в обработчиках
    application.bot_data['study_plan_texts'] = study_plan_texts
    application.bot_data['gemini_api_key'] = GEMINI_API_KEY


    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Регистрируем обработчик для текстовых сообщений (кроме команд)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота (начинаем опрос обновлений от Telegram)
    print("Бот запущен. Ожидание сообщений...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
