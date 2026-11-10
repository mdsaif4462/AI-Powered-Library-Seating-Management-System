import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    DB_CONFIG = dict(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "Saif@12345"),
        database=os.environ.get("DB_NAME", "library_seating"),
    )
    OPEN_HOUR = 8          # library opens 08:00
    CLOSE_HOUR = 21        # library closes 21:00
    MAX_DURATION = 4       # max hours per booking
    GRACE_MINUTES = 15     # no check-in within this many minutes => no-show
