from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty

class DoorbellLayout(BoxLayout):
    status_text = StringProperty("아무도 없어요.")

    def on_button_press(self):
        print("초인종이 눌렸습니다!")
        self.status_text = "딩동! 누가 왔어요!"

class DoorbellApp(App):
    def build(self):
        return DoorbellLayout()

if __name__ == '__main__':
    DoorbellApp().run()