from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .routes import api
from .storage import close_db, init_storage


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE='provenance_guard.db',
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    Limiter(key_func=get_remote_address, app=app)

    init_storage(app)
    app.teardown_appcontext(close_db)
    app.register_blueprint(api)
    return app
