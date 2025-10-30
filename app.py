from flask import Flask, render_template, redirect, url_for

def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        # Redirect to auth for now but we can check for stored credentials later
        return redirect(url_for("auth"))

    @app.route("/auth", methods=["GET", "POST"])
    def auth():
        return render_template("auth.html")

    @app.route("/home")
    def home():
        return render_template("home.html")

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)


