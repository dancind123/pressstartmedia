from datetime import datetime
from pathlib import Path


class MediaLogger:
    def __init__(self, log_directory: str, filename: str = "media-manager.log"):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)

        self.log_file = self.log_directory / filename

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{timestamp} [{level.upper()}] {message}"

        print(entry)

        with self.log_file.open("a", encoding="utf-8") as file:
            file.write(entry + "\n")

    def info(self, message: str):
        self.log(message, "INFO")

    def warning(self, message: str):
        self.log(message, "WARNING")

    def error(self, message: str):
        self.log(message, "ERROR")
