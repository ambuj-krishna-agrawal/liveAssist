import json
import os
import re
import threading
import time
from random import uniform

from moviepy.video.io.VideoFileClip import VideoFileClip
from datetime import datetime, timedelta
import google.generativeai as genai

processed_chunks = {}
processing = False


def crop_video(video_path, output_path, start_time, end_time):
    video = VideoFileClip(video_path)
    cropped_video = video.subclip(start_time, end_time)
    cropped_video.write_videofile(output_path, codec="libx264")


def seconds_to_time_string(seconds):
    return str(timedelta(seconds=seconds))


def simulate_streaming(video_path, extension, chunk_duration=30, starting_time=0):
    final_existing_location = f"{video_path}.{extension}"
    video = VideoFileClip(final_existing_location)
    video_duration = int(video.duration)

    num_chunks = video_duration // chunk_duration

    for i in range(num_chunks + 1):
        start_time_seconds = i * chunk_duration
        end_time_seconds = min((i + 1) * chunk_duration, video_duration)

        if end_time_seconds <= starting_time:
            continue
        start_time_str = seconds_to_time_string(start_time_seconds)
        end_time_str = seconds_to_time_string(end_time_seconds)
        output_path = f"{video_path}_chunks/chunk_{i + 1}.{extension}"

        print(f"Creating chunk {i + 1}: from {start_time_str} to {end_time_str} seconds.")
        crop_video(final_existing_location, output_path, start_time_str, end_time_str)

        # Simulate waiting time (streaming delay)
        time.sleep(chunk_duration)


def process_chunk_with_retries(chunk_path, video_path, model, starting_time, max_retries=5, initial_delay=1, max_delay=5):
    retries = 0
    while retries < max_retries:
        try:
            result = process_chunk(chunk_path, video_path, model, starting_time)
            return result
        except Exception as e:
            retries += 1
            delay = min(max_delay, initial_delay * 2 ** retries)
            delay_with_jitter = delay + uniform(0, 1)
            print(f"Error processing chunk {chunk_path}: {e}. Retrying in {delay_with_jitter:.2f} seconds...")
            time.sleep(delay_with_jitter)
    print(f"Failed to process chunk {chunk_path} after {max_retries} retries.")
    return None


def extract_chunk_number(filename):
    match = re.search(r'chunk_(\d+)\.mp4', filename)
    return int(match.group(1)) if match else float('inf')

def monitor_directory(video_path, extension, model, starting_time):

    processed_files = set()
    chunk_directory = f"{video_path}_chunks"
    while processing:
        chunk_files = [f for f in os.listdir(chunk_directory) if f.endswith(extension) and f not in processed_files]
        sorted_chunk_files = sorted(chunk_files, key=extract_chunk_number)

        for filename in sorted_chunk_files:
            chunk_path = os.path.join(chunk_directory, filename)
            print(f"Processing chunk: {filename}")
            result = process_chunk_with_retries(chunk_path, video_path, model, starting_time)
            if result is not None:
                processed_chunks[filename] = result
            processed_files.add(filename)

        time.sleep(5)


def start_monitoring(video_path, extension, model, starting_time=0):
    global processing
    processing = True
    monitor_thread = threading.Thread(target=monitor_directory, args=(video_path, extension, model, starting_time))
    monitor_thread.daemon = True  # This makes sure the thread will exit when the main program exits
    monitor_thread.start()


def start_streaming(video_path, extension, chunk_duration, starting_time=0):
    global processing
    processing = True
    monitor_thread = threading.Thread(target=simulate_streaming, args=(video_path, extension, chunk_duration, starting_time))
    monitor_thread.daemon = True
    monitor_thread.start()


def stop_processing(status_of_stream):
    global processing
    processing = status_of_stream


def convert_to_seconds(time_str):
    h = 0
    m = 0
    s = 0
    time_str_splitted = time_str.split(":")
    if len(time_str_splitted) == 1:
        s = int(time_str_splitted[0])
    elif len(time_str_splitted) == 2:
        m, s = map(int, time_str_splitted)
    else:
        h, m, s = map(int, time_str.split(':'))
    return timedelta(hours=h, minutes=m, seconds=s).total_seconds()


def convert_to_time_str(seconds):
    # Convert seconds back to "HH:MM:SS" format
    return str(timedelta(seconds=seconds))


def process_times(final_data, last_entry):
    last_end_time_seconds = convert_to_seconds(last_entry['end_time'])

    adjusted_data = []
    for entry in final_data:
        duration = convert_to_seconds(entry['end_time']) - convert_to_seconds(entry['start_time'])
        new_start_time = last_end_time_seconds
        new_end_time = new_start_time + duration

        adjusted_entry = {
            "message": entry['message'],
            "start_time": convert_to_time_str(new_start_time),
            "end_time": convert_to_time_str(new_end_time)
        }
        adjusted_data.append(adjusted_entry)

        last_end_time_seconds = new_end_time  # Update for the next entry

    return adjusted_data


def process_time_zero(final_data, starting_time):
    if starting_time == 0:
        return

    starting_time_str = convert_to_time_str(starting_time)

    starting_time_seconds = convert_to_seconds(starting_time_str)

    time_diff = starting_time_seconds

    for entry in final_data:
        entry_start_time = convert_to_seconds(entry["start_time"])
        entry_end_time = convert_to_seconds(entry["end_time"])

        # Adjust start and end times
        entry["start_time"] = convert_to_time_str(entry_start_time + time_diff)
        entry["end_time"] = convert_to_time_str(entry_end_time + time_diff)
    return final_data


def find_max_context(length_of_existing_context):
    if length_of_existing_context < 5:
        return -1
    return -2


def process_chunk(chunk_path, video_path, model, starting_time):
    print(f"Uploading file...")
    video_file_uploaded = genai.upload_file(path=chunk_path)
    print(f"Completed upload: {video_file_uploaded.uri}")
    while video_file_uploaded.state.name == "PROCESSING":
        print('Waiting for video to be processed.')
        time.sleep(10)
        video_file_uploaded = genai.get_file(video_file_uploaded.name)
    if video_file_uploaded.state.name == "FAILED":
        genai.delete_file(video_file_uploaded.name)
        raise ValueError(video_file_uploaded.state.name)
    print(f'Video processing complete: ' + video_file_uploaded.uri)
    video_file = video_file_uploaded

    output_file = f'{video_path}.json'
    existing_data = "None"
    if os.path.exists(output_file):
        with open(output_file, 'r') as file:
            data = json.load(file)
            existing_data = json.dumps(data[:find_max_context(len(existing_data))], indent=4)

    try:
        response = model.generate_content([
            "This is a cricket match. In every 10 seconds of the complete video, I want the timestamps and the corresponding detailed summary of what happened in every last 10 second window. Do not say that \"commentatory\" is saying something, as an assistant you directly summarize. The data you are getting is from the commentary done in the video and the match you are witnessing in the video. Give detailed explanation of what's happening and specially focus on what shots the batsman is playing, how the bowler is bowling, the score card, number of overs and how the players are reacting in the match. Also give the response in a particular json format. The given json file should be directly usable using json.loads in python. example - \"[{message:<your response>, \"start_time\": <start time>, \"end_time\": <end time>\" }]. Also do not start with \"the video starts with\", always assume that the video has been going on from before",
            video_file],
            request_options={"timeout": 600})
    except Exception as e:
        raise
    finally:
        genai.delete_file(video_file_uploaded.name)
    match = re.search(r'\[.*\]', response.text, re.DOTALL)
    if match:
        json_string = match.group(0)
        final_data = json.loads(json_string)
        if len(final_data) > 3:
            final_data = final_data[:3]
        output_file = f'{video_path}.json'

        # Append to the JSON file
        if os.path.exists(output_file):
            with open(output_file, 'r') as file:
                existing_data = json.load(file)
            final_data = process_times(final_data, existing_data[-1])
            existing_data.extend(final_data)
        else:
            existing_data = process_time_zero(final_data, starting_time)

        with open(output_file, 'w') as file:
            json.dump(existing_data, file, indent=4)

        return final_data
    else:
        return {"error": "No JSON data found"}
