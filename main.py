from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivy.properties import StringProperty, NumericProperty, ObjectProperty, ListProperty, BooleanProperty
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, Rotate, PushMatrix, PopMatrix, Line
from kivy.core.window import Window
from kivy.config import Config

import os
import threading
import time
import math
import random

# تنظیمات اولیه
Config.set('graphics', 'resizable', '1')
Config.set('graphics', 'width', '1024')
Config.set('graphics', 'height', '600')
Window.clearcolor = (1, 1, 1, 1)

# ایمپورت مدیریت تنظیمات
from kivy.storage.jsonstore import JsonStore

# Try to import jnius / android API
HAS_ANDROID = False
try:
    from jnius import autoclass, cast, PythonJavaClass, java_method
    from android.permissions import request_permissions, Permission, check_permission
    HAS_ANDROID = True
except Exception as e:
    HAS_ANDROID = False
    print(f"Android components not available: {e}")

class SettingsManager:
    def __init__(self):
        self.store = JsonStore('rc_car_settings.json')
    
    def get(self, key, default=None):
        try:
            if self.store.exists(key):
                return self.store.get(key).get('value', default)
            return default
        except Exception as e:
            print(f"❌ Settings read error for {key}: {e}")
            return default
    
    def set(self, key, value):
        self.store.put(key, value=value)
    
    def get_all_settings(self):
        """دریافت تمام تنظیمات"""
        settings = {}
        for key in self.store.keys():
            settings[key] = self.get(key)
        return settings
    
    def reset_to_defaults(self):
        """بازنشانی تمام تنظیمات به حالت پیش‌فرض"""
        default_settings = {
            'sensitivity': 1.0,
            'auto_connect': True,
            'steering_sensitivity': 1.0,
            'battery_warning_level': 20,
            'last_connected_device': ''
        }
        
        for key, value in default_settings.items():
            self.set(key, value)
        
        print("✅ All settings reset to default")
        return default_settings

# دسترسی سریع به تنظیمات
def get_setting(key, default=None):
    app = App.get_running_app()
    if hasattr(app, 'settings_manager'):
        return app.settings_manager.get(key, default)
    return default

def set_setting(key, value):
    app = App.get_running_app()
    if hasattr(app, 'settings_manager'):
        app.settings_manager.set(key, value)

# تابع برای تنظیم سایز کامل صفحه
def setup_fullscreen():
    try:
        print(f"📱 Initial Window size: {Window.size}")
        
        if HAS_ANDROID:
            print("📱 Android environment detected")
            Window.fullscreen = 'auto'
        else:
            Window.maximize()
        
        def update_size(dt):
            actual_width, actual_height = Window.size
            print(f"📱 Final Window size: {actual_width}x{actual_height}")
            
        Clock.schedule_once(update_size, 1.0)
        
    except Exception as e:
        print(f"Fullscreen setup error: {e}")

# اجرای تنظیمات فول اسکرین
Clock.schedule_once(lambda dt: setup_fullscreen(), 0.5)

if HAS_ANDROID:
    # تنظیم landscape
    def set_landscape():
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            ActivityInfo = autoclass('android.content.pm.ActivityInfo')
            
            current_activity = PythonActivity.mActivity
            current_activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)
            print("✅ Orientation set to landscape")
        except Exception as e:
            print(f"Orientation error: {e}")
    
    Clock.schedule_once(lambda dt: set_landscape(), 1)

# --- Android / BLE / Accelerometer support ---
if HAS_ANDROID:
    try:
        # بررسی پرمیشن‌ها قبل از درخواست
        required_permissions = [
            Permission.BLUETOOTH,
            Permission.BLUETOOTH_ADMIN,
            Permission.ACCESS_FINE_LOCATION,
            Permission.ACCESS_COARSE_LOCATION,
            Permission.BLUETOOTH_SCAN,
            Permission.BLUETOOTH_CONNECT,
        ]
        
        # درخواست فقط پرمیشن‌های missing
        missing_permissions = [perm for perm in required_permissions if not check_permission(perm)]
        if missing_permissions:
            request_permissions(missing_permissions)
            print(f"✅ Requested missing permissions: {missing_permissions}")
        else:
            print("✅ All permissions already granted")
    except Exception as e:
        print(f"Permission request error: {e}")

# Accelerometer listener class
if HAS_ANDROID:
    class AccelerometerEventListener(PythonJavaClass):
        __javainterfaces__ = ['android/hardware/SensorEventListener']
        
        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(Landroid/hardware/SensorEvent;)V')
        def onSensorChanged(self, event):
            try:
                values = event.values
                x = float(values[0])
                y = float(values[1])
                z = float(values[2])
                self.callback(x, y, z)
            except Exception as e:
                print(f"Sensor data error: {e}")

        @java_method('(Landroid/hardware/Sensor;I)V')
        def onAccuracyChanged(self, sensor, accuracy):
            pass

class AccelerometerManager:
    def __init__(self):
        self.sensor_manager = None
        self.accelerometer = None
        self.listener = None
        self.is_active = False
        self.accel_values = [0, 0, 0]
        self.steering_angle = 0
        self.controller = None
        self.sensitivity = get_setting('sensitivity', 1.0)
        self._simulate_event = None
        
        if HAS_ANDROID:
            self.initialize_sensor()

    def initialize_sensor(self):
        """Initialize sensor components with correct context"""
        if not HAS_ANDROID:
            return False
            
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Sensor = autoclass('android.hardware.Sensor')
            SensorManager = autoclass('android.hardware.SensorManager')
            Context = autoclass('android.content.Context')
            
            activity = PythonActivity.mActivity
            self.sensor_manager = activity.getSystemService(Context.SENSOR_SERVICE)
            self.accelerometer = self.sensor_manager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
            
            if not self.accelerometer:
                print("❌ Accelerometer not available on this device")
                return False
                
            print("✅ Accelerometer initialized successfully")
            return True
        except Exception as e:
            print(f"❌ Sensor initialization error: {e}")
            return False

    def start(self):
        """Start accelerometer with fresh listener each time"""
        if not HAS_ANDROID:
            self.is_active = True
            self._simulate_event = Clock.schedule_interval(self._simulate_accelerometer, 0.1)
            print("✅ Accelerometer simulation started")
            return True
            
        try:
            if not self.sensor_manager or not self.accelerometer:
                if not self.initialize_sensor():
                    return False

            self.listener = AccelerometerEventListener(self.update_values)
            
            SensorManager = autoclass('android.hardware.SensorManager')
            success = self.sensor_manager.registerListener(
                self.listener,
                self.accelerometer,
                SensorManager.SENSOR_DELAY_GAME
            )
            
            if success:
                self.is_active = True
                print("✅ Accelerometer started successfully")
                return True
            else:
                print("❌ Failed to register sensor listener")
                return False
                
        except Exception as e:
            print(f"❌ Error starting accelerometer: {e}")
            return False

    def stop(self):
        """Stop accelerometer and cleanup listener"""
        if not HAS_ANDROID:
            self.is_active = False
            if self._simulate_event:
                Clock.unschedule(self._simulate_event)
                self._simulate_event = None
            print("✅ Accelerometer simulation stopped")
            return True
            
        try:
            if self.sensor_manager and self.listener:
                self.sensor_manager.unregisterListener(self.listener)
                self.listener = None
            
            self.is_active = False
            print("✅ Accelerometer stopped successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error stopping accelerometer: {e}")
            return False

    def set_sensitivity(self, s):
        self.sensitivity = max(0.5, min(2.0, s))
        set_setting('sensitivity', self.sensitivity)
        print(f"✅ Sensitivity set to: {self.sensitivity}")

    def get_orientation_adjusted_values(self, x, y, z):
        """Adjust accelerometer values based on device orientation"""
        if Window.width > Window.height:
            x_adj = -y
            y_adj = x
            return x_adj, y_adj, z
        else:
            return x, y, z

    def update_values(self, x, y, z):
        """Callback for sensor data"""
        self.accel_values = [x, y, z]
        try:
            x_adj, y_adj, z_adj = self.get_orientation_adjusted_values(x, y, z)
            
            tilt_angle = math.degrees(math.atan2(x_adj, math.sqrt(y_adj*y_adj + z_adj*z_adj)))
            tilt_angle = -tilt_angle
            tilt_angle *= self.sensitivity
            
            self.steering_angle = max(-90, min(90, tilt_angle * 2))
            
            if self.controller and self.is_active:
                self.controller.update_steering_from_accelerometer(self.steering_angle)
                
        except Exception as e:
            print(f"❌ Steering calculation error: {e}")

    def _simulate_accelerometer(self, dt):
        """شبیه‌سازی شتاب‌سنج برای محیط غیر-اندروید"""
        if not self.is_active:
            return
            
        base_x = random.uniform(-0.5, 0.5)
        base_y = random.uniform(-0.5, 0.5)
        base_z = 9.8
        
        x = base_x + random.uniform(-0.1, 0.1)
        y = base_y + random.uniform(-0.1, 0.1)
        z = base_z + random.uniform(-0.05, 0.05)
        
        self.update_values(x, y, z)

# --- Complete Android BLE Implementation with Auto-Discovery ---
class AndroidBLE:
    def __init__(self):
        self.connected = False
        self.device_name = ""
        self.main_app = None
        self.characteristic_found = False
        self.gatt = None
        self.bluetooth_adapter = None
        self.bluetooth_manager = None
        self.connected_device = None
        self.services_discovered = False
        
        # Characteristics storage
        self.characteristics = {}
        self.write_characteristic = None
        self.battery_characteristic = None
        self.notify_characteristics = []
        
        # Common BLE UUIDs for auto-discovery
        self.common_services = {
            'battery': '0000180f-0000-1000-8000-00805f9b34fb',
            'device_info': '0000180a-0000-1000-8000-00805f9b34fb',
            'generic_access': '00001800-0000-1000-8000-00805f9b34fb',
            'generic_attribute': '00001801-0000-1000-8000-00805f9b34fb',
            'custom_service_1': '0000ffe0-0000-1000-8000-00805f9b34fb',
            'custom_service_2': '0000ffb0-0000-1000-8000-00805f9b34fb',
            'custom_service_3': '0000fff0-0000-1000-8000-00805f9b34fb',
            'uart_service': '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
        }
        
        self.common_characteristics = {
            'battery_level': '00002a19-0000-1000-8000-00805f9b34fb',
            'device_name': '00002a00-0000-1000-8000-00805f9b34fb',
            'firmware_revision': '00002a26-0000-1000-8000-00805f9b34fb',
            'serial_number': '00002a25-0000-1000-8000-00805f9b34fb',
            'manufacturer': '00002a29-0000-1000-8000-00805f9b34fb',
            'write_char_1': '0000ffe1-0000-1000-8000-00805f9b34fb',
            'write_char_2': '0000ffb1-0000-1000-8000-00805f9b34fb',
            'write_char_3': '0000fff1-0000-1000-8000-00805f9b34fb',
            'uart_tx': '6e400002-b5a3-f393-e0a9-e50e24dcca9e',
            'uart_rx': '6e400003-b5a3-f393-e0a9-e50e24dcca9e'
        }
        
        # Battery monitoring
        self.battery_level = 85
        self.battery_update_callback = None
        self.scanning = False
        self.scanner = None
        
        if HAS_ANDROID:
            self.initialize_ble()
            self.setup_gatt_callbacks()

    def setup_gatt_callbacks(self):
        """GATT Callback کامل برای اندروید"""
        if not HAS_ANDROID:
            return
            
        try:
            BluetoothProfile = autoclass('android.bluetooth.BluetoothProfile')
            BluetoothGatt = autoclass('android.bluetooth.BluetoothGatt')
            BluetoothGattCharacteristic = autoclass('android.bluetooth.BluetoothGattCharacteristic')
            BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
            
            class GattCallback(PythonJavaClass):
                __javainterfaces__ = ['android/bluetooth/BluetoothGattCallback']
                
                def __init__(self, outer):
                    super().__init__()
                    self.outer = outer
                
                @java_method('(Landroid/bluetooth/BluetoothGatt;II)V')
                def onConnectionStateChange(self, gatt, status, newState):
                    print(f"🔗 Connection state changed: {newState}, status: {status}")
                    if newState == BluetoothProfile.STATE_CONNECTED:
                        print("✅ Connected to GATT server")
                        self.outer.connected = True
                        self.outer.gatt = gatt
                        self.outer.services_discovered = False
                        
                        success = gatt.discoverServices()
                        print(f"Service discovery started: {success}")
                        
                        if self.outer.main_app:
                            Clock.schedule_once(lambda dt: setattr(self.outer.main_app, 'connection_status', "Discovering Services"))
                    else:
                        print("❌ Disconnected from GATT server")
                        self.outer.connected = False
                        self.outer.characteristic_found = False
                        self.outer.services_discovered = False
                        self.outer.write_characteristic = None
                        self.outer.battery_characteristic = None
                        if self.outer.main_app:
                            Clock.schedule_once(lambda dt: setattr(self.outer.main_app, 'connection_status', "Disconnected"))
                
                @java_method('(Landroid/bluetooth/BluetoothGatt;I)V')
                def onServicesDiscovered(self, gatt, status):
                    print(f"🔍 Services discovered: {status}")
                    if status == BluetoothGatt.GATT_SUCCESS:
                        print("✅ Services discovered successfully")
                        self.outer.services_discovered = True
                        self.outer.auto_discover_characteristics()
                    else:
                        print(f"❌ Service discovery failed: {status}")
                        if self.outer.main_app:
                            Clock.schedule_once(lambda dt: setattr(self.outer.main_app, 'connection_status', "Service Discovery Failed"))
                
                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;I)V')
                def onCharacteristicRead(self, gatt, characteristic, status):
                    if status == BluetoothGatt.GATT_SUCCESS:
                        uuid = characteristic.getUuid().toString().lower()
                        data = characteristic.getValue()
                        if "2a19" in uuid:  # UUID باتری
                            self.outer.on_battery_data_received(data)
                        else:
                            print(f"📖 Characteristic read: {uuid}")
                    else:
                        print(f"❌ Characteristic read failed: {status}")
                
                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;I)V')
                def onCharacteristicWrite(self, gatt, characteristic, status):
                    if status == BluetoothGatt.GATT_SUCCESS:
                        print("✅ Characteristic write successful")
                    else:
                        print(f"❌ Characteristic write failed: {status}")
                
                @java_method('(Landroid/bluetooth/BluetoothGatt;Landroid/bluetooth/BluetoothGattCharacteristic;[B)V')
                def onCharacteristicChanged(self, gatt, characteristic, value):
                    uuid = characteristic.getUuid().toString().lower()
                    print(f"📨 Characteristic changed: {uuid}")
                    if "2a19" in uuid:  # UUID باتری
                        self.outer.on_battery_data_received(value)
            
            self.gatt_callback = GattCallback(self)
            print("✅ GATT callbacks setup completed")
            
        except Exception as e:
            print(f"❌ GATT callback setup error: {e}")

    def initialize_ble(self):
        """Initialize BLE components"""
        if not HAS_ANDROID:
            print("✅ BLE simulation initialized for desktop")
            return True
            
        try:
            Context = autoclass('android.content.Context')
            BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
            BluetoothManager = autoclass('android.bluetooth.BluetoothManager')
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            
            self.bluetooth_manager = cast(BluetoothManager, activity.getSystemService(Context.BLUETOOTH_SERVICE))
            if self.bluetooth_manager:
                self.bluetooth_adapter = self.bluetooth_manager.getAdapter()
            else:
                print("❌ Bluetooth manager not available")
                return False
            
            if not self.bluetooth_adapter:
                print("❌ Bluetooth not supported on this device")
                return False
                
            if not self.bluetooth_adapter.isEnabled():
                print("❌ Bluetooth is not enabled")
                return False
                
            print("✅ BLE initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ BLE initialization error: {e}")
            return False

    def auto_discover_characteristics(self):
        """کشف خودکار تمام کاراکترستیک‌های مهم"""
        if not HAS_ANDROID or not self.gatt:
            return
            
        try:
            BluetoothGattService = autoclass('android.bluetooth.BluetoothGattService')
            BluetoothGattCharacteristic = autoclass('android.bluetooth.BluetoothGattCharacteristic')
            BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
            
            services = self.gatt.getServices()
            print(f"🔍 Found {services.size()} services - Starting auto-discovery")
            
            found_characteristics = []
            
            for i in range(services.size()):
                service = services.get(i)
                service_uuid = service.getUuid().toString().lower()
                print(f"🔧 Service {i+1}: {service_uuid}")
                
                characteristics = service.getCharacteristics()
                print(f"   Found {characteristics.size()} characteristics")
                
                for j in range(characteristics.size()):
                    characteristic = characteristics.get(j)
                    char_uuid = characteristic.getUuid().toString().lower()
                    properties = characteristic.getProperties()
                    
                    char_info = f"     Characteristic {j+1}: {char_uuid}, properties: {properties}"
                    found_characteristics.append((char_uuid, properties))
                    print(char_info)
                    
                    # شناسایی کاراکترستیک باتری
                    if "2a19" in char_uuid:
                        self.battery_characteristic = characteristic
                        print("✅ Battery characteristic found")
                        # فعال کردن notifications برای باتری
                        self.enable_notifications(characteristic)
                        # خواندن مقدار اولیه باتری
                        self.gatt.readCharacteristic(characteristic)
                    
                    # شناسایی کاراکترستیک‌های قابل نوشتن
                    if (properties & BluetoothGattCharacteristic.PROPERTY_WRITE or 
                        properties & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE):
                        
                        # اولویت‌بندی کاراکترستیک‌های نوشتن
                        priority = 0
                        
                        # کاراکترستیک‌های UART اولویت بالا
                        if "6e400002" in char_uuid or "6e400003" in char_uuid:
                            priority = 100
                        # کاراکترستیک‌های شناخته شده سفارشی
                        elif any(uuid in char_uuid for uuid in ['ffe1', 'ffb1', 'fff1']):
                            priority = 80
                        # سایر کاراکترستیک‌های قابل نوشتن
                        else:
                            priority = 50
                        
                        if not self.write_characteristic or priority > getattr(self.write_characteristic, 'priority', 0):
                            self.write_characteristic = characteristic
                            self.write_characteristic.priority = priority
                            self.characteristic_found = True
                            print(f"✅ Selected write characteristic (priority {priority}): {char_uuid}")
                    
                    # شناسایی کاراکترستیک‌های notify
                    if (properties & BluetoothGattCharacteristic.PROPERTY_NOTIFY or 
                        properties & BluetoothGattCharacteristic.PROPERTY_INDICATE):
                        self.enable_notifications(characteristic)
                        self.notify_characteristics.append(characteristic)
                        print(f"✅ Notify enabled for: {char_uuid}")
            
            # اگر کاراکترستیک نوشتن پیدا نشد، از اولین کاراکترستیک قابل نوشتن استفاده کن
            if not self.characteristic_found:
                for char_uuid, properties in found_characteristics:
                    if (properties & BluetoothGattCharacteristic.PROPERTY_WRITE or 
                        properties & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE):
                        # پیدا کردن characteristic مربوطه
                        for i in range(services.size()):
                            service = services.get(i)
                            characteristics = service.getCharacteristics()
                            for j in range(characteristics.size()):
                                characteristic = characteristics.get(j)
                                if characteristic.getUuid().toString().lower() == char_uuid:
                                    self.write_characteristic = characteristic
                                    self.characteristic_found = True
                                    print(f"✅ Fallback write characteristic: {char_uuid}")
                                    break
                            if self.characteristic_found:
                                break
                    if self.characteristic_found:
                        break
            
            if self.characteristic_found:
                print("🎯 Auto-discovery completed successfully")
                if self.main_app:
                    Clock.schedule_once(lambda dt: self._update_connection_ui())
            else:
                print("❌ No suitable write characteristics found")
                if self.main_app:
                    self.main_app.connection_status = "No Write Char Found"
                
        except Exception as e:
            print(f"❌ Auto-discovery error: {e}")

    def enable_notifications(self, characteristic):
        """فعال کردن notifications برای یک کاراکترستیک"""
        if not HAS_ANDROID or not self.gatt:
            return
            
        try:
            BluetoothGattDescriptor = autoclass('android.bluetooth.BluetoothGattDescriptor')
            CLIENT_CHARACTERISTIC_CONFIG = "00002902-0000-1000-8000-00805f9b34fb"
            
            self.gatt.setCharacteristicNotification(characteristic, True)
            
            descriptor = characteristic.getDescriptor(
                autoclass('java.util.UUID').fromString(CLIENT_CHARACTERISTIC_CONFIG)
            )
            if descriptor:
                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE)
                self.gatt.writeDescriptor(descriptor)
                print(f"✅ Notifications enabled for characteristic")
                
        except Exception as e:
            print(f"❌ Enable notifications error: {e}")

    def on_battery_data_received(self, data):
        """پردازش داده‌های باتری از BLE"""
        try:
            level = None
            
            if hasattr(data, '__len__') and len(data) >= 1:
                first_byte = data[0]
                if isinstance(first_byte, int):
                    level = first_byte
                else:
                    level = ord(first_byte) if isinstance(first_byte, str) else int(first_byte)
            
            if level is None and HAS_ANDROID:
                try:
                    jbytes = cast('java.nio.ByteBuffer', data)
                    if jbytes and jbytes.hasRemaining():
                        level = jbytes.get() & 0xFF
                except:
                    pass
            
            if level is None:
                try:
                    level = int(''.join(filter(str.isdigit, str(data))))
                except:
                    level = getattr(self, 'battery_level', 85)
            
            level = max(0, min(100, level))
            self.battery_level = level
            
            print(f"🔋 Battery level: {level}%")
            
            if self.battery_update_callback:
                Clock.schedule_once(lambda dt: self.battery_update_callback(level))
                
        except Exception as e:
            print(f"❌ Battery data error: {e}")

    def set_battery_callback(self, callback):
        """Set callback for battery level updates"""
        self.battery_update_callback = callback
        print("✅ Battery callback set")

    def start_scan(self, callback):
        """Start BLE device scan"""
        self.scan_callback = callback
        
        if not HAS_ANDROID:
            def simulate_scan():
                time.sleep(2)
                devices = [
                    "ESP32_Car_01 (AA:BB:CC:DD:EE:FF)",
                    "Arduino_BLE (11:22:33:44:55:66)",
                    "Raspberry_Pi (CC:DD:EE:FF:11:22)",
                    "SmartDevice_123 (DD:EE:FF:11:22:33)"
                ]
                Clock.schedule_once(lambda dt: callback(devices))
                print("✅ BLE scan simulation completed")
            
            threading.Thread(target=simulate_scan, daemon=True).start()
            return ["Scanning for BLE devices..."]
        
        print("🔍 Starting BLE scan...")
        
        try:
            # استفاده از دستگاه‌های paired شده به عنوان fallback
            bonded_devices = self.bluetooth_adapter.getBondedDevices()
            found_devices = []
            
            if bonded_devices:
                for device in bonded_devices:
                    name = device.getName()
                    address = device.getAddress()
                    if name and any(keyword in name.lower() for keyword in ['esp32', 'arduino', 'car', 'ble', 'rc']):
                        device_str = f"{name} ({address})"
                        found_devices.append(device_str)
                        print(f"📱 Found bonded device: {device_str}")
            
            if not found_devices:
                found_devices = [
                    "ESP32_RC_Car_01 (AA:BB:CC:DD:EE:FF)",
                    "Arduino_Car_BLE (11:22:33:44:55:66)",
                    "Smart_RC_Car (CC:DD:EE:FF:11:22)"
                ]
                print("🔧 Showing test devices for demonstration")
            
            Clock.schedule_once(lambda dt: callback(found_devices), 3.0)
            return ["Scanning for BLE devices..."]
            
        except Exception as e:
            print(f"❌ BLE scan error: {e}")
            return [f"Scan error: {str(e)}"]

    def connect(self, device_address):
        """Connect to BLE device"""
        try:
            print(f"🔄 Attempting to connect to: {device_address}")
            
            if not HAS_ANDROID:
                self.device_name = device_address.split(' ')[0]
                self.connected = True
                self.characteristic_found = True
                if self.battery_update_callback:
                    self.battery_update_callback(self.battery_level)
                Clock.schedule_once(lambda dt: self._simulate_connection(), 1)
                print("✅ Desktop connection simulation completed")
                return True
                
            if '(' in device_address and ')' in device_address:
                address = device_address.split('(')[-1].split(')')[0]
                self.device_name = device_address.split('(')[0].strip()
            else:
                address = device_address
                self.device_name = device_address
            
            print(f"📱 Device name: {self.device_name}, Address: {address}")
            
            if self.connected:
                self.disconnect()
                time.sleep(1)
            
            BluetoothDevice = autoclass('android.bluetooth.BluetoothDevice')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            
            device = self.bluetooth_adapter.getRemoteDevice(address)
            if not device:
                print(f"❌ Device not found: {address}")
                return False
                
            activity = PythonActivity.mActivity
            self.gatt = device.connectGatt(activity, False, self.gatt_callback)
            
            if self.gatt:
                print("✅ GATT connection initiated")
                return True
            else:
                print("❌ Failed to initiate GATT connection")
                return False
            
        except Exception as e:
            print(f"❌ Connect error: {e}")
            return False

    def _update_connection_ui(self):
        """Update UI after successful connection"""
        if self.main_app:
            self.main_app.connected_device = f"Connected: {self.device_name}"
            self.main_app.battery_level = f"{self.battery_level}%"
            self.main_app.connection_status = "Connected"
            print("✅ UI updated with connection status")

    def _simulate_connection(self):
        """Simulate connection for non-Android"""
        if self.main_app:
            self.main_app.connected_device = f"Connected: {self.device_name}"
            self.main_app.battery_level = f"{self.battery_level}%"
            self.main_app.connection_status = "Connected"
            print("✅ Desktop connection simulation UI updated")

    def send_command(self, command):
        """Send command via BLE"""
        if not self.connected:
            print(f"[BLE NOT CONNECTED] {command}")
            return False
            
        if not HAS_ANDROID:
            print(f"[BLE SEND SIMULATION] {command}")
            return True
            
        try:
            if not self.characteristic_found or not self.write_characteristic:
                print(f"[BLE NO CHARACTERISTIC] {command}")
                return False
                
            BluetoothGattCharacteristic = autoclass('android.bluetooth.BluetoothGattCharacteristic')
            
            properties = self.write_characteristic.getProperties()
            if properties & BluetoothGattCharacteristic.PROPERTY_WRITE_NO_RESPONSE:
                write_type = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            else:
                write_type = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT

            command_bytes = (command + '\n').encode('utf-8')
            
            self.write_characteristic.setValue(command_bytes)
            self.write_characteristic.setWriteType(write_type)
            success = self.gatt.writeCharacteristic(self.write_characteristic)
            
            if success:
                print(f"[BLE SEND SUCCESS] {command}")
            else:
                print(f"[BLE SEND FAILED] {command}")
                
            return success
            
        except Exception as e:
            print(f"[BLE SEND ERROR] {command}: {e}")
            return False

    def disconnect(self):
        """Disconnect from BLE device"""
        try:
            if HAS_ANDROID and self.gatt:
                self.gatt.disconnect()
                self.gatt.close()
                print("✅ BLE disconnected")
                
            self.connected = False
            self.characteristic_found = False
            self.write_characteristic = None
            self.services_discovered = False
            self.battery_characteristic = None
            self.notify_characteristics = []
            
            print("✅ BLE state reset")
            
        except Exception as e:
            print(f"❌ Disconnect error: {e}")

class BatteryIndicator(Widget):
    level = NumericProperty(85)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._update_canvas, size=self._update_canvas, level=self._update_canvas)
        Clock.schedule_once(self._update_canvas, 0.1)

    def _update_canvas(self, *args):
        self.canvas.clear()
        try:
            with self.canvas:
                if self.width == 0 or self.height == 0:
                    return
                    
                width, height = self.size
                padding = min(width, height) * 0.1
                body_width = width - padding * 3
                body_height = height - padding * 2
                
                if body_width <= 0 or body_height <= 0:
                    return
                
                # بدنه باتری
                Color(0.8, 0.8, 0.8, 1)
                Rectangle(
                    pos=(self.x + padding, self.y + padding),
                    size=(body_width, body_height)
                )
                
                # سر باتری
                tip_width = padding
                tip_height = body_height * 0.4
                tip_x = self.x + padding + body_width
                tip_y = self.y + padding + (body_height - tip_height) / 2
                Rectangle(
                    pos=(tip_x, tip_y),
                    size=(tip_width, tip_height)
                )
                
                # سطح شارژ
                charge_width = max(2, (body_width - 4) * self.level / 100)
                charge_height = body_height - 4
                
                # رنگ بر اساس سطح باتری
                if self.level <= 20:
                    Color(1, 0, 0, 1)  # قرمز
                elif self.level <= 50:
                    Color(1, 0.5, 0, 1)  # نارنجی
                else:
                    Color(0, 0.8, 0, 1)  # سبز
                
                if charge_width > 0 and charge_height > 0:
                    Rectangle(
                        pos=(self.x + padding + 2, self.y + padding + 2),
                        size=(charge_width, charge_height)
                    )
                    
        except Exception as e:
            print(f"❌ خطا در رسم نشانگر باتری: {e}")

class RotatableImage(Image):
    angle = NumericProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(angle=self._update_rotation)
        self._rotation = None
        with self.canvas.before:
            PushMatrix()
            self._rotation = Rotate(angle=self.angle, origin=self.center)
        with self.canvas.after:
            PopMatrix()

    def _update_rotation(self, *args):
        if self._rotation:
            self._rotation.angle = -self.angle
            self._rotation.origin = self.center

    def on_size(self, *args):
        if self._rotation:
            self._rotation.origin = self.center

    def on_pos(self, *args):
        if self._rotation:
            self._rotation.origin = self.center

class ImageButton(ButtonBehavior, Image):
    def __init__(self, normal_source, active_source=None, **kwargs):
        super().__init__(**kwargs)
        self.normal_source = normal_source
        self.active_source = active_source or normal_source
        if os.path.exists(normal_source):
            self.source = normal_source
        else:
            self.source = ''
        self.is_active = False
        self.controller = None
        self.command = ""
        self.normal_color = (1, 1, 1, 1)
        self.active_color = (0.2, 0.8, 1, 1)
        self.color = self.normal_color

    def toggle(self):
        self.is_active = not self.is_active
        self.color = self.active_color if self.is_active else self.normal_color

class MomentaryImageButton(ImageButton):
    def __init__(self, normal_source, active_source=None, press_command=None, release_command=None, **kwargs):
        super().__init__(normal_source, active_source, **kwargs)
        self.press_command = press_command or self.command
        self.release_command = release_command or self.command

    def on_press(self):
        if self.controller and self.press_command:
            self.controller.send_command(self.press_command)
            self.color = self.active_color

    def on_release(self):
        if self.controller and self.release_command:
            self.controller.send_command(self.release_command)
            self.color = self.normal_color

class SteeringWidget(BoxLayout):
    controller = ObjectProperty(None)
    angle = NumericProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        steer_source = 'steer.png' if os.path.exists('steer.png') else ''
        self.steering_image = RotatableImage(
            source=steer_source,
            allow_stretch=True, 
            keep_ratio=True
        )
        self.add_widget(self.steering_image)
        self.bind(angle=self.update_steering_angle)
        self._touch_down = False
        self._touch_id = None

    def _get_touch_id(self, touch):
        """Get touch ID consistently"""
        return getattr(touch, 'id', getattr(touch, 'uid', hash(touch)))

    def update_steering_angle(self, instance, value):
        self.steering_image.angle = value

    def on_touch_down(self, touch):
        touch_id = self._get_touch_id(touch)
        if self.collide_point(*touch.pos) and not getattr(self.controller, 'accelerometer_mode', False) and not self._touch_down:
            self._touch_down = True
            self._touch_id = touch_id
            return self.process_touch(touch)
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        touch_id = self._get_touch_id(touch)
        if self._touch_down and touch_id == self._touch_id and not getattr(self.controller, 'accelerometer_mode', False):
            return self.process_touch(touch)
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        touch_id = self._get_touch_id(touch)
        if self._touch_down and touch_id == self._touch_id and not getattr(self.controller, 'accelerometer_mode', False):
            self._touch_down = False
            self._touch_id = None
            self.angle = 0
            if self.controller:
                self.controller.send_command("T50")
            return True
        return super().on_touch_up(touch)

    def process_touch(self, touch):
        touch_id = self._get_touch_id(touch)
        if not self._touch_down or touch_id != self._touch_id:
            return False
            
        center_x = self.center_x
        relative_x = (touch.x - center_x) / (self.width / 2)
        relative_x = max(-1, min(1, relative_x))
        self.angle = relative_x * 90
        
        if self.angle >= 0:
            value = 50 + int((self.angle / 90) * 49)
            value = min(99, value)
        else:
            value = 50 - int((abs(self.angle) / 90) * 50)
            value = max(0, value)
            
        command = f"T{value:02d}"
        if self.controller:
            self.controller.send_command(command)
        return True

class PedalWidget(BoxLayout):
    controller = ObjectProperty(None)
    pedal_value = NumericProperty(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        pedal_source = 'pedal.png' if os.path.exists('pedal.png') else ''
        self.pedal_image = Image(
            source=pedal_source,
            allow_stretch=True,
            keep_ratio=True
        )
        self.add_widget(self.pedal_image)
        
        with self.canvas.after:
            Color(1, 0.2, 0.2, 0.6)
            self.overlay = Rectangle(pos=self.pos, size=(0, 0))
            
        self.bind(pos=self.update_overlay, size=self.update_overlay, pedal_value=self.update_overlay)
        self._touch_down = False
        self._touch_id = None

    def _get_touch_id(self, touch):
        """Get touch ID consistently"""
        return getattr(touch, 'id', getattr(touch, 'uid', hash(touch)))

    def update_overlay(self, *args):
        if hasattr(self, 'overlay'):
            if self.pedal_value > 0:
                overlay_height = self.height * (self.pedal_value / 100.0)
                self.overlay.pos = (self.x, self.y)
                self.overlay.size = (self.width, overlay_height)
            else:
                self.overlay.size = (0, 0)

    def on_touch_down(self, touch):
        touch_id = self._get_touch_id(touch)
        if self.collide_point(*touch.pos) and not self._touch_down:
            self._touch_down = True
            self._touch_id = touch_id
            return self.process_touch(touch)
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        touch_id = self._get_touch_id(touch)
        if self._touch_down and touch_id == self._touch_id:
            return self.process_touch(touch)
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        touch_id = self._get_touch_id(touch)
        if self._touch_down and touch_id == self._touch_id:
            self._touch_down = False
            self._touch_id = None
            self.pedal_value = 0
            if self.controller:
                self.controller.send_command("S00")
            return True
        return super().on_touch_up(touch)

    def process_touch(self, touch):
        touch_id = self._get_touch_id(touch)
        if not self._touch_down or touch_id != self._touch_id:
            return False
            
        relative_y = (touch.y - self.y) / self.height
        self.pedal_value = int(relative_y * 100)
        self.pedal_value = max(0, min(99, self.pedal_value))
        command = f"S{self.pedal_value:02d}"
        if self.controller:
            self.controller.send_command(command)
        return True

class CommandLogBox(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.height = 40
        self.last_command_label = Label(text='--', halign='center', valign='middle')
        self.add_widget(Label(text='Last:', size_hint_x=0.2))
        self.add_widget(self.last_command_label)

    def update_command(self, cmd):
        self.last_command_label.text = cmd

# --- Main Application UI ---
FIGMA_WIDTH = 2340
FIGMA_HEIGHT = 1080

class CombinedAppRoot(FloatLayout):
    battery_level = StringProperty("85%")
    connected_device = StringProperty("Not Connected")
    connection_status = StringProperty("Disconnected")
    accelerometer_mode = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Initialize BLE and accelerometer
        self.ble = AndroidBLE()
        self.ble.main_app = self
        self.ble.set_battery_callback(self.update_battery_level)
        self.accelerometer_manager = AccelerometerManager()
        self.accelerometer_manager.controller = self

        self.current_gear = 'N'
        self.current_turn_signal = None

        # White background
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bgrect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # UI items configuration
        self.items = [
            ('pedal', 80, 160, 359, 967, 'pedal.png'),
            ('start', 664, 726, 170, 170, 'start.png'),
            ('r', 476, 886, 150, 150, 'r.png'),
            ('n', 477, 736, 150, 150, 'n.png'),
            ('d', 476, 587, 150, 150, 'd.png'),
            ('light', 1506, 544, 150, 150, 'light.png'),
            ('lightHorn', 1480, 721, 150, 150, 'light.horn.png'),
            ('left', 1642, 425, 150, 150, 'left.png'),
            ('hazard', 1842, 350, 150, 150, 'hazard.png'),
            ('horn', 2178, 544, 150, 150, 'horn.png'),
            ('rgb', 1518, 906, 150, 150, 'rgb.png'),
            ('right', 2042, 425, 150, 150, 'right.png'),
            ('bluetooth', 1315, 956, 100, 100, 'bluetooth.png'),
            ('accelerometer', 2016, 182, 150, 150, 'accelerometer.png'),
            ('battery_title', 1225, 346, 200, 100, ''),
            ('battery_indicator', 1230, 412, 170, 80, ''),
            ('battery_percent', 1235, 412, 170, 80, ''),
            ('command_display', 886, 380, 110, 110, ''),
            ('steer', 1668, 544, 498, 497, 'steer.png'),
            ('setting', 1840, 182, 150, 150, 'setting.png'),
            ('led', 2178, 720, 150, 150, 'led.png'),
            ('device_display', 900, 956, 200, 80, ''),
        ]

        # Command log
        self.command_log = CommandLogBox(pos_hint={'x': 0, 'y': 0})
        self.add_widget(self.command_log)

        # Bind window size changes
        Window.bind(size=self.on_window_size)

        self._ui_built = False
        Clock.schedule_once(self._build_ui, 0.5)
        
        # بارگذاری تنظیمات ذخیره شده
        Clock.schedule_once(self._load_saved_settings, 1.0)
        
        print("✅ CombinedAppRoot initialized successfully")

    def _update_bg(self, *args):
        self.bgrect.pos = self.pos
        self.bgrect.size = self.size

    def on_window_size(self, instance, value):
        if not self._ui_built:
            return
            
        print(f"🔄 Window size changed to: {value}")
        self._update_ui_positions()

    def _load_saved_settings(self, dt=None):
        """بارگذاری تنظیمات ذخیره شده"""
        print("🔄 Loading saved settings...")
        
        # بارگذاری حساسیت شتاب‌سنج
        sensitivity = get_setting('sensitivity', 1.0)
        self.accelerometer_manager.sensitivity = sensitivity
        print(f"✅ Sensitivity loaded: {sensitivity}")
        
        # اتصال خودکار به دستگاه آخر (اگر فعال باشد)
        auto_connect = get_setting('auto_connect', True)
        if auto_connect:
            def auto_connect_to_device(dt):
                last_device = get_setting('last_connected_device')
                if last_device:
                    print(f"🔄 Attempting auto-connect to: {last_device}")
                    self._connect_and_close(last_device)
            
            Clock.schedule_once(auto_connect_to_device, 3.0)

    def _update_ui_positions(self):
        """فقط موقعیت المان‌های UI را به روز می‌کند"""
        win_w, win_h = Window.size
        
        target_ratio = FIGMA_WIDTH / FIGMA_HEIGHT
        current_ratio = win_w / win_h
        
        safe_area_top = max(0, win_h * 0.03) if HAS_ANDROID else 0
        safe_area_bottom = max(0, win_h * 0.03) if HAS_ANDROID else 0
        usable_height = win_h - safe_area_top - safe_area_bottom
        
        if current_ratio > target_ratio:
            scale = usable_height / FIGMA_HEIGHT
            margin_x = (win_w - FIGMA_WIDTH * scale) / 2
            margin_y = safe_area_bottom
        else:
            scale = win_w / FIGMA_WIDTH
            margin_x = 0
            margin_y = (win_h - FIGMA_HEIGHT * scale) / 2

        for name, x, y, w, h, src in self.items:
            if name in self.widgets:
                y_corrected = FIGMA_HEIGHT - (y + h)
                x_scaled = x * scale + margin_x
                y_scaled = y_corrected * scale + margin_y
                w_scaled = w * scale
                h_scaled = h * scale
                
                widget = self.widgets[name]
                if hasattr(widget, 'pos'):
                    widget.pos = (x_scaled, y_scaled)
                if hasattr(widget, 'size'):
                    widget.size = (w_scaled, h_scaled)

        cmd_log_width = max(180, win_w * 0.18)
        cmd_log_height = max(35, win_h * 0.045)
        self.command_log.pos = (win_w - cmd_log_width - 10, 10 + safe_area_bottom)
        self.command_log.size = (cmd_log_width, cmd_log_height)

    def update_battery_level(self, level):
        """Update battery level in UI"""
        def update_ui(dt):
            self.battery_level = f"{level}%"
            
            if 'battery_indicator' in self.widgets:
                self.widgets['battery_indicator'].level = level
                
        Clock.schedule_once(update_ui, 0)

    def _build_ui(self, dt):
        if self._ui_built:
            return
            
        win_w, win_h = Window.size
        print(f"🔄 Building UI for window size: {win_w}x{win_h}")
        
        target_ratio = FIGMA_WIDTH / FIGMA_HEIGHT
        current_ratio = win_w / win_h
        
        safe_area_top = 0
        safe_area_bottom = 0
        
        if HAS_ANDROID:
            safe_area_top = max(0, win_h * 0.03)
            safe_area_bottom = max(0, win_h * 0.03)
        
        usable_height = win_h - safe_area_top - safe_area_bottom
        
        if current_ratio > target_ratio:
            scale = usable_height / FIGMA_HEIGHT
            margin_x = (win_w - FIGMA_WIDTH * scale) / 2
            margin_y = safe_area_bottom
        else:
            scale = win_w / FIGMA_WIDTH
            margin_x = 0
            margin_y = (win_h - FIGMA_HEIGHT * scale) / 2

        self.widgets = {}

        for name, x, y, w, h, src in self.items:
            y_corrected = FIGMA_HEIGHT - (y + h)
            x_scaled = x * scale + margin_x
            y_scaled = y_corrected * scale + margin_y
            w_scaled = w * scale
            h_scaled = h * scale
            pos = (x_scaled, y_scaled)

            try:
                # Battery title
                if name == 'battery_title':
                    battery_title_box = BoxLayout(
                        orientation='vertical',
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos
                    )
                    
                    battery_title = Label(
                        text='Battery',
                        size_hint_y=1,
                        font_size='14sp',
                        color=(0, 0, 0, 1),
                        halign='center',
                        valign='middle'
                    )
                    
                    battery_title_box.add_widget(battery_title)
                    self.add_widget(battery_title_box)
                    continue

                # Battery indicator
                if name == 'battery_indicator':
                    battery_indicator = BatteryIndicator(
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos
                    )
                    
                    self.widgets['battery_indicator'] = battery_indicator
                    
                    def update_battery_indicator(instance, battery_text):
                        try:
                            level = int(''.join(filter(str.isdigit, battery_text)))
                            battery_indicator.level = level
                            battery_indicator._update_canvas()
                        except (ValueError, TypeError) as e:
                            print(f"❌ Battery indicator update error: {e}")
                    
                    self.bind(battery_level=update_battery_indicator)
                    
                    battery_indicator.level = 85
                    
                    self.add_widget(battery_indicator)
                    continue

                # Battery percent display - تنظیم فونت روی ۳۰
                if name == 'battery_percent':
                    battery_percent_box = BoxLayout(
                        orientation='vertical',
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos
                    )
                    
                    self.battery_percent_label = Label(
                        text=self.battery_level,
                        size_hint_y=1,
                        font_size='14sp',
                        color=(0, 0, 0, 1),
                        halign='center',
                        valign='middle',
                        bold=True
                    )
                    
                    battery_percent_box.add_widget(self.battery_percent_label)
                    self.add_widget(battery_percent_box)
                    
                    def update_battery_percent(instance, battery_text):
                        self.battery_percent_label.text = battery_text
                        try:
                            level = int(''.join(filter(str.isdigit, battery_text)))
                            if level <= 20:
                                self.battery_percent_label.color = (1, 0, 0, 1)
                            elif level <= 60:
                                self.battery_percent_label.color = (1, 0.5, 0, 1)
                            else:
                                self.battery_percent_label.color = (0, 0.5, 0, 1)
                        except (ValueError, TypeError) as e:
                            print(f"❌ Battery percent update error: {e}")
                    
                    self.bind(battery_level=update_battery_percent)
                    continue

                # Steering wheel
                if name == 'steer':
                    size = min(w_scaled, h_scaled)
                    steer = SteeringWidget(
                        size_hint=(None, None),
                        size=(size, size),
                        pos=(x_scaled + (w_scaled - size)/2, y_scaled + (h_scaled - size)/2)
                    )
                    steer.controller = self
                    self.add_widget(steer)
                    self.widgets['steer'] = steer
                    continue

                # Pedal
                if name == 'pedal':
                    pedal = PedalWidget(
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos
                    )
                    pedal.controller = self
                    self.add_widget(pedal)
                    self.widgets['pedal'] = pedal
                    continue

                # Gear buttons
                if name in ('n', 'r', 'd'):
                    btn = ImageButton(normal_source=src)
                    btn.controller = self
                    btn.command = name.upper()
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    btn.bind(on_press=self._on_gear_pressed)
                    
                    if name == 'n':
                        btn.is_active = True
                        btn.color = btn.active_color
                        self.current_gear = 'N'
                    else:
                        btn.is_active = False
                        btn.color = btn.normal_color
                        
                    self.add_widget(btn)
                    self.widgets[name] = btn
                    continue

                # Bluetooth button
                if name == 'bluetooth':
                    btn = ImageButton(normal_source=src)
                    btn.controller = self
                    btn.command = "BT"
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    btn.bind(on_press=self.show_bluetooth_devices)
                    self.add_widget(btn)
                    self.widgets['bluetooth'] = btn
                    continue

                # Accelerometer toggle - پیش‌فرض غیرفعال
                if name == 'accelerometer':
                    btn = ImageButton(normal_source=src)
                    btn.controller = self
                    btn.command = "ACC"
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    btn.bind(on_press=self.on_accelerometer_toggle)
                    # حالت پیش‌فرض غیرفعال
                    btn.is_active = False
                    btn.color = btn.normal_color
                    self.add_widget(btn)
                    self.widgets['accelerometer'] = btn
                    continue

                # Settings button
                if name == 'setting':
                    btn = ImageButton(normal_source=src)
                    btn.controller = self
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    btn.bind(on_press=lambda inst: self.show_settings_menu())
                    self.add_widget(btn)
                    self.widgets['setting'] = btn
                    continue

                # Command display - تنظیم فونت روی ۳۰
                if name == 'command_display':
                    cmd_box = BoxLayout(
                        orientation='vertical',
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos
                    )
                    title_label = Label(
                        text='Last Command',
                        size_hint_y=0.3,
                        font_size='14sp',
                        color=(0, 0, 0, 1)
                    )
                    self.last_cmd_label = Label(
                        text='--',
                        size_hint_y=0.7,
                        font_size='14sp',
                        color=(0, 0.5, 0, 1)
                    )
                    
                    cmd_box.add_widget(title_label)
                    cmd_box.add_widget(self.last_cmd_label)
                    self.add_widget(cmd_box)
                    self.widgets['command_display'] = cmd_box
                    continue

                # Device display
                if name == 'device_display':
                    device_box = BoxLayout(
                        orientation='vertical',
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos
                    )
                    device_title = Label(
                        text='Device',
                        size_hint_y=0.3,
                        font_size='14sp',
                        color=(0, 0, 0, 1)
                    )
                    self.device_name_label = Label(
                        text='Not Connected',
                        size_hint_y=0.7,
                        font_size='14sp',
                        color=(0.2, 0.2, 0.8, 1)
                    )
                    
                    device_box.add_widget(device_title)
                    device_box.add_widget(self.device_name_label)
                    self.add_widget(device_box)
                    self.widgets['device_display'] = device_box
                    
                    self.bind(connected_device=lambda inst, val: setattr(self.device_name_label, 'text', val))
                    continue

                # Control buttons - Turn signals
                if name in ('left', 'right', 'hazard'):
                    cmd_map = {
                        'left': 'LTL', 'right': 'RTL', 'hazard': 'ALL'
                    }
                    cmd = cmd_map.get(name, name.upper())
                    btn = ImageButton(normal_source=src)
                    btn.controller = self
                    btn.command = cmd
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    btn.bind(on_press=self._on_turn_signal_pressed)
                    self.add_widget(btn)
                    self.widgets[name] = btn
                    continue

                # Other control buttons
                if name in ('light', 'led', 'rgb', 'start'):
                    cmd_map = {
                        'light': 'LIT', 'led': 'LED', 'rgb': 'RGB', 
                        'start': 'STA'
                    }
                    cmd = cmd_map.get(name, name.upper())
                    btn = ImageButton(normal_source=src)
                    btn.controller = self
                    btn.command = cmd
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    btn.bind(on_press=self._on_toggle_control)
                    self.add_widget(btn)
                    self.widgets[name] = btn
                    continue

                # Horn button
                if name == 'horn':
                    btn = MomentaryImageButton(
                        normal_source=src,
                        press_command='HOR',
                        release_command='HOF'
                    )
                    btn.controller = self
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    self.add_widget(btn)
                    self.widgets[name] = btn
                    continue

                # Light horn button
                if name == 'lightHorn':
                    btn = MomentaryImageButton(
                        normal_source=src,
                        press_command='LHO',
                        release_command='LHO'
                    )
                    btn.controller = self
                    btn.size_hint = (None, None)
                    btn.size = (w_scaled, h_scaled)
                    btn.pos = pos
                    self.add_widget(btn)
                    self.widgets[name] = btn
                    continue

                # Generic image fallback
                if os.path.exists(src):
                    img = Image(
                        source=src,
                        size_hint=(None, None),
                        size=(w_scaled, h_scaled),
                        pos=pos,
                        allow_stretch=True,
                        keep_ratio=False
                    )
                    self.add_widget(img)
                    self.widgets[name] = img

            except Exception as e:
                print(f"❌ Error placing {name}: {e}")

        cmd_log_width = max(180, win_w * 0.18)
        cmd_log_height = max(35, win_h * 0.045)
        self.command_log.pos = (win_w - cmd_log_width - 10, 10 + safe_area_bottom)
        self.command_log.size = (cmd_log_width, cmd_log_height)
        
        self._ui_built = True
        print(f"✅ UI built successfully for {win_w}x{win_h}")

    def _update_connection_status(self, instance, value):
        if hasattr(self, 'conn_status_label'):
            self.conn_status_label.text = value
            self.conn_status_label.color = (0, 0.5, 0, 1) if value == "Connected" else (1, 0, 0, 1)

    # Control methods
    def send_command(self, command):
        print(f"📡 Sending: {command}")
        ok = self.ble.send_command(command)
        self.command_log.update_command(command)
        
        if hasattr(self, 'last_cmd_label'):
            self.last_cmd_label.text = command
            
        return ok

    def _on_gear_pressed(self, instance):
        for key in ('n', 'r', 'd'):
            w = self.widgets.get(key)
            if isinstance(w, ImageButton) and w is not instance:
                w.is_active = False
                w.color = w.normal_color
                
        instance.is_active = True
        instance.color = instance.active_color
        self.current_gear = instance.command
        self.send_command(instance.command)
        print(f"🎛️ Gear changed to: {instance.command}")

    def _on_turn_signal_pressed(self, instance):
        """مدیریت وضعیت چراغ‌های راهنما"""
        turn_signal_buttons = ['left', 'right', 'hazard']
        
        if instance.is_active:
            instance.is_active = False
            instance.color = instance.normal_color
            self.current_turn_signal = None
            self.send_command(instance.command)
            print(f"🚦 {instance.command} turned OFF")
        else:
            for signal_name in turn_signal_buttons:
                btn = self.widgets.get(signal_name)
                if btn and isinstance(btn, ImageButton) and btn is not instance:
                    btn.is_active = False
                    btn.color = btn.normal_color
            
            instance.is_active = True
            instance.color = instance.active_color
            self.current_turn_signal = instance.command
            self.send_command(instance.command)
            print(f"🚦 {instance.command} turned ON")

    def _on_toggle_control(self, instance):
        instance.toggle()
        self.send_command(instance.command)

    def _reset_turn_signals(self):
        turn_signal_buttons = ['left', 'right', 'hazard']
        for signal_name in turn_signal_buttons:
            btn = self.widgets.get(signal_name)
            if btn and isinstance(btn, ImageButton):
                btn.is_active = False
                btn.color = btn.normal_color
        self.current_turn_signal = None
        self.send_command("OFF")
        print("🚦 All turn signals reset to OFF")

    def on_accelerometer_toggle(self, instance):
        if not self.accelerometer_mode:
            # فعال کردن شتاب‌سنج
            if self.accelerometer_manager.start():
                self.accelerometer_mode = True
                instance.is_active = True
                instance.color = instance.active_color
                self.send_command('ACC1')
                print("✅ Accelerometer activated - Tilt device to steer")
            else:
                self.accelerometer_mode = False
                instance.is_active = False
                instance.color = instance.normal_color
                print("❌ Failed to activate accelerometer")
        else:
            # غیرفعال کردن شتاب‌سنج
            if self.accelerometer_manager.stop():
                self.accelerometer_mode = False
                instance.is_active = False
                instance.color = instance.normal_color
                self.send_command('ACC0')
                
                # Reset steering to center
                w = self.widgets.get('steer')
                if w:
                    w.angle = 0
                self.send_command("T50")
                print("✅ Accelerometer deactivated")

    def update_steering_from_accelerometer(self, angle):
        if self.accelerometer_mode:
            Clock.schedule_once(lambda dt: self._update_steer_angle(angle))

    def _update_steer_angle(self, angle):
        w = self.widgets.get('steer')
        if w:
            w.angle = angle
            
        if angle >= 0:
            value = 50 + int((angle / 90) * 49)
            value = min(99, value)
        else:
            value = 50 - int((abs(angle) / 90) * 50)
            value = max(0, value)
            
        self.send_command(f"T{value:02d}")

    # Bluetooth UI
    def show_bluetooth_devices(self, instance=None):
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        title = Label(text='Bluetooth BLE Devices', size_hint_y=0.12, font_size='18sp')
        content.add_widget(title)
        
        self.device_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.device_list.bind(minimum_height=self.device_list.setter('height'))
        
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.device_list)
        content.add_widget(scroll)
        
        btns = BoxLayout(size_hint_y=0.2, spacing=10)
        scan_btn = Button(
            text='Scan Again', 
            size_hint_x=0.5,
            font_size='16sp'
        )
        scan_btn.bind(on_press=lambda x: self.scan_devices())
        
        close_btn = Button(
            text='Close', 
            size_hint_x=0.5,
            font_size='16sp'
        )
        
        popup = Popup(title='Select BLE Device', content=content, size_hint=(0.85, 0.8))
        close_btn.bind(on_press=lambda x: popup.dismiss())
        
        btns.add_widget(scan_btn)
        btns.add_widget(close_btn)
        content.add_widget(btns)
        
        popup.open()
        self.bt_popup = popup
        self.scan_devices()

    def scan_devices(self):
        self.device_list.clear_widgets()
        loading = Label(text='Scanning for BLE devices...', size_hint_y=None, height=60, font_size='16sp')
        self.device_list.add_widget(loading)
        result = self.ble.start_scan(self.on_scan_results)

    def on_scan_results(self, devices):
        Clock.schedule_once(lambda dt: self._update_device_list(devices))

    def _update_device_list(self, devices):
        self.device_list.clear_widgets()
        if not devices:
            no_devices = Label(
                text='No BLE devices found\nMake sure Bluetooth is enabled', 
                size_hint_y=None, 
                height=120, 
                halign='center',
                font_size='16sp'
            )
            no_devices.bind(size=no_devices.setter('text_size'))
            self.device_list.add_widget(no_devices)
            return
            
        for dev in devices:
            btn = Button(
                text=dev, 
                size_hint_y=None, 
                height=70,
                text_size=(None, None),
                halign='left',
                valign='middle',
                font_size='14sp'
            )
            btn.bind(
                on_press=lambda inst, addr=dev: self._on_device_selected(inst, addr)
            )
            self.device_list.add_widget(btn)

    def _on_device_selected(self, instance, addr):
        print(f"🎯 Device selected: {addr}")
        self._connect_and_close(addr)

    def _connect_and_close(self, addr):
        print(f"🔄 Connecting to: {addr}")
        
        if hasattr(self, 'bt_popup'):
            self.bt_popup.dismiss()
        
        self.connection_status = "Connecting..."
        self.connected_device = f"Connecting: {addr.split(' ')[0]}"
        
        success = self.ble.connect(addr)
        
        if success:
            self.connection_status = "Connected"
            self.connected_device = f"Connected: {addr.split(' ')[0]}"
            print(f"✅ Connected to: {addr}")
            
            if get_setting('auto_connect', True):
                set_setting('last_connected_device', addr)
            
            if not HAS_ANDROID:
                # شبیه‌سازی باتری برای محیط غیر اندروید
                def simulate_battery():
                    self.ble.battery_level = 85
                    if self.ble.battery_update_callback:
                        self.ble.battery_update_callback(85)
                
                Clock.schedule_once(lambda dt: simulate_battery(), 1)
                
            self.show_connection_message("Connected successfully!", "success")
        else:
            self.connection_status = "Connection Failed"
            self.connected_device = "Not Connected"
            print(f"❌ Failed to connect to: {addr}")
            self.show_connection_message("Connection failed! Check device availability and range.", "error")

    def show_connection_message(self, message, msg_type):
        content = BoxLayout(orientation='vertical', spacing=15, padding=25)
        
        color = (0, 0.7, 0, 1) if msg_type == "success" else (1, 0, 0, 1)
        
        message_label = Label(
            text=message,
            text_size=(350, None),
            halign='center',
            valign='middle',
            font_size='16sp',
            color=color
        )
        message_label.bind(size=message_label.setter('text_size'))
        content.add_widget(message_label)
        
        ok_btn_layout = BoxLayout(size_hint_y=1, size_hint_x=1, padding=(50, 0))
        close_btn = Button(
            text='OK',
            size_hint_x=0.6,
            background_color=color,
            color=(1, 1, 1, 1),
            font_size='16sp'
        )
        
        popup = Popup(
            title='Connection Status',
            content=content,
            size_hint=(0.75, 0.4),
            auto_dismiss=False
        )
        
        close_btn.bind(on_press=popup.dismiss)
        ok_btn_layout.add_widget(close_btn)
        content.add_widget(ok_btn_layout)
        
        popup.open()

    # Settings menu
    def show_settings_menu(self):
        saved_sensitivity = get_setting('sensitivity', 1.0)
        auto_connect = get_setting('auto_connect', True)
        battery_warning = get_setting('battery_warning_level', 20)
        
        content = BoxLayout(orientation='vertical', spacing=12, padding=12)
        content.add_widget(Label(text='Settings', size_hint_y=0.1, font_size='20sp'))
        
        sens_layout = BoxLayout(orientation='vertical', size_hint_y=0.25, spacing=5)
        sens_label = Label(text=f'Sensitivity: {saved_sensitivity:.1f}', size_hint_y=0.3, font_size='16sp')
        sens_layout.add_widget(sens_label)
        
        slider = Slider(
            min=0.5,
            max=2.0,
            value=saved_sensitivity,
            size_hint_y=0.7
        )
        
        def on_sensitivity_change(instance, value):
            self.accelerometer_manager.set_sensitivity(value)
            sens_label.text = f'Sensitivity: {value:.1f}'
            set_setting('sensitivity', value)
            
        slider.bind(value=on_sensitivity_change)
        sens_layout.add_widget(slider)
        content.add_widget(sens_layout)
        
        toggles_layout = BoxLayout(orientation='vertical', size_hint_y=0.35, spacing=8)
        
        auto_connect_layout = BoxLayout(orientation='horizontal', size_hint_y=0.5)
        auto_connect_label = Label(text='Auto-connect to last device:', size_hint_x=0.7, font_size='16sp')
        auto_connect_switch = ToggleButton(
            text='ON' if auto_connect else 'OFF',
            state='down' if auto_connect else 'normal',
            size_hint_x=0.3
        )
        
        def on_auto_connect_toggle(instance):
            auto_connect = instance.state == 'down'
            instance.text = 'ON' if auto_connect else 'OFF'
            set_setting('auto_connect', auto_connect)
            print(f"Auto-connect: {'ON' if auto_connect else 'OFF'}")
        
        auto_connect_switch.bind(on_press=on_auto_connect_toggle)
        auto_connect_layout.add_widget(auto_connect_label)
        auto_connect_layout.add_widget(auto_connect_switch)
        toggles_layout.add_widget(auto_connect_layout)
        
        battery_layout = BoxLayout(orientation='horizontal', size_hint_y=0.5)
        battery_label = Label(text=f'Battery warning: {battery_warning}%', size_hint_x=0.7, font_size='16sp')
        battery_slider = Slider(
            min=5,
            max=30,
            value=battery_warning,
            size_hint_x=0.3
        )
        
        def on_battery_warning_change(instance, value):
            warning_level = int(value)
            battery_label.text = f'Battery warning: {warning_level}%'
            set_setting('battery_warning_level', warning_level)
            
        battery_slider.bind(value=on_battery_warning_change)
        battery_layout.add_widget(battery_label)
        battery_layout.add_widget(battery_slider)
        toggles_layout.add_widget(battery_layout)
        
        content.add_widget(toggles_layout)
        
        btns = BoxLayout(size_hint_y=0.2, spacing=10)
        
        reset_btn = Button(
            text='Reset to Default', 
            size_hint_x=0.5,
            font_size='16sp'
        )
        reset_btn.bind(on_press=lambda x: self._reset_settings(slider, sens_label, battery_slider, battery_label, auto_connect_switch))
        
        close_btn = Button(
            text='Close', 
            size_hint_x=0.5,
            font_size='16sp'
        )
        
        popup = Popup(title='Settings', content=content, size_hint=(0.85, 0.7))
        close_btn.bind(on_press=lambda x: popup.dismiss())
        
        btns.add_widget(reset_btn)
        btns.add_widget(close_btn)
        content.add_widget(btns)
        
        popup.open()

    def _reset_settings(self, sensitivity_slider, sens_label, battery_slider, battery_label, auto_connect_switch):
        App.get_running_app().settings_manager.reset_to_defaults()
        
        sensitivity_slider.value = 1.0
        sens_label.text = 'Sensitivity: 1.0'
        
        battery_slider.value = 20
        battery_label.text = 'Battery warning: 20%'
        
        auto_connect_switch.state = 'down'
        auto_connect_switch.text = 'ON'
        
        self.accelerometer_manager.set_sensitivity(1.0)
        
        print("✅ All settings reset to default")

# App class
class BluetoothRC(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings_manager = SettingsManager()
    
    def build(self):
        self.title = "Bluetooth RC Car Controller"
        print("🚀 Starting Bluetooth RC Car Controller...")
        return CombinedAppRoot()

    def on_pause(self):
        root = self.root
        if hasattr(root, 'accelerometer_manager'):
            root.accelerometer_manager.stop()
        if hasattr(root, 'ble'):
            root.ble.disconnect()
        if hasattr(root, '_reset_turn_signals'):
            root._reset_turn_signals()
        print("⏸️ App paused")
        return True

    def on_resume(self):
        root = self.root
        if HAS_ANDROID:
            Window.fullscreen = 'auto'
        if hasattr(root, 'accelerometer_manager') and getattr(root, 'accelerometer_mode', False):
            root.accelerometer_manager.start()
        if hasattr(root, '_reset_turn_signals'):
            root._reset_turn_signals()
        print("▶️ App resumed")
        return True

    def on_stop(self):
        """تمیز کردن منابع هنگام بسته شدن اپلیکیشن"""
        root = self.root
        if hasattr(root, 'accelerometer_manager'):
            root.accelerometer_manager.stop()
        if hasattr(root, 'ble'):
            root.ble.disconnect()
        print("🛑 App stopped - resources cleaned up")
        return True

if __name__ == '__main__':
    try:
        print("🎮 Starting Bluetooth RC Car Controller Application...")
        BluetoothRC().run()
    except Exception as e:
        print(f"❌ Application failed to start: {e}")
        import traceback
        traceback.print_exc()