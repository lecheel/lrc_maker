# Audio Transcription Tool

A Python-based tool that converts speech from MP3 files into timestamped 
text using OpenAI's Whisper model (via Faster-Whisper). The output is 
saved in LRC format, making it perfect for subtitles or synchronized lyrics.

<img src="./png/screen_01.png" width="800"/>

## Features

- 🎯 Interactive file selection with fuzzy finder
- 🚀 GPU-accelerated transcription
- ⏱️ Real-time progress tracking
- 🎯 Timestamped output in LRC format
- 📊 Performance metrics and timing information
- 🛑 Graceful interrupt handling

## Prerequisites

- Python 3.8+
- CUDA-capable GPU (recommended)
- FFmpeg (for audio processing)
- Test on Ubuntu 22.04 CUDA 12.5

## Installation

1. Clone the repository: 
