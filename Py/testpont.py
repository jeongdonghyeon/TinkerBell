from kivy.app import App
from kivy.uix.label import Label
from kivy.core.text import LabelBase
from kivy.resources import resource_add_path

resource_add_path(".")
LabelBase.register(name="NotoSansKR", fn_regular="NotoSansKR-Regular.ttf")

class TestApp(App):
    def build(self):
        return Label(text="한글 폰트 잘 나오나요?", font_name="NotoSansKR", font_size="40sp")

TestApp().run()
