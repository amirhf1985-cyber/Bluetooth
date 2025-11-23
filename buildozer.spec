# عنوان اپلیکیشن
title = Bluetooth RC
# نام پکیج
package.name = bluetoothrc
# دامنه پکیج
package.domain = ir.bluetoothrc

# مسیر کد اصلی
source.dir = .
# فایل اصلی پایتون
source.main = main.py

# نسخه اپلیکیشن
version = 1.0.0
# شماره نسخه برای استور
version.code = 1

# الزامات پایتون
requirements = python3,kivy,pyjnius,android

# نسخه پایتون
python.version = 3.9

# اندروید SDK و NDK
android.api = 31
android.minapi = 21
android.ndk = 25b
android.sdk = 26
android.ndk_api = 21

# دسترسی‌های مورد نیاز اندروید
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,BLUETOOTH_SCAN,BLUETOOTH_CONNECT

# ویژگی‌های مورد نیاز
android.features = android.hardware.bluetooth,android.hardware.sensor.accelerometer

# آیکون و لوگو
icon.filename = icon.png
presplash.filename = presplash.png

# جهت صفحه
orientation = landscape

# تنظیمات بیلد
fullscreen = 1
android.window_soft_input_mode = adjustResize

# بک‌اند Kivy
osx.python_version = 3
osx.kivy_version = 2.3.0

# تنظیمات بیلد
[buildozer]
log_level = 2