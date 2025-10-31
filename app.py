<<<<<<< HEAD
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


=======
from flask import Flask, render_template, redirect, url_for
import os, re

def create_app():
    app = Flask(__name__)

    # ---------- Helpers ----------
    def slugify(name: str) -> str:
        # lowercase, replace non-alnum with '-', trim '-'
        return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

    def pick_user_image_by_slug(slug: str) -> str:
        """Return a static URL for the best image matching the given slug
        inside static/uploads/. Falls back to placeholder."""
        uploads_path = os.path.join(app.static_folder, "uploads")
        os.makedirs(uploads_path, exist_ok=True)

        exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")
        # Prefer exact slug match first
        for ext in exts:
            candidate = os.path.join(uploads_path, f"{slug}{ext}")
            if os.path.exists(candidate):
                return url_for("static", filename=f"uploads/{slug}{ext}")

        # Otherwise, fallback to most recent image in uploads (for that user you might add logic later)
        images = [f for f in os.listdir(uploads_path) if f.lower().endswith(exts)]
        if images:
            latest = max(images, key=lambda f: os.path.getmtime(os.path.join(uploads_path, f)))
            return url_for("static", filename=f"uploads/{latest}")

        # Final fallback: placeholder
        return url_for("static", filename="images/profile_placeholder.png")

    # ---------- Routes ----------
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

    # Main user's profile (not for viewing other users)
    @app.route("/profile")
    def profile():
        # Choose main user's image. You can change this slug to your main username.
        main_user_slug = "main-user"   # <--- rename if desired
        img_url = pick_user_image_by_slug(main_user_slug)
        display_name = "Your Profile"
        return render_template("profile.html", img_url=img_url, display_name=display_name)

    # New: read-only profile page for viewing other users
    @app.route("/u/<path:username>")
    def user_profile(username):
        # slug from the username in the URL
        slug = slugify(username)
        img_url = pick_user_image_by_slug(slug)
        display_name = username
        return render_template("profile_view.html", img_url=img_url, display_name=display_name)

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
>>>>>>> e3c12d6 (changed, user profile,  matchmaking w/ matchmaking user profiles, added messaging users and a non functional message thread)
