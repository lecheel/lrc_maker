import threading
import glob
import time
import signal
import sys
from tqdm import tqdm
from pyfzf.pyfzf import FzfPrompt
from faster_whisper import WhisperModel

# Configuration
MODEL_SIZE = "medium"
DEVICE = "cuda"
COMPUTE_TYPE = "int8_float16"
BEAM_SIZE = 5

def setup_signal_handler():
    def handler(sig, frame):
        signal_name = signal.Signals(sig).name
        print(f"\n{signal_name} received. Exiting...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    if sys.platform != "win32":
        signal.signal(signal.SIGQUIT, handler)
        signal.signal(signal.SIGHUP, handler)
        signal.signal(signal.SIGTSTP, handler)

def select_input_file():
    files = glob.glob("*.mp3")
    if not files:
        raise FileNotFoundError("No MP3 files found in current directory")
    fzf = FzfPrompt()
    selected = fzf.prompt(files)
    if not selected:
        raise KeyboardInterrupt("No file selected")
    return selected[0]

def create_transcription(fname, model):
    print(f"\nProcessing '{fname}' with Whisper...\n")
    start_time = time.time()
    
    # Get segments without processing to count total segments
    segments_list = list(model.transcribe(fname, beam_size=BEAM_SIZE)[0])
    
    lrc_content = ""
    # Create progress bar
    with tqdm(total=len(segments_list), desc="Transcribing", 
             bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} segments [{elapsed}<{remaining}]') as pbar:
        for segment in segments_list:
            start_time_fmt = "%02d:%02d.%02d" % (
                segment.start // 60,
                segment.start % 60,
                (segment.start % 1) * 100
            )
            lrc_line = f"[{start_time_fmt}] {segment.text}\n"
            lrc_content += lrc_line
            pbar.update(1)
    
    process_time = time.time() - start_time
    return lrc_content, process_time

def show_preview(content, num_lines=5):
    lines = content.splitlines()
    if not lines:
        return
    
    print("\nPreview of first few lines:")
    print("-" * 40)
    for line in lines[:num_lines]:
        print(line)
    print(" ...... ")
    print("-" * 40)
    print(f"Total lines: {len(lines)}")

def main():
    setup_signal_handler()
    
    try:
        fname = select_input_file()
        lrc_name = fname.replace(".mp3", ".lrc")
        
        print(f"\nLoading Whisper {MODEL_SIZE} model on {DEVICE}...")
        with tqdm(total=1, desc="Loading model", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            model_start_time = time.time()
            model = WhisperModel(
                MODEL_SIZE,
                device=DEVICE,
                compute_type=COMPUTE_TYPE
            )
            model_load_time = time.time() - model_start_time
            pbar.update(1)
        print(f"Model loaded successfully! (took {model_load_time:.2f}s)")
        
        lrc_content, transcription_time = create_transcription(fname, model)
        
        print(f"\nTranscription completed! Saving to {lrc_name}...")
        with open(lrc_name, "w") as f:
            f.write(lrc_content)
        
        show_preview(lrc_content)
        print("\nTime Summary:")
        print(f"Model loading: {model_load_time:.2f}s")
        print(f"Transcription: {transcription_time:.2f}s")
        print(f"Total time: {(model_load_time + transcription_time):.2f}s")
        print("\nDone!")
            
    except (FileNotFoundError, KeyboardInterrupt) as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

