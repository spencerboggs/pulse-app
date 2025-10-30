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

    @app.route("/profile")
    def profile():
        return render_template("profile.html")

    @app.route("/events")
    def events():
        return render_template("events.html")
    
    @app.route("/concert-map")
    def concert_map():
        return render_template("concert_map.html")

    @app.route("/settings")
    def settings():
        return render_template("settings.html")

    @app.route("/weekly-insights")
    def weekly_insights():
        return render_template("weekly_insights.html")

    @app.route("/matchmaking")
    def matchmaking():
        return render_template("matchmaking.html")

    @app.route("/message")
    def message():
        return render_template("message.html")

    @app.route("/blocked-accounts")
    def blocked_accounts():
        return render_template("blocked_accounts.html")

    @app.route("/report")
    def report():
        return render_template("report.html")

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)


