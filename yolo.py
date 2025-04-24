from gstreamer_utils import GstSubscriber, GstPublisher
import cv2
import numpy as np
import os
import threading
import queue
import time
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Отключаем использование Wayland для Qt
# os.environ["QT_QPA_PLATFORM"] = "xcb"

# Создаем очереди для передачи кадров между потоками
input_queue = queue.Queue(maxsize=10)
output_queue = queue.Queue(maxsize=10)

# Флаг для контроля работы потоков
running = True

def draw_rectangle(frame):
    """Рисует красный прямоугольник в центре кадра"""
    try:
        if not isinstance(frame, np.ndarray):
            raise ValueError("Кадр должен быть numpy массивом")
            
        height, width = frame.shape[:2]
        # Вычисляем размеры и положение прямоугольника
        rect_width = width // 4
        rect_height = height // 4
        x = (width - rect_width) // 2
        y = (height - rect_height) // 2
        
        # Рисуем прямоугольник
        cv2.rectangle(frame, (x, y), (x + rect_width, y + rect_height), (0, 0, 255), 2)
        return frame
    except Exception as e:
        logger.error(f"Ошибка при рисовании прямоугольника: {e}")
        return frame

def receive_frames(subscriber):
    """Поток для получения кадров"""
    while running and subscriber.is_running:
        try:
            frame = subscriber.get_frame()
            if frame is not None:
                try:
                    input_queue.put(frame, block=False)
                except queue.Full:
                    # Если очередь полна, пропускаем кадр
                    logger.warning("Очередь ввода переполнена, пропускаем кадр")
                    pass
            time.sleep(0.001)
        except Exception as e:
            logger.error(f"Ошибка при получении кадра: {e}")
            time.sleep(0.1)  # Пауза перед следующей попыткой

def process_frames():
    """Поток для обработки кадров"""
    while running:
        try:
            frame = input_queue.get(timeout=1)
            processed_frame = draw_rectangle(frame.copy())
            try:
                output_queue.put(processed_frame, block=False)
            except queue.Full:
                logger.warning("Очередь вывода переполнена, пропускаем кадр")
                pass
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Ошибка при обработке кадра: {e}")
            time.sleep(0.1)

def send_frames(publisher):
    """Поток для отправки кадров"""
    while running and publisher.is_running:
        try:
            frame = output_queue.get(timeout=1)
            if not publisher.publish_frame(frame):
                logger.warning("Не удалось отправить кадр")
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Ошибка при отправке кадра: {e}")
            time.sleep(0.1)

def main():
    global running
    
    try:
        # Создаем подписчика для приема кадров от out.py
        subscriber = GstSubscriber(ip="127.0.0.1", port=5000)
        
        # Создаем издателя для отправки обработанных кадров в in.py
        publisher = GstPublisher(ip="127.0.0.1", port=5001)
        
        # Запускаем pipeline'ы
        subscriber.start()
        publisher.start()
        logger.info("Обработка кадров запущена. Для выхода нажмите Ctrl+C")
        
        # Создаем и запускаем потоки
        receive_thread = threading.Thread(target=receive_frames, args=(subscriber,))
        process_thread = threading.Thread(target=process_frames)
        send_thread = threading.Thread(target=send_frames, args=(publisher,))
        
        receive_thread.daemon = True
        process_thread.daemon = True
        send_thread.daemon = True
        
        receive_thread.start()
        process_thread.start()
        send_thread.start()
        
        # Бесконечный цикл в главном потоке
        while running:
            time.sleep(0.1)  # Небольшая задержка для снижения нагрузки на CPU
                    
    except KeyboardInterrupt:
        logger.info("Обработка остановлена пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        running = False  # Останавливаем все потоки
        try:
            subscriber.stop()
            publisher.stop()
            # Ждем завершения потоков
            receive_thread.join(timeout=1)
            process_thread.join(timeout=1)
            send_thread.join(timeout=1)
        except Exception as e:
            logger.error(f"Ошибка при остановке: {e}")

if __name__ == "__main__":
    main()