import io
import json
import os
from collections import deque
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from PIL import Image, ImageDraw, ImageFont
from werkzeug.exceptions import HTTPException

load_dotenv()

app = Flask(__name__, template_folder="templates")

PORT = int(os.getenv("PORT", 5000))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
CONFIG_PATH = Path(os.getenv("ADMIN_CONFIG_PATH", "admin_config.json"))
LOG_PATH = Path(os.getenv("FRONTPAGE_LOG_PATH", "frontpage_logs.jsonl"))

MAX_LOG_RETURN = 200


@app.errorhandler(HTTPException)
def handle_exception(e):
    """Return JSON instead of HTML for HTTP errors."""
    response = e.get_response()
    response.data = json.dumps(
        {
            "code": e.code,
            "name": e.name,
            "description": e.description,
        }
    )
    response.content_type = "application/json"
    return response


def load_admin_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Admin config file not found at {CONFIG_PATH.resolve()}."
        )

    try:
        data = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse admin config file {CONFIG_PATH}: {exc}"
        ) from exc

    data.setdefault("subjects", [])
    data.setdefault("ece_subjects", [])
    data.setdefault("aiml_subjects", [])
    data.setdefault("subject_codes", {})
    data.setdefault("stream_labels", {})
    return data


def save_admin_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))


admin_config = load_admin_config()


def _get_subject_lists():
    return (
        admin_config.get("subjects", []),
        admin_config.get("ece_subjects", []),
        admin_config.get("aiml_subjects", []),
    )


def _get_stream_label(stream_code: int) -> str:
    labels = admin_config.get("stream_labels", {})
    return labels.get(str(stream_code), "N/A")


def _get_subject_code(subject: str) -> str:
    codes = admin_config.get("subject_codes", {})
    return codes.get(subject, "N/A")


def log_frontpage_event(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(entry)}\n")


def read_frontpage_logs(limit: int) -> list:
    if not LOG_PATH.exists():
        return []
    bucket = deque(maxlen=limit)
    with LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                bucket.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(bucket)


def count_frontpage_logs() -> int:
    if not LOG_PATH.exists():
        return 0
    count = 0
    with LOG_PATH.open("r", encoding="utf-8") as handle:
        for _ in handle:
            count += 1
    return count


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not ADMIN_API_KEY:
            abort(403, description="Admin API key not configured")
        provided = request.headers.get("X-Admin-Key") or request.args.get("admin_key")
        if provided != ADMIN_API_KEY:
            abort(401, description="Invalid admin credentials")
        return func(*args, **kwargs)

    return wrapper


def _add_subject_entry(category: str, name: str, code: str) -> None:
    cat_map = {
        "general": "subjects",
        "ece": "ece_subjects",
        "aiml": "aiml_subjects",
    }
    target_key = cat_map.get(category, "subjects")

    target_list = admin_config.setdefault(target_key, [])
    if name not in target_list:
        target_list.append(name)

    for key in cat_map.values():
        if key != target_key:
            other_list = admin_config.get(key, [])
            if name in other_list:
                admin_config[key] = [x for x in other_list if x != name]

    admin_config.setdefault("subject_codes", {})[name] = code
    save_admin_config(admin_config)


def _remove_subject_entry(name: str) -> bool:
    removed = False
    for bucket in ("subjects", "ece_subjects", "aiml_subjects"):
        items = admin_config.get(bucket, [])
        if name in items:
            admin_config[bucket] = [item for item in items if item != name]
            removed = True
    if removed:
        save_admin_config(admin_config)
    return removed


@app.route("/")
def index():
    return redirect(url_for("generate_frontpage"))


def _format_semester(raw_semester: int) -> str:
    ordinal_map = {
        1: "1ST",
        2: "2ND",
        3: "3RD",
        4: "4TH",
        5: "5TH",
        6: "6TH",
        7: "7TH",
        8: "8TH",
    }
    return ordinal_map.get(raw_semester, "N/A")


@app.route("/frontpages", methods=["GET", "POST"])
def generate_frontpage():
    if request.method == "POST":
        name = request.form["name"].strip()
        roll = request.form["roll"].strip()
        reg = request.form["reg"].strip()
        subject = request.form["subject"].strip()

        semester = _format_semester(int(request.form["semester"]))

        stream_code = int(request.form["stream"])
        final_stream = _get_stream_label(stream_code)

        if stream_code == 3 and subject == "Data Structures & Algorithms Lab":
            subject = "Data Structure Lab"

        subject_code = _get_subject_code(subject)

        print(
            f"Received Data : Name : {name} \nRoll : {roll} \nReg : {reg} \nSubject : {subject}"
        )

        img = Image.open("static/template.png")
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype("static/Sans.ttf", size=45)

        start_x = 530
        start_y = 1060
        line_gap = 87

        draw.text((start_x, start_y + 0 * line_gap), name, font=font, fill="black")
        draw.text((start_x, start_y + 1 * line_gap), roll, font=font, fill="black")
        draw.text((start_x, start_y + 2 * line_gap), reg, font=font, fill="black")
        draw.text(
            (start_x, start_y + 3 * line_gap), final_stream, font=font, fill="black"
        )
        draw.text((start_x, start_y + 4 * line_gap), semester, font=font, fill="black")
        draw.text(
            (start_x, start_y + 5 * line_gap), subject_code, font=font, fill="black"
        )
        draw.text((start_x, start_y + 6 * line_gap), subject, font=font, fill="black")

        img_io = io.BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)

        log_frontpage_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "name": name,
                "roll": roll,
                "reg": reg,
                "subject": subject,
                "stream": final_stream,
                "semester": semester,
            }
        )

        safe_subject = subject.replace(" ", "-")
        download_name = f"{name}-{safe_subject}-FrontPageCover.png"

        return send_file(
            img_io,
            mimetype="image/png",
            as_attachment=True,
            download_name=download_name,
        )

    subjects, ece_subjects, aiml_subjects = _get_subject_lists()
    return render_template(
        "index.html",
        subjects=subjects,
        ece_subjects=ece_subjects,
        aiml_subjects=aiml_subjects,
    )


@app.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin.html")


@app.route("/admin/subjects", methods=["GET", "POST", "DELETE", "PUT"])
@admin_required
def admin_subjects():
    if request.method == "GET":
        subjects, ece_subjects, aiml_subjects = _get_subject_lists()
        return jsonify(
            {
                "subjects": subjects,
                "ece_subjects": ece_subjects,
                "aiml_subjects": aiml_subjects,
                "subject_codes": admin_config.get("subject_codes", {}),
                "stream_labels": admin_config.get("stream_labels", {}),
            }
        )

    payload = request.get_json(force=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        abort(400, description="'name' is required")

    category = (payload.get("category") or "general").lower()
    if category not in ("general", "ece", "aiml"):
        abort(400, description="'category' must be 'general', 'ece', or 'aiml'")

    if request.method == "POST":
        code = (payload.get("code") or "N/A").strip() or "N/A"
        _add_subject_entry(category, name, code)
        return (
            jsonify({"message": "Subject saved", "name": name, "code": code}),
            201,
        )

    if request.method == "PUT":
        original_name = (payload.get("original_name") or "").strip()
        code = (payload.get("code") or "N/A").strip() or "N/A"

        if not original_name:
            abort(400, description="Original name is required")

        _remove_subject_entry(original_name)
        admin_config.get("subject_codes", {}).pop(original_name, None)

        _add_subject_entry(category, name, code)

        return jsonify({"message": "Subject updated", "name": name, "code": code})

    removed = _remove_subject_entry(name)
    if not removed:
        abort(404, description="Subject not found")
    if payload.get("remove_code"):
        admin_config.get("subject_codes", {}).pop(name, None)
        save_admin_config(admin_config)
    return jsonify({"message": "Subject removed", "name": name})


@app.route("/admin/streams", methods=["POST", "DELETE"])
@admin_required
def admin_streams():
    payload = request.get_json(force=True) or {}
    stream_id = str(payload.get("id") or "").strip()

    if not stream_id:
        abort(400, description="'id' is required")

    if request.method == "POST":
        label = (payload.get("label") or "").strip()
        if not label:
            abort(400, description="'label' is required")

        admin_config.setdefault("stream_labels", {})[stream_id] = label
        save_admin_config(admin_config)
        return jsonify(
            {"message": "Stream label saved", "id": stream_id, "label": label}
        ), 201

    if request.method == "DELETE":
        labels = admin_config.get("stream_labels", {})
        if stream_id in labels:
            del labels[stream_id]
            save_admin_config(admin_config)
            return jsonify({"message": "Stream label removed", "id": stream_id})
        abort(404, description="Stream ID not found")


@app.route("/admin/config", methods=["GET"])
@admin_required
def admin_config_snapshot():
    return jsonify(admin_config)


@app.route("/admin/logs", methods=["GET"])
@admin_required
def admin_logs():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        abort(400, description="limit must be an integer")
    limit = max(1, min(MAX_LOG_RETURN, limit))
    return jsonify({"logs": read_frontpage_logs(limit)})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    count = count_frontpage_logs()
    return jsonify({"generated_count": count})


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=PORT, debug=debug_mode)
