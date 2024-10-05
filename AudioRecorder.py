import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QListWidget, QFileDialog, QTextEdit, QGraphicsDropShadowEffect, QHBoxLayout
from PySide6.QtCore import Signal, Qt, QObject, QEvent
import pyaudio
import wave
import threading
import subprocess
from datetime import datetime
from llmvoice import SpeechRecognitionService
import tempfile
import shutil, os
import signal

class AudioRecorder(QMainWindow):
    transcription_signal = Signal(str)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Audio Recorder")
        self.setGeometry(100, 100, 800, 600)
        self.service = SpeechRecognitionService()
        self.transcription_signal.connect(self.update_transcription)
        self.is_recording = False
        self.ffplay_process = None
        self.is_paused = False
        self.transcriptions = {}  # Cache for transcriptions
        self.play_queue = []  # Queue for files to play

        self.initUI()

    def initUI(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        self.recording_list = QListWidget()
        self.recording_list.setSelectionMode(QListWidget.MultiSelection)  # Enable multiple selection
        layout.addWidget(self.recording_list)
     
        self.recording_list.setStyleSheet("""
            QListWidget::item:selected {
                background-color: lightblue;
                color: black;
            }
        """)
        # Create a horizontal layout for the buttons
        button_layout = QHBoxLayout()

        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load_audio)
        button_layout.addWidget(self.load_button)

        self.record_button = QPushButton("Record")
        self.record_button.clicked.connect(self.record_audio)
        button_layout.addWidget(self.record_button)

        self.play_pause_button = QPushButton("Play")
        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        button_layout.addWidget(self.play_pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_audio)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)  # Add button layout to main layout

        self.transcription_window = QTextEdit()
        self.transcription_window.setReadOnly(True)
        layout.addWidget(self.transcription_window)

        # Apply styles with a more common font
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F0F0F0;
            }
            QPushButton {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #E0E0E0);
                color: #333333;
                border-radius: 15px;
                padding: 10px;
                font-size: 16px;
                font-family: 'Arial', sans-serif;  /* Changed font family */
                border: 1px solid #CCCCCC;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
            QListWidget, QTextEdit {
                background-color: #FFFFFF;
                color: #333333;
                border: 1px solid #DDDDDD;
                border-radius: 5px;
                font-family: 'Arial', sans-serif;  /* Changed font family */
            }
        """)

        shadow_effect = QGraphicsDropShadowEffect()
        shadow_effect.setBlurRadius(10)
        shadow_effect.setXOffset(2)
        shadow_effect.setYOffset(2)
        shadow_effect.setColor(Qt.gray)

        self.record_button.setGraphicsEffect(shadow_effect)
        self.load_button.setGraphicsEffect(shadow_effect)
        self.play_pause_button.setGraphicsEffect(shadow_effect)
        self.stop_button.setGraphicsEffect(shadow_effect)

        central_widget.setLayout(layout)

    def record_audio(self):
        if not self.is_recording:
            self.is_recording = True
            self.record_button.setText("Stop Recording")
            threading.Thread(target=self._record).start()
        else:
            self.is_recording = False
            self.record_button.setText("Record")

    def _record(self):
        chunk = 1024
        sample_format = pyaudio.paInt16
        channels = 1
        fs = 44100
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"output_{timestamp}.wav"

        p = pyaudio.PyAudio()

        stream = p.open(format=sample_format,
                        channels=channels,
                        rate=fs,
                        frames_per_buffer=chunk,
                        input=True)

        frames = []

        while self.is_recording:
            data = stream.read(chunk)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(sample_format))
            wf.setframerate(fs)
            wf.writeframes(b''.join(frames))

        self.recording_list.addItem(filename)

    def load_audio(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Load Audio Files", "", "Audio Files (*.wav *.mp3)")
        for file in files:
            self.recording_list.addItem(file)

    def toggle_play_pause(self):
        if self.ffplay_process is None:
            self.play_audio()
        elif self.is_paused:
            self.resume_audio()
        else:
            self.pause_audio()

    def play_audio(self):
        selected_items = self.recording_list.selectedItems()
        self.play_queue = [item.text() for item in selected_items]
        if self.play_queue:
            self.play_next_in_queue()

    def play_next_in_queue(self):
        if self.play_queue:
            audio_file = self.play_queue.pop(0)
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file_name = temp_file.name
            temp_file.close()

            shutil.copy(audio_file, temp_file_name)

            if audio_file not in self.transcriptions:
                transcription_thread = threading.Thread(target=self.transcribe_audio, args=(audio_file, temp_file_name))
                transcription_thread.start()

            playback_thread = threading.Thread(target=self._playback, args=(temp_file_name,))
            playback_thread.start()

    def _playback(self, temp_file_name):
        try:
            self.ffplay_process = subprocess.Popen(['ffplay', '-nodisp', '-autoexit', temp_file_name])
            self.play_pause_button.setText("Pause")
            self.ffplay_process.wait()
        except subprocess.CalledProcessError as e:
            print(f"An error occurred: {e}")
        finally:
            self.ffplay_process = None
            self.play_pause_button.setText("Play")
            os.remove(temp_file_name)
            self.play_next_in_queue()  # Play the next file in the queue

    def pause_audio(self):
        if self.ffplay_process:
            self.ffplay_process.send_signal(signal.SIGSTOP)
            self.is_paused = True
            self.play_pause_button.setText("Play")

    def resume_audio(self):
        if self.ffplay_process:
            self.ffplay_process.send_signal(signal.SIGCONT)
            self.is_paused = False
            self.play_pause_button.setText("Pause")

    def stop_audio(self):
        if self.ffplay_process:
            self.ffplay_process.terminate()
            self.ffplay_process = None
            self.play_pause_button.setText("Play")

    def transcribe_audio(self, audio_file, temp_file_name):
        transcription = self.service.transcribe(temp_file_name)
        self.transcriptions[audio_file] = transcription
        self.transcription_signal.emit(f"{audio_file}: {transcription}")

    def update_transcription(self, text):
        if text not in self.transcription_window.toPlainText():
            self.transcription_window.append(text)

    def record_audio(self):
        if not self.is_recording:
            self.is_recording = True
            self.record_button.setText("Stop Recording")
            threading.Thread(target=self._record).start()
        else:
            self.is_recording = False
            self.record_button.setText("Record")

    def _record(self):
        chunk = 1024
        sample_format = pyaudio.paInt16
        channels = 1
        fs = 44100
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"output_{timestamp}.wav"

        p = pyaudio.PyAudio()

        stream = p.open(format=sample_format,
                        channels=channels,
                        rate=fs,
                        frames_per_buffer=chunk,
                        input=True)

        frames = []

        while self.is_recording:
            data = stream.read(chunk)
            frames.append(data)

        stream.stop_stream()
        stream.close()
        p.terminate()

        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(sample_format))
            wf.setframerate(fs)
            wf.writeframes(b''.join(frames))

        self.recording_list.addItem(filename)

    def load_audio(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Load Audio Files", "", "Audio Files (*.wav *.mp3)")
        for file in files:
            self.recording_list.addItem(file)

    def toggle_play_pause(self):
        if self.ffplay_process is None:
            self.play_audio()
        elif self.is_paused:
            self.resume_audio()
        else:
            self.pause_audio()

    def play_audio(self):
        selected_items = self.recording_list.selectedItems()
        self.play_queue = [item.text() for item in selected_items]
        if self.play_queue:
            self.play_next_in_queue()

    def play_next_in_queue(self):
        if self.play_queue:
            audio_file = self.play_queue.pop(0)
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file_name = temp_file.name
            temp_file.close()

            shutil.copy(audio_file, temp_file_name)

            if audio_file not in self.transcriptions:
                transcription_thread = threading.Thread(target=self.transcribe_audio, args=(audio_file, temp_file_name))
                transcription_thread.start()

            playback_thread = threading.Thread(target=self._playback, args=(temp_file_name,))
            playback_thread.start()

    def _playback(self, temp_file_name):
        try:
            self.ffplay_process = subprocess.Popen(['ffplay', '-nodisp', '-autoexit', temp_file_name])
            self.play_pause_button.setText("Pause")
            self.ffplay_process.wait()
        except subprocess.CalledProcessError as e:
            print(f"An error occurred: {e}")
        finally:
            self.ffplay_process = None
            self.play_pause_button.setText("Play")
            os.remove(temp_file_name)
            self.play_next_in_queue()  # Play the next file in the queue

    def pause_audio(self):
        if self.ffplay_process:
            self.ffplay_process.send_signal(signal.SIGSTOP)
            self.is_paused = True
            self.play_pause_button.setText("Play")

    def resume_audio(self):
        if self.ffplay_process:
            self.ffplay_process.send_signal(signal.SIGCONT)
            self.is_paused = False
            self.play_pause_button.setText("Pause")

    def stop_audio(self):
        if self.ffplay_process:
            self.ffplay_process.terminate()
            self.ffplay_process = None
            self.play_pause_button.setText("Play")

    def transcribe_audio(self, audio_file, temp_file_name):
        transcription = self.service.transcribe(temp_file_name)
        file_name = os.path.basename(audio_file)
        self.transcriptions[file_name] = transcription
        self.transcription_signal.emit(f"{file_name}: {transcription}")

    def update_transcription(self, text):
        file_name, transcription = text.split(": ", 1)
        formatted_text = f"<span style='color: #007BFF;'>{file_name}:</span> <span style='color: #333333;'>{transcription}</span>"
        if formatted_text not in self.transcription_window.toHtml():
            self.transcription_window.append(formatted_text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_selected_items()

    def delete_selected_items(self):
        # Delete selected items from the recording list
        for item in self.recording_list.selectedItems():
            self.recording_list.takeItem(self.recording_list.row(item))
            # Optionally, remove the corresponding transcription
            file_name = os.path.basename(item.text()) 
            if file_name in self.transcriptions:
                del self.transcriptions[file_name]
        self.update_transcription_display()

    def update_transcription_display(self):
        # Clear the QTextEdit and repopulate it with remaining transcriptions
        self.transcription_window.clear()
        for file_name, transcription in self.transcriptions.items():
            formatted_text = f"<span style='color: #007BFF;'>{file_name}:</span> <span style='color: #333333;'>{transcription}</span>"
            self.transcription_window.append(formatted_text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AudioRecorder()
    window.show()
    sys.exit(app.exec())