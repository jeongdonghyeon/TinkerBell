import os
import requests
from dotenv import load_dotenv

from datetime import datetime
from kivy.clock import Clock

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.fitimage import FitImage

load_dotenv()


FONT_PATH = "Spoqa Han Sans Regular.ttf"

class DoorbellScreen(MDScreen):
    pass

class DoorbellApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Light"
        return DoorbellScreen()

    def on_start(self):

        self.theme_cls.font_name = FONT_PATH


        Clock.schedule_interval(self.update_time, 1)


        self.get_weather()

    def update_time(self, *args):
        now = datetime.now()

        self.root.ids.time_label.text = now.strftime("%H:%M:%S")
        self.root.ids.date_label.text = now.strftime("%Y.%m.%d [%A]")

    def get_weather(self, *args):
        api_key = os.getenv('OPENWEATHER_API_KEY')
        if not api_key:
            self.root.ids.weather_label.text = "API 키 필요"
            return


        city_name = "Incheon"
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric&lang=kr"

        try:
            response = requests.get(url)
            data = response.json()

            if data['cod'] == 200:
                temp = data['main']['temp']
                weather_desc = data['weather'][0]['description']
                self.root.ids.weather_label.text = f"{temp:.1f}°C, {weather_desc}"
            else:
                self.root.ids.weather_label.text = "날씨 정보 실패"
        except requests.exceptions.RequestException:
            self.root.ids.weather_label.text = "네트워크 오류"

if __name__ == '__main__':
    DoorbellApp().run()