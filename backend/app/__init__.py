# Uygulama fabrikası: Flask uygulamasını yapılandırır, veritabanını başlatır
# ve gerekli blueprint'leri (auth vb.) kaydederek uygulamayı hazır hale getirir.
import os
from flask import Flask, request

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev"),
        DATABASE=os.path.join(app.instance_path, "rezerv.db"),
    )
    app.json.ensure_ascii = False  # JSON çıktısında Türkçe karakterler \uXXXX yerine düz yazılsın

    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from .logging_config import setup_logging
    setup_logging(app)

    from . import db
    db.init_app(app)
    
    # Hata yanıtları için ortak modül
    from . import errors

    # ---- Beklenmeyen (yakalanmamış) hatalar için genel yakalayıcı ----
    # Buraya kadar hiçbir yerde logger.error() çağrılmıyordu, bu yüzden
    # error.log hep boş kalıyordu. Bu handler, kodun hiçbir yerde
    # try/except ile beklemediği gerçek hataları (örn. beklenmeyen bir
    # None.attribute erişimi, veritabanı bağlantı hatası vb.) yakalar,
    # error.log'a tam hata izi (traceback) ile yazar ve kullanıcıya genel
    # bir 500 yanıtı döner. 400/401/403/404/409 gibi kendi ürettiğimiz
    # "beklenen" hatalar zaten normal return ile döndüğü için buraya hiç
    # düşmez; bu handler yalnızca gerçek programlama hataları içindir.
    from werkzeug.exceptions import HTTPException
    from .logging_config import logger
    from .errors import error_response

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        if isinstance(e, HTTPException):
            # 404 (bilinmeyen route), 405 (yanlış HTTP metodu) gibi
            # Flask/Werkzeug'un kendi ürettiği durumlar; bunlar "beklenmeyen
            # hata" değil, normal akışın bir parçası, error.log'u kirletmesin.
            return e
        logger.error(
            f"Beklenmeyen hata: {type(e).__name__}: {e} "
            f"[{request.method} {request.path}]",
            exc_info=True,
        )
        return error_response(
            "internal_error", "Sunucuda beklenmeyen bir hata oluştu.", 500
        )

    from . import auth
    app.register_blueprint(auth.bp)
    from . import rooms
    app.register_blueprint(rooms.bp)
    from . import reservations
    app.register_blueprint(reservations.bp)
    from . import admin
    app.register_blueprint(admin.bp)

    @app.get("/health")
    def health():
        from .db import get_db
        get_db().execute("SELECT 1").fetchone()
        return {"status": "ok", "database": app.config["DATABASE"]}

    # ---- Frontend'i ayni origin'den servis et ----
    # (boylece fetch() session cookie'sini CORS ayari gerekmeden gonderebilir)
    from flask import send_from_directory
    FRONTEND_DIR = os.path.join(os.path.dirname(app.root_path), "..", "frontend")

    @app.get("/")
    def frontend_index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/css/<path:filename>")
    def frontend_css(filename):
        return send_from_directory(os.path.join(FRONTEND_DIR, "css"), filename)

    @app.get("/js/<path:filename>")
    def frontend_js(filename):
        return send_from_directory(os.path.join(FRONTEND_DIR, "js"), filename)

    @app.get("/assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(os.path.join(FRONTEND_DIR, "assets"), filename)

    return app