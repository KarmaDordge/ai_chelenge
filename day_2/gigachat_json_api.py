"""
GigaChat API - Запросы с гарантированным JSON-форматом ответа

Этот модуль предоставляет функцию для отправки запросов к GigaChat API,
которые гарантированно возвращают ответ в строго заданном JSON-формате.
"""

import os
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# Загружаем переменные окружения
load_dotenv()


# Системный промпт для гарантированного JSON-формата
SYSTEM_PROMPT = """Ты - помощник, который ВСЕГДА отвечает ТОЛЬКО в формате JSON, без дополнительного текста.

КРИТИЧЕСКИ ВАЖНО:
- Твой ответ должен быть ТОЛЬКО валидным JSON-объектом
- НЕ добавляй никаких пояснений, комментариев или текста до или после JSON
- НЕ используй markdown-разметку (не заключай JSON в ```json блоки)
- Формат ответа ДОЛЖЕН быть строго следующим:

{
  "answer": "Полный текстовый ответ на вопрос пользователя",
  "key_points": ["Массив", "с", "ключевыми", "мыслями"],
  "sentiment": "neutral|positive|negative"
}

Правила:
1. "answer" - полный и развернутый ответ на вопрос пользователя
2. "key_points" - массив строк с ключевыми мыслями из ответа (минимум 3 пункта)
3. "sentiment" - один из трех вариантов: "neutral", "positive" или "negative"

Пример правильного ответа:
{"answer": "Искусственный интеллект в медицине...", "key_points": ["Точность диагностики", "Автоматизация процессов", "Персонализированное лечение"], "sentiment": "positive"}

Помни: твой ответ - это ТОЛЬКО JSON, ничего больше!"""


def get_gigachat_client() -> Optional[GigaChat]:
    """
    Инициализация клиента GigaChat API
    
    Returns:
        GigaChat клиент или None в случае ошибки
    """
    # Пробуем сначала GIGACHAT_AUTH_DATA, затем GIGACHAT_CREDENTIALS
    credentials = os.getenv("GIGACHAT_AUTH_DATA") or os.getenv("GIGACHAT_CREDENTIALS")
    
    if not credentials:
        raise ValueError(
            "Не найден ключ авторизации в переменных окружения.\n"
            "Установите GIGACHAT_AUTH_DATA или GIGACHAT_CREDENTIALS в .env файле."
        )
    
    try:
        client = GigaChat(
            credentials=credentials,
            verify_ssl_certs=False
        )
        client.__enter__()
        return client
    except Exception as e:
        raise ConnectionError(f"Не удалось подключиться к GigaChat API: {e}")


def validate_json_response(response_data: Dict[str, Any]) -> bool:
    """
    Валидация структуры JSON-ответа
    
    Args:
        response_data: Словарь с данными ответа
        
    Returns:
        True если структура корректна, иначе False
    """
    required_fields = ["answer", "key_points", "sentiment"]
    
    # Проверяем наличие всех обязательных полей
    if not all(field in response_data for field in required_fields):
        return False
    
    # Проверяем типы данных
    if not isinstance(response_data["answer"], str):
        return False
    
    if not isinstance(response_data["key_points"], list):
        return False
    
    if not all(isinstance(point, str) for point in response_data["key_points"]):
        return False
    
    # Проверяем sentiment
    valid_sentiments = ["neutral", "positive", "negative"]
    if response_data["sentiment"] not in valid_sentiments:
        return False
    
    return True


def clean_json_response(text: str) -> str:
    """
    Очистка текста от возможных markdown-разметки и лишнего текста
    
    Args:
        text: Исходный текст ответа
        
    Returns:
        Очищенный JSON-текст
    """
    # Убираем markdown-блоки кода
    text = text.strip()
    
    # Убираем ```json и ``` в начале и конце
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Пытаемся найти JSON объект в тексте
    # Ищем первую { и последнюю }
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
    
    return text


def send_json_request(user_message: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    Отправка запроса к GigaChat API с гарантированным JSON-форматом ответа
    
    Args:
        user_message: Вопрос пользователя
        max_retries: Максимальное количество попыток при ошибках парсинга
        
    Returns:
        Словарь с структурированным ответом:
        {
            "answer": str,
            "key_points": List[str],
            "sentiment": str
        }
        
    Raises:
        ValueError: Если не удалось получить валидный JSON после всех попыток
        ConnectionError: Если не удалось подключиться к API
    """
    client = None
    
    try:
        client = get_gigachat_client()
        
        if not client:
            raise ConnectionError("Не удалось инициализировать клиент GigaChat")
        
        # Формируем сообщения с системным промптом
        messages = [
            Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
            Messages(role=MessagesRole.USER, content=user_message)
        ]
        
        chat = Chat(messages=messages)
        
        # Отправляем запрос
        response = client.chat(chat)
        response_text = response.choices[0].message.content
        
        # Пытаемся распарсить JSON
        for attempt in range(max_retries):
            try:
                # Очищаем ответ от возможных артефактов
                cleaned_text = clean_json_response(response_text)
                
                # Парсим JSON
                json_data = json.loads(cleaned_text)
                
                # Валидируем структуру
                if validate_json_response(json_data):
                    return json_data
                else:
                    raise ValueError("Структура JSON не соответствует требованиям")
                    
            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    # Если не получилось распарсить, пробуем снова с более строгим промптом
                    retry_prompt = f"{SYSTEM_PROMPT}\n\nВАЖНО: Твой предыдущий ответ был неверным. Отвечай ТОЛЬКО JSON, без дополнительного текста!"
                    messages = [
                        Messages(role=MessagesRole.SYSTEM, content=retry_prompt),
                        Messages(role=MessagesRole.USER, content=user_message)
                    ]
                    chat = Chat(messages=messages)
                    response = client.chat(chat)
                    response_text = response.choices[0].message.content
                else:
                    raise ValueError(
                        f"Не удалось распарсить JSON после {max_retries} попыток. "
                        f"Ответ от API: {response_text[:200]}... "
                        f"Ошибка парсинга: {e}"
                    )
            except ValueError as e:
                if attempt < max_retries - 1:
                    # Пробуем снова с более строгим промптом
                    retry_prompt = f"{SYSTEM_PROMPT}\n\nОШИБКА: Твой ответ не соответствует требуемой структуре. Обязательно используй поля: answer (строка), key_points (массив строк), sentiment (neutral|positive|negative)"
                    messages = [
                        Messages(role=MessagesRole.SYSTEM, content=retry_prompt),
                        Messages(role=MessagesRole.USER, content=user_message)
                    ]
                    chat = Chat(messages=messages)
                    response = client.chat(chat)
                    response_text = response.choices[0].message.content
                else:
                    raise ValueError(
                        f"Не удалось получить валидный JSON после {max_retries} попыток. "
                        f"Ошибка валидации: {e}"
                    )
        
        # Этот код не должен выполниться, но на всякий случай
        raise ValueError("Не удалось получить валидный ответ")
        
    except Exception as e:
        raise
    finally:
        # Закрываем соединение
        if client:
            try:
                client.__exit__(None, None, None)
            except:
                pass


def main():
    """
    Пример использования функции send_json_request
    """
    # Тестовый запрос
    test_question = "Расскажи о преимуществах использования искусственного интеллекта в медицине."
    
    print("=" * 60)
    print("GigaChat API - Запрос с гарантированным JSON-форматом")
    print("=" * 60)
    print(f"\nВопрос: {test_question}\n")
    
    try:
        # Отправляем запрос
        print("Отправка запроса к GigaChat API...")
        result = send_json_request(test_question)
        
        # Выводим результат
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТ:")
        print("=" * 60)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n" + "=" * 60)
        print("РАСШИФРОВКА:")
        print("=" * 60)
        print(f"\nОтвет:\n{result['answer']}\n")
        print(f"Ключевые моменты:")
        for i, point in enumerate(result['key_points'], 1):
            print(f"  {i}. {point}")
        print(f"\nТональность: {result['sentiment']}")
        
    except ValueError as e:
        print(f"\n❌ Ошибка валидации: {e}")
    except ConnectionError as e:
        print(f"\n❌ Ошибка подключения: {e}")
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
