"""Translations (English, Farsi, Russian) and right-to-left text handling for AutoScribe."""
import re

LANGUAGES = {"en": "English", "fa": "فارسی", "ru": "Русский"}

LANG = "en"
RTL = False


def set_language(lang):
    global LANG, RTL
    LANG = lang if lang in LANGUAGES else "en"
    RTL = LANG == "fa"


def detect_language():
    """Picks the UI language from the Windows display language on first launch."""
    try:
        import ctypes
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x29: "fa", 0x19: "ru"}.get(primary, "en")
    except Exception:
        return "en"


def t(key, **kw):
    entry = STRINGS[key]
    text = entry.get(LANG) or entry["en"]
    return text.format(**kw) if kw else text


def num(n):
    text = f"{n:,}"
    return text.replace(",", "\u00a0") if LANG == "ru" else text


def region_name(region):
    return REGIONS.get(region, {}).get(LANG) or region


def duration(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return t("dur_h", h=h, m=f"{m:02d}")
    if m:
        return t("dur_m", m=m)
    return t("dur_s", s=s)


# ---------------------------------------------------------------------------
# Right-to-left text
#
# Tk on Windows shapes Persian correctly but always lays a line out left to right and ignores
# the Unicode embedding controls, so mixed Persian / Latin text comes out in the wrong order.
# vis() rearranges a line into right-to-left display order: it splits the text into Persian
# runs, Latin/number runs and the punctuation between them, reverses the order of those runs,
# and separates them with LRM marks so Windows only reverses the letters inside each Persian run.
# ---------------------------------------------------------------------------
_AR = "\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\u200C"
# Persian letters only: punctuation such as "،" at the edge of a run is neutral and must not anchor the run.
_AR_LETTER = "\u0621-\u065F\u066E-\u06D3\u06D5-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
_LTR = "A-Za-z0-9\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF"
_TOKEN = re.compile(
    rf"(?P<rtl>[{_AR_LETTER}](?:[^{_LTR}]*[{_AR_LETTER}])?)"
    rf"|(?P<ltr>[{_LTR}]+(?:[.,:/_'@#+\-][{_LTR}]+)*%?)"
    rf"|(?P<neu>[^{_AR_LETTER}{_LTR}]+)")
_HAS_AR = re.compile(f"[{_AR}]")
_HAS_LETTER = re.compile("[A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF]")
_JOINER = re.compile(r"[ \-–—:·/]+")
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
_LRM = "\u200e"


def _vis_line(line):
    if not _HAS_AR.search(line):
        return line
    runs = []
    for m in _TOKEN.finditer(line):
        kind = m.lastgroup
        text = m.group()
        # Latin words joined by spaces or dashes ("Amsterdam – Tulip") stay together, left to right.
        if (kind == "ltr" and len(runs) >= 2 and runs[-1][0] == "neu" and runs[-2][0] == "ltr"
                and _JOINER.fullmatch(runs[-1][1]) and _HAS_LETTER.search(runs[-2][1])
                and _HAS_LETTER.search(text)):
            joiner = runs.pop()[1]
            runs[-1] = ("ltr", runs[-1][1] + joiner + text)
            continue
        runs.append((kind, text))
    out = [text[::-1].translate(_MIRROR) if kind == "neu" else text for kind, text in reversed(runs)]
    return _LRM + _LRM.join(out) + _LRM


def vis(text):
    """Display form of a string: unchanged for English and Russian, reordered for Farsi."""
    if not RTL or not isinstance(text, str) or not text:
        return text
    return "\n".join(_vis_line(line) for line in text.split("\n"))


def wrap(text, measure, width):
    """Word-wraps in reading order (Tk would wrap the reordered Farsi text from the wrong end)."""
    lines = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and measure(candidate) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return "\n".join(lines)


REGIONS = {
    "All": {"fa": "همه", "ru": "Все"},
    "USA": {"fa": "آمریکا", "ru": "США"},
    "Europe": {"fa": "اروپا", "ru": "Европа"},
    "Asia": {"fa": "آسیا", "ru": "Азия"},
    "Africa": {"fa": "آفریقا", "ru": "Африка"},
    "Oceania": {"fa": "اقیانوسیه", "ru": "Океания"},
    "Antarctica": {"fa": "جنوبگان", "ru": "Антарктида"},
    "North America": {"fa": "آمریکای شمالی", "ru": "Северная Америка"},
    "South America": {"fa": "آمریکای جنوبی", "ru": "Южная Америка"},
}

STRINGS = {
    # --- general ---
    "language": {"en": "Language", "fa": "زبان", "ru": "Язык"},
    "tagline": {"en": "Protocol & ping tester · v{v}", "fa": "آزمایش پروتکل و پینگ · نسخهٔ {v}",
                "ru": "Тест протоколов и пинга · v{v}"},
    "dur_h": {"en": "{h} h {m} min", "fa": "{h} ساعت و {m} دقیقه", "ru": "{h} ч {m} мин"},
    "dur_m": {"en": "{m} min", "fa": "{m} دقیقه", "ru": "{m} мин"},
    "dur_s": {"en": "{s} s", "fa": "{s} ثانیه", "ru": "{s} с"},
    "secs": {"en": "{v} s", "fa": "{v} ثانیه", "ru": "{v} с"},
    "ms": {"en": "ms", "fa": "ms", "ru": "мс"},
    "and": {"en": " and ", "fa": " و ", "ru": " и "},
    "save": {"en": "Save", "fa": "ذخیره", "ru": "Сохранить"},
    "cancel": {"en": "Cancel", "fa": "انصراف", "ru": "Отмена"},
    "done": {"en": "Done", "fa": "تأیید", "ru": "Готово"},
    "copy": {"en": "Copy", "fa": "کپی", "ru": "Копировать"},
    "clear": {"en": "Clear", "fa": "پاک کردن", "ru": "Очистить"},
    "browse": {"en": "Browse", "fa": "انتخاب", "ru": "Обзор"},
    "download": {"en": "Download", "fa": "دانلود", "ru": "Загрузить"},
    "open_folder": {"en": "Open folder", "fa": "باز کردن پوشه", "ru": "Открыть папку"},
    "lang_busy": {"en": "Finish or stop the current run before changing the language.",
                  "fa": "پیش از تغییر زبان، تست فعلی را تمام یا متوقف کنید.",
                  "ru": "Завершите или остановите текущий тест, прежде чем менять язык."},

    # --- sidebar ---
    "hide_panel_tip": {"en": "Hide the setup panel  (Ctrl+B)", "fa": "پنهان کردن پنل تنظیمات  (Ctrl+B)",
                       "ru": "Скрыть панель настроек  (Ctrl+B)"},
    "show_panel_tip": {"en": "Show the setup panel  (Ctrl+B)", "fa": "نمایش پنل تنظیمات  (Ctrl+B)",
                       "ru": "Показать панель настроек  (Ctrl+B)"},
    "profile": {"en": "Profile", "fa": "پروفایل", "ru": "Профиль"},
    "save_profile_tip": {"en": "Save settings as a profile  (Ctrl+S)", "fa": "ذخیرهٔ تنظیمات به‌عنوان پروفایل  (Ctrl+S)",
                         "ru": "Сохранить настройки как профиль  (Ctrl+S)"},
    "delete_profile_tip": {"en": "Delete this profile", "fa": "حذف این پروفایل", "ru": "Удалить этот профиль"},
    "choose_profile": {"en": "Choose a profile…", "fa": "یک پروفایل انتخاب کنید…", "ru": "Выберите профиль…"},
    "no_profiles": {"en": "No saved profiles", "fa": "پروفایلی ذخیره نشده", "ru": "Профилей нет"},
    "locations": {"en": "Locations", "fa": "مکان‌ها", "ru": "Локации"},
    "locations_tip": {"en": "Locations  (Ctrl+L)", "fa": "مکان‌ها  (Ctrl+L)", "ru": "Локации  (Ctrl+L)"},
    "update_list": {"en": "Update list", "fa": "به‌روزرسانی فهرست", "ru": "Обновить список"},
    "updating": {"en": "Updating…", "fa": "در حال به‌روزرسانی…", "ru": "Обновление…"},
    "change": {"en": "Change", "fa": "تغییر", "ru": "Изменить"},
    "change_tip": {"en": "Search and pick countries, cities or servers  (Ctrl+L)",
                   "fa": "جستجو و انتخاب کشور، شهر یا سرور  (Ctrl+L)",
                   "ru": "Поиск и выбор стран, городов и серверов  (Ctrl+L)"},
    "no_list_hint": {"en": "No server list yet. Click Update list to download it from windscribe.com.",
                     "fa": "هنوز فهرست سروری وجود ندارد. برای دانلود آن از windscribe.com روی «به‌روزرسانی فهرست» کلیک کنید.",
                     "ru": "Списка серверов пока нет. Нажмите «Обновить список», чтобы загрузить его с windscribe.com."},
    "protocols": {"en": "Protocols", "fa": "پروتکل‌ها", "ru": "Протоколы"},
    "censorship": {"en": "Censorship tweaks (Linux CLI)", "fa": "ترفندهای ضدسانسور (CLI لینوکس)",
                   "ru": "Обход цензуры (Linux CLI)"},
    "amnezia": {"en": "Amnezia", "fa": "Amnezia", "ru": "Amnezia"},
    "amnezia_title": {"en": "Amnezia configs", "fa": "پیکربندی‌های Amnezia", "ru": "Конфиги Amnezia"},
    "amnezia_hint": {"en": "Each selected config is tried on every selected WireGuard port. Other protocols run with protocol tweaks off.",
                     "fa": "هر پیکربندی انتخاب‌شده روی همه پورت‌های انتخابی WireGuard آزمایش می‌شود. بقیه پروتکل‌ها با تنظیمات پروتکل خاموش اجرا می‌شوند.",
                     "ru": "Каждый выбранный конфиг проверяется на всех выбранных портах WireGuard. Остальные протоколы идут с выключенными правками протокола."},
    "amnezia_off": {"en": "off", "fa": "خاموش", "ru": "выкл"},
    "amnezia_n": {"en": "{n} configs", "fa": "{n} پیکربندی", "ru": "{n} конфиг."},
    "amnezia_loading": {"en": "Asking windscribe-cli for the list…", "fa": "در حال دریافت فهرست از windscribe-cli…",
                        "ru": "Запрашиваю список у windscribe-cli…"},
    "amnezia_empty": {"en": "Could not list presets. Check that the Linux CLI is logged in.",
                      "fa": "فهرست پیکربندی‌ها خوانده نشد. ورود CLI لینوکس را بررسی کنید.",
                      "ru": "Не удалось получить список. Проверьте, что Linux CLI вошёл в аккаунт."},
    "large_tls": {"en": "Large TLS", "fa": "TLS بزرگ", "ru": "Большая TLS"},
    "routing": {"en": "Server routing", "fa": "مسیریابی سرور", "ru": "Маршрутизация серверов"},
    "mode_off": {"en": "Off", "fa": "خاموش", "ru": "Выкл"},
    "mode_on": {"en": "On", "fa": "روشن", "ru": "Вкл"},
    "mode_both": {"en": "Test both", "fa": "تست هر دو", "ru": "Оба"},
    "mode_auto": {"en": "Auto", "fa": "خودکار", "ru": "Авто"},
    "mode_regular": {"en": "Regular", "fa": "عادی", "ru": "Рег."},
    "mode_alternate": {"en": "Alternate", "fa": "جایگزین", "ru": "Альтерн."},
    "top_first": {"en": "top runs first", "fa": "بالایی‌ها اول اجرا می‌شوند", "ru": "верхние — первыми"},
    "ports_tip": {"en": "Choose which ports to test", "fa": "انتخاب پورت‌ها برای تست", "ru": "Выбрать порты для теста"},
    "options": {"en": "Options", "fa": "گزینه‌ها", "ru": "Параметры"},
    "opt_resume": {"en": "Skip already tested", "fa": "رد کردن موارد تست‌شده", "ru": "Пропускать проверенные"},
    "opt_resume_tip": {"en": "Keep stored results and only test what is missing.",
                       "fa": "نتایج ذخیره‌شده حفظ می‌شود و فقط موارد باقی‌مانده تست می‌شوند.",
                       "ru": "Сохранить прежние результаты и проверить только недостающее."},
    "opt_shuffle": {"en": "Shuffle cities", "fa": "ترتیب تصادفی شهرها", "ru": "Перемешать города"},
    "opt_shuffle_tip": {"en": "Test cities in random order.", "fa": "شهرها به ترتیب تصادفی تست می‌شوند.",
                        "ru": "Проверять города в случайном порядке."},
    "opt_chaos": {"en": "Shuffle every test", "fa": "ترتیب تصادفی همهٔ تست‌ها", "ru": "Перемешать все тесты"},
    "opt_chaos_tip": {"en": "Randomise the full list of server × protocol × port tests.",
                      "fa": "کل فهرست تست‌های سرور × پروتکل × پورت به‌صورت تصادفی مرتب می‌شود.",
                      "ru": "Случайный порядок всех тестов «сервер × протокол × порт»."},
    "opt_stop": {"en": "Stop on first success", "fa": "توقف با اولین اتصال موفق", "ru": "Стоп при первом успехе"},
    "opt_stop_tip": {"en": "End the run as soon as one route works and stay connected.",
                     "fa": "به محض کار کردن یک مسیر، تست متوقف می‌شود و اتصال برقرار می‌ماند.",
                     "ru": "Завершить тест, как только заработает маршрут, и остаться подключённым."},
    "timing_summary": {"en": "Ping & timing · {host} · {count} pings · {timeout} s",
                       "fa": "پینگ و زمان‌بندی · {host} · {count} پینگ · {timeout} ثانیه",
                       "ru": "Пинг и тайминги · {host} · пингов: {count} · {timeout} с"},
    "ping_timing": {"en": "Ping & timing", "fa": "پینگ و زمان‌بندی", "ru": "Пинг и тайминги"},
    "ping_host": {"en": "Ping host", "fa": "میزبان پینگ", "ru": "Адрес для пинга"},
    "ping_host_tip": {"en": "Host pinged through the tunnel after connecting.",
                      "fa": "آدرسی که پس از اتصال از داخل تونل پینگ می‌شود.",
                      "ru": "Адрес, который пингуется через туннель после подключения."},
    "pings_per_test": {"en": "Pings per test", "fa": "تعداد پینگ در هر تست", "ru": "Пингов на тест"},
    "connect_timeout": {"en": "Connect timeout (s)", "fa": "مهلت اتصال (ثانیه)", "ru": "Тайм-аут подключения (с)"},
    "connect_timeout_tip": {"en": "3 – 300 seconds", "fa": "3 تا 300 ثانیه", "ru": "3–300 секунд"},
    "settle_delay": {"en": "Settle delay (s)", "fa": "مکث پس از اتصال (ثانیه)", "ru": "Пауза после подключения (с)"},
    "settle_delay_tip": {"en": "Pause after connecting before pinging (0 – 60 s).",
                         "fa": "مکث بین اتصال و پینگ (0 تا 60 ثانیه).",
                         "ru": "Пауза между подключением и пингом (0–60 с)."},
    "windscribe_cli": {"en": "Windscribe CLI", "fa": "Windscribe CLI", "ru": "Windscribe CLI"},
    "cli_ready": {"en": "Windscribe CLI ready", "fa": "Windscribe CLI آماده است", "ru": "Windscribe CLI готов"},
    "cli_missing": {"en": "Windscribe CLI not found · set path", "fa": "Windscribe CLI پیدا نشد · مسیر را تعیین کنید",
                    "ru": "Windscribe CLI не найден · укажите путь"},
    "set_cli_path": {"en": "Set the path to windscribe-cli under Ping & timing.",
                     "fa": "مسیر windscribe-cli را در بخش «پینگ و زمان‌بندی» تعیین کنید.",
                     "ru": "Укажите путь к windscribe-cli в разделе «Пинг и тайминги»."},
    "locate_cli": {"en": "Locate windscribe-cli", "fa": "پیدا کردن windscribe-cli", "ru": "Найти windscribe-cli"},
    "all_files": {"en": "All files", "fa": "همهٔ فایل‌ها", "ru": "Все файлы"},
    "cli_found": {"en": "Windscribe CLI found.", "fa": "Windscribe CLI پیدا شد.", "ru": "Windscribe CLI найден."},

    # --- header / buttons ---
    "export_csv": {"en": "Export CSV", "fa": "خروجی CSV", "ru": "Экспорт CSV"},
    "export_tip": {"en": "Save all stored results to the reports folder  (Ctrl+E)",
                   "fa": "ذخیرهٔ همهٔ نتایج در پوشهٔ reports  (Ctrl+E)",
                   "ru": "Сохранить все результаты в папку reports  (Ctrl+E)"},
    "disconnect": {"en": "Disconnect", "fa": "قطع اتصال", "ru": "Отключить"},
    "disconnect_tip": {"en": "Disconnect Windscribe", "fa": "قطع اتصال Windscribe", "ru": "Отключить Windscribe"},
    "start": {"en": "Start", "fa": "شروع", "ru": "Старт"},
    "start_n": {"en": "Start  ·  {n} tests", "fa": "شروع  ·  {n} تست", "ru": "Старт  ·  тестов: {n}"},
    "start_tip": {"en": "Start testing  (Ctrl+Enter)", "fa": "شروع تست  (Ctrl+Enter)", "ru": "Начать тест  (Ctrl+Enter)"},
    "stop": {"en": "Stop    Esc", "fa": "توقف    Esc", "ru": "Стоп    Esc"},
    "stopping": {"en": "Stopping…", "fa": "در حال توقف…", "ru": "Остановка…"},
    "disconnecting": {"en": "Disconnecting…", "fa": "در حال قطع اتصال…", "ru": "Отключение…"},
    "connected_chip": {"en": "Connected · {x}", "fa": "متصل · {x}", "ru": "Подключено · {x}"},

    # --- header titles ---
    "ready": {"en": "Ready to test", "fa": "آمادهٔ تست", "ru": "Готово к тесту"},
    "ready_sub": {"en": "{scope} · {n} tests", "fa": "{scope} · {n} تست", "ru": "{scope} · тестов: {n}"},
    "testing": {"en": "Testing {scope}", "fa": "در حال تست {scope}", "ru": "Тестирование: {scope}"},
    "started": {"en": "Started {t}", "fa": "شروع در {t}", "ru": "Начато в {t}"},
    "with_profile": {"en": " · profile “{p}”", "fa": " · پروفایل «{p}»", "ru": " · профиль «{p}»"},
    "finished_sub": {"en": "{scope} · finished {t} · took {d}", "fa": "{scope} · پایان در {t} · مدت {d}",
                     "ru": "{scope} · завершено в {t} · заняло {d}"},
    "found_route": {"en": "Found a working route", "fa": "یک مسیر سالم پیدا شد", "ru": "Найден рабочий маршрут"},
    "stopped_first": {"en": "Stopped on first success", "fa": "توقف با اولین موفقیت",
                      "ru": "Остановлено на первом успехе"},
    "run_stopped": {"en": "Run stopped", "fa": "تست متوقف شد", "ru": "Тест остановлен"},
    "run_complete": {"en": "Run complete", "fa": "تست کامل شد", "ru": "Тест завершён"},
    "n_of_tests": {"en": "{a} of {b} tests", "fa": "{a} از {b} تست", "ru": "тестов: {a} из {b}"},

    # --- live card ---
    "cap_ready": {"en": "Ready to test", "fa": "آمادهٔ تست", "ru": "Готово к тесту"},
    "cap_testing": {"en": "Now testing", "fa": "در حال تست", "ru": "Сейчас проверяется"},
    "cap_connecting": {"en": "Connecting", "fa": "در حال اتصال", "ru": "Подключение"},
    "cap_starting": {"en": "Starting", "fa": "در حال شروع", "ru": "Запуск"},
    "cap_stopping": {"en": "Stopping after this step", "fa": "توقف پس از این مرحله", "ru": "Остановка после этого шага"},
    "phase_disconnect": {"en": "Disconnect", "fa": "قطع اتصال", "ru": "Отключение"},
    "phase_connect": {"en": "Connect", "fa": "اتصال", "ru": "Подключение"},
    "phase_settle": {"en": "Settle", "fa": "مکث", "ru": "Пауза"},
    "phase_ping": {"en": "Ping", "fa": "پینگ", "ru": "Пинг"},
    "skipped": {"en": "skipped", "fa": "رد شد", "ru": "пропущено"},
    "failed_lc": {"en": "failed", "fa": "ناموفق", "ru": "ошибка"},
    "tests_queued": {"en": "{n} tests queued", "fa": "{n} تست در صف", "ru": "Тестов в очереди: {n}"},
    "press_start": {"en": "Press Start or Ctrl+Enter", "fa": "روی «شروع» بزنید یا Ctrl+Enter",
                    "ru": "Нажмите «Старт» или Ctrl+Enter"},
    "test_progress": {"en": "Test {i} of {total} · {pct}%", "fa": "تست {i} از {total} · {pct}%",
                      "ru": "Тест {i} из {total} · {pct}%"},
    "preparing": {"en": "Preparing the test queue…", "fa": "در حال آماده‌سازی صف تست…",
                  "ru": "Подготовка очереди тестов…"},
    "manual_connection": {"en": "Manual connection", "fa": "اتصال دستی", "ru": "Ручное подключение"},
    "elapsed": {"en": "{t} elapsed", "fa": "{t} گذشته", "ru": "прошло {t}"},
    "time_left": {"en": "about {left} left · {elapsed}", "fa": "حدود {left} مانده · {elapsed}",
                  "ru": "осталось около {left} · {elapsed}"},
    "estimating": {"en": "estimating time left · {elapsed}", "fa": "در حال تخمین زمان باقی‌مانده · {elapsed}",
                   "ru": "оценка оставшегося времени · {elapsed}"},
    "ping_detail": {"en": "min {a} · max {b} · loss {c}%", "fa": "کمترین {a} · بیشترین {b} · اتلاف {c}%",
                    "ru": "мин {a} · макс {b} · потери {c}%"},
    "no_reply": {"en": "no reply", "fa": "بدون پاسخ", "ru": "нет ответа"},

    # --- best route card / stats ---
    "best_route_caption": {"en": "Best route on this network", "fa": "بهترین مسیر در این شبکه",
                           "ru": "Лучший маршрут в этой сети"},
    "ping": {"en": "Ping", "fa": "پینگ", "ru": "Пинг"},
    "loss": {"en": "Loss", "fa": "اتلاف", "ru": "Потери"},
    "connect_time": {"en": "Connect", "fa": "زمان اتصال", "ru": "Подключение"},
    "connect_btn": {"en": "Connect", "fa": "اتصال", "ru": "Подключить"},
    "stat_connected": {"en": "Connected", "fa": "متصل", "ru": "Подключено"},
    "stat_failed": {"en": "Failed", "fa": "ناموفق", "ru": "Неудачно"},
    "stat_rate": {"en": "Success rate", "fa": "درصد موفقیت", "ru": "Успешность"},
    "stat_best": {"en": "Best ping", "fa": "بهترین پینگ", "ru": "Лучший пинг"},
    "stat_avg": {"en": "Avg connect", "fa": "میانگین زمان اتصال", "ru": "Ср. подключение"},

    # --- results ---
    "tab_results": {"en": "Results", "fa": "نتایج", "ru": "Результаты"},
    "tab_best": {"en": "Best routes", "fa": "بهترین مسیرها", "ru": "Лучшие"},
    "tab_log": {"en": "Log", "fa": "گزارش", "ru": "Журнал"},
    "search_results": {"en": "Search city, country, protocol…", "fa": "جستجو در نتایج…", "ru": "Поиск…"},
    "search_tip": {"en": "Filter the results  (Ctrl+F)", "fa": "فیلتر نتایج  (Ctrl+F)",
                   "ru": "Фильтр результатов  (Ctrl+F)"},
    "filter_all": {"en": "All", "fa": "همه", "ru": "Все"},
    "filter_connected": {"en": "Connected", "fa": "متصل", "ru": "Успех"},
    "filter_failed": {"en": "Failed", "fa": "ناموفق", "ru": "Сбои"},
    "col_location": {"en": "Location", "fa": "مکان", "ru": "Локация"},
    "col_country": {"en": "Country", "fa": "کشور", "ru": "Страна"},
    "col_route": {"en": "Route", "fa": "مسیر", "ru": "Маршрут"},
    "col_result": {"en": "Result", "fa": "نتیجه", "ru": "Результат"},
    "col_connect": {"en": "Connect", "fa": "اتصال", "ru": "Подкл."},
    "col_ping": {"en": "Ping", "fa": "پینگ", "ru": "Пинг"},
    "col_loss": {"en": "Loss", "fa": "اتلاف", "ru": "Потери"},
    "status_SUCCESS": {"en": "Connected", "fa": "متصل شد", "ru": "Подключено"},
    "status_FAILURE": {"en": "Timed out", "fa": "پایان مهلت", "ru": "Тайм-аут"},
    "status_INVALID_LOC": {"en": "Unavailable", "fa": "ناموجود", "ru": "Недоступно"},
    "menu_connect": {"en": "Connect to this route", "fa": "اتصال به این مسیر", "ru": "Подключиться к этому маршруту"},
    "menu_copy_route": {"en": "Copy route", "fa": "کپی مسیر", "ru": "Копировать маршрут"},
    "menu_copy_row": {"en": "Copy row", "fa": "کپی ردیف", "ru": "Копировать строку"},
    "empty_results": {"en": "No results yet.\nPress Start (Ctrl+Enter) to begin testing.",
                      "fa": "هنوز نتیجه‌ای نیست.\nبرای شروع تست روی «شروع» بزنید (Ctrl+Enter).",
                      "ru": "Результатов пока нет.\nНажмите «Старт» (Ctrl+Enter), чтобы начать."},
    "empty_filter": {"en": "Nothing matches this filter.", "fa": "موردی با این فیلتر پیدا نشد.",
                     "ru": "По этому фильтру ничего не найдено."},
    "copied": {"en": "Copied to clipboard.", "fa": "در کلیپ‌بورد کپی شد.", "ru": "Скопировано в буфер обмена."},
    "log_copied": {"en": "Log copied to clipboard.", "fa": "گزارش در کلیپ‌بورد کپی شد.",
                   "ru": "Журнал скопирован в буфер обмена."},

    # --- insights ---
    "works_title": {"en": "What works here", "fa": "اینجا چه کار می‌کند", "ru": "Что здесь работает"},
    "works_sub": {"en": "Success rate by protocol", "fa": "درصد موفقیت هر پروتکل", "ru": "Успешность по протоколам"},
    "works_empty": {"en": "Once tests run, this shows which protocols get through on your network.",
                    "fa": "پس از اجرای تست‌ها، اینجا نشان می‌دهد کدام پروتکل‌ها در شبکهٔ شما کار می‌کنند.",
                    "ru": "После тестов здесь будет видно, какие протоколы проходят в вашей сети."},
    "tip_one": {"en": "Tip: {names} rarely connects here. Turn it off to save time.",
                "fa": "پیشنهاد: {names} اینجا به‌ندرت وصل می‌شود. برای صرفه‌جویی در زمان، خاموشش کنید.",
                "ru": "Совет: {names} здесь почти не подключается. Отключите его, чтобы сэкономить время."},
    "tip_many": {"en": "Tip: {names} rarely connect here. Turn them off to save time.",
                 "fa": "پیشنهاد: {names} اینجا به‌ندرت وصل می‌شوند. برای صرفه‌جویی در زمان، خاموششان کنید.",
                 "ru": "Совет: {names} здесь почти не подключаются. Отключите их, чтобы сэкономить время."},

    # --- scope ---
    "all_servers": {"en": "All servers", "fa": "همهٔ سرورها", "ru": "Все серверы"},
    "servers_in": {"en": "{n} servers in {c} countries", "fa": "{n} سرور در {c} کشور",
                   "ru": "Серверов: {n} · стран: {c}"},
    "servers_in_one": {"en": "{n} servers in 1 country", "fa": "{n} سرور در 1 کشور",
                       "ru": "Серверов: {n} · стран: 1"},
    "more": {"en": " +{n} more", "fa": " و {n} مورد دیگر", "ru": " и ещё {n}"},
    "scope_math": {"en": "{s} servers × {r} routes", "fa": "{s} سرور × {r} مسیر",
                   "ru": "{s} серв. × {r} маршр."},
    "tests_n": {"en": "{n} tests", "fa": "{n} تست", "ru": "тестов: {n}"},
    "no_list_toast": {"en": "There's no server list yet.", "fa": "هنوز فهرست سروری وجود ندارد.",
                      "ru": "Списка серверов пока нет."},
    "update_tip": {"en": "Download the latest server list from windscribe.com.",
                   "fa": "دانلود جدیدترین فهرست سرورها از windscribe.com.",
                   "ru": "Загрузить актуальный список серверов с windscribe.com."},
    "current_list": {"en": "Current list: {d}", "fa": "فهرست فعلی: {d}", "ru": "Текущий список: {d}"},
    "no_list_yet": {"en": "No list downloaded yet.", "fa": "هنوز فهرستی دانلود نشده است.",
                    "ru": "Список ещё не загружен."},
    "update_failed": {"en": "Couldn't download the server list: {e}", "fa": "دانلود فهرست سرورها ممکن نشد: {e}",
                      "ru": "Не удалось загрузить список серверов: {e}"},
    "list_updated": {"en": "Server list updated: {n} servers in {c} countries",
                     "fa": "فهرست سرورها به‌روز شد: {n} سرور در {c} کشور",
                     "ru": "Список серверов обновлён: серверов — {n}, стран — {c}"},
    "changes_new": {"en": "{n} new", "fa": "{n} جدید", "ru": "новых: {n}"},
    "changes_removed": {"en": "{n} removed", "fa": "{n} حذف‌شده", "ru": "удалено: {n}"},
    "selection_gone": {"en": " None of your selected servers exist any more, so all servers are selected.",
                       "fa": " هیچ‌کدام از سرورهای انتخاب‌شده دیگر وجود ندارند، پس همهٔ سرورها انتخاب شدند.",
                       "ru": " Выбранных серверов больше нет, поэтому выбраны все серверы."},

    # --- picker ---
    "choose_locations": {"en": "Choose locations", "fa": "انتخاب مکان‌ها", "ru": "Выбор локаций"},
    "picker_hint": {"en": "Search, or browse by region. Click a server to select it, or the column on the right "
                          "to select a whole country. Nothing selected means every server.",
                    "fa": "جستجو کنید یا بر اساس منطقه مرور کنید. برای انتخاب هر سرور روی آن کلیک کنید و برای انتخاب "
                          "کل یک کشور روی ستون سمت راست. اگر چیزی انتخاب نشود، همهٔ سرورها تست می‌شوند.",
                    "ru": "Ищите или выбирайте по региону. Нажмите на сервер, чтобы выбрать его, или на колонку справа, "
                          "чтобы выбрать всю страну. Если ничего не выбрано, проверяются все серверы."},
    "search_locations": {"en": "Search country, city or server…", "fa": "جستجوی کشور، شهر یا سرور…",
                         "ru": "Поиск страны, города или сервера…"},
    "no_match_locations": {"en": "No locations match your search.", "fa": "مکانی با این جستجو پیدا نشد.",
                           "ru": "По вашему запросу ничего не найдено."},
    "n_selected": {"en": "{n} of {total} servers selected", "fa": "{n} از {total} سرور انتخاب شده",
                   "ru": "Выбрано серверов: {n} из {total}"},
    "nothing_selected": {"en": "Nothing selected · all {total} servers will be tested",
                         "fa": "چیزی انتخاب نشده · همهٔ {total} سرور تست می‌شوند",
                         "ru": "Ничего не выбрано · будут проверены все серверы ({total})"},
    "select_shown": {"en": "Select shown", "fa": "انتخاب موارد نمایش‌داده‌شده", "ru": "Выбрать показанные"},

    # --- ports ---
    "ports_title": {"en": "{p} ports", "fa": "پورت‌های {p}", "ru": "Порты {p}"},
    "ports_hint": {"en": "Each selected port is tested on every server.",
                   "fa": "هر پورت انتخاب‌شده روی همهٔ سرورها تست می‌شود.",
                   "ru": "Каждый выбранный порт проверяется на всех серверах."},
    "select_all": {"en": "Select all", "fa": "انتخاب همه", "ru": "Выбрать все"},
    "select_none": {"en": "None", "fa": "هیچ‌کدام", "ru": "Ничего"},
    "ports_none": {"en": "none", "fa": "هیچ", "ru": "нет"},
    "ports_all": {"en": "all {n}", "fa": "همه ({n})", "ru": "все {n}"},
    "ports_some": {"en": "{a} of {b}", "fa": "{a} از {b}", "ru": "{a} из {b}"},

    # --- profiles ---
    "save_profile": {"en": "Save profile", "fa": "ذخیرهٔ پروفایل", "ru": "Сохранить профиль"},
    "save_profile_hint": {"en": "Saves locations, protocols and options under this name.",
                          "fa": "مکان‌ها، پروتکل‌ها و گزینه‌ها با این نام ذخیره می‌شوند.",
                          "ru": "Локации, протоколы и параметры сохраняются под этим именем."},
    "profile_name": {"en": "Profile name", "fa": "نام پروفایل", "ru": "Название профиля"},
    "profile_saved": {"en": "Profile “{n}” saved.", "fa": "پروفایل «{n}» ذخیره شد.", "ru": "Профиль «{n}» сохранён."},
    "profile_loaded": {"en": "Profile “{n}” loaded.", "fa": "پروفایل «{n}» بارگذاری شد.",
                       "ru": "Профиль «{n}» загружен."},
    "profile_deleted": {"en": "Profile “{n}” deleted.", "fa": "پروفایل «{n}» حذف شد.", "ru": "Профиль «{n}» удалён."},
    "choose_to_delete": {"en": "Choose a saved profile to delete.", "fa": "یک پروفایل ذخیره‌شده را برای حذف انتخاب کنید.",
                         "ru": "Выберите сохранённый профиль для удаления."},
    "delete_profile": {"en": "Delete profile", "fa": "حذف پروفایل", "ru": "Удалить профиль"},
    "delete_profile_q": {"en": "Delete profile “{n}”?", "fa": "پروفایل «{n}» حذف شود؟", "ru": "Удалить профиль «{n}»?"},

    # --- validation / jobs ---
    "need_protocol": {"en": "Turn on at least one protocol with at least one port.",
                      "fa": "دست‌کم یک پروتکل با دست‌کم یک پورت را روشن کنید.",
                      "ru": "Включите хотя бы один протокол хотя бы с одним портом."},
    "must_be_number": {"en": "{name} must be a whole number between {a} and {b}.",
                       "fa": "«{name}» باید عددی صحیح بین {a} و {b} باشد.",
                       "ru": "«{name}» — целое число от {a} до {b}."},
    "name_timeout": {"en": "Connect timeout", "fa": "مهلت اتصال", "ru": "Тайм-аут подключения"},
    "name_settle": {"en": "Settle delay", "fa": "مکث پس از اتصال", "ru": "Пауза после подключения"},
    "name_pings": {"en": "Pings per test", "fa": "تعداد پینگ در هر تست", "ru": "Пингов на тест"},
    "bad_host": {"en": "Enter a valid ping host, for example 1.1.1.1.",
                 "fa": "یک میزبان پینگ معتبر وارد کنید، مثلاً 1.1.1.1.",
                 "ru": "Введите корректный адрес для пинга, например 1.1.1.1."},
    "start_fresh": {"en": "Start fresh?", "fa": "از نو شروع شود؟", "ru": "Начать заново?"},
    "start_fresh_q": {"en": "This will erase {n} stored results and start over.\n\n"
                            "Turn on “Skip already tested” to keep them and continue instead.",
                      "fa": "{n} نتیجهٔ ذخیره‌شده پاک می‌شود و تست از نو شروع می‌شود.\n\n"
                            "برای نگه داشتن آن‌ها و ادامهٔ کار، «رد کردن موارد تست‌شده» را روشن کنید.",
                      "ru": "Сохранённые результаты ({n}) будут удалены, и тест начнётся заново.\n\n"
                            "Включите «Пропускать проверенные», чтобы сохранить их и продолжить."},
    "connected_to": {"en": "Connected to {x}.", "fa": "به {x} متصل شد.", "ru": "Подключено: {x}."},
    "finished_toast": {"en": "Finished: {ok} connected, {fail} failed.", "fa": "پایان: {ok} متصل، {fail} ناموفق.",
                       "ru": "Готово: успешно — {ok}, неудачно — {fail}."},
    "wait_run": {"en": "Wait for the current run to finish first.", "fa": "ابتدا صبر کنید تست فعلی تمام شود.",
                 "ru": "Сначала дождитесь окончания текущего теста."},
    "connected_via": {"en": "Connected to {w} via {r}.", "fa": "از طریق {r} به {w} متصل شد.",
                      "ru": "Подключено к {w} через {r}."},
    "could_not_connect": {"en": "Could not connect to {w} via {r}.", "fa": "اتصال به {w} از طریق {r} ممکن نشد.",
                          "ru": "Не удалось подключиться к {w} через {r}."},
    "disconnected": {"en": "Disconnected.", "fa": "اتصال قطع شد.", "ru": "Отключено."},
    "could_not_disconnect": {"en": "Could not disconnect.", "fa": "قطع اتصال ممکن نشد.",
                             "ru": "Не удалось отключиться."},
    "csv_failed": {"en": "Could not save CSV. {e}", "fa": "ذخیرهٔ CSV ممکن نشد. {e}", "ru": "Не удалось сохранить CSV. {e}"},
    "exported": {"en": "Exported {n} rows to {f}", "fa": "{n} ردیف در {f} ذخیره شد",
                 "ru": "Экспортировано строк: {n} → {f}"},
    "quit": {"en": "Quit", "fa": "خروج", "ru": "Выход"},
    "quit_q": {"en": "A test is still running. Stop it and quit?", "fa": "تستی در حال اجراست. متوقف شود و خارج شوید؟",
               "ru": "Тест ещё идёт. Остановить его и выйти?"},
}
