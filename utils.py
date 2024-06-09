import json

from commentory import Commentory
from files_upload import FilesUpload


def write_to_json_file(dto_list, filename):
    with open(filename, 'w') as file:
        json_data = [dto.to_dict() for dto in dto_list]
        json.dump(json_data, file, indent=4)


def write_to_json_file_video(video_context_json, filename):
    with open(filename, 'w') as file:
        json.dump(video_context_json, file, indent=4)


def read_from_json_file_get_commentaries(filename):
    try:
        with open(filename, 'r') as file:
            json_data = json.load(file)
            return [Commentory.from_dict(item) for item in json_data]
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return None


def read_from_json_file_get_files_upload(filename):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        return None
