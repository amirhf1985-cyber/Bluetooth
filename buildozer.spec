[app]

title = Bluetooth RC
package.name = bluetoothrc
package.domain = org.amirhf

source.dir = .
source.include_exts = py,png,jpg,kv,json

version = 0.1

requirements = python3,kivy==2.3.0,pyjnius,android,openssl,libffi
orientation = landscape
fullscreen = 1

android.api = 33
android.minapi = 21

android.ndk = 25b
android.ndk_path = /usr/lib/android-ndk/android-ndk-r25b
android.sdk_path = /usr/lib/android-sdk
android.ndk_api = 21

android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,BLUETOOTH_CONNECT,BLUETOOTH_SCAN
