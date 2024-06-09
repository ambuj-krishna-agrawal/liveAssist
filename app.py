import time
from datetime import datetime
from threading import Thread

from flask import Flask, jsonify, request
import textwrap
import os

import google.generativeai as genai
import re, json

from IPython.display import Markdown
from cricbuzz import update_context as cb_update_context, format_commentary
from files_upload import FilesUpload
from utils import read_from_json_file_get_files_upload, read_from_json_file_get_commentaries, write_to_json_file, \
    write_to_json_file_video
from video_processing import crop_video, stop_processing, \
    start_monitoring, start_streaming


def to_markdown(text):
    text = text.replace('•', '  *')
    return Markdown(textwrap.indent(text, '> ', predicate=lambda _: True))


app = Flask(__name__)
match_to_context = {}
match_to_video_context = {}
user_to_history = {}
files_upload = {}
model = genai.GenerativeModel('gemini-1.5-flash')


@app.route('/')
def gemini_generate():  # put application's code here
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("What is the meaning of life?")
    return response.text


@app.route('/video/', methods=['POST'])
def gemini_generate_stream():  # put application's code here

    # temp -> adding files/mfxvpuo5q7d because video is not uploading currently
    global result
    files_upload["video.mov"] = FilesUpload(file_name="video.mov", file_id='files/mfxvpuo5q7d',
                                            creation_timestamp=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                                            uri='v1beta/files/rwnarbhacv6k')

    data = request.get_json()
    file_name = data.get('file_name')
    match_id = data.get('match_id')
    file_id = None
    files_list = []

    if file_name in files_upload:
        file_id = files_upload[file_name].file_id
    else:
        files_list = read_from_json_file_get_files_upload(f"video_data.json")
        if files_list is not None and len(files_list) > 0:
            file_id = files_list[file_name].file_id

    video_file = None
    if file_id is None or file_id == "":
        print(f"Uploading file...")
        video_file_uploaded = genai.upload_file(path=file_name)
        print(f"Completed upload: {video_file_uploaded.uri}")
        while video_file_uploaded.state.name == "PROCESSING":
            print('Waiting for video to be processed.')
            time.sleep(10)
            video_file_uploaded = genai.get_file(video_file_uploaded.name)
        if video_file_uploaded.state.name == "FAILED":
            raise ValueError(video_file_uploaded.state.name)
        print(f'Video processing complete: ' + video_file_uploaded.uri)
        video_file = genai.get_file(video_file_uploaded.name)
        file = FilesUpload(file_name=file_name, file_id=video_file.name,
                           creation_timestamp=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), uri=video_file.uri)
        files_upload[file_name] = file
        files_list.append(file)
        write_to_json_file(files_list, "video_data.json")
    else:
        video_file = genai.get_file(file_id)

    print("Making LLM inference request...")
    response = model.generate_content([
        "I want the response in a particular format. In every 10 seconds of the complete video, I want the timestamps and the corresponding summary of the details that happened in every last 10 second window.  Also give the response in json format. The given json file should be directly be usable using json.loads in python",
        video_file],
        request_options={"timeout": 600})
    match = re.search(r'\{.*\}', response.text, re.DOTALL)
    if match:
        json_string = match.group(0)
        final_data = json.loads(json_string)
        write_to_json_file_video(final_data, f'match_video_{match_id}.json')
        # Load the JSON string into a Python dictionary
        return jsonify({'data': final_data})
    else:
        return jsonify({'error': "No JSON data found"})


@app.route('/live-context/', methods=['POST'])
def update_live_context():
    try:
        data = request.get_json()
        match_id = data.get('match_id')
        context, formatted_context = cb_update_context(match_id)
        match_to_context[match_id] = context
        return jsonify({'message': 'Context updated successfully', 'data': formatted_context}), 200

    except Exception as e:
        # Log the exception and return a generic error message
        app.logger.error(f"An error occurred: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


@app.route('/text-context/chat/', methods=['POST'])
def gemini_text_chat():
    try:
        # Get the user ID and prompt from the POST request body
        data = request.get_json()
        user_id = data.get('user_id')
        prompt = data.get('prompt')
        match_id = data.get('match_id')

        context_data = None
        if match_id in match_to_context:
            context_data = match_to_context[match_id]
        else:
            context_data = read_from_json_file_get_commentaries(f"match_{match_id}.json")

        history = user_to_history.get(user_id, [])

        # if history not present then talk with gemini a bit as warmup
        if not history:
            warmup_chat = model.start_chat(history=[])
            warmup_response = warmup_chat.send_message("Let's start the conversation.")
            history = warmup_chat.history

        chat = model.start_chat(history=history)
        combined_prompt = (
            f"Context:\n{format_commentary(context_data)}\n\n"
            f"User's Question:\n{prompt}\n\n"
            f"Instructions to AI: If the answer to the user's question is present in the provided context, "
            f"answer confidently using only the context. If the answer is not in the context, use your general knowledge "
            f"to provide an answer. Do not mention the context in your response. Just give a direct answer based on the context, "
            f"your general knowledge, or a combination of both."
        )

        response = chat.send_message([combined_prompt])
        user_to_history[user_id] = chat.history

        return jsonify({'response': response.text})

    except Exception as e:
        # Log the exception and return a generic error message
        app.logger.error(f"An error occurred: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


@app.route('/video-context/chat/', methods=['POST'])
def gemini_video_chat():
    try:
        # Get the user ID and prompt from the POST request body
        data = request.get_json()
        user_id = data.get('user_id')
        prompt = data.get('prompt')
        match_id = data.get('match_id')
        video_path = f"match_video_{match_id}"
        extension = "mp4"

        context_data = None
        if match_id in match_to_video_context:
            context_data = match_to_video_context[match_id]
        else:
            context_data = read_from_json_file_get_files_upload(f"{video_path}.json")

        history = user_to_history.get(user_id, [])

        # if history not present then talk with gemini a bit as warmup
        if not history:
            warmup_chat = model.start_chat(history=[])
            warmup_response = warmup_chat.send_message("Let's start the conversation.")
            history = warmup_chat.history

        chat = model.start_chat(history=history)
        combined_prompt = (
                f"Context:\n{context_data}\n\n"
                f"User's Question:\n{prompt}\n\n"
                f"Instructions to AI: If the answer to the user's question is present in the provided context, "
                f"answer confidently using only the context. If the answer is not in the context, use your general knowledge "
                f"to provide an answer. Do not mention the context in your response. Just give a direct answer based on the context, "
                f"your general knowledge, or a combination of both. Additionally, please give the response in a particular json format example - "
                + "{message:<your response>, \"start_time\": <start time>, \"end_time\": <end time>\" }. Here the start time and end time refers to the start time which answers the user's query and end time which answers the user's query."
        )

        response = chat.send_message([combined_prompt])
        user_to_history[user_id] = chat.history

        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            json_string = match.group(0)
            final_data = json.loads(json_string)
            # Load the JSON string into a Python dictionary
            print(final_data.get('start_time', '-'), final_data.get('end_time', '-'))
            if 'start_time' in final_data and 'end_time' in final_data:
                crop_video(f"{video_path}.{extension}", "video_cut.mov", final_data['start_time'], final_data['end_time'])
                return jsonify({'data': final_data.get('message', '-')})
            else:
                return jsonify({'error': "could not find end or starting time for video cropping"})
        else:
            return jsonify({'error': "No JSON data found"})

    except Exception as e:
        # Log the exception and return a generic error message
        app.logger.error(f"An error occurred: {e}")
        return jsonify({"error": "Internal Server Error"}), 500


@app.route('/stream_video/', methods=['POST'])
def stream_video_resource():
    data = request.get_json()
    match_id = data.get('match_id')
    video_path = f"match_video_{match_id}"
    # w44aui56gres
    start_monitoring(video_path, "mp4", model, 180)
    return jsonify({"message": "Started processing video chunks"}), 202


@app.route('/simulate-streaming/', methods=['POST'])
def simulate_streaming_resource():
    data = request.get_json()
    match_id = data.get('match_id')
    video_path = f"match_video_{match_id}"
    start_streaming(video_path, "mp4", 30, 180)
    return jsonify({"message": "Have started streaming"}), 202


@app.route('/stop_stream/', methods=['GET'])
def stop_stream_resource():
    stop_processing(False)
    return jsonify({"message": "Stopped processing video chunks"}), 200


if __name__ == '__main__':
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    genai.configure(api_key=GOOGLE_API_KEY)
    app.run()

# install brew install ffmpeg for moviepy
