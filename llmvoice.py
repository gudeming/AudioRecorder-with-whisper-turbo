import os
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from pydub import AudioSegment

class SpeechRecognitionService:
    def __init__(self):
        device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )
        print(f"Using {device} device")
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        model_id = "openai/whisper-large-v3-turbo"

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, torch_dtype=torch_dtype, use_safetensors=True
        )
        model.to(device)

        processor = AutoProcessor.from_pretrained(model_id)

        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=device,
        )

    def transcribe(self, audio_input):
        segments = self.split_audio(audio_input, segment_length=29)
        results = []
        batch_size = len(segments)

        
        batch_results = self.pipe(segments, batch_size=batch_size)

        full_transcription = self.merge_results(batch_results)
        self.cleanup(segments)
        return full_transcription

    def split_audio(self, audio_input, segment_length=29):
        audio = AudioSegment.from_file(audio_input)
        duration = len(audio) / 1000  # Convert to seconds
        segments = []

        for start in range(0, int(duration), segment_length):
            end = min(start + segment_length, duration)
            segment = audio[start * 1000:end * 1000]  # Convert to milliseconds
            segment_file = f"segment_{start}_{end}.mp3"
            segment.export(segment_file, format="mp3")
            segments.append(segment_file)

        return segments

    def merge_results(self, results):
        return " ".join(d['text'] for d in results if 'text' in d)

    def cleanup(self, segments):
        for segment in segments:
            if os.path.exists(segment):
                os.remove(segment)

# Usage in another file
# from llmvoice import SpeechRecognitionService
# service = SpeechRecognitionService()
# result = service.transcribe(audio_input)