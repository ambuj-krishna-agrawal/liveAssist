from datetime import datetime


class Commentory:
    def __init__(self, comms, timestamp, over, score):
        self.comms = comms
        self.timestamp = timestamp
        self.over = over
        self.score = score

    def to_dict(self):
        return {
            "comms": self.comms,
            "timestamp": self.timestamp,
            "over": self.over,
            "score": self.score
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            comms=data["comms"],
            timestamp=data["timestamp"],
            over=data["over"],
            score=data["score"]
        )

    def __str__(self):
        return f"Timestamp: {self.timestamp}\nOver: {self.over}\nScore: {self.score}\nCommentary: {self.comms}\n"
