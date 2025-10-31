from flask import Flask, render_template, redirect, url_for
import os, re

def create_app() -> Flask:
    app = Flask(__name__)

    # ============================================================
    # HELPERS
    # ============================================================
    
    def slugify(name: str) -> str:
        """Convert a name to a URL-friendly slug."""
        return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

    def pick_user_image_by_slug(slug: str) -> str:
        """Return a static URL for the best image matching the given slug.
        Falls back to placeholder if no image found."""
        uploads_path = os.path.join(app.static_folder, "uploads")
        os.makedirs(uploads_path, exist_ok=True)

        exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")
        
        # Try exact slug match
        for ext in exts:
            candidate = os.path.join(uploads_path, f"{slug}{ext}")
            if os.path.exists(candidate):
                return url_for("static", filename=f"uploads/{slug}{ext}")

        # Fallback to most recent image
        images = [f for f in os.listdir(uploads_path) if f.lower().endswith(exts)]
        if images:
            latest = max(images, key=lambda f: os.path.getmtime(os.path.join(uploads_path, f)))
            return url_for("static", filename=f"uploads/{latest}")

        return url_for("static", filename="images/profile_placeholder.png")

    # ============================================================
    # ROUTES
    # ============================================================
    
    @app.route("/")
    def index():
        return redirect(url_for("auth"))

    @app.route("/auth", methods=["GET", "POST"])
    def auth():
        return render_template("auth.html")

    @app.route("/home")
    def home():
        return render_template("home.html")

    @app.route("/profile")
    def profile():
        # ========== PLACEHOLDER DATA - REMOVE BEFORE PRODUCTION ==========
        main_user_slug = "main-user"
        img_url = pick_user_image_by_slug(main_user_slug)
        display_name = "Your Profile"
        # =================================================================
        return render_template("profile.html", img_url=img_url, display_name=display_name)

    @app.route("/u/<path:username>")
    def user_profile(username):
        # ========== PLACEHOLDER DATA - REMOVE BEFORE PRODUCTION ==========
        slug = slugify(username)
        img_url = pick_user_image_by_slug(slug)
        display_name = username
        # =================================================================
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
