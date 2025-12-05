# Build Instructions untuk Git Archive Generator

## Persyaratan
- Python 3.7 atau lebih baru
- PyInstaller (akan diinstall otomatis jika belum ada)

## Cara Build

### Metode 1: Menggunakan build.bat (Windows)
1. Buka Command Prompt atau PowerShell
2. Navigate ke folder project
3. Jalankan:
   ```
   build.bat
   ```
4. File executable akan berada di folder `dist\GitArchiveGenerator.exe`

### Metode 2: Menggunakan PyInstaller langsung
1. Install PyInstaller:
   ```
   pip install pyinstaller
   ```

2. Build executable:
   ```
   pyinstaller --onefile --windowed --name "GitArchiveGenerator" git_archive_ui.py
   ```

3. File executable akan berada di folder `dist\GitArchiveGenerator.exe`

### Metode 3: Menggunakan build.spec
1. Install PyInstaller:
   ```
   pip install pyinstaller
   ```

2. Build menggunakan spec file:
   ```
   pyinstaller build.spec
   ```

## Catatan
- File `git_archive_by_date.py` akan otomatis di-bundle ke dalam executable
- Aplikasi akan berjalan sebagai windowed application (tanpa console)
- Untuk menambahkan icon, edit `build.spec` dan tambahkan path ke file `.ico` di bagian `icon=None`

