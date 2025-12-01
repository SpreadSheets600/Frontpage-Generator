import io
import os
import json
from pathlib import Path
from functools import wraps
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    url_for,
    request,
    redirect,
    send_file,
    render_template,
)
from flask_sqlalchemy import SQLAlchemy
from PIL import Image, ImageDraw, ImageFont
from werkzeug.exceptions import HTTPException

load_dotenv()

app = Flask(__name__, template_folder="templates")

PORT = int(os.getenv("PORT", 5000))

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///frontpage.db")

CONFIG_PATH = Path(os.getenv("ADMIN_CONFIG_PATH", "admin_config.json"))

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

MAX_LOG_RETURN = 200


class Semester(db.Model):
    __tablename__ = "semesters"
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(32), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, unique=True)
    offerings = db.relationship(
        "SubjectOffering",
        back_populates="semester",
        cascade="all, delete-orphan",
    )


class Stream(db.Model):
    __tablename__ = "streams"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    short_code = db.Column(db.String(32), nullable=False, unique=True)
    logs = db.relationship("GenerationLog", back_populates="stream")


class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    code = db.Column(db.String(32), nullable=False)
    offerings = db.relationship(
        "SubjectOffering", back_populates="subject", cascade="all, delete-orphan"
    )
    logs = db.relationship("GenerationLog", back_populates="subject")


class SubjectOffering(db.Model):
    __tablename__ = "subject_offerings"
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=False)
    __table_args__ = (
        db.UniqueConstraint("subject_id", "semester_id", name="uq_subject_semester"),
    )

    subject = db.relationship("Subject", back_populates="offerings")
    semester = db.relationship("Semester", back_populates="offerings")


class GenerationLog(db.Model):
    __tablename__ = "generation_logs"
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    student_name = db.Column(db.String(120), nullable=False)
    roll = db.Column(db.String(64), nullable=False)
    registration = db.Column(db.String(64), nullable=False)
    subject_name = db.Column(db.String(120), nullable=False)
    subject_code = db.Column(db.String(32), nullable=False)
    stream_label = db.Column(db.String(64), nullable=False)
    semester_label = db.Column(db.String(32), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=True)
    stream_id = db.Column(db.Integer, db.ForeignKey("streams.id"), nullable=True)
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=True)

    subject = db.relationship("Subject", back_populates="logs")
    stream = db.relationship("Stream", back_populates="logs")
    semester = db.relationship("Semester")


@app.errorhandler(HTTPException)
def handle_exception(error):
    response = error.get_response()
    response.data = json.dumps(
        {
            "code": error.code,
            "name": error.name,
            "description": error.description,
        }
    )
    response.content_type = "application/json"
    return response


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


def ordinal_text(value: int) -> str:
    suffix = "th"
    if value % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def init_db() -> None:
    db.create_all()
    if Semester.query.count() == 0:
        for idx in range(1, 9):
            db.session.add(Semester(label=ordinal_text(idx), order_index=idx))

        db.session.commit()

    if Stream.query.count() == 0:
        defaults = {
            "1": "CSE",
            "2": "IT",
            "3": "ECE",
            "4": "CSE AIML",
        }
        if CONFIG_PATH.exists():
            try:
                payload = json.loads(CONFIG_PATH.read_text())
                defaults.update(payload.get("stream_labels", {}))

            except json.JSONDecodeError:
                pass

        for raw_id, label in defaults.items():
            try:
                stream_id = int(raw_id)

            except ValueError:
                stream_id = None

            short_code = label.upper().replace(" ", "_")
            stream = Stream(id=stream_id, name=label, short_code=short_code)
            db.session.add(stream)
        db.session.commit()

    if Subject.query.count() == 0 and CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())

        except json.JSONDecodeError:
            data = {}

        subject_codes = data.get("subject_codes", {})
        default_semester = Semester.query.filter_by(order_index=1).first()

        def seed_subject_list(names, semester):
            if not semester:
                return
            for label in names:
                code = subject_codes.get(label, "N/A") or "N/A"
                subject = Subject(name=label, code=code)

                db.session.add(subject)
                db.session.flush()

                if not SubjectOffering.query.filter_by(
                    subject_id=subject.id, semester_id=semester.id
                ).first():
                    db.session.add(
                        SubjectOffering(subject_id=subject.id, semester_id=semester.id)
                    )

        seed_subject_list(data.get("subjects", []), default_semester)
        seed_subject_list(data.get("ece_subjects", []), default_semester)
        seed_subject_list(data.get("aiml_subjects", []), default_semester)

        db.session.commit()


with app.app_context():
    init_db()


def serialize_catalog():
    catalog = []
    semesters = Semester.query.order_by(Semester.order_index).all()
    for semester in semesters:
        offerings = (
            SubjectOffering.query.filter_by(semester_id=semester.id)
            .join(Subject)
            .order_by(Subject.name)
            .all()
        )
        catalog.append(
            {
                "semester": {"id": semester.id, "label": semester.label},
                "subjects": [
                    {
                        "offering_id": offering.id,
                        "subject_id": offering.subject.id,
                        "name": offering.subject.name,
                        "code": offering.subject.code,
                    }
                    for offering in offerings
                ],
            }
        )
    return catalog


def count_frontpage_logs() -> int:
    return GenerationLog.query.count()


def read_frontpage_logs(limit: int) -> list:
    logs = (
        GenerationLog.query.order_by(GenerationLog.created_at.desc()).limit(limit).all()
    )
    results = []
    for log in logs:
        results.append(
            {
                "timestamp": log.created_at.isoformat(),
                "name": log.student_name,
                "roll": log.roll,
                "reg": log.registration,
                "subject": log.subject_name,
                "stream": log.stream_label,
                "semester": log.semester_label,
                "code": log.subject_code,
            }
        )
    return results


def log_frontpage_event(entry: dict) -> None:
    log = GenerationLog(**entry)
    db.session.add(log)
    db.session.commit()


@app.route("/")
def index():
    return redirect(url_for("generate_frontpage"))


@app.route("/frontpages", methods=["GET", "POST"])
def generate_frontpage():
    if request.method == "POST":
        name = request.form["name"].strip()
        roll = request.form["roll"].strip()
        reg = request.form["reg"].strip()
        semester_id = int(request.form["semester_id"])
        stream_id = int(request.form["stream_id"])
        subject_id = int(request.form["subject_id"])
        as_pdf = request.form.get("as_pdf") == "on"

        stream = Stream.query.get_or_404(stream_id)
        offering = SubjectOffering.query.filter_by(
            semester_id=semester_id, subject_id=subject_id
        ).first()
        if not offering:
            abort(400, description="Invalid subject selection for semester")

        subject = offering.subject
        semester = offering.semester

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
            (start_x, start_y + 3 * line_gap), stream.name, font=font, fill="black"
        )
        draw.text(
            (start_x, start_y + 4 * line_gap), semester.label, font=font, fill="black"
        )
        draw.text(
            (start_x, start_y + 5 * line_gap), subject.code, font=font, fill="black"
        )
        draw.text(
            (start_x, start_y + 6 * line_gap), subject.name, font=font, fill="black"
        )

        img_io = io.BytesIO()
        mimetype = "image/png"
        download_ext = "png"
        if as_pdf:
            pdf_ready = img.convert("RGB")
            pdf_ready.save(img_io, "PDF", resolution=100.0)
            mimetype = "application/pdf"
            download_ext = "pdf"
        else:
            img.save(img_io, "PNG")
        img_io.seek(0)

        log_frontpage_event(
            {
                "created_at": datetime.now(timezone.utc),
                "student_name": name,
                "roll": roll,
                "registration": reg,
                "subject_name": subject.name,
                "subject_code": subject.code,
                "stream_label": stream.name,
                "semester_label": semester.label,
                "subject_id": subject.id,
                "stream_id": stream.id,
                "semester_id": semester.id,
            }
        )

        safe_subject = subject.name.replace(" ", "-")
        download_name = f"{name}-{safe_subject}-FrontPageCover.{download_ext}"

        return send_file(
            img_io,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name,
        )

    catalog = serialize_catalog()
    semesters = [
        {"id": sem.id, "label": sem.label}
        for sem in Semester.query.order_by(Semester.order_index).all()
    ]
    streams = [
        {"id": stream.id, "name": stream.name}
        for stream in Stream.query.order_by(Stream.name).all()
    ]
    return render_template(
        "index.html", catalog=catalog, semesters=semesters, streams=streams
    )


@app.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin.html")


@app.route("/api/catalog", methods=["GET"])
def api_catalog():
    return jsonify({"catalog": serialize_catalog()})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify({"generated_count": count_frontpage_logs()})


@app.route("/admin/subjects", methods=["GET", "POST", "PUT", "DELETE"])
@admin_required
def admin_subjects():
    if request.method == "GET":
        response = {
            "catalog": serialize_catalog(),
            "streams": [
                {
                    "id": stream.id,
                    "name": stream.name,
                    "short_code": stream.short_code,
                }
                for stream in Stream.query.order_by(Stream.name).all()
            ],
            "semesters": [
                {"id": sem.id, "label": sem.label}
                for sem in Semester.query.order_by(Semester.order_index).all()
            ],
        }
        return jsonify(response)

    payload = request.get_json(force=True) or {}
    subject_name = (payload.get("name") or "").strip()
    code = (payload.get("code") or "N/A").strip() or "N/A"
    semester_id = payload.get("semester_id")
    if semester_id is not None:
        try:
            semester_id = int(semester_id)
        except (TypeError, ValueError):
            abort(400, description="semester_id must be an integer")

    if request.method in {"POST", "PUT"}:
        if not subject_name:
            abort(400, description="Subject name is required")
        if not semester_id:
            abort(400, description="semester_id is required")

    if request.method == "POST":
        subject = Subject.query.filter(
            db.func.lower(Subject.name) == subject_name.lower()
        ).first()
        if subject:
            subject.code = code
        else:
            subject = Subject(name=subject_name, code=code)
            db.session.add(subject)
            db.session.flush()

        offering = SubjectOffering.query.filter_by(
            subject_id=subject.id, semester_id=semester_id
        ).first()
        if not offering:
            offering = SubjectOffering(subject_id=subject.id, semester_id=semester_id)
            db.session.add(offering)
        db.session.commit()
        return (
            jsonify({"message": "Subject saved", "offering_id": offering.id}),
            201,
        )

    if request.method == "PUT":
        offering_id = payload.get("offering_id")
        if not offering_id:
            abort(400, description="offering_id is required")
        offering = SubjectOffering.query.get_or_404(offering_id)
        subject = offering.subject

        # Update subject details
        existing = Subject.query.filter(
            db.func.lower(Subject.name) == subject_name.lower(),
            Subject.id != subject.id,
        ).first()
        if existing:
            abort(400, description="Another subject with that name exists")

        subject.name = subject_name
        subject.code = code
        offering.semester_id = semester_id
        db.session.commit()
        return jsonify({"message": "Subject updated"})

    if request.method == "DELETE":
        offering_id = payload.get("offering_id")
        if not offering_id:
            abort(400, description="offering_id is required")
        offering = SubjectOffering.query.get_or_404(offering_id)
        subject = offering.subject
        db.session.delete(offering)
        db.session.flush()
        if not subject.offerings:
            db.session.delete(subject)
        db.session.commit()
        return jsonify({"message": "Subject removed"})


@app.route("/admin/streams", methods=["POST", "DELETE"])
@admin_required
def admin_streams():
    payload = request.get_json(force=True) or {}
    if request.method == "POST":
        name = (payload.get("label") or payload.get("name") or "").strip()
        if not name:
            abort(400, description="label is required")
        short_code = (payload.get("short_code") or name).upper().replace(" ", "_")
        stream = Stream(name=name, short_code=short_code)
        db.session.add(stream)
        db.session.commit()
        return jsonify({"message": "Stream created", "id": stream.id}), 201

    stream_id = payload.get("id")
    if not stream_id:
        abort(400, description="id is required")
    stream = Stream.query.get_or_404(stream_id)
    db.session.delete(stream)
    db.session.commit()
    return jsonify({"message": "Stream removed"})


@app.route("/admin/logs", methods=["GET"])
@admin_required
def admin_logs():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        abort(400, description="limit must be an integer")
    limit = max(1, min(MAX_LOG_RETURN, limit))
    return jsonify({"logs": read_frontpage_logs(limit)})


@app.route("/downloads/index-page", methods=["GET"])
def download_index_page():
    index_path = Path("static/index_page.pdf")
    if not index_path.exists():
        abort(404, description="Index page file is unavailable")
    return send_file(
        index_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="IndexPage.pdf",
    )


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=PORT, debug=debug_mode)
