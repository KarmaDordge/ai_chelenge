"""
GigaChat AI - Чат-бот с графическим интерфейсом и гарантированным JSON-форматом

Для использования:
1. Установите зависимости: pip install gigachat python-dotenv
2. Создайте файл .env с GIGACHAT_CREDENTIALS или GIGACHAT_AUTH_DATA
3. Запустите: python chatbot_gui.py
"""

import os
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox
from threading import Thread
from datetime import datetime
from typing import Dict, Any
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


def validate_json_response(response_data: Dict[str, Any]) -> bool:
    """Валидация структуры JSON-ответа"""
    required_fields = ["answer", "key_points", "sentiment"]
    
    if not all(field in response_data for field in required_fields):
        return False
    
    if not isinstance(response_data["answer"], str):
        return False
    
    if not isinstance(response_data["key_points"], list):
        return False
    
    if not all(isinstance(point, str) for point in response_data["key_points"]):
        return False
    
    valid_sentiments = ["neutral", "positive", "negative"]
    if response_data["sentiment"] not in valid_sentiments:
        return False
    
    return True


def clean_json_response(text: str) -> str:
    """Очистка текста от возможной markdown-разметки и лишнего текста"""
    text = text.strip()
    
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
    
    return text


def send_json_request(client: GigaChat, user_message: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    Отправка запроса к GigaChat API с гарантированным JSON-форматом ответа
    
    Args:
        client: GigaChat клиент
        user_message: Вопрос пользователя
        max_retries: Максимальное количество попыток при ошибках парсинга
        
    Returns:
        Словарь с структурированным ответом
    """
    if not client:
        raise ConnectionError("Клиент GigaChat не инициализирован")
    
    # Формируем сообщения с системным промптом
    messages = [
        Messages(role=MessagesRole.SYSTEM, content=SYSTEM_PROMPT),
        Messages(role=MessagesRole.USER, content=user_message)
    ]
    
    chat = Chat(messages=messages)
    response_text = None
    
    # Отправляем запрос с повторными попытками
    for attempt in range(max_retries):
        try:
            # Отправляем запрос
            response = client.chat(chat)
            response_text = response.choices[0].message.content
            
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
                # Пробуем снова с более строгим промптом
                retry_prompt = f"{SYSTEM_PROMPT}\n\nВАЖНО: Твой предыдущий ответ был неверным. Отвечай ТОЛЬКО JSON, без дополнительного текста!"
                messages = [
                    Messages(role=MessagesRole.SYSTEM, content=retry_prompt),
                    Messages(role=MessagesRole.USER, content=user_message)
                ]
                chat = Chat(messages=messages)
            else:
                raise ValueError(
                    f"Не удалось распарсить JSON после {max_retries} попыток. "
                    f"Ответ от API: {response_text[:200] if response_text else 'Нет ответа'}... "
                    f"Ошибка парсинга: {e}"
                )
        except ValueError as e:
            if "Структура JSON" in str(e) and attempt < max_retries - 1:
                # Пробуем снова с более строгим промптом
                retry_prompt = f"{SYSTEM_PROMPT}\n\nОШИБКА: Твой ответ не соответствует требуемой структуре. Обязательно используй поля: answer (строка), key_points (массив строк), sentiment (neutral|positive|negative)"
                messages = [
                    Messages(role=MessagesRole.SYSTEM, content=retry_prompt),
                    Messages(role=MessagesRole.USER, content=user_message)
                ]
                chat = Chat(messages=messages)
            else:
                raise
    
    raise ValueError("Не удалось получить валидный ответ после всех попыток")


class ChatBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GigaChat AI")
        self.root.geometry("700x700")
        self.root.configure(bg="#0066cc")
        
        # Инициализация GigaChat клиента
        self.giga_client = None
        self.last_json_response = None  # Храним последний JSON-ответ
        self.init_gigachat()
        
        # Создание интерфейса
        self.create_widgets()
        
    def init_gigachat(self):
        """Инициализация GigaChat клиента"""
        # Пробуем сначала GIGACHAT_AUTH_DATA, затем GIGACHAT_CREDENTIALS
        credentials = os.getenv("GIGACHAT_AUTH_DATA") or os.getenv("GIGACHAT_CREDENTIALS")
        
        if not credentials:
            messagebox.showerror(
                "Ошибка", 
                "Не найден ключ авторизации в переменных окружения.\n\n"
                "Создайте файл .env в корне проекта со следующим содержимым:\n"
                "GIGACHAT_CREDENTIALS=ваш_ключ_авторизации\n"
                "или\n"
                "GIGACHAT_AUTH_DATA=ваш_ключ_авторизации"
            )
            return
        
        try:
            self.giga_client = GigaChat(
                credentials=credentials, 
                verify_ssl_certs=False
            )
            self.giga_client.__enter__()
        except Exception as e:
            messagebox.showerror("Ошибка подключения", f"Не удалось подключиться к GigaChat API:\n{e}")
            self.giga_client = None
    
    def create_widgets(self):
        """Создание элементов интерфейса"""
        
        # Заголовок с кнопкой показа JSON
        header_frame = tk.Frame(self.root, bg="#0066cc")
        header_frame.pack(fill=tk.X)
        
        title_label = tk.Label(
            header_frame, 
            text="GigaChat AI Чат-бот (JSON формат)",
            font=("Arial", 16, "bold"),
            bg="#0066cc",
            fg="white",
            pady=15
        )
        title_label.pack(side=tk.LEFT, padx=20)
        
        # Кнопка показа JSON
        self.show_json_button = tk.Button(
            header_frame,
            text="📋 Показать JSON",
            command=self.show_json_window,
            font=("Arial", 10),
            bg="#ffffff",
            fg="#0066cc",
            activebackground="#e0e0e0",
            padx=10,
            pady=5,
            relief=tk.RAISED,
            state=tk.DISABLED  # Неактивна пока нет JSON
        )
        self.show_json_button.pack(side=tk.RIGHT, padx=20, pady=10)
        
        # Область с ответами бота
        self.chat_display = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            font=("Arial", 11),
            state=tk.DISABLED,
            bg="#ffffff",
            fg="#000000",
            padx=15,
            pady=15,
            borderwidth=0,
            highlightthickness=0
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Настройка тегов для форматирования
        self.chat_display.tag_config("user_tag", foreground="#0066cc", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("bot_tag", foreground="#28a745", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("error_tag", foreground="#dc3545", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("key_point_tag", foreground="#6c757d", font=("Arial", 10, "italic"))
        self.chat_display.tag_config("sentiment_tag", foreground="#17a2b8", font=("Arial", 10, "bold"))
        
        # Приветственное сообщение
        if self.giga_client:
            self.add_message("bot", "Привет! Я GigaChat AI. Готов помочь вам с любыми вопросами!\n\nОтветы будут в структурированном JSON-формате с ключевыми моментами и тональностью.")
        else:
            self.add_message("error", "Ошибка: не удалось подключиться к GigaChat API")
        
        # Фрейм для ввода
        input_frame = tk.Frame(self.root, bg="#0066cc")
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Прямоугольная область для ввода вопроса
        self.message_entry = tk.Text(
            input_frame,
            height=4,
            font=("Arial", 12),
            wrap=tk.WORD,
            bg="#ffffff",
            fg="#000000",
            borderwidth=2,
            relief=tk.SOLID,
            highlightthickness=0,
            insertbackground="#0066cc",
            selectbackground="#0066cc",
            selectforeground="white",
            padx=8,
            pady=8
        )
        self.message_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Кнопка Отправить
        self.send_button = tk.Button(
            input_frame,
            text="Отправить",
            command=self.send_message,
            font=("Arial", 13, "bold"),
            bg="#ffffff",
            fg="#000000",
            activebackground="#e0e0e0",
            activeforeground="#000000",
            padx=25,
            pady=10,
            relief=tk.RAISED,
            borderwidth=2,
            cursor="hand2",
            state=tk.DISABLED if not self.giga_client else tk.NORMAL
        )
        self.send_button.pack(side=tk.RIGHT)
        
        # Привязка Enter для отправки (Ctrl+Enter, так как обычный Enter переносит строку)
        self.message_entry.bind('<Control-Return>', lambda e: self.send_message())
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def add_message(self, sender, message):
        """Добавление сообщения в чат"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Время
        time_str = datetime.now().strftime("%H:%M")
        self.chat_display.insert(tk.END, f"[{time_str}] ")
        
        # Отправитель
        if sender == "user":
            self.chat_display.insert(tk.END, "Вы: ", "user_tag")
        elif sender == "bot":
            self.chat_display.insert(tk.END, "Бот: ", "bot_tag")
        elif sender == "error":
            self.chat_display.insert(tk.END, "Ошибка: ", "error_tag")
        
        # Сообщение
        self.chat_display.insert(tk.END, f"{message}\n\n")
        
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
    
    def add_json_response(self, json_data: Dict[str, Any]):
        """Добавление структурированного JSON-ответа в чат"""
        self.chat_display.config(state=tk.NORMAL)
        
        # Время
        time_str = datetime.now().strftime("%H:%M")
        self.chat_display.insert(tk.END, f"[{time_str}] ")
        self.chat_display.insert(tk.END, "Бот: ", "bot_tag")
        
        # Основной ответ
        self.chat_display.insert(tk.END, f"{json_data['answer']}\n\n")
        
        # Ключевые моменты
        if json_data.get('key_points'):
            self.chat_display.insert(tk.END, "Ключевые моменты:\n", "bot_tag")
            for i, point in enumerate(json_data['key_points'], 1):
                self.chat_display.insert(tk.END, f"  • {point}\n", "key_point_tag")
            self.chat_display.insert(tk.END, "\n")
        
        # Тональность
        sentiment_text = json_data.get('sentiment', 'neutral')
        sentiment_ru = {"positive": "Положительная", "negative": "Отрицательная", "neutral": "Нейтральная"}.get(sentiment_text, sentiment_text)
        self.chat_display.insert(tk.END, f"Тональность: ", "bot_tag")
        self.chat_display.insert(tk.END, f"{sentiment_ru}\n\n", "sentiment_tag")
        
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
    
    def send_message(self):
        """Отправка сообщения боту"""
        if not self.giga_client:
            return
        
        message = self.message_entry.get("1.0", tk.END).strip()
        
        if not message:
            return
        
        # Очищаем поле ввода
        self.message_entry.delete("1.0", tk.END)
        
        # Добавляем сообщение пользователя
        self.add_message("user", message)
        
        # Блокируем элементы
        self.send_button.config(state=tk.DISABLED, text="Отправка...")
        self.message_entry.config(state=tk.DISABLED)
        
        # Запускаем запрос в отдельном потоке
        Thread(target=self.get_bot_response, args=(message,), daemon=True).start()
    
    def get_bot_response(self, user_message):
        """Получение ответа от бота в JSON-формате"""
        try:
            json_response = send_json_request(self.giga_client, user_message)
            
            # Обновляем UI в главном потоке
            self.root.after(0, lambda: self.display_json_response(json_response))
            
        except ValueError as e:
            error_msg = f"Ошибка валидации JSON: {str(e)}"
            self.root.after(0, lambda: self.display_error(error_msg))
        except ConnectionError as e:
            error_msg = f"Ошибка подключения: {str(e)}"
            self.root.after(0, lambda: self.display_error(error_msg))
        except Exception as e:
            error_msg = f"Произошла ошибка: {str(e)}"
            self.root.after(0, lambda: self.display_error(error_msg))
    
    def display_json_response(self, json_data: Dict[str, Any]):
        """Отображение структурированного ответа"""
        # Сохраняем JSON для показа
        self.last_json_response = json_data
        self.show_json_button.config(state=tk.NORMAL)  # Активируем кнопку
        
        self.add_json_response(json_data)
        self.send_button.config(state=tk.NORMAL, text="Отправить")
        self.message_entry.config(state=tk.NORMAL)
        self.message_entry.focus()
    
    def show_json_window(self):
        """Показ оригинального JSON в отдельном окне"""
        if not self.last_json_response:
            messagebox.showinfo("Информация", "Нет сохраненного JSON-ответа")
            return
        
        # Создаем новое окно
        json_window = tk.Toplevel(self.root)
        json_window.title("Оригинальный JSON ответ")
        json_window.geometry("600x500")
        json_window.configure(bg="#f8f9fa")
        
        # Заголовок
        header_label = tk.Label(
            json_window,
            text="Оригинальный JSON ответ",
            font=("Arial", 14, "bold"),
            bg="#f8f9fa",
            fg="#333333",
            pady=10
        )
        header_label.pack(fill=tk.X)
        
        # Текстовое поле с JSON
        json_text = scrolledtext.ScrolledText(
            json_window,
            wrap=tk.NONE,
            font=("Courier New", 11),
            bg="#ffffff",
            fg="#000000",
            padx=15,
            pady=15,
            relief=tk.SOLID,
            borderwidth=1
        )
        json_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Форматируем JSON с отступами
        formatted_json = json.dumps(self.last_json_response, ensure_ascii=False, indent=2)
        json_text.insert("1.0", formatted_json)
        json_text.config(state=tk.DISABLED)
        
        # Кнопка копирования
        def copy_json():
            json_window.clipboard_clear()
            json_window.clipboard_append(formatted_json)
            messagebox.showinfo("Успех", "JSON скопирован в буфер обмена!")
        
        # Фрейм для кнопок
        button_frame = tk.Frame(json_window, bg="#f8f9fa")
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        copy_button = tk.Button(
            button_frame,
            text="📋 Копировать JSON",
            command=copy_json,
            font=("Arial", 10, "bold"),
            bg="#28a745",
            fg="white",
            activebackground="#218838",
            padx=15,
            pady=5
        )
        copy_button.pack(side=tk.LEFT, padx=5)
        
        close_button = tk.Button(
            button_frame,
            text="Закрыть",
            command=json_window.destroy,
            font=("Arial", 10),
            bg="#6c757d",
            fg="white",
            activebackground="#5a6268",
            padx=15,
            pady=5
        )
        close_button.pack(side=tk.RIGHT, padx=5)
    
    def display_error(self, error_msg):
        """Отображение ошибки"""
        self.add_message("error", error_msg)
        self.send_button.config(state=tk.NORMAL, text="Отправить")
        self.message_entry.config(state=tk.NORMAL)
        self.message_entry.focus()
    
    def on_closing(self):
        """Обработка закрытия приложения"""
        if self.giga_client:
            try:
                self.giga_client.__exit__(None, None, None)
            except:
                pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = ChatBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
