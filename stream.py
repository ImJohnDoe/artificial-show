from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env

import logging
import os
import subprocess
import signal

image_path = os.getenv("IMAGE_PATH")
stream_url = os.getenv("STREAM_URL")

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

fifo_path = "/tmp/audio.fifo"

ffmpeg_process = None  # Global variable to store the Popen object

def signal_handler(sig, frame):
    global ffmpeg_process
    if ffmpeg_process is not None:
        logging.info("Terminating FFmpeg process...")
        ffmpeg_process.terminate()
        ffmpeg_process.wait()  # Wait for the process to terminate
        logging.info("FFmpeg process terminated.")
    exit(0)  # Exit the script

def start_stream():
    logging.info("Starting stream...")
    # Ensure FIFO pipe exists
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path)

    command = [
        "ffmpeg",
        "-loop",
        "1",
        "-thread_queue_size",
        "512",
        "-i",
        image_path,
        "-thread_queue_size",
        "512",
        "-i",
        fifo_path,
        "-c:a",
        "copy",
        "-c:v",
        "libx264",
        "-shortest",
        "-flvflags",
        "no_duration_filesize",
        "-f",
        "flv",
        stream_url,
    ]

    try:
        subprocess.Popen(command)
        logging.info("Stream started.")
    except Exception as e:
        logging.error(f"Error starting stream: {e}")

    # Register the signal handler for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, signal_handler)

    # Wait for the FFmpeg process to complete (if it ever does)
    ffmpeg_process.wait()

def main():
    start_stream()


if __name__ == "__main__":
    main()
