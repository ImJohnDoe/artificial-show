from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env

import logging
import os
import queue
import subprocess
import threading
import time

import boto3
import openai

aws_access_key = os.getenv("AWS_ACCESS_KEY")
aws_secret_key = os.getenv("AWS_SECRET_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
image_path = os.getenv("IMAGE_PATH")
stream_url = os.getenv("STREAM_URL")

# Set OpenAI API key
openai.api_key = openai_api_key

# Create Polly client
polly_client = boto3.Session(
    aws_access_key_id=aws_access_key,
    aws_secret_access_key=aws_secret_key,
    region_name="us-west-2",
).client("polly")

# Create a new queue
audio_queue = queue.Queue(maxsize=4)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

fifo_path = "/tmp/audio.fifo"


def moderate_content(text):
    try:
        moderation_resp = openai.Moderation.create(input=text)
        output = moderation_resp["results"][0]
        if output["flagged"]:
            return False
        return True
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return False


def generate_response(messages):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=messages, max_tokens=100
        )
        logging.info("Received response from OpenAI.")
    except Exception as e:
        logging.error(f"Error generating response: {e}")
        return "Sorry, I had trouble understanding that."
    return response["choices"][0]["message"]["content"].strip()


def text_to_speech(text):
    try:
        response = polly_client.synthesize_speech(
            VoiceId="Joanna", OutputFormat="mp3", Text=text
        )
    except Exception as e:
        logging.error(f"Error synthesizing speech: {e}")
        return None
    return response["AudioStream"].read()


def stream_audio(data):
    if data is not None:
        try:
            with open(fifo_path, "ab") as f:
                f.write(data)
        except Exception as e:
            logging.error(f"Error streaming audio: {e}")


def stream_audio(data):
    if data is not None:
        try:
            # Wait if the pipe is full
            while os.stat(fifo_path).st_size >= 512:
                logging.info("Pipe is full, waiting...")
                time.sleep(0.1)  # Wait for 100 milliseconds

            # Write data to the pipe
            with open(fifo_path, "ab") as f:
                f.write(data)

        except Exception as e:
            logging.error(f"Error streaming audio: {e}")


def stream_audio_from_queue():
    while True:
        data = audio_queue.get()
        if data is None:
            break
        stream_audio(data)
        audio_queue.task_done()


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


def main():
    # uncomment this if you want to start the stream all in one command
    # otherwise, run python main.py and then run python stream.py
    # start_stream()

    messages = [
        {"role": "system", "content": "You are a witty punster."},
        {
            "role": "user",
            "name": "hackler",
            "content": "Who won the world series in 2020?",
        },
    ]

    currentSpeaker = "punster"
    speakers = ["hackler", "punster"]
    currentSpeakerRole = "assistant"
    speakerRoles = ["user", "assistant"]

    # Start a new thread to stream audio from the queue
    threading.Thread(target=stream_audio_from_queue).start()

    while True:
        if len(messages) > 100:
            messages = messages[-100:]
        response_text = generate_response(messages)
        if moderate_content(response_text):
            logging.info("Message passed moderation.")
            logging.info(f"Adding message: {response_text}")
            messages.append(
                {
                    "role": currentSpeakerRole,
                    "name": currentSpeaker,
                    "content": response_text,
                }
            )
        else:
            logging.info("Message failed moderation.")
            messages.append(
                {
                    "role": "system",
                    "content": "I just stopped myself from saying something inappropriate.",
                }
            )
            currentSpeakerRole = (
                speakerRoles[0]
                if currentSpeakerRole == speakerRoles[1]
                else speakerRoles[1]
            )
            currentSpeaker = (
                speakers[0] if currentSpeaker == speakers[1] else speakers[1]
            )

        # Only start streaming when there are at least two messages
        if len(messages) > 2:
            audio_data = text_to_speech(response_text)
            # Wait if the queue is full
            audio_queue.put(audio_data)
            logging.info(
                f"Audio message added to queue. Queue size: {audio_queue.qsize()}"
            )


if __name__ == "__main__":
    main()
