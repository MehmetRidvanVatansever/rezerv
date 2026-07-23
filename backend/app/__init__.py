# Uygulama fabrikası: Flask uygulamasını yapılandırır, veritabanını başlatır
# ve gerekli blueprint'leri (auth vb.) kaydederek uygulamayı hazır hale getirir.
import os
from flask import Flask

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

    from . import auth
    app.register_blueprint(auth.bp)
    from . import rooms
    app.register_blueprint(rooms.bp)
    from . import reservations
    app.register_blueprint(reservations.bp)

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

    return app