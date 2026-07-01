from app import create_app
from app.storage import close_db

app = create_app()
app.teardown_appcontext(close_db)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
