"""
🤖 Telegram бот для удалённого управления ПК
Установка зависимостей:
    pip install pyTelegramBotAPI psutil pillow pynput

Настройка:
    1. Получи токен бота у @BotFather в Telegram
    2. Узнай свой Telegram ID у @userinfobot
    3. Вставь токен и ID ниже
    4. Запусти: python pc_remote_bot.py
"""

import telebot
import psutil
import os
import sys
import platform
import io
import subprocess
import threading
import time
import socket
import urllib.request
from datetime import datetime
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN       = "8749268938:AAE0AmUDO5rft6WWpb3Egp0owo6xMy7FGTk"
ALLOWED_USER_ID = 5328380224
# ====================================================

bot = telebot.TeleBot(BOT_TOKEN)

# ── Громкость через pycaw ────────────────────────────
def get_volume_interface():
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))

# ── Состояние безопасности ───────────────────────────
security_enabled  = False
security_thread   = None
keyboard_buffer   = []
last_kb_flush     = time.time()
last_click_time   = 0
last_window       = ""

# ── Вспомогательные функции ─────────────────────────

def is_allowed(message):
    return message.from_user.id == ALLOWED_USER_ID

def access_denied(message):
    bot.reply_to(message, "⛔ Доступ запрещён.")

def fmt_bytes(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"

def bar(pct, width=10):
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

# ── Клавиатуры ──────────────────────────────────────

def main_keyboard():
    m = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("💻 Статус",    "📸 Скриншот")
    m.row("📊 Диспетчер", "🌐 Сеть")
    m.row("🔴 Выключить", "🔄 Перезагрузить")
    m.row("😴 Сон",       "🔒 Заблокировать")
    m.row("🔊 Громкость", "⌨️ Команда")
    m.row("🛡 Безопасность", "❓ Помощь")
    m.row("🚪 Выгрузить бота")
    return m

PAGE_SIZE = 10

def process_page_kb(page, total_pages, sort_by):
    m = telebot.types.InlineKeyboardMarkup()
    sort_label = "🔃 по RAM" if sort_by == "cpu" else "🔃 по CPU"
    m.row(
        telebot.types.InlineKeyboardButton(sort_label,    callback_data=f"proc|{'ram' if sort_by == 'cpu' else 'cpu'}|0"),
        telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data=f"proc|{sort_by}|{page}"),
    )
    nav = []
    if page > 0:
        nav.append(telebot.types.InlineKeyboardButton("◀️", callback_data=f"proc|{sort_by}|{page-1}"))
    nav.append(telebot.types.InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(telebot.types.InlineKeyboardButton("▶️", callback_data=f"proc|{sort_by}|{page+1}"))
    m.row(*nav)
    m.row(telebot.types.InlineKeyboardButton("💀 Завершить процесс", callback_data="kill_prompt"))
    return m

# ── /start ───────────────────────────────────────────

@bot.message_handler(commands=["start"])
def start(message):
    if not is_allowed(message):
        return access_denied(message)
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    text = (
        f"🖥️ *Удалённое управление ПК*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏠 `{platform.node()}` · {platform.system()} {platform.release()}\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y  %H:%M:%S')}\n\n"
        f"⚙️ CPU  {bar(cpu)} {cpu}%\n"
        f"🧠 RAM  {bar(ram.percent)} {ram.percent}%\n\n"
        f"Выбери действие 👇"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_keyboard())

# ── Помощь ───────────────────────────────────────────

@bot.message_handler(commands=["help"])
@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def help_cmd(message):
    if not is_allowed(message):
        return access_denied(message)
    text = (
        "📖 *Что умеет бот:*\n\n"
        "💻 *Статус* — CPU, RAM, диск, аптайм, температура\n"
        "📸 *Скриншот* — снимок экрана прямо сейчас\n"
        "📊 *Диспетчер* — процессы, сортировка CPU/RAM, завершение\n"
        "🌐 *Сеть* — IP, скорость, трафик\n"
        "🔴 *Выключить* — через 30 сек, с отменой\n"
        "🔄 *Перезагрузить* — через 30 сек, с отменой\n"
        "😴 *Сон* — сон или гибернация\n"
        "🔒 *Заблокировать* — блокировка экрана\n"
        "🔊 *Громкость* — кнопки или ввод 0–100\n"
        "⌨️ *Команда* — выполнить cmd-команду\n"
        "🛡 *Безопасность* — мониторинг клавиш и активности мыши\n"
        "🚪 *Выгрузить бота* — остановить скрипт\n\n"
        "⚠️ Выключение отменяется кнопкой или /cancel"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=main_keyboard())

# ── Статус системы ───────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "💻 Статус")
def system_status(message):
    if not is_allowed(message):
        return access_denied(message)

    cpu  = psutil.cpu_percent(interval=1)
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot = datetime.fromtimestamp(psutil.boot_time())
    up   = datetime.now() - boot
    hours, rem = divmod(int(up.total_seconds()), 3600)
    mins = rem // 60

    temps = ""
    try:
        t = psutil.sensors_temperatures()
        if t:
            for entries in t.values():
                if entries:
                    temps = f"\n🌡️ *Температура:* {entries[0].current:.0f}°C"
                    break
    except Exception:
        pass

    bat = ""
    b = psutil.sensors_battery()
    if b:
        plug = "🔌 заряжается" if b.power_plugged else "🔋 батарея"
        bat = f"\n🔋 *Батарея:* {b.percent:.0f}% ({plug})"

    text = (
        f"🖥️ *Статус системы*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 *Время:* {datetime.now().strftime('%H:%M:%S')}\n"
        f"⏱ *Аптайм:* {hours}ч {mins}м\n\n"
        f"⚙️ *CPU:*  {bar(cpu)} {cpu}%\n"
        f"🧠 *RAM:*  {bar(ram.percent)} {ram.percent}%\n"
        f"    └ {fmt_bytes(ram.used)} / {fmt_bytes(ram.total)}\n"
        f"💾 *Диск:* {bar(disk.percent)} {disk.percent}%\n"
        f"    └ {fmt_bytes(disk.used)} / {fmt_bytes(disk.total)}"
        f"{temps}{bat}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ── Скриншот ─────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "📸 Скриншот")
def screenshot(message):
    if not is_allowed(message):
        return access_denied(message)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        bot.send_photo(message.chat.id, buf,
                       caption=f"📸 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка скриншота: {e}")

# ── Диспетчер задач ──────────────────────────────────

def get_procs(sort_by="cpu"):
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except Exception:
            pass
    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    procs.sort(key=lambda x: x.get(key) or 0, reverse=True)
    return procs

def render_procs(procs, page, sort_by):
    total_pages = max(1, (len(procs) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = procs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    sort_label = "CPU" if sort_by == "cpu" else "RAM"
    lines = [
        f"📊 *Диспетчер задач* · по {sort_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"`{'PID':>6}  {'Процесс':<18} CPU    RAM`"
    ]
    for p in chunk:
        cpu_p = p.get("cpu_percent") or 0
        mem_p = p.get("memory_percent") or 0
        lines.append(
            f"`{p['pid']:>6}  {(p['name'] or '?')[:18]:<18} {cpu_p:>4.1f}%  {mem_p:>4.1f}%`"
        )
    lines.append(f"\n_Всего процессов: {len(procs)}_")
    return "\n".join(lines), total_pages, page

@bot.message_handler(func=lambda m: m.text == "📊 Диспетчер")
def task_manager(message):
    if not is_allowed(message):
        return access_denied(message)
    procs = get_procs("cpu")
    text, total, page = render_procs(procs, 0, "cpu")
    bot.send_message(message.chat.id, text, parse_mode="Markdown",
                     reply_markup=process_page_kb(page, total, "cpu"))

@bot.callback_query_handler(func=lambda c: c.data.startswith("proc|"))
def cb_proc(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    _, sort_by, page_str = call.data.split("|")
    page = int(page_str)
    procs = get_procs(sort_by)
    text, total, page = render_procs(procs, page, sort_by)
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              parse_mode="Markdown",
                              reply_markup=process_page_kb(page, total, sort_by))
    except Exception:
        pass
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "kill_prompt")
def cb_kill_prompt(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id,
                           "💀 Введи *PID* процесса для завершения:",
                           parse_mode="Markdown")
    bot.register_next_step_handler(msg, do_kill_process)

def do_kill_process(message):
    if not is_allowed(message):
        return access_denied(message)
    try:
        pid = int(message.text.strip())
        p = psutil.Process(pid)
        name = p.name()
        p.kill()
        bot.send_message(message.chat.id,
                         f"✅ Процесс `{name}` (PID {pid}) завершён.",
                         parse_mode="Markdown", reply_markup=main_keyboard())
    except psutil.NoSuchProcess:
        bot.send_message(message.chat.id, "❌ Процесс не найден.", reply_markup=main_keyboard())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число (PID).", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda c: c.data == "noop")
def cb_noop(call):
    bot.answer_callback_query(call.id)

# ── Сеть ─────────────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "🌐 Сеть")
def network_info(message):
    if not is_allowed(message):
        return access_denied(message)

    io1 = psutil.net_io_counters()
    time.sleep(1)
    io2 = psutil.net_io_counters()

    sent_speed = io2.bytes_sent - io1.bytes_sent
    recv_speed = io2.bytes_recv - io1.bytes_recv

    try:
        ext_ip = urllib.request.urlopen("https://api.ipify.org", timeout=4).read().decode()
    except Exception:
        ext_ip = "недоступен"

    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "?"

    text = (
        f"🌐 *Сетевая статистика*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏠 *Локальный IP:* `{local_ip}`\n"
        f"🌍 *Внешний IP:*   `{ext_ip}`\n\n"
        f"📥 *Приём:*    {fmt_bytes(recv_speed)}/с\n"
        f"📤 *Отправка:* {fmt_bytes(sent_speed)}/с\n\n"
        f"📊 *Всего получено:*   {fmt_bytes(io2.bytes_recv)}\n"
        f"📊 *Всего отправлено:* {fmt_bytes(io2.bytes_sent)}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ── Выключение / Перезагрузка ────────────────────────

def shutdown_kb():
    m = telebot.types.InlineKeyboardMarkup()
    m.add(telebot.types.InlineKeyboardButton("❌ Отменить", callback_data="cancel_shutdown"))
    return m

@bot.message_handler(func=lambda m: m.text == "🔴 Выключить")
def shutdown(message):
    if not is_allowed(message):
        return access_denied(message)
    bot.send_message(message.chat.id, "⚠️ *Выключение через 30 секунд!*",
                     parse_mode="Markdown", reply_markup=shutdown_kb())
    os.system("shutdown /s /t 1" if platform.system() == "Windows" else "shutdown -h +1")

@bot.message_handler(func=lambda m: m.text == "🔄 Перезагрузить")
def reboot(message):
    if not is_allowed(message):
        return access_denied(message)
    bot.send_message(message.chat.id, "⚠️ *Перезагрузка через 30 секунд!*",
                     parse_mode="Markdown", reply_markup=shutdown_kb())
    os.system("shutdown /r /t 1" if platform.system() == "Windows" else "shutdown -r +1")

@bot.callback_query_handler(func=lambda c: c.data == "cancel_shutdown")
def cancel_shutdown(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    os.system("shutdown /a" if platform.system() == "Windows" else "shutdown -c")
    bot.answer_callback_query(call.id, "✅ Отменено!")
    bot.edit_message_text("✅ Отменено.", call.message.chat.id, call.message.message_id)

@bot.message_handler(commands=["cancel"])
def cancel_cmd(message):
    if not is_allowed(message):
        return access_denied(message)
    os.system("shutdown /a" if platform.system() == "Windows" else "shutdown -c")
    bot.send_message(message.chat.id, "✅ Отменено.")

# ── Сон / Гибернация ─────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "😴 Сон")
def sleep_mode(message):
    if not is_allowed(message):
        return access_denied(message)
    m = telebot.types.InlineKeyboardMarkup()
    m.row(
        telebot.types.InlineKeyboardButton("😴 Сон",        callback_data="sleep"),
        telebot.types.InlineKeyboardButton("❄️ Гибернация", callback_data="hibernate"),
    )
    bot.send_message(message.chat.id, "Выбери режим:", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data in ("sleep", "hibernate"))
def do_sleep(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    if call.data == "sleep":
        bot.edit_message_text("😴 Переходим в режим сна…", call.message.chat.id, call.message.message_id)
        cmd = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0" if platform.system() == "Windows" else "systemctl suspend"
    else:
        bot.edit_message_text("❄️ Гибернация…", call.message.chat.id, call.message.message_id)
        cmd = "shutdown /h" if platform.system() == "Windows" else "systemctl hibernate"
    bot.answer_callback_query(call.id)
    os.system(cmd)

# ── Блокировка ───────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "🔒 Заблокировать")
def lock_screen(message):
    if not is_allowed(message):
        return access_denied(message)
    if platform.system() == "Windows":
        os.system("rundll32.exe user32.dll,LockWorkStation")
    else:
        os.system("loginctl lock-session")
    bot.send_message(message.chat.id, "🔒 Экран заблокирован.")

# ── Громкость (через pycaw) ──────────────────────────

@bot.message_handler(func=lambda m: m.text == "🔊 Громкость")
def volume_prompt(message):
    if not is_allowed(message):
        return access_denied(message)

    # Показываем текущую громкость
    try:
        vol_iface = get_volume_interface()
        current = int(vol_iface.GetMasterVolumeLevelScalar() * 100)
        current_text = f"Сейчас: *{current}%*\n\n"
    except Exception:
        current_text = ""

    m = telebot.types.InlineKeyboardMarkup()
    m.row(
        telebot.types.InlineKeyboardButton("🔇 0%",  callback_data="vol|0"),
        telebot.types.InlineKeyboardButton("🔉 25%", callback_data="vol|25"),
        telebot.types.InlineKeyboardButton("🔉 50%", callback_data="vol|50"),
    )
    m.row(
        telebot.types.InlineKeyboardButton("🔊 75%",  callback_data="vol|75"),
        telebot.types.InlineKeyboardButton("🔊 100%", callback_data="vol|100"),
    )
    msg = bot.send_message(message.chat.id,
                           f"🔊 {current_text}Выбери или введи громкость (0–100):",
                           parse_mode="Markdown",
                           reply_markup=m)
    bot.register_next_step_handler(msg, set_volume_text)

def apply_volume(level):
    level = max(0, min(100, int(level)))
    vol_iface = get_volume_interface()
    vol_iface.SetMasterVolumeLevelScalar(level / 100, None)
    return level

@bot.callback_query_handler(func=lambda c: c.data.startswith("vol|"))
def cb_volume(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    level = int(call.data.split("|")[1])
    try:
        apply_volume(level)
        bot.answer_callback_query(call.id, f"✅ Громкость {level}%")
        bot.edit_message_text(f"🔊 Громкость установлена: *{level}%*",
                              call.message.chat.id, call.message.message_id,
                              parse_mode="Markdown")
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Ошибка")
        bot.edit_message_text(f"❌ Не удалось: {e}",
                              call.message.chat.id, call.message.message_id)

def set_volume_text(message):
    if not is_allowed(message):
        return access_denied(message)
    try:
        level = int(message.text.strip())
        apply_volume(level)
        bot.send_message(message.chat.id,
                         f"🔊 Громкость: *{max(0, min(100, level))}%*",
                         parse_mode="Markdown", reply_markup=main_keyboard())
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число от 0 до 100.", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка громкости: {e}", reply_markup=main_keyboard())

# ── CMD команда ──────────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "⌨️ Команда")
def cmd_prompt(message):
    if not is_allowed(message):
        return access_denied(message)
    msg = bot.send_message(message.chat.id,
                           "⌨️ Введи команду для выполнения:\n_(например: `dir C:\\` или `ipconfig`)_",
                           parse_mode="Markdown")
    bot.register_next_step_handler(msg, run_cmd)

def run_cmd(message):
    if not is_allowed(message):
        return access_denied(message)
    cmd = message.text.strip()
    bot.send_message(message.chat.id, f"⚙️ Выполняю: `{cmd}`", parse_mode="Markdown")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=15)
        for enc in ("cp866", "utf-8", "cp1251"):
            try:
                output = (result.stdout.decode(enc) + result.stderr.decode(enc)).strip()
                break
            except Exception:
                output = ""
        output = output[:3500] or "(нет вывода)"
        bot.send_message(message.chat.id, f"```\n{output}\n```",
                         parse_mode="Markdown", reply_markup=main_keyboard())
    except subprocess.TimeoutExpired:
        bot.send_message(message.chat.id, "⏱ Таймаут.", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}", reply_markup=main_keyboard())

# ── Безопасность ─────────────────────────────────────

def get_active_window():
    """Получить название активного окна (Windows)."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""
    except Exception:
        return ""

def security_monitor_loop():
    global security_enabled, keyboard_buffer, last_kb_flush, last_window

    from pynput import keyboard, mouse

    typed_chars = []
    flush_lock = threading.Lock()

    def flush_keyboard():
        """Отправить накопленные нажатия клавиш."""
        nonlocal typed_chars
        with flush_lock:
            if typed_chars:
                text = "".join(typed_chars)
                typed_chars = []
                try:
                    bot.send_message(
                        ALLOWED_USER_ID,
                        f"🚨 *Тревога — клавиатура*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"⌨️ Набрано: `{text[:300]}`\n"
                        f"🕐 {datetime.now().strftime('%H:%M:%S')}",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    def on_press(key):
        if not security_enabled:
            return False  # остановить listener
        nonlocal typed_chars
        try:
            c = key.char
            if c:
                with flush_lock:
                    typed_chars.append(c)
        except AttributeError:
            # Спецклавиши
            special = {
                "Key.space": " ",
                "Key.enter": " [Enter] ",
                "Key.backspace": " [←] ",
                "Key.tab": " [Tab] ",
                "Key.shift": "",
                "Key.ctrl_l": " [Ctrl] ",
                "Key.alt_l": " [Alt] ",
                "Key.delete": " [Del] ",
            }
            label = special.get(str(key), f" [{str(key).replace('Key.','')}] ")
            if label:
                with flush_lock:
                    typed_chars.append(label)

    click_count   = [0]
    last_click_ts = [0.0]

    def on_click(x, y, button, pressed):
        if not security_enabled:
            return False
        if not pressed:
            return
        now = time.time()
        click_count[0] += 1
        # Отправляем если накопилось 5 кликов или прошло 10 сек с первого
        if click_count[0] == 1:
            last_click_ts[0] = now
        if click_count[0] >= 5 or (now - last_click_ts[0] > 10 and click_count[0] > 0):
            n = click_count[0]
            click_count[0] = 0
            win = get_active_window()
            win_text = f"\n🖥️ Окно: `{win[:50]}`" if win else ""
            try:
                bot.send_message(
                    ALLOWED_USER_ID,
                    f"🚨 *Тревога — активность мыши*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🖱️ Кликов: {n} · позиция ({x}, {y})"
                    f"{win_text}\n"
                    f"🕐 {datetime.now().strftime('%H:%M:%S')}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    # Мониторинг смены активного окна
    def window_watcher():
        global last_window
        while security_enabled:
            win = get_active_window()
            if win and win != last_window:
                last_window = win
                try:
                    bot.send_message(
                        ALLOWED_USER_ID,
                        f"🚨 *Тревога — смена окна*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🪟 Открыто: `{win[:80]}`\n"
                        f"🕐 {datetime.now().strftime('%H:%M:%S')}",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
            time.sleep(2)

    # Таймер сброса клавиш каждые 5 секунд
    def kb_flush_timer():
        while security_enabled:
            time.sleep(5)
            flush_keyboard()

    threading.Thread(target=window_watcher, daemon=True).start()
    threading.Thread(target=kb_flush_timer,  daemon=True).start()

    kb_listener    = keyboard.Listener(on_press=on_press)
    mouse_listener = mouse.Listener(on_click=on_click)
    kb_listener.start()
    mouse_listener.start()

    while security_enabled:
        time.sleep(1)

    kb_listener.stop()
    mouse_listener.stop()
    flush_keyboard()  # отправить остаток

@bot.message_handler(func=lambda m: m.text == "🛡 Безопасность")
def security_toggle(message):
    global security_enabled, security_thread
    if not is_allowed(message):
        return access_denied(message)

    if not security_enabled:
        security_enabled = True
        security_thread = threading.Thread(target=security_monitor_loop, daemon=True)
        security_thread.start()

        m = telebot.types.InlineKeyboardMarkup()
        m.add(telebot.types.InlineKeyboardButton("🔴 Выключить мониторинг", callback_data="sec_off"))
        bot.send_message(
            message.chat.id,
            "🛡 *Безопасность — ВКЛЮЧЕНА*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Буду слать уведомления если:\n"
            "• ⌨️ Кто-то печатает на клавиатуре\n"
            "• 🖱️ Активно кликает мышью\n"
            "• 🪟 Открывается новое окно\n\n"
            "Все сообщения начинаются с 🚨 *Тревога*",
            parse_mode="Markdown",
            reply_markup=m
        )
    else:
        security_enabled = False
        bot.send_message(
            message.chat.id,
            "🛡 *Безопасность — ВЫКЛЮЧЕНА*",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

@bot.callback_query_handler(func=lambda c: c.data == "sec_off")
def cb_sec_off(call):
    global security_enabled
    if call.from_user.id != ALLOWED_USER_ID:
        return
    security_enabled = False
    bot.answer_callback_query(call.id, "Мониторинг выключен")
    bot.edit_message_text(
        "🛡 *Безопасность — ВЫКЛЮЧЕНА*",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown"
    )

# ── Выгрузить бота ───────────────────────────────────

@bot.message_handler(func=lambda m: m.text == "🚪 Выгрузить бота")
def exit_bot(message):
    if not is_allowed(message):
        return access_denied(message)
    m = telebot.types.InlineKeyboardMarkup()
    m.row(
        telebot.types.InlineKeyboardButton("✅ Да, остановить", callback_data="confirm_exit"),
        telebot.types.InlineKeyboardButton("❌ Отмена",         callback_data="cancel_exit"),
    )
    bot.send_message(message.chat.id, "🚪 Остановить бота? ПК останется включён.", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data == "confirm_exit")
def cb_confirm_exit(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    bot.answer_callback_query(call.id)
    bot.edit_message_text("🚪 Бот остановлен. До свидания!", call.message.chat.id, call.message.message_id)
    threading.Timer(1, lambda: sys.exit(0)).start()

@bot.callback_query_handler(func=lambda c: c.data == "cancel_exit")
def cb_cancel_exit(call):
    if call.from_user.id != ALLOWED_USER_ID:
        return
    bot.answer_callback_query(call.id, "Отменено")
    bot.edit_message_text("✅ Бот продолжает работу.", call.message.chat.id, call.message.message_id)

# ── Запуск ───────────────────────────────────────────

if __name__ == "__main__":
    print("🤖 Бот запущен!")
    print(f"🖥️  {platform.system()} {platform.release()} · {platform.node()}")
    print("Ctrl+C для остановки\n")

    try:
        boot = datetime.fromtimestamp(psutil.boot_time())
        up   = (datetime.now() - boot).total_seconds()
        ram  = psutil.virtual_memory()
        cpu  = psutil.cpu_percent(interval=1)
        text = (
            f"🟢 *ПК включён!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏠 `{platform.node()}`\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y  %H:%M:%S')}\n"
            f"⏱ Аптайм: {int(up // 60)} мин\n\n"
            f"⚙️ CPU  {bar(cpu)} {cpu}%\n"
            f"🧠 RAM  {bar(ram.percent)} {ram.percent}%\n"
            f"    └ {fmt_bytes(ram.used)} / {fmt_bytes(ram.total)}"
        )
        bot.send_message(ALLOWED_USER_ID, text, parse_mode="Markdown")
        print("✅ Уведомление о запуске отправлено")
    except Exception as e:
        print(f"⚠️  Уведомление не отправлено: {e}")

    bot.infinity_polling()
