"""
Loglama Yapılandırması (FR-9)

Rezervasyon oluşturma/güncelleme/iptal, reddedilen çakışma/kapasite
denemeleri ve kullanıcı girişleri; zaman damgası ve ilgili kullanıcı/oda
bilgisiyle app.log dosyasına yazılır.

ÖNEMLİ: Şifre veya şifre hash'i hiçbir log satırında yer almaz.
"""
import logging
import os

# backend/app/logging_config.py -> backend/app.log
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.log")

logger = logging.getLogger("rezerv")


def setup_logging(app):
    """create_app() içinden bir kez çağrılır. Flask debug reloader'da
    modül iki kez import edilebildiği için handler'ın tekrar tekrar
    eklenmesini engelliyoruz."""
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)