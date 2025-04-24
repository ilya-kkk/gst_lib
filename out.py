from gstreamer_utils import GstPublisher
import cv2
import numpy as np
import time
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_numbered_frame(number: int, width: int = 1280, height: int = 720) -> np.ndarray:
    """Создание кадра с номером"""
    try:
        if not isinstance(number, int) or number < 0:
            raise ValueError("Номер должен быть положительным целым числом")
        if not isinstance(width, int) or not isinstance(height, int):
            raise ValueError("Размеры должны быть целыми числами")
        if width <= 0 or height <= 0:
            raise ValueError("Размеры должны быть положительными числами")
            
        # Создаем белый кадр
        frame = np.ones((height, width, 3), dtype=np.uint8) * 255
        
        # Настраиваем параметры текста
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 5.0
        thickness = 10
        text = str(number)
        text_color = (0, 0, 255)  # BGR формат, красный цвет
        
        # Получаем размеры текста и центрируем его
        (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)
        x = (width - text_width) // 2
        y = (height + text_height) // 2
        
        # Рисуем текст
        cv2.putText(frame, text, (x, y), font, font_scale, text_color, thickness)
        
        return frame
    except Exception as e:
        logger.error(f"Ошибка при создании кадра: {e}")
        # Возвращаем пустой кадр в случае ошибки
        return np.ones((height, width, 3), dtype=np.uint8) * 255

def main():
    publisher = None
    try:
        # Создаем публикатора
        publisher = GstPublisher(ip="127.0.0.1", port=5000)
        
        # Запускаем pipeline
        publisher.start()
        logger.info("Отправка кадров начата. Для остановки нажмите Ctrl+C")
        
        # Отправляем кадры с числами от 1 до 100
        counter = 1
        while publisher.is_running:
            try:
                frame = create_numbered_frame(counter)
                if not publisher.publish_frame(frame):
                    logger.warning("Не удалось отправить кадр")
                    
                counter = (counter % 100) + 1  # Циклически от 1 до 100
                time.sleep(1/30)  # Примерно 30 FPS
            except Exception as e:
                logger.error(f"Ошибка при отправке кадра: {e}")
                time.sleep(0.1)  # Пауза перед следующей попыткой
            
    except KeyboardInterrupt:
        logger.info("Отправка остановлена пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        if publisher:
            try:
                publisher.stop()
            except Exception as e:
                logger.error(f"Ошибка при остановке публикатора: {e}")

if __name__ == "__main__":
    main() 