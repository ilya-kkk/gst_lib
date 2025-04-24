from gstreamer_utils import GstSubscriber
import cv2
import os
import time
import gi
import logging
import gc
import weakref
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Отключаем использование Wayland для Qt
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["OPENCV_VIDEOIO_BACKEND"] = "v4l2"

# Инициализация GStreamer
Gst.init(None)

class VideoDisplay:
    def __init__(self, window_name='Received Video'):
        self.window_name = window_name
        self._create_window()
        
    def _create_window(self):
        """Создание окна для отображения видео"""
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        
    def show_frame(self, frame):
        """Отображение кадра"""
        if frame is not None:
            cv2.imshow(self.window_name, frame)
            
    def destroy(self):
        """Закрытие окна"""
        cv2.destroyWindow(self.window_name)
        cv2.waitKey(1)  # Даем время на закрытие окна

def main():
    subscriber = None
    display = None
    try:
        # Создаем подписчика
        subscriber = GstSubscriber(ip="127.0.0.1", port=5001)
        
        # Создаем дисплей
        display = VideoDisplay()
        
        # Запускаем pipeline
        subscriber.start()
        logger.info("Прием кадров начат. Для выхода нажмите ESC")
        
        # Создаем главный цикл GLib
        loop = GLib.MainLoop()
        
        def check_key():
            try:
                frame = subscriber.get_frame()
                if frame is not None:
                    # Отображаем кадр
                    display.show_frame(frame)
                    
                    # Очищаем память
                    del frame
                    gc.collect()
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:  # ESC
                        loop.quit()
                        return False
                return True
            except Exception as e:
                logger.error(f"Ошибка при обработке кадра: {e}")
                return True
        
        # Добавляем таймер для проверки клавиш с большим интервалом
        GLib.timeout_add(33, check_key)  # ~30 FPS
        
        # Запускаем главный цикл
        loop.run()
                    
    except KeyboardInterrupt:
        logger.info("Прием остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Останавливаем подписчика
        if subscriber:
            try:
                subscriber.stop()
            except Exception as e:
                logger.error(f"Ошибка при остановке подписчика: {e}")
                
        # Закрываем окно
        if display:
            try:
                display.destroy()
            except Exception as e:
                logger.error(f"Ошибка при закрытии окна: {e}")
                
        # Принудительная очистка памяти
        gc.collect()
        
        # Даем время на освобождение ресурсов
        time.sleep(0.1)

if __name__ == "__main__":
    main() 