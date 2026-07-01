from flask import Flask

from .routes import api
from .storage import close_db, init_storage


def create_app(test_config: dict | None = None) -> Flask:
    from .extensions import limiter

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE='provenance_guard.db',
        JSON_SORT_KEYS=False,
    )

    if test_config:
        app.config.update(test_config)

    limiter.init_app(app)

    init_storage(app)
    app.teardown_appcontext(close_db)
    app.register_blueprint(api)
    return app
