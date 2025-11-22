from kivy.storage.jsonstore import JsonStore
from kivy.app import App

class SettingsManager:
    def __init__(self):
        self.store = JsonStore('rc_car_settings.json')
    
    def get(self, key, default=None):
        try:
            return self.store.get(key)['value']
        except KeyError:
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
            'accelerometer_mode': False,
            'auto_connect': True,
            'steering_sensitivity': 1.0,
            'battery_warning_level': 20
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