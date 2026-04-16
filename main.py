import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, Response, redirect, render_template, request, send_file

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

PORT = int(os.getenv("PORT", 5000))
WORKER_API_BASE = str(os.getenv("WORKER_API_BASE", "http://127.0.0.1:8787")).rstrip("/")


def worker_url(path):
    if not path.startswith("/"):
        path = f"/{path}"
    query = request.query_string.decode("utf-8", errors="ignore").strip()
    if query:
        return f"{WORKER_API_BASE}{path}?{query}"
    return f"{WORKER_API_BASE}{path}"


def forward_to_worker(path):
    method = request.method.upper()
    payload = None
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        payload = request.get_data() or None

    headers = {}
    content_type = request.headers.get("Content-Type")
    if content_type:
        headers["Content-Type"] = content_type

    admin_key = request.headers.get("X-Admin-Key")
    if admin_key:
        headers["X-Admin-Key"] = admin_key

    target = worker_url(path)
    upstream_request = Request(target, data=payload, headers=headers, method=method)

    try:
        with urlopen(upstream_request, timeout=30) as upstream_response:
            body = upstream_response.read()
            status = upstream_response.getcode()
            response = Response(body, status=status)
            content_type = upstream_response.headers.get("Content-Type")
            content_disposition = upstream_response.headers.get("Content-Disposition")
            if content_type:
                response.headers["Content-Type"] = content_type
            if content_disposition:
                response.headers["Content-Disposition"] = content_disposition
            return response
    except HTTPError as error:
        body = error.read() if hasattr(error, "read") else b""
        response = Response(body, status=error.code)
        if error.headers:
            content_type = error.headers.get("Content-Type")
            if content_type:
                response.headers["Content-Type"] = content_type
        return response
    except URLError as error:
        return Response(
            f'{{"error":"Could not reach Worker API","details":"{error}"}}',
            status=502,
            mimetype="application/json",
        )


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/feedback")
@app.route("/feedback/")
def feedback():
    return send_file("feedback/index.html")


@app.route("/frontpages", methods=["GET", "POST"])
def frontpages_redirect():
    return redirect("/")


@app.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin.html")


@app.route("/downloads/index-page", methods=["GET"])
def download_index_page():
    index_path = Path("static/index_page.pdf")
    if not index_path.exists():
        return Response(
            '{"error":"Index page file is unavailable"}',
            status=404,
            mimetype="application/json",
        )
    return send_file(
        index_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="IndexPage.pdf",
    )


@app.route("/api/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def proxy_api(subpath):
    return forward_to_worker(f"/api/{subpath}")


@app.route("/admin/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def proxy_admin(subpath):
    if subpath == "dashboard":
        return admin_dashboard()
    return forward_to_worker(f"/admin/{subpath}")


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=PORT, debug=debug_mode)
