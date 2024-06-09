import json


class FilesUpload:
    def __init__(self, file_name, creation_timestamp, uri, file_id):
        self.file_name = file_name
        self.creation_timestamp = creation_timestamp
        self.uri = uri
        self.file_id = file_id

    def to_dict(self):
        return {
            "file_name": self.file_name,
            "creation_timestamp": self.creation_timestamp,
            "uri": self.uri,
            "file_id": self.file_id,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            creation_timestamp=data["creation_timestamp"],
            file_name=data["file_name"],
            uri=data["uri"],
            file_id=data["file_id"],
        )

    def __str__(self):
        return f"File Name: {self.file_name}\nFile Id: {self.file_id}\nCreation Timestamp: {self.creation_timestamp}\nURI: {self.uri}\n"