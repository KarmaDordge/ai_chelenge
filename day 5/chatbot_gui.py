"""
GigaChat AI - Агент-архитектор данных для проектирования DWH

Агент собирает информацию от пользователя и создает техническое задание
на разработку хранилища данных (DWH).

Для использования:
1. Установите зависимости: pip install gigachat python-dotenv
2. Создайте файл .env с GIGACHAT_CREDENTIALS
3. Запустите: python chatbot_gui.py
"""

import os
import json
import tkinter as tk
from tkinter import scrolledtext, messagebox
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole
from collections import OrderedDict

# Загружаем переменные окружения
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
PROMPTS_FILE_PATH = os.path.join(CONFIG_DIR, "preset_prompts.json")
PROMPT_NAMES_FILE_PATH = os.path.join(CONFIG_DIR, "preset_prompt_names.json")

DEFAULT_PRESET_PROMPTS = OrderedDict({
    "no_settings": "Ты — полезный AI-ассистент. Помогай пользователю решать его задачи максимально эффективно."
})

DEFAULT_PRESET_NAMES = OrderedDict({
    "no_settings": "Без настроек"
})

DEFAULT_PRESET_KEY = "no_settings"

# Температура по умолчанию
DEFAULT_TEMPERATURE = 0.6


def load_json_mapping(file_path: str) -> OrderedDict:
    if not os.path.exists(file_path):
        return OrderedDict()
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
            if isinstance(data, dict):
                return OrderedDict(data)
    except Exception:
        pass
    return OrderedDict()


def load_preset_definitions() -> OrderedDict:
    prompts = OrderedDict(DEFAULT_PRESET_PROMPTS)
    prompt_names = OrderedDict(DEFAULT_PRESET_NAMES)

    file_prompts = load_json_mapping(PROMPTS_FILE_PATH)
    file_names = load_json_mapping(PROMPT_NAMES_FILE_PATH)

    if file_prompts:
        prompts = file_prompts
    if file_names:
        prompt_names = file_names

    available_keys = [key for key in prompt_names if key in prompts]
    presets = OrderedDict()
    for key in available_keys:
        presets[key] = {
            "name": prompt_names[key],
            "prompt": prompts[key]
        }

    return presets


class ChatBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Агент-архитектор данных DWH")
        self.root.geometry("800x700")
        self.root.configure(bg="#0066cc")
        self.configure_mac_integration()
        
        # Загрузка доступных пресетов (названия и промпты)
        self.presets = load_preset_definitions()
        if not self.presets:
            messagebox.showwarning(
                "Предустановки недоступны",
                "Не удалось загрузить предустановленные промпты. "
                "Будет использован промпт по умолчанию."
            )
            self.presets = OrderedDict({
                key: {"name": name, "prompt": DEFAULT_PRESET_PROMPTS[key]}
                for key, name in DEFAULT_PRESET_NAMES.items()
                if key in DEFAULT_PRESET_PROMPTS
            })
        self.current_preset_key = DEFAULT_PRESET_KEY if DEFAULT_PRESET_KEY in self.presets else next(iter(self.presets))
        
        # История диалога для контекста
        self.conversation_history = []
        
        # Текущий промпт
        self.current_prompt = self.presets[self.current_preset_key]["prompt"]
        self.current_prompt_name = self.presets[self.current_preset_key]["name"]
        
        # Текущая модель (по умолчанию GigaChat Lite)
        self.current_model = "GigaChat"  # GigaChat Lite по умолчанию
        
        # Температура выборки для генерации ответов
        self.temperature = DEFAULT_TEMPERATURE
        
        # Флаги запросов к GigaChat (отключаем кеширование ответов)
        self.request_flags = ["no_cache"]
        
        # Инициализация GigaChat клиента
        self.giga_client = None
        self.init_gigachat()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Инициализация диалога с системным промптом
        if self.giga_client:
            self.initialize_conversation()
        
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
    
    def initialize_conversation(self):
        """Инициализация диалога с системным промптом"""
        # Добавляем системное сообщение в историю
        self.conversation_history = [
            Messages(role=MessagesRole.SYSTEM, content=self.current_prompt)
        ]
        
        # Отправляем приветственное сообщение от агента
        Thread(target=self.get_initial_greeting, daemon=True).start()
    
    def get_initial_greeting(self):
        """Получение приветственного сообщения от агента"""
        try:
            # Универсальное приветственное сообщение, которое не навязывает роль
            greeting_message = "Привет! Представься и начни диалог."
            
            # Создаем чат с системным промптом и запросом на приветствие
            messages = self.conversation_history + [
                Messages(role=MessagesRole.USER, content=greeting_message)
            ]
            chat = Chat(
                messages=messages,
                model=self.current_model,
                temperature=self.temperature,
                flags=self.request_flags
            )
            
            response = self.giga_client.chat(chat)
            greeting = response.choices[0].message.content
            
            # Обновляем историю
            self.conversation_history.append(Messages(role=MessagesRole.USER, content=greeting_message))
            self.conversation_history.append(Messages(role=MessagesRole.ASSISTANT, content=greeting))
            
            # Обновляем UI в главном потоке
            self.root.after(0, lambda: self.display_response(greeting))
            
        except Exception as e:
            error_msg = f"Ошибка при инициализации: {str(e)}"
            self.root.after(0, lambda: self.display_error(error_msg))
    
    def create_widgets(self):
        """Создание элементов интерфейса"""
        
        # Заголовок с кнопкой настроек
        header_frame = tk.Frame(self.root, bg="#0066cc")
        header_frame.pack(fill=tk.X)
        
        title_label = tk.Label(
            header_frame, 
            text="🏗️ Агент-архитектор данных DWH",
            font=("Arial", 16, "bold"),
            bg="#0066cc",
            fg="white",
            pady=15
        )
        title_label.pack(side=tk.LEFT, padx=20)
        
        # Кнопка настроек
        settings_button = tk.Button(
            header_frame,
            text="⚙️ Настройки",
            command=self.open_settings,
            font=("Arial", 10),
            bg="#ffffff",
            fg="#0066cc",
            activebackground="#e0e0e0",
            padx=10,
            pady=5,
            relief=tk.RAISED
        )
        settings_button.pack(side=tk.RIGHT, padx=20, pady=10)
        
        # Информационная панель
        model_display = "Pro" if self.current_model == "GigaChat-Pro" else "Lite"
        info_label = tk.Label(
            self.root,
            text=f"Режим: {self.current_prompt_name} | Модель: {model_display} | Температура: {self.temperature:.2f}",
            font=("Arial", 9, "italic"),
            bg="#0066cc",
            fg="#e0e0e0",
            pady=5
        )
        info_label.pack(fill=tk.X)
        self.info_label = info_label  # Сохраняем ссылку для обновления
        
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
        self.setup_chat_display_bindings()
        
        # Настройка тегов для форматирования
        self.chat_display.tag_config("user_tag", foreground="#0066cc", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("bot_tag", foreground="#28a745", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("error_tag", foreground="#dc3545", font=("Arial", 11, "bold"))
        self.chat_display.tag_config("tz_tag", foreground="#6f42c1", font=("Arial", 11, "bold"))
        
        # Приветственное сообщение (если клиент не инициализирован)
        if not self.giga_client:
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
        self.message_entry.bind('<Shift-Return>', lambda e: self.insert_newline(e))
        self.message_entry.bind('<Return>', lambda e: self.handle_send_shortcut(e))
        self.setup_input_bindings()
        
        # Обработка закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def add_message(self, sender, message):
        """Добавление сообщения в чат"""
        # Время
        time_str = datetime.now().strftime("%H:%M")
        self.chat_display.configure(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"[{time_str}] ")
        
        # Отправитель
        if sender == "user":
            self.chat_display.insert(tk.END, "Вы: ", "user_tag")
        elif sender == "bot":
            self.chat_display.insert(tk.END, "Архитектор: ", "bot_tag")
        elif sender == "error":
            self.chat_display.insert(tk.END, "Ошибка: ", "error_tag")
        elif sender == "tz":
            self.chat_display.insert(tk.END, "📋 ТЗ: ", "tz_tag")
        
        # Сообщение
        self.chat_display.insert(tk.END, f"{message}\n\n")
        
        self.chat_display.configure(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    # ------------------------------------------------------------
    # Горячие клавиши и обработчики ввода
    # ------------------------------------------------------------

    def setup_input_bindings(self):
        """Горячие клавиши для поля ввода сообщения"""
        widget = self.message_entry
        widget.bind("<Control-a>", lambda e, w=widget: self._text_select_all(w))
        widget.bind("<Command-a>", lambda e, w=widget: self._text_select_all(w))
        widget.bind("<Control-c>", lambda e, w=widget: self._text_copy(w))
        widget.bind("<Command-c>", lambda e, w=widget: self._text_copy(w))
        widget.bind("<Control-v>", lambda e, w=widget: self._text_paste(w))
        widget.bind("<Command-v>", lambda e, w=widget: self._text_paste(w))
        widget.bind("<Control-x>", lambda e, w=widget: self._text_cut(w))
        widget.bind("<Command-x>", lambda e, w=widget: self._text_cut(w))
        widget.bind("<Control-Return>", lambda e: self.send_message())
        widget.bind("<Command-Return>", lambda e: self.send_message())

    def setup_chat_display_bindings(self):
        """Горячие клавиши для окна истории (только копирование/выделение)"""
        widget = self.chat_display
        widget.bind("<Control-a>", self._chat_display_select_all)
        widget.bind("<Command-a>", self._chat_display_select_all)
        widget.bind("<Control-c>", self._chat_display_copy)
        widget.bind("<Command-c>", self._chat_display_copy)
        widget.bind("<Control-v>", lambda e: "break")
        widget.bind("<Command-v>", lambda e: "break")
        widget.bind("<Control-x>", lambda e: "break")
        widget.bind("<Command-x>", lambda e: "break")

    def insert_newline(self, event):
        """Вставка переноса строки при Shift+Enter"""
        event.widget.insert(tk.INSERT, "\n")
        return "break"

    def handle_send_shortcut(self, event):
        """Отправка сообщения при нажатии Enter"""
        self.send_message()
        return "break"

    def configure_mac_integration(self):
        """Заглушка для совместимости (ранее добавлялась интеграция с macOS-меню)."""
        return

    # ------------------------------------------------------------------
    # Вспомогательные функции для работы с буфером обмена и выделением
    # ------------------------------------------------------------------

    def _text_select_all(self, widget: tk.Text):
        widget.tag_add("sel", "1.0", "end-1c")
        widget.mark_set(tk.INSERT, "end-1c")
        return "break"

    def _text_copy(self, widget: tk.Text):
        widget.event_generate("<<Copy>>")
        return "break"

    def _text_paste(self, widget: tk.Text):
        widget.event_generate("<<Paste>>")
        return "break"

    def _text_cut(self, widget: tk.Text):
        widget.event_generate("<<Cut>>")
        return "break"

    def _with_chat_display_access(self, action):
        was_disabled = self.chat_display.cget("state") == tk.DISABLED
        if was_disabled:
            self.chat_display.config(state=tk.NORMAL)
        try:
            action()
        finally:
            if was_disabled:
                self.chat_display.config(state=tk.DISABLED)

    def _chat_display_select_all(self, event):
        def action():
            self.chat_display.tag_add("sel", "1.0", "end-1c")
        self._with_chat_display_access(action)
        return "break"

    def _chat_display_copy(self, event):
        def action():
            self.chat_display.event_generate("<<Copy>>")
        self._with_chat_display_access(action)
        return "break"

    def _handle_copy(self, event):
        return "break"

    def _handle_cut(self, event):
        return "break"

    def _handle_paste(self, event):
        return "break"

    def _handle_select_all(self, event):
        return "break"

    # Удалены устаревшие обработчики для chat_display
    
    def send_message(self):
        """Отправка сообщения агенту"""
        if not self.giga_client:
            return
        
        message = self.message_entry.get("1.0", tk.END).strip()
        
        if not message:
            return
        
        # Очищаем поле ввода
        self.message_entry.delete("1.0", tk.END)
        
        # Добавляем сообщение пользователя
        self.add_message("user", message)
        
        # Добавляем в историю
        self.conversation_history.append(Messages(role=MessagesRole.USER, content=message))
        
        # Блокируем элементы
        self.send_button.config(state=tk.DISABLED, text="Отправка...")
        self.message_entry.config(state=tk.DISABLED)
        
        # Запускаем запрос в отдельном потоке
        Thread(target=self.get_bot_response, args=(message,), daemon=True).start()
    
    def get_bot_response(self, user_message):
        """Получение ответа от агента с учетом истории диалога"""
        try:
            # Создаем чат с полной историей диалога
            chat = Chat(
                messages=self.conversation_history,
                model=self.current_model,
                temperature=self.temperature,
                flags=self.request_flags
            )
            
            response = self.giga_client.chat(chat)
            bot_message = response.choices[0].message.content
            
            # Добавляем ответ в историю
            self.conversation_history.append(Messages(role=MessagesRole.ASSISTANT, content=bot_message))
            
            # Определяем, является ли это ТЗ (проверяем ключевые слова)
            is_tz = any(keyword in bot_message.lower() for keyword in [
                "техническое задание", "тз", "проект:", "цели:", "источники данных:"
            ]) and "спасибо за ответы" in bot_message.lower()
            
            # Обновляем UI в главном потоке
            if is_tz:
                self.root.after(0, lambda: self.display_tz(bot_message))
            else:
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
    
    def display_tz(self, message):
        """Отображение технического задания"""
        self.add_message("tz", message)
        self.send_button.config(state=tk.NORMAL, text="Отправить")
        self.message_entry.config(state=tk.NORMAL)
        self.message_entry.focus()
    
    def display_error(self, error_msg):
        """Отображение ошибки"""
        self.add_message("error", error_msg)
        self.send_button.config(state=tk.NORMAL, text="Отправить")
        self.message_entry.config(state=tk.NORMAL)
        self.message_entry.focus()
    
    def open_settings(self):
        """Открытие окна настроек"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Настройки агента")
        settings_window.geometry("840x750")
        settings_window.configure(bg="#f8f9fa")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        loaded_presets = load_preset_definitions()
        if loaded_presets:
            self.presets = loaded_presets
        if not self.presets:
            messagebox.showerror("Ошибка", "Не удалось загрузить предустановленные промпты.")
            settings_window.destroy()
            return
        if self.current_preset_key and self.current_preset_key not in self.presets:
            self.current_preset_key = next(iter(self.presets))
            self.current_prompt = self.presets[self.current_preset_key]["prompt"]
            self.current_prompt_name = self.presets[self.current_preset_key]["name"]
        
        # Заголовок
        header_label = tk.Label(
            settings_window,
            text="⚙️ Настройки промпта и модели агента",
            font=("Arial", 14, "bold"),
            bg="#f8f9fa",
            fg="#333333",
            pady=15
        )
        header_label.pack(fill=tk.X)
        
        # Фрейм для редактирования промпта
        edit_frame = tk.LabelFrame(
            settings_window,
            text="Редактирование промпта",
            font=("Arial", 11, "bold"),
            bg="#f8f9fa",
            fg="#333333",
            padx=10,
            pady=10
        )
        edit_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Текстовое поле для редактирования промпта
        editor = scrolledtext.ScrolledText(
            edit_frame,
            wrap=tk.WORD,
            font=("Courier New", 10),
            bg="#ffffff",
            fg="#000000",
            padx=10,
            pady=10,
            height=12
        )
        editor.pack(fill=tk.BOTH, expand=True)
        editor.insert("1.0", self.current_prompt)
        
        # Фрейм для выбора предустановленного промпта
        preset_frame = tk.LabelFrame(
            settings_window,
            text="Выберите предустановленный промпт",
            font=("Arial", 11, "bold"),
            bg="#f8f9fa",
            fg="#333333",
            padx=10,
            pady=10
        )
        preset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Переменная для выбранного промпта (хранит ключ)
        selected_preset = tk.StringVar(value=self.current_preset_key or "")
        
        # Переменная для выбранной модели
        selected_model = tk.StringVar(value=self.current_model)
        
        # Переменная для температуры (храним как строку для ввода)
        temperature_var = tk.StringVar(value=f"{self.temperature:.2f}")
        
        # Функция для загрузки промпта в редактор
        def load_preset_to_editor(preset_key):
            preset = self.presets.get(preset_key)
            if preset:
                editor.delete("1.0", tk.END)
                editor.insert("1.0", preset["prompt"])
                selected_preset.set(preset_key)
        
        # Функция для обновления модели при выборе промпта "Эксперт"
        def update_model_on_preset_change(preset_key):
            if preset_key == "expert":
                selected_model.set("GigaChat-Pro")
            else:
                selected_model.set("GigaChat")  # Lite по умолчанию
        
        # Объединенная функция для загрузки промпта и обновления модели
        def load_preset_with_model(preset_key):
            load_preset_to_editor(preset_key)
            update_model_on_preset_change(preset_key)
        
        # Радиокнопки для выбора промпта
        for preset_key, preset_data in self.presets.items():
            rb = tk.Radiobutton(
                preset_frame,
                text=preset_data["name"],
                variable=selected_preset,
                value=preset_key,
                font=("Arial", 10),
                bg="#f8f9fa",
                anchor="w",
                command=lambda key=preset_key: load_preset_with_model(key)
            )
            rb.pack(fill=tk.X, padx=5, pady=2)
        
        # Загружаем текущий промпт и определяем выбранный пресет
        if self.current_preset_key and self.current_preset_key in self.presets:
            selected_preset.set(self.current_preset_key)
            if self.current_preset_key == "expert":
                    selected_model.set("GigaChat-Pro")
        else:
            selected_preset.set("")  # Кастомный промпт
        
        # Фрейм для выбора модели
        model_frame = tk.LabelFrame(
            settings_window,
            text="Выберите модель",
            font=("Arial", 11, "bold"),
            bg="#f8f9fa",
            fg="#333333",
            padx=10,
            pady=10
        )
        model_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Радиокнопки для выбора модели
        model_lite = tk.Radiobutton(
            model_frame,
            text="GigaChat Lite (быстрая, стандартная)",
            variable=selected_model,
            value="GigaChat",
            font=("Arial", 10),
            bg="#f8f9fa",
            anchor="w"
        )
        model_lite.pack(fill=tk.X, padx=5, pady=2)
        
        model_pro = tk.Radiobutton(
            model_frame,
            text="GigaChat Pro (продвинутая, для экспертов)",
            variable=selected_model,
            value="GigaChat-Pro",
            font=("Arial", 10),
            bg="#f8f9fa",
            anchor="w"
        )
        model_pro.pack(fill=tk.X, padx=5, pady=2)
        
        # Фрейм для настройки температуры
        temperature_frame = tk.LabelFrame(
            settings_window,
            text="Температура ответа",
            font=("Arial", 11, "bold"),
            bg="#f8f9fa",
            fg="#333333",
            padx=10,
            pady=10
        )
        temperature_frame.pack(fill=tk.X, padx=10, pady=5)
        
        temperature_description = tk.Label(
            temperature_frame,
            text="Введите число от 0.00 до 2.00 (0.00 — детерминированные ответы, 2.00 — максимально креативные).",
            font=("Arial", 9),
            bg="#f8f9fa",
            fg="#333333",
            anchor="w",
            justify="left",
            wraplength=640
        )
        temperature_description.pack(fill=tk.X, pady=(0, 8))
        
        def validate_temperature(value: str) -> bool:
            if value == "":
                return True
            try:
                number = float(value)
            except ValueError:
                return False
            return 0.0 <= number <= 2.0
        
        validate_command = settings_window.register(validate_temperature)
        
        temperature_spinbox = tk.Spinbox(
            temperature_frame,
            from_=0.0,
            to=2.0,
            increment=0.05,
            format="%.2f",
            textvariable=temperature_var,
            font=("Arial", 12),
            width=8,
            justify="center",
            validate="all",
            validatecommand=(validate_command, "%P"),
            relief=tk.SOLID,
            borderwidth=1
        )
        temperature_spinbox.pack(pady=5)
        
        # Фрейм для кнопок
        button_frame = tk.Frame(settings_window, bg="#f8f9fa")
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Кнопка применения
        def apply_settings():
            new_prompt = editor.get("1.0", tk.END).strip()
            if not new_prompt:
                messagebox.showerror("Ошибка", "Промпт не может быть пустым!")
                return
            
            # Обновляем промпт
            self.current_prompt = new_prompt
            preset_key = selected_preset.get()
            if preset_key and preset_key in self.presets:
                self.current_preset_key = preset_key
                self.current_prompt_name = self.presets[preset_key]["name"]
            else:
                self.current_preset_key = None
                self.current_prompt_name = "Кастомный промпт"
            
            # Обновляем модель
            self.current_model = selected_model.get()
            
            # Обновляем температуру
            temp_value_str = temperature_var.get().strip()
            if not temp_value_str:
                messagebox.showerror("Ошибка", "Температура не может быть пустой.")
                return
            try:
                temp_value = float(temp_value_str)
            except ValueError:
                messagebox.showerror("Ошибка", "Температура должна быть числом от 0.0 до 2.0.")
                return
            if not 0.0 <= temp_value <= 2.0:
                messagebox.showerror("Ошибка", "Температура должна быть в диапазоне от 0.0 до 2.0.")
                return
            self.temperature = round(temp_value, 2)
            temperature_var.set(f"{self.temperature:.2f}")
            
            # Перезапускаем диалог с новым промптом
            self.conversation_history = [
                Messages(role=MessagesRole.SYSTEM, content=self.current_prompt)
            ]
            
            # Очищаем чат
            self.chat_display.config(state=tk.NORMAL)
            self.chat_display.delete("1.0", tk.END)
            self.chat_display.config(state=tk.DISABLED)
            
            # Обновляем информационную панель
            model_display = "Pro" if self.current_model == "GigaChat-Pro" else "Lite"
            self.info_label.config(text=f"Режим: {self.current_prompt_name} | Модель: {model_display} | Температура: {self.temperature:.2f}")
            
            # Получаем новое приветствие
            if self.giga_client:
                Thread(target=self.get_initial_greeting, daemon=True).start()
            
            messagebox.showinfo("Успех", "Настройки применены! Диалог перезапущен с новым промптом.")
            settings_window.destroy()
        
        apply_button = tk.Button(
            button_frame,
            text="Применить",
            command=apply_settings,
            font=("Arial", 11, "bold"),
            bg="#28a745",
            fg="white",
            activebackground="#218838",
            padx=20,
            pady=5
        )
        apply_button.pack(side=tk.LEFT, padx=5)
        
        # Кнопка отмены
        cancel_button = tk.Button(
            button_frame,
            text="Отмена",
            command=settings_window.destroy,
            font=("Arial", 11),
            bg="#6c757d",
            fg="white",
            activebackground="#5a6268",
            padx=20,
            pady=5
        )
        cancel_button.pack(side=tk.RIGHT, padx=5)
        
        # Кнопка сброса
        def reset_to_default():
            if messagebox.askyesno("Подтверждение", "Сбросить к промпту по умолчанию?"):
                editor.delete("1.0", tk.END)
                default_key = DEFAULT_PRESET_KEY if DEFAULT_PRESET_KEY in self.presets else next(iter(self.presets))
                editor.insert("1.0", self.presets[default_key]["prompt"])
                selected_preset.set(default_key)
                selected_model.set("GigaChat" if default_key != "expert" else "GigaChat-Pro")
                temperature_var.set(f"{DEFAULT_TEMPERATURE:.2f}")
        
        reset_button = tk.Button(
            button_frame,
            text="Сбросить",
            command=reset_to_default,
            font=("Arial", 10),
            bg="#ffc107",
            fg="#000000",
            activebackground="#e0a800",
            padx=15,
            pady=5
        )
        reset_button.pack(side=tk.LEFT, padx=5)
    
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
