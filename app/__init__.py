from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import os
import logging

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)

    raw_url = os.getenv("DATABASE_URL", "")
    app.config["SQLALCHEMY_DATABASE_URI"] = raw_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-this")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "images")

    logging.basicConfig(level=logging.INFO)

    db.init_app(app)
    migrate.init_app(app, db)

    from app.admin import admin_bp
    from app.buyer import buyer_bp
    from app.base import base_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(buyer_bp)
    app.register_blueprint(base_bp)

    return app