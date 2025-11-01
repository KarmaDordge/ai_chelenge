"""
GigaChat AI - Чат-бот с графическим интерфейсом

Для использования:
1. Установите зависимости: pip install gigachat python-dotenv
2. Создайте файл .env с GIGACHAT_CREDENTIALS
3. Запустите: python chatbot_gui.py
"""

import os
import tkinter as tk
from tkinter import scrolledtext, messagebox
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv
from gigachat import GigaChat

# Загружаем переменные окружения
load_dotenv()


class ChatBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("GigaChat AI")
        self.root.geometry("700x600")
        self.root.configure(bg="#0066cc")
        
        # Инициализация GigaChat клиента
        self.giga_client = None
        self.init_gigachat()
        
        # Создание интерфейса
        self.create_widgets()
        
    def init_gigachat(self):
        """Инициализация GigaChat клиента"""
        credentials = os.getenv("GIGACHAT_CREDENTIALS")
        
        if not credentials:
            messagebox.showerror(
                "Ошибка", 
                "Не найден GIGACHAT_CREDENTIALS в переменных окружения.\n\n"
                "Создайте файл .env в корне проекта со следующим содержимым:\n"
                "GIGACHAT_CREDENTIALS=ваш_ключ_авторизации"
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
        
        # Заголовок
        title_label = tk.Label(
            self.root, 
            text="GigaChat AI Чат-бот",
            font=("Arial", 16, "bold"),
            bg="#0066cc",
            fg="white",
            pady=15
        )
        title_label.pack(fill=tk.X)
        
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
        
        # Приветственное сообщение
        if self.giga_client:
            self.add_message("bot", "Привет! Я GigaChat AI. Готов помочь вам с любыми вопросами!")
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
        
        # Настройка тегов
        self.chat_display.tag_config("user_tag", foreground="#0066cc", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("bot_tag", foreground="#28a745", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("error_tag", foreground="#dc3545", font=("Arial", 11, "bold"))
        
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
        """Получение ответа от бота"""
        try:
            response = self.giga_client.chat(user_message)
            bot_message = response.choices[0].message.content
            
            # Обновляем UI в главном потоке
            self.root.after(0, lambda: self.display_response(bot_message))
            
        except Exception as e:
            error_msg = f"Ошибка: {str(e)}"
            self.root.after(0, lambda: self.display_error(error_msg))
    
    def display_response(self, message):
        """Отображение ответа"""
        self.add_message("bot", message)
        self.send_button.config(state=tk.NORMAL, text="Отправить")
        self.message_entry.config(state=tk.NORMAL)
        self.message_entry.focus()
    
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
