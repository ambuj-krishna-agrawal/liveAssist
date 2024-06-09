import http.client
import json
import time
from datetime import datetime

from commentory import Commentory
from utils import write_to_json_file

api_key = "3f252661abmsh4f76f360e11c61ap1d5c84jsn926d45176be6"
cc_api_host = "cricbuzz-cricket.p.rapidapi.com"
uc_api_host = "unofficial-cricbuzz.p.rapidapi.com"


def fetch_commentary(match_id, timestamp=None):
    conn = http.client.HTTPSConnection(uc_api_host)

    headers = {
        'x-rapidapi-key': api_key,
        # 'x-rapidapi-host': cc_api_host,
        'x-rapidapi-host': uc_api_host
    }

    # Construct the request path with timestamp if provided
    # path = f"/mcenter/v1/{match_id}/comm"
    path = f"/matches/get-commentaries?matchId={match_id}"

    if timestamp:
        path += f"&tms={timestamp}"

    # if timestamp:
    #     path += f"?tms={timestamp}"
    conn.request("GET", path, headers=headers)

    res = conn.getresponse()
    data = res.read()

    return json.loads(data.decode("utf-8"))


def get_timestamp_from_entry(entry):
    if "commSnippet" in entry:
        return int(entry["commSnippet"]["commTimestamp"])
    elif "commentary" in entry:
        return int(entry["commentary"]["timestamp"])
    else:
        return None


def get_all_commentaries(match_id):
    all_commentaries = []
    timestamp = None
    while True:
        data = fetch_commentary(match_id, timestamp)
        commentaries = data.get("commentaryLines", [])

        if not commentaries:
            break

        all_commentaries.extend(commentaries)

        # Update the timestamp for the next request
        if commentaries:
            last_commentary = commentaries[-1]
            timestamp = get_timestamp_from_entry(last_commentary)

    return all_commentaries


def replace_formats(text, formats):
    if "bold" in formats:
        for format_id, format_value in zip(formats["bold"]["formatId"], formats["bold"]["formatValue"]):
            text = text.replace(format_id, format_value)
    return text


def format_commentary(dto_list):
    if dto_list is None or len(dto_list) == 0:
        return "No context yet"
    formatted_commentary = [str(dto) for dto in dto_list]
    return "\n".join(formatted_commentary)


def convert_to_dto(commentary_list):
    dto_list = []

    for entry in commentary_list:
        if "commSnippet" in entry:
            comm_snippet = entry["commSnippet"]
            timestamp = datetime.fromtimestamp(int(comm_snippet["commTimestamp"]) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            over = f"{commentary.get('overNum', '-') if 'overNum' in comm_snippet else '-'} over"
            comm_text = replace_formats(comm_snippet.get("headline", ""), entry.get("commentaryFormats", {}))
        elif "commentary" in entry:
            commentary = entry["commentary"]
            timestamp = datetime.fromtimestamp(int(commentary["timestamp"]) / 1000).strftime('%Y-%m-%d %H:%M:%S')
            over = f"{commentary.get('overNum', '-') if 'overNum' in commentary else '-'} over"
            comm_text = commentary.get("commtxt", "")

        dto_list.append(Commentory(comms=comm_text, timestamp=timestamp, over=over, score=None))

    return dto_list


def fetch_recent_commentary(match_id, current_timestamp, last_timestamp):
    # Fetch commentary data just after the provided timestamp
    commentary_data = fetch_commentary(match_id, current_timestamp)
    commentaries = commentary_data.get("commentaryLines", [])

    filtered_commentaries = []
    for c in commentaries:
        timestamp = get_timestamp_from_entry(c)
        if timestamp and timestamp > last_timestamp:
            filtered_commentaries.append(c)
    return filtered_commentaries


def update_context(match_id):
    # make paginated calls to fetch all the context
    commentary_data = get_all_commentaries(match_id)
    last_timestamp = get_timestamp_from_entry(commentary_data[-1])
    while True:
        current_timestamp = datetime.utcnow().timestamp() * 1000
        data = fetch_recent_commentary(match_id, last_timestamp, current_timestamp)
        if not data:
            break
        commentary_data.extend(data)
        last_timestamp = current_timestamp
        time.sleep(1)
    commentary_data = convert_to_dto(commentary_data)
    write_to_json_file(commentary_data, "match_" + str(match_id) + ".json")
    return commentary_data, format_commentary(commentary_data)



