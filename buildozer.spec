[app]

# عنوان اپلیکیشن
title = Bluetooth RC
# نام پکیج
package.name = bluetoothrc
# دامنه پکیج
package.domain = ir.bluetoothrc

# مسیر کد اصلی
source.dir = .
source.main = main.py

# نسخه اپلیکیشن
version = 1.0.0
version.code = 1

# الزامات پایتون
requirements = python3.11,kivy==2.3.0,pyjnius,android,hostpython3,openssl,libffi

# نسخه پایتون برای Buildozer
python.version = 3.11

# تنظیمات اندروید
android.api = 31
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.sdk = 31

# مجوزهای اندروید
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,INTERNET

# ویژگی‌ها
android.features = android.hardware.bluetooth,android.hardware.sensor.accelerometer

# آیکون و لوگو
icon.filename = icon.png
presplash.filename = presplash.png

# جهت صفحه
orientation = landscape

# تنظیمات بیلد
fullscreen = 1
android.window_soft_input_mode = adjustResize
android.allow_backup = True
android.accept_sdk_license = True

# پیکربندی p4a
p4a.branch = master

# OSX (اختیاری)
osx.python_version = 3
osx.kivy_version = 2.3.0

[buildozer]
log_level = 2
