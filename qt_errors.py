"""Localized messages from the Cold Steel I preview controller."""

import re


RU = {
    "Choose a .csv file for inventory export.": "Для экспорта инвентаря выберите файл .csv.",
    "Open a compatible save first": "Сначала откройте совместимое сохранение.",
    "No save loaded": "Сохранение не открыто.",
    "No compatible Cold Steel I Steam slots were found.": "Совместимые сохранения Cold Steel I для Steam не найдены.",
    "Expected a Cold Steel I XSEED PC save (460,992 bytes, version 8).":
        "Ожидается сохранение Cold Steel I для Steam (460 992 байта, версия 8).",
    "Unrecognized inventory record in the save.": "В сохранении обнаружена неизвестная запись инвентаря.",
    "Steam save operations are unavailable in sample mode.": "Файлы Steam недоступны в учебном режиме.",
    "The save changed while it was being read. Reopen it.": "Файл изменился во время чтения. Откройте его заново.",
    "The source save changed on disk. Reopen it or save a copy.":
        "Исходный файл изменился на диске. Откройте его заново или сохраните отдельную копию.",
    "Choose a .dat file for the save copy.": "Выберите файл с расширением .dat для копии.",
    "Use Save with backup to replace the opened slot.": "Для перезаписи открытого слота используйте запись с резервной копией.",
    "Save a new .dat copy when a backup is open.": "Для открытой резервной копии сохраните отдельный файл .dat.",
    "This Master Quartz is already equipped.": "Этот мастер-кварц уже экипирован.",
    "The inventory has no free slots.": "В инвентаре нет свободных слотов.",
    "Game directory not found": "Папка игры не найдена.",
    "No readable item tables found": "Выберите папку Cold Steel I с таблицей data/text/dat_us/t_item.tbl.",
    "Select an original English catalog. This file contains Russian or another language.":
        "Выберите оригинальную английскую таблицу предметов Cold Steel I.",
    "Expected a Cold Steel I t_item.tbl.": "Ожидается таблица предметов t_item.tbl из Cold Steel I.",
    "Invalid Cold Steel I item table.": "Таблица предметов Cold Steel I повреждена.",
    "Invalid Cold Steel I fishing notebook table.": "Таблица журнала рыбалки Cold Steel I повреждена.",
    "Invalid Cold Steel I DLC table.": "Таблица дополнений Cold Steel I повреждена.",
    "Invalid t_item.tbl size.": "Некорректный размер таблицы t_item.tbl.",
    "This item cannot be edited.": "Этот предмет недоступен для редактирования.",
    "Unable to save preferences.": "Не удалось сохранить настройки.",
    "The optional item translations could not be loaded.": "Не удалось загрузить дополнительные переводы предметов.",
}


def error_text(error, language: str) -> str:
    message = str(error)
    if language != "ru":
        return message
    limit = re.fullmatch(r"Quantity must be between 0 and (\d+)\.", message)
    if limit:
        return f"Количество должно быть от 0 до {limit[1]}."
    if message.startswith("A concurrent save was preserved as: "):
        return "Другая программа заменила файл во время записи. Её версия сохранена здесь: " + message.partition(": ")[2]
    if isinstance(error, FileExistsError):
        return "Файл уже существует. Выберите другое имя."
    duplicate = re.fullmatch(r"Duplicate (inventory ID|item ID) ([\dA-F]+) in the (save|t_item\.tbl)\.", message)
    if duplicate:
        source = "сохранении" if duplicate[3] == "save" else "таблице t_item.tbl"
        return f"В {source} повторяется ID предмета 0x{duplicate[2]}."
    if isinstance(error, FileNotFoundError) and message not in RU:
        return f"Файл или папка не найдены. {error.filename or message}"
    if isinstance(error, PermissionError):
        return f"Нет доступа к файлу или папке. {error.filename or message}"
    return RU.get(message, message)
