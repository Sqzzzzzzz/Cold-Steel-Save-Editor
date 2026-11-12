# Trails of Cold Steel I Inventory Editor

Редактор инвентаря для Windows и сохранений Trails of Cold Steel I (XSEED PC, формат 460 992 байта). Проверен на слотах Steam. Поддержка GOG зависит от совпадения формата сохранения и расположения игровых файлов.

Интерфейс RU/EN показывает инвентарь и каталог рядом. В каталоге можно искать по названию и шестнадцатеричному ID, в обеих таблицах есть фильтр по категориям. Названия, описания и ограничения количества берутся из английского `t_item.tbl` установленной игры.

## Запуск

В PowerShell из папки проекта выполните:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\Run_Editor.bat
```

Стандартную папку Steam редактор находит при запуске. Для другой установки нажмите **«Папка игры»** и выберите каталог с `ed8.exe`. Кнопка **«Открыть сохранение…»** открывает папку слотов `Saved Games\Falcom\ed8`, если она существует.

- **«Добавить»** увеличивает количество предмета, выбранного в каталоге.
- **«Изменить»** устанавливает указанное количество выбранного предмета в инвентаре, **«Удалить»** убирает его из инвентаря.
- **«Сохранить»** записывает правки в открытый слот и оставляет рядом резервную копию `*.bak`. **«Сохранить копию…»** записывает результат по выбранному пути. Имя обычного слота в игре имеет вид `save019.dat`.

Редактируются предметы в инвентаре. Экипированные мастер-кварцы видны в каталоге, их повторное добавление заблокировано.

## Оригинальные иконки

Для импорта текстур из своей копии игры запустите команду с путями к игре и к [SenPatcher](https://github.com/AdmiralCurtiss/SenPatcher/releases):

```powershell
.\.venv\Scripts\python.exe game_art.py "C:\Program Files (x86)\Steam\steamapps\common\Trails of Cold Steel" "C:\Tools\SenPatcher.exe"
```

Импорт извлекает оригинальные атласы предметов и мастер-кварцев из `I_SYSTEM.pkg`, логотип из файлов игры и обложку из локального кэша Steam, если она доступна. Папка `assets` локальная. Чтобы заменить оформление шапки, используйте свои `assets/hero.jpg`, `assets/logo.png` и, при наличии, `assets/crest.png` для герба в боковой панели.

## Проверки

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Разметка слота сопоставлена с [описанием инвентаря Stormwave](https://github.com/Stormwave/SaveEditor/blob/main/public/modules/trails_of_cold_steel_1/data.json) и [открытым образцом PC](https://github.com/ItsAllAboutTheCode/save-converters/blob/main/tests/test_files/cold_steel_i/SAVE.pc). Формат таблицы предметов описан в [SenPatcher](https://github.com/AdmiralCurtiss/SenPatcher/blob/master/native/sen1/tbl.cpp).
