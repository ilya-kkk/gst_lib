import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import cv2
import numpy as np
import threading
import queue
from typing import Optional, Tuple

class GstBase:
    """Базовый класс для GStreamer"""
    def __init__(self, ip: str, port: int, width: int = 1280, height: int = 720, framerate: int = 30):
        if not isinstance(ip, str) or not isinstance(port, int):
            raise ValueError("IP должен быть строкой, а port - целым числом")
        if not (0 < port < 65536):
            raise ValueError("Port должен быть в диапазоне 1-65535")
        if not (0 < width < 10000) or not (0 < height < 10000):
            raise ValueError("Недопустимые размеры видео")
        if not (0 < framerate < 120):
            raise ValueError("Недопустимая частота кадров")
            
        self.ip = ip
        self.port = port
        self.width = width
        self.height = height
        self.framerate = framerate
        self.pipeline = None
        self._mainloop = None
        self._mainloop_thread = None
        self.is_running = False
        
        # Инициализация GStreamer
        Gst.init(None)
        
    def _run_mainloop(self):
        """Запуск главного цикла GStreamer в отдельном потоке"""
        try:
            self._mainloop = GLib.MainLoop()
            self.is_running = True
            self._mainloop.run()
        except Exception as e:
            print(f"Ошибка в главном цикле: {e}")
            self.is_running = False
            
    def start(self):
        """Запуск pipeline"""
        if not self.pipeline:
            raise RuntimeError("Pipeline не создан")
            
        try:
            # Запускаем pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Не удалось запустить pipeline")
                
            # Запускаем главный цикл в отдельном потоке
            self._mainloop_thread = threading.Thread(target=self._run_mainloop)
            self._mainloop_thread.daemon = True
            self._mainloop_thread.start()
        except Exception as e:
            print(f"Ошибка при запуске: {e}")
            self.stop()
            raise
        
    def stop(self):
        """Остановка pipeline"""
        self.is_running = False
        try:
            if self._mainloop:
                self._mainloop.quit()
            if self.pipeline:
                self.pipeline.set_state(Gst.State.NULL)
            if self._mainloop_thread and self._mainloop_thread.is_alive():
                self._mainloop_thread.join(timeout=1.0)
        except Exception as e:
            print(f"Ошибка при остановке: {e}")


class GstPublisher(GstBase):
    """Класс для публикации видео"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = None
        self._build_pipeline()
        
    def _build_pipeline(self):
        """Создание pipeline для отправки"""
        try:
            pipeline_str = (
                "appsrc name=source do-timestamp=true is-live=true ! "
                f"video/x-raw,format=BGR,width={self.width},height={self.height},framerate={self.framerate}/1 ! "
                "videoconvert ! video/x-raw,format=I420 ! "
                "x264enc tune=zerolatency bitrate=2000 speed-preset=superfast ! "
                "rtph264pay ! "
                f"udpsink host={self.ip} port={self.port}"
            )
            
            self.pipeline = Gst.parse_launch(pipeline_str)
            if not self.pipeline:
                raise RuntimeError("Ошибка создания pipeline")
                
            self.source = self.pipeline.get_by_name("source")
            if not self.source:
                raise RuntimeError("Не удалось получить источник")
                
            caps = Gst.Caps.from_string(
                f"video/x-raw,format=BGR,width={self.width},height={self.height},framerate={self.framerate}/1"
            )
            self.source.set_property("caps", caps)
            self.source.set_property("format", Gst.Format.TIME)
        except Exception as e:
            print(f"Ошибка при создании pipeline: {e}")
            raise
        
    def publish_frame(self, frame: np.ndarray) -> bool:
        """Публикация кадра"""
        if not self.source or not self.is_running:
            return False
            
        try:
            # Проверяем размеры кадра
            if not isinstance(frame, np.ndarray):
                raise ValueError("Кадр должен быть numpy массивом")
            if frame.dtype != np.uint8:
                raise ValueError("Кадр должен быть в формате uint8")
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                raise ValueError("Кадр должен быть в формате BGR (3 канала)")
            if frame.shape[0] != self.height or frame.shape[1] != self.width:
                raise ValueError(f"Неверный размер кадра. Ожидается: {self.width}x{self.height}")
                
            data = frame.tobytes()
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            if not buf:
                raise RuntimeError("Не удалось создать буфер")
                
            buf.fill(0, data)
            return self.source.emit("push-buffer", buf) == Gst.FlowReturn.OK
        except Exception as e:
            print(f"Ошибка при публикации кадра: {e}")
            return False


class GstSubscriber(GstBase):
    """Класс для приема видео"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sink = None
        self.frame_queue = queue.Queue(maxsize=1)
        self._build_pipeline()
        
    def _build_pipeline(self):
        """Создание pipeline для приема"""
        try:
            pipeline_str = (
                f"udpsrc port={self.port} ! "
                "application/x-rtp,media=video,encoding-name=H264,payload=96 ! "
                "rtph264depay ! avdec_h264 ! "
                "videoconvert ! videoscale ! "
                f"video/x-raw,width={self.width},height={self.height},format=BGR ! "
                "appsink name=sink emit-signals=true"
            )
            
            self.pipeline = Gst.parse_launch(pipeline_str)
            if not self.pipeline:
                raise RuntimeError("Ошибка создания pipeline")
                
            self.sink = self.pipeline.get_by_name("sink")
            if not self.sink:
                raise RuntimeError("Не удалось получить приемник")
                
            self.sink.connect("new-sample", self._on_new_sample)
        except Exception as e:
            print(f"Ошибка при создании pipeline: {e}")
            raise
        
    def _on_new_sample(self, sink):
        """Обработка нового кадра"""
        try:
            sample = sink.emit("pull-sample")
            if not sample:
                return Gst.FlowReturn.ERROR
                
            buffer = sample.get_buffer()
            caps = sample.get_caps()
            
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                return Gst.FlowReturn.ERROR
                
            try:
                # Преобразуем буфер в массив numpy
                frame = np.ndarray(
                    shape=(self.height, self.width, 3),
                    dtype=np.uint8,
                    buffer=map_info.data
                ).copy()
                
                # Обновляем очередь кадров
                try:
                    # Очищаем очередь перед добавлением нового кадра
                    while not self.frame_queue.empty():
                        self.frame_queue.get_nowait()
                    self.frame_queue.put_nowait(frame)
                except queue.Full:
                    pass  # Пропускаем кадр если очередь заполнена
                    
            finally:
                buffer.unmap(map_info)
                
            return Gst.FlowReturn.OK
        except Exception as e:
            print(f"Ошибка при обработке кадра: {e}")
            return Gst.FlowReturn.ERROR
        
    def get_frame(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Получение кадра из очереди"""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None
        except Exception as e:
            print(f"Ошибка при получении кадра: {e}")
            return None 