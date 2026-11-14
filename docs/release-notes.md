# Cold Steel I Inventory Editor v1.0.2

## What's new

- Fixed an error that prevented some New Game Plus saves from opening ([issue #1](https://github.com/Sqzzzzzzz/Cold-Steel-Save-Editor/issues/1)).
- Inventory edits preserve the second inventory block byte for byte. The fix was tested on copies of New Game Plus and regular Steam saves.
- Исправлена ошибка при загрузке сохранений из «Новой игры+». При записи второй блок инвентаря сохраняется побайтно.
- Added Russian and English reference descriptions for sepith and notebook entries.
- Corrected item descriptions and stats in both languages, including remaining English text in Russian descriptions.
- The translation report now includes missing descriptions.
- The Windows x64 ZIP contains a single EXE with the theme and translations built in.

## Installation

1. [Download the Windows x64 ZIP with a single EXE](https://github.com/Sqzzzzzzz/Cold-Steel-Save-Editor/releases/download/v1.0.2/Cold-Steel-I-Inventory-Editor-v1.0.2-windows-x64-onefile.zip). You can verify it with the [SHA-256 checksum](https://github.com/Sqzzzzzzz/Cold-Steel-Save-Editor/releases/download/v1.0.2/SHA256SUMS.txt).
2. Extract and run `Cold_Steel_I_Inventory_Editor.exe`.
3. Select your Steam game directory if the editor does not find it automatically, then open a compatible save.

Close the game before overwriting a slot. The editor creates a backup when overwriting. The [README](https://github.com/Sqzzzzzzz/Cold-Steel-Save-Editor#readme) covers recovery and supported saves.
