"""
i18n.py
===============================================================================
FUTAS — trilingual interface (English / Русский / Oʻzbek).

A tiny, dependency-free translation layer. `t(key, lang)` returns the string for
the active language, falling back to English and then to the key itself, so a
missing translation never crashes the UI. The app stores the chosen language in
session state and wraps user-facing labels with `t(...)`. The Telegram alert is
built from the same dictionary so messages can be sent in the selected language.
===============================================================================
"""

from __future__ import annotations

from typing import Dict

# Display name -> language code (order = selector order)
LANGUAGES: Dict[str, str] = {"English": "en", "Русский": "ru", "Oʻzbek": "uz"}
CODES = list(LANGUAGES.values())

# key -> {en, ru, uz}
_T: Dict[str, Dict[str, str]] = {
    # ---- app chrome ----------------------------------------------------------
    "subtitle": {
        "en": "Adaptive market-structure analysis on the Fibonacci Urvin coefficient system",
        "ru": "Адаптивный анализ структуры рынка на системе коэффициентов Фибоначчи Урвин",
        "uz": "Fibonachchi Urvin koeffitsiyentlari tizimida moslashuvchan bozor tahlili"},
    "language": {"en": "Language", "ru": "Язык", "uz": "Til"},
    "data_source": {"en": "Data source", "ru": "Источник данных", "uz": "Maʼlumot manbai"},
    "asset_symbol": {"en": "Asset symbol", "ru": "Актив (символ)", "uz": "Aktiv (belgi)"},
    "analysis_settings": {"en": "Analysis settings", "ru": "Настройки анализа",
                          "uz": "Tahlil sozlamalari"},
    "data_params": {"en": "Data & parameters", "ru": "Данные и параметры",
                    "uz": "Maʼlumot va parametrlar"},
    "load_data_info": {
        "en": "Load market data from the sidebar to begin (CSV, live fetch, manual, "
              "or a synthetic sample).",
        "ru": "Загрузите рыночные данные на боковой панели, чтобы начать (CSV, "
              "онлайн-загрузка, вручную или синтетический пример).",
        "uz": "Boshlash uchun yon paneldan bozor maʼlumotini yuklang (CSV, jonli "
              "yuklash, qoʻlda yoki sintetik namuna)."},
    "run_analysis": {"en": "Run FUTAS analysis", "ru": "Запустить анализ FUTAS",
                     "uz": "FUTAS tahlilini ishga tushirish"},
    "not_advice": {"en": "Scientific research & algorithmic-testing tool. Not financial advice.",
                   "ru": "Научно-исследовательский инструмент. Не финансовая рекомендация.",
                   "uz": "Ilmiy-tadqiqot vositasi. Moliyaviy maslahat emas."},
    # ---- tabs ----------------------------------------------------------------
    "tab_live": {"en": "Live Center", "ru": "Лайв-центр", "uz": "Jonli markaz"},
    "tab_analysis": {"en": "Analysis", "ru": "Анализ", "uz": "Tahlil"},
    "tab_signal": {"en": "Signal & Risk", "ru": "Сигнал и риск", "uz": "Signal va risk"},
    "tab_backtest": {"en": "Backtest report", "ru": "Бэктест-отчёт", "uz": "Backtest hisoboti"},
    "tab_worked": {"en": "Worked example", "ru": "Разбор сделки", "uz": "Tahlil namunasi"},
    "tab_screenshot": {"en": "Screenshot TA", "ru": "Скриншот-анализ", "uz": "Skrinshot tahlili"},
    "tab_telegram": {"en": "Telegram", "ru": "Telegram", "uz": "Telegram"},
    "tab_data": {"en": "Data", "ru": "Данные", "uz": "Maʼlumotlar"},
    "tab_explanation": {"en": "Explanation", "ru": "Объяснение", "uz": "Izoh"},
    "tab_science": {"en": "Science", "ru": "Наука", "uz": "Ilmiy asos"},
    # ---- overview metrics ----------------------------------------------------
    "high": {"en": "High", "ru": "Максимум", "uz": "Yuqori"},
    "low": {"en": "Low", "ru": "Минимум", "uz": "Quyi"},
    "range": {"en": "Range", "ru": "Диапазон", "uz": "Diapazon"},
    "current": {"en": "Current", "ru": "Текущая", "uz": "Joriy narx"},
    "trend": {"en": "Trend", "ru": "Тренд", "uz": "Trend"},
    "phase": {"en": "Phase", "ru": "Фаза", "uz": "Faza"},
    "structure_bias": {"en": "Structure bias", "ru": "Структурный уклон", "uz": "Struktura yoʻnalishi"},
    "momentum": {"en": "Momentum (confirm-only)", "ru": "Моментум (подтверждение)",
                 "uz": "Momentum (tasdiq)"},
    "volume": {"en": "Volume (confirm-only)", "ru": "Объём (подтверждение)", "uz": "Hajm (tasdiq)"},
    "higher_tf": {"en": "Higher timeframe", "ru": "Старший таймфрейм", "uz": "Yuqori vaqt oraligʻi"},
    # ---- signal / risk -------------------------------------------------------
    "entry": {"en": "Entry", "ru": "Вход", "uz": "Kirish"},
    "stop_loss": {"en": "Stop Loss", "ru": "Стоп-лосс", "uz": "Stop Loss"},
    "take_profit": {"en": "Take Profit", "ru": "Тейк-профит", "uz": "Take Profit"},
    "risk_reward": {"en": "Risk/Reward", "ru": "Риск/Прибыль", "uz": "Risk/Daromad"},
    "confidence": {"en": "Confidence", "ru": "Уверенность", "uz": "Ishonch"},
    # ---- active-timeframe banner --------------------------------------------
    "active_tf": {"en": "ACTIVE ANALYSIS TIMEFRAME", "ru": "АКТИВНЫЙ ТАЙМФРЕЙМ АНАЛИЗА",
                  "uz": "FAOL TAHLIL VAQT ORALIGʻI"},
    "candles": {"en": "candles", "ru": "свечей", "uz": "sham"},
    "signal_word": {"en": "signal", "ru": "сигнал", "uz": "signal"},
    "htf_confirmation": {"en": "Higher-TF confirmation", "ru": "Подтверждение старшего ТФ",
                         "uz": "Yuqori TF tasdigʻi"},
    "tf_note": {
        "en": "Everything below is computed only from the active timeframe. The higher "
              "timeframe is a separate confirmation read.",
        "ru": "Всё ниже рассчитано только по активному таймфрейму. Старший таймфрейм — "
              "отдельное подтверждение.",
        "uz": "Quyidagilarning barchasi faqat faol vaqt oraligʻidan hisoblanadi. Yuqori "
              "vaqt oraligʻi — alohida tasdiq."},
    # ---- Telegram status -----------------------------------------------------
    "connected": {"en": "Connected", "ru": "Подключено", "uz": "Ulangan"},
    "not_connected": {"en": "Not Connected", "ru": "Не подключено", "uz": "Ulanmagan"},
    # ---- Telegram alert field labels ----------------------------------------
    "alert_title": {"en": "FUTAS TRADING ALERT", "ru": "ТОРГОВЫЙ СИГНАЛ FUTAS",
                    "uz": "FUTAS SAVDO SIGNALI"},
    "f_asset": {"en": "Asset", "ru": "Актив", "uz": "Aktiv"},
    "f_timeframe": {"en": "Timeframe", "ru": "Таймфрейм", "uz": "Vaqt oraligʻi"},
    "f_signal_type": {"en": "Signal Type", "ru": "Тип сигнала", "uz": "Signal turi"},
    "f_entry": {"en": "Entry Price", "ru": "Цена входа", "uz": "Kirish narxi"},
    "f_sl": {"en": "Stop Loss", "ru": "Стоп-лосс", "uz": "Stop Loss"},
    "f_tp1": {"en": "Take Profit 1", "ru": "Тейк-профит 1", "uz": "Take Profit 1"},
    "f_tp2": {"en": "Take Profit 2", "ru": "Тейк-профит 2", "uz": "Take Profit 2"},
    "f_tp3": {"en": "Take Profit 3", "ru": "Тейк-профит 3", "uz": "Take Profit 3"},
    "f_rr": {"en": "Risk/Reward Ratio", "ru": "Соотношение риск/прибыль", "uz": "Risk/Daromad nisbati"},
    "f_rsi": {"en": "RSI", "ru": "RSI", "uz": "RSI"},
    "f_volume": {"en": "Volume Status", "ru": "Состояние объёма", "uz": "Hajm holati"},
    "f_structure": {"en": "Market Structure", "ru": "Структура рынка", "uz": "Bozor strukturasi"},
    "f_fu_level": {"en": "Fibonacci Urvin Level", "ru": "Уровень Фибоначчи Урвин",
                   "uz": "Fibonachchi Urvin darajasi"},
    "f_htf": {"en": "Higher Timeframe Confirmation", "ru": "Подтверждение старшего ТФ",
              "uz": "Yuqori vaqt oraligʻi tasdigʻi"},
    "f_confidence": {"en": "Confidence Score", "ru": "Оценка уверенности", "uz": "Ishonch bahosi"},
    "f_session": {"en": "World Session", "ru": "Мировая сессия", "uz": "Jahon sessiyasi"},
    "f_condition": {"en": "Market Condition", "ru": "Состояние рынка", "uz": "Bozor holati"},
    "f_time": {"en": "Signal Time", "ru": "Время сигнала", "uz": "Signal vaqti"},
    "f_valid": {"en": "Signal Valid Until", "ru": "Сигнал действителен до",
                "uz": "Signal amal qiladi"},
    "f_status": {"en": "Status", "ru": "Статус", "uz": "Holat"},
    "f_status_active": {"en": "ACTIVE (monitoring TP / SL)", "ru": "АКТИВЕН (мониторинг TP / SL)",
                        "uz": "FAOL (TP / SL kuzatilmoqda)"},
    "f_scenario": {"en": "Scenario", "ru": "Сценарий", "uz": "Stsenariy"},
    "f_reason": {"en": "Reason for Entry", "ru": "Причина входа", "uz": "Kirish sababi"},
    "f_invalidation": {"en": "Invalidation Condition", "ru": "Условие отмены",
                       "uz": "Bekor qilish sharti"},
    "f_notice": {"en": "Notice", "ru": "Примечание", "uz": "Eslatma"},
    "notice_text": {
        "en": "This is an analytical alert only and not financial advice.",
        "ru": "Это аналитическое уведомление, а не финансовая рекомендация.",
        "uz": "Bu faqat tahliliy ogohlantirish, moliyaviy maslahat emas."},
}


def t(key: str, lang: str = "en") -> str:
    """Translate `key` into `lang`, falling back to English then to the key."""
    entry = _T.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get("en") or key


def alert_labels(lang: str = "en") -> Dict[str, str]:
    """All Telegram-alert field labels for `lang` (passed to format_signal)."""
    keys = ["alert_title", "f_asset", "f_timeframe", "f_signal_type", "f_entry", "f_sl",
            "f_tp1", "f_tp2", "f_tp3", "f_rr", "f_rsi", "f_volume", "f_structure",
            "f_fu_level", "f_htf", "f_confidence", "f_session", "f_condition", "f_time",
            "f_valid", "f_status", "f_status_active", "f_scenario", "f_reason",
            "f_invalidation", "f_notice", "notice_text"]
    return {k: t(k, lang) for k in keys}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for code in CODES:
        print(f"[{code}] tab_analysis={t('tab_analysis', code)} · "
              f"run={t('run_analysis', code)} · entry={t('entry', code)}")
    print("missing-key fallback:", t("does_not_exist", "ru"))
    print("alert_labels(ru) keys:", len(alert_labels("ru")))
