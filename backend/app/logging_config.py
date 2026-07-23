"""
Loglama Yapılandırması (FR-9)

Rezervasyon oluşturma/güncelleme/iptal, reddedilen çakışma/kapasite
denemeleri ve kullanıcı girişleri; zaman damgası ve ilgili kullanıcı/oda
bilgisiyle app.log dosyasına yazılır.

Log Rotation:
- app.log   -> tüm INFO ve üstü loglar. 10MB dolunca döner, 5 yedek tutulur
               (app.log.1, app.log.2, ... app.log.5).
- error.log -> sadece ERROR ve üstü loglar. 5MB dolunca döner, 3 yedek tutulur.

ÖNEMLİ: Şifre veya şifre hash'i hiçbir log satırında yer almaz.
"""
import logging
from logging.handlers import RotatingFileHandler
import os

# backend/app/logging_config.py -> backend/app.log , backend/error.log
BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
APP_LOG_FILE = os.path.join(BACKEND_DIR, "app.log")
ERROR_LOG_FILE = os.path.join(BACKEND_DIR, "error.log")

logger = logging.getLogger("rezerv")


def setup_logging(app):
    """create_app() içinden bir kez çağrılır. Flask debug reloader'da
    modül iki kez import edilebildiği için handler'ın tekrar tekrar
    eklenmesini engelliyoruz."""
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # app.log: INFO ve üstü, 10MB x 5 yedek
    app_handler = RotatingFileHandler(
        APP_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    logger.addHandler(app_handler)

    # error.log: sadece ERROR ve üstü, 5MB x 3 yedek
    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)