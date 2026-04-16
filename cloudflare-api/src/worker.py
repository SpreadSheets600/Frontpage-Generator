import html
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from workers import Response, WorkerEntrypoint, fetch


def json_response(data, status=200, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return Response(json.dumps(data), status=status, headers=headers)


def allowed_origin(env):
    return env_value(env, "ALLOWED_ORIGIN", "*") or "*"


def cors_headers(env):
    return {
        "Access-Control-Allow-Origin": allowed_origin(env),
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Admin-Key",
    }


def with_cors(env, response):
    merged_headers = {}
    existing_headers = getattr(response, "headers", None)
    if existing_headers:
        if hasattr(existing_headers, "entries"):
            for key, value in existing_headers.entries():
                merged_headers[str(key)] = str(value)
        else:
            merged_headers.update(dict(existing_headers))
    merged_headers.update(cors_headers(env))
    return Response(
        response.body,
        status=getattr(response, "status", 200),
        headers=merged_headers,
    )


def path_for(request):
    return urlparse(request.url).path.rstrip("/") or "/"


def query_params(request):
    parsed = urlparse(request.url)
    return parse_qs(parsed.query or "")


def sanitize_text(value):
    return html.escape(str(value or "").strip())


def plain_text(value):
    return str(value or "").strip()


def word_count(value):
    return len(str(value or "").strip().split())


def require_fields(payload, names):
    missing = [name for name in names if not str(payload.get(name, "")).strip()]
    return missing


def is_gmail_address(email):
    if not email:
        return False
    email_lower = str(email).strip().lower()
    return email_lower.endswith("@gmail.com") and email_lower.count("@") == 1


def env_value(env, name, default=""):
    value = getattr(env, name, None)
    if value not in (None, ""):
        return value
    try:
        value = env[name]
        if value not in (None, ""):
            return value
    except Exception:
        pass
    getter = getattr(env, "get", None)
    if callable(getter):
        try:
            value = getter(name)
            if value not in (None, ""):
                return value
        except Exception:
            pass
    global_value = getattr(globals().get("env"), name, None)
    if global_value not in (None, ""):
        return global_value
    return default


def local_render_mode(env):
    return str(env_value(env, "LOCAL_RENDER_MODE", "") or "").strip().lower()


def row_to_dict(row):
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if hasattr(row, "to_py"):
        converted = row.to_py()
        if isinstance(converted, dict):
            return converted
    if hasattr(row, "object_entries"):
        return dict(row.object_entries())
    return {}


async def response_bytes(response):
    array_buffer = getattr(response, "arrayBuffer", None)
    if callable(array_buffer):
        return await array_buffer()
    array_buffer = getattr(response, "array_buffer", None)
    if callable(array_buffer):
        return await array_buffer()
    text_method = getattr(response, "text", None)
    if callable(text_method):
        return (await text_method()).encode("utf-8")
    raise TypeError("Unsupported response body reader")


def normalized_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def request_header_value(request, name):
    headers = getattr(request, "headers", None)
    if not headers:
        return ""
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value not in (None, ""):
            return str(value)
    try:
        value = headers[name]
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass
    return ""


def admin_key_from_request(request):
    header_value = request_header_value(request, "X-Admin-Key")
    if header_value:
        return header_value.strip()
    params = query_params(request)
    query_value = (params.get("admin_key") or [""])[0]
    return str(query_value).strip()


def is_admin_authorized(worker_env, request):
    expected = str(env_value(worker_env, "ADMIN_API_KEY", "") or "").strip()
    if not expected:
        return False, "Admin API key not configured"
    if admin_key_from_request(request) != expected:
        return False, "Invalid admin credentials"
    return True, ""


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp_text(value, limit):
    text = plain_text(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)].rstrip() + "…"


def normalize_feedback_text(value, limit):
    lines = [line.strip() for line in plain_text(value).splitlines()]
    text = "\n".join(line for line in lines if line)
    return clamp_text(text.replace("@", "@\u200b"), limit)


async def parse_json_payload(request):
    try:
        payload = await request.json()
    except Exception:
        return None, json_response({"error": "Invalid JSON payload"}, status=400)
    if not isinstance(payload, dict):
        return None, json_response({"error": "JSON body must be an object"}, status=400)
    return payload, None


async def send_feedback_to_discord(env, payload):
    webhook_url = plain_text(env_value(env, "DISCORD_FEEDBACK_WEBHOOK_URL", ""))
    if not webhook_url:
        raise ValueError("Feedback webhook is not configured.")

    name = normalize_feedback_text(payload.get("name"), 120) or "Anonymous"
    contact = normalize_feedback_text(payload.get("contact"), 180) or "Not provided"
    topic = normalize_feedback_text(payload.get("topic"), 120) or "General"
    message = normalize_feedback_text(payload.get("message"), 4000)
    source_page = normalize_feedback_text(payload.get("page"), 200) or "/feedback/"

    discord_payload = {
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": "New Frontpage Feedback",
                "color": 3903746,
                "description": message,
                "fields": [
                    {"name": "Name", "value": name, "inline": True},
                    {"name": "Contact", "value": contact, "inline": True},
                    {"name": "Topic", "value": topic, "inline": True},
                    {"name": "Source", "value": source_page, "inline": False},
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    response = await fetch(
        webhook_url,
        method="POST",
        headers={"Content-Type": "application/json"},
        body=json.dumps(discord_payload),
    )
    if not response.ok:
        details = await response.text()
        raise RuntimeError(details or "Discord webhook request failed.")


async def log_generation(env, payload):
    created_at = datetime.now(timezone.utc).isoformat()
    await (
        env.DB.prepare(
            """
        INSERT INTO generation_logs (
          created_at,
          student_name,
          roll,
          registration,
          subject_name,
          subject_code,
          stream_label,
          semester_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        )
        .bind(
            created_at,
            str(payload["name"]).strip(),
            str(payload["roll"]).strip(),
            str(payload["reg"]).strip(),
            str(payload["subject_name"]).strip(),
            str(payload["subject_code"]).strip(),
            str(payload["stream_label"]).strip(),
            str(payload["semester_label"]).strip(),
        )
        .run()
    )


def render_frontpage_html(payload, env):
    font_url = env_value(env, "PUBLIC_FONT_URL", "")

    font_face = ""
    if font_url:
        font_face = f"""
        @font-face {{
          font-family: "FrontpageSans";
          src: url("{font_url}") format("truetype");
        }}
        """

    subject_name = sanitize_text(payload["subject_name"])
    subject_code = sanitize_text(payload["subject_code"])
    rows = [
        sanitize_text(payload["name"]),
        sanitize_text(payload["roll"]),
        sanitize_text(payload["reg"]),
        sanitize_text(payload["stream_label"]),
        sanitize_text(payload["semester_label"]),
        subject_code,
        subject_name,
    ]

    table_rows = [
        ("Name", rows[0]),
        ("Roll No.", rows[1]),
        ("Registration No.", rows[2]),
        ("Stream", rows[3]),
        ("Semester", rows[4]),
        ("Paper Code", rows[5]),
        ("Paper Name", rows[6]),
    ]
    paper_name_compact_class = (
        " value-cell--compact" if word_count(payload["subject_name"]) > 3 else ""
    )
    row_markup = "\n".join(
        f"""
        <div class="info-row">
          <div class="label-cell">{label}</div>
          <div class="value-cell{" value-cell--paper-name" + paper_name_compact_class if label == "Paper Name" else ""}">{value}</div>
        </div>
        """
        for label, value in table_rows
    )

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    {font_face}

    * {{
      box-sizing: border-box;
    }}

    @page {{
      size: A4 portrait;
      margin: 0;
    }}

    html, body {{
      margin: 0;
      padding: 0;
      background: white;
      font-family: "FrontpageSans", Arial, sans-serif;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}

    .page {{
      position: relative;
      width: 210mm;
      height: 297mm;
      overflow: hidden;
      padding: 6mm;
    }}

    .sheet {{
      position: relative;
      width: 100%;
      height: 100%;
      border: 1.2mm solid #2f2f2f;
      border-radius: 1.2mm;
      padding: 10mm 8mm 8mm;
      color: #111;
      background: #fff;
    }}

    .header {{
      text-align: center;
    }}

    .title {{
      font-size: 16pt;
      font-weight: 700;
      margin: 0;
    }}

    .subtitle {{
      margin: 1mm 0 0;
      font-size: 8.5pt;
      font-weight: 600;
    }}

    .affiliation {{
      margin: 5mm 0 0;
      font-size: 8.8pt;
    }}

    .college-code {{
      margin: 2mm 0 0;
      font-size: 11pt;
      font-weight: 700;
    }}

    .logos {{
      margin: 12mm auto 0;
      width: 92mm;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .logo-box {{
      width: 38mm;
      height: 30mm;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 0.4mm solid #d9d9d9;
      color: #1c1c1c;
      font-size: 15pt;
      font-weight: 700;
      background: #fff;
    }}

    .report-title {{
      margin: 16mm 0 10mm;
      text-align: center;
      font-size: 15pt;
      font-weight: 700;
      text-decoration: underline;
    }}

    .table {{
      width: 183mm;
      margin: 0 auto;
      border: 0.45mm solid #2f2f2f;
    }}

    .info-row {{
      display: grid;
      grid-template-columns: 31% 69%;
      min-height: 12.6mm;
      border-bottom: 0.35mm solid #2f2f2f;
    }}

    .info-row:last-child {{
      border-bottom: 0;
      min-height: 17.5mm;
    }}

    .label-cell,
    .value-cell {{
      display: flex;
      align-items: center;
      padding: 0 3mm;
      font-size: 8.8pt;
      font-weight: 700;
    }}

    .label-cell {{
      border-right: 0.35mm solid #2f2f2f;
    }}

    .value-cell {{
      font-weight: 500;
      white-space: normal;
      overflow-wrap: anywhere;
    }}

    .value-cell--paper-name {{
      line-height: 1.2;
    }}

    .value-cell--paper-name.value-cell--compact {{
      font-size: 8pt;
    }}

    .footer {{
      position: absolute;
      left: 0;
      right: 0;
      bottom: 4.5mm;
      text-align: center;
      font-size: 7.2pt;
      color: #333;
      line-height: 1.25;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="sheet">
      <div class="header">
        <h1 class="title">Techno Bengal Institute of Technology</h1>
        <p class="subtitle">( Formerly known as Bengal Institute of Technology )</p>
        <p class="affiliation">Affiliated to Maulana Abul KalamAzad University of Technology</p>
        <p class="college-code">College Code : 121</p>
      </div>

      <div class="logos">
        <div class="logo-box">BiT</div>
        <div class="logo-box">Utech</div>
      </div>

      <div class="report-title">Lab Report</div>

      <div class="table">
        {row_markup}
      </div>

      <div class="footer">
        Techno Bengal Institute of Technology, Tech Town, on Basanti Highway, No. 1 Govt. Colony,<br />
        Kolkata-700150, West Bengal, India.
      </div>
    </div>
  </div>
</body>
</html>
"""


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = path_for(request)
        method = request.method.upper()
        if method == "HEAD":
            method = "GET"

        if method == "OPTIONS":
            return with_cors(self.env, Response("", status=204))

        if path == "/api/health" and method == "GET":
            return with_cors(self.env, json_response({"ok": True}))

        if path == "/api/stats" and method == "GET":
            row = await self.env.DB.prepare(
                "SELECT COUNT(*) AS count FROM generation_logs"
            ).first()
            row_data = row_to_dict(row)
            count = row_data.get("count", 0) or 0
            return with_cors(self.env, json_response({"generated_count": count}))

        if path == "/api/catalog" and method == "GET":
            semesters_result = await self.env.DB.prepare(
                "SELECT id, label, order_index FROM semesters ORDER BY order_index"
            ).all()
            streams_result = await self.env.DB.prepare(
                "SELECT id, name, short_code FROM streams ORDER BY name"
            ).all()
            subjects_result = await self.env.DB.prepare(
                "SELECT id, name, code FROM subjects ORDER BY name"
            ).all()

            semesters = [row_to_dict(row) for row in (semesters_result.results or [])]
            streams = [row_to_dict(row) for row in (streams_result.results or [])]
            subjects = [row_to_dict(row) for row in (subjects_result.results or [])]

            return with_cors(
                self.env,
                json_response(
                    {"semesters": semesters, "streams": streams, "subjects": subjects}
                ),
            )

        if path == "/api/generate-pdf" and method == "POST":
            payload, parse_error = await parse_json_payload(request)
            if parse_error:
                return with_cors(self.env, parse_error)
            required_fields = [
                "name",
                "roll",
                "reg",
                "stream_label",
                "semester_label",
                "subject_name",
                "subject_code",
            ]
            missing = require_fields(payload, required_fields)
            if missing:
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "Missing required fields",
                            "fields": missing,
                        },
                        status=400,
                    ),
                )

            try:
                html_document = render_frontpage_html(payload, self.env)
                if local_render_mode(self.env) == "html":
                    filename = f"{str(payload['name']).strip()}-{str(payload['subject_name']).strip()}-FrontPagePreview.html"
                    response = Response(
                        html_document,
                        headers={
                            "Content-Type": "text/html; charset=utf-8",
                            "Content-Disposition": f'inline; filename="{filename}"',
                        },
                    )
                    return with_cors(self.env, response)

                browser_account_id = env_value(self.env, "CLOUDFLARE_ACCOUNT_ID", "")
                browser_token = env_value(self.env, "BROWSER_RENDERING_API_TOKEN", "")

                if not browser_account_id or not browser_token:
                    return with_cors(
                        self.env,
                        json_response(
                            {
                                "error": "Browser Rendering credentials are not configured."
                            },
                            status=500,
                        ),
                    )

                wants_pdf = normalized_bool(payload.get("as_pdf"), default=True)
                endpoint = "pdf" if wants_pdf else "screenshot"
                request_body = {"html": html_document}
                if wants_pdf:
                    request_body["pdfOptions"] = {
                        "margin": {
                            "top": "0",
                            "right": "0",
                            "bottom": "0",
                            "left": "0",
                        },
                        "printBackground": True,
                    }
                else:
                    request_body["viewport"] = {
                        "width": 794,
                        "height": 1123,
                        "deviceScaleFactor": 1,
                    }
                    request_body["screenshotOptions"] = {
                        "type": "png",
                        "fullPage": False,
                    }

                browser_response = await fetch(
                    f"https://api.cloudflare.com/client/v4/accounts/{browser_account_id}/browser-rendering/{endpoint}",
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {browser_token}",
                        "Content-Type": "application/json",
                    },
                    body=json.dumps(request_body),
                )

                if not browser_response.ok:
                    error_text = await browser_response.text()
                    error_status = getattr(browser_response, "status", 502)
                    error_message = "Browser Rendering PDF request failed."
                    if (
                        error_status == 429
                        or "rate limit exceeded" in error_text.lower()
                    ):
                        error_status = 429
                        error_message = (
                            "Cloudflare Browser Rendering rate limit exceeded."
                        )
                    return with_cors(
                        self.env,
                        json_response(
                            {
                                "error": error_message,
                                "details": error_text,
                            },
                            status=error_status,
                        ),
                    )

                await log_generation(self.env, payload)

                document_bytes = await response_bytes(browser_response)
                download_ext = "pdf" if wants_pdf else "png"
                content_type = "application/pdf" if wants_pdf else "image/png"
                safe_subject = str(payload["subject_name"]).strip().replace(" ", "-")
                filename = f"{str(payload['name']).strip()}-{safe_subject}-FrontPageCover.{download_ext}"
                response = Response(
                    document_bytes,
                    headers={
                        "Content-Type": content_type,
                        "Content-Disposition": f'attachment; filename="{filename}"',
                    },
                )
                return with_cors(self.env, response)
            except Exception as error:
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "PDF generation failed unexpectedly.",
                            "details": str(error),
                        },
                        status=502,
                    ),
                )

        if path == "/api/log-generation" and method == "POST":
            payload, parse_error = await parse_json_payload(request)
            if parse_error:
                return with_cors(self.env, parse_error)
            required_fields = [
                "name",
                "roll",
                "reg",
                "stream_label",
                "semester_label",
                "subject_name",
                "subject_code",
            ]
            missing = require_fields(payload, required_fields)
            if missing:
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "Missing required fields",
                            "fields": missing,
                        },
                        status=400,
                    ),
                )

            try:
                await log_generation(self.env, payload)
                return with_cors(self.env, json_response({"ok": True}, status=201))
            except Exception as error:
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "Could not log generation.",
                            "details": str(error),
                        },
                        status=500,
                    ),
                )

        if path == "/api/feedback" and method == "POST":
            payload, parse_error = await parse_json_payload(request)
            if parse_error:
                return with_cors(self.env, parse_error)
            required_fields = ["name", "topic", "message"]
            missing = require_fields(payload, required_fields)
            if missing:
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "Missing required fields",
                            "fields": missing,
                        },
                        status=400,
                    ),
                )

            contact = str(payload.get("contact", "")).strip()
            if contact and not is_gmail_address(contact):
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "Contact must be a valid Gmail address",
                        },
                        status=400,
                    ),
                )

            try:
                await send_feedback_to_discord(self.env, payload)
                return with_cors(
                    self.env,
                    json_response({"ok": True, "message": "Feedback sent"}, status=201),
                )
            except ValueError as error:
                return with_cors(
                    self.env,
                    json_response({"error": str(error)}, status=500),
                )
            except Exception as error:
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "error": "Could not send feedback.",
                            "details": str(error),
                        },
                        status=502,
                    ),
                )

        if path == "/admin/subjects":
            allowed, reason = is_admin_authorized(self.env, request)
            if not allowed:
                return with_cors(self.env, json_response({"error": reason}, status=401))

            if method == "GET":
                semesters_result = await self.env.DB.prepare(
                    "SELECT id, label, order_index FROM semesters ORDER BY order_index"
                ).all()
                streams_result = await self.env.DB.prepare(
                    "SELECT id, name, short_code FROM streams ORDER BY name"
                ).all()
                subjects_result = await self.env.DB.prepare(
                    "SELECT id, name, code FROM subjects ORDER BY name"
                ).all()

                semesters = [
                    row_to_dict(row) for row in (semesters_result.results or [])
                ]
                streams = [row_to_dict(row) for row in (streams_result.results or [])]
                subjects = [row_to_dict(row) for row in (subjects_result.results or [])]

                return with_cors(
                    self.env,
                    json_response(
                        {
                            "semesters": semesters,
                            "streams": streams,
                            "subjects": subjects,
                        }
                    ),
                )

            if method in {"POST", "PUT", "DELETE"}:
                payload, parse_error = await parse_json_payload(request)
                if parse_error:
                    return with_cors(self.env, parse_error)

            if method == "POST":
                subject_name = str(payload.get("name", "") or "").strip()
                code = str(payload.get("code", "N/A") or "N/A").strip() or "N/A"
                semester_id = parse_int(payload.get("semester_id"))

                if not subject_name:
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "Subject name is required"}, status=400
                        ),
                    )
                if not semester_id:
                    return with_cors(
                        self.env,
                        json_response({"error": "semester_id is required"}, status=400),
                    )

                subject_row = (
                    await self.env.DB.prepare(
                        "SELECT id FROM subjects WHERE lower(name) = lower(?)"
                    )
                    .bind(subject_name)
                    .first()
                )
                subject = row_to_dict(subject_row)
                subject_id = subject.get("id")

                if subject_id:
                    await (
                        self.env.DB.prepare(
                            "UPDATE subjects SET name = ?, code = ? WHERE id = ?"
                        )
                        .bind(subject_name, code, subject_id)
                        .run()
                    )
                else:
                    await (
                        self.env.DB.prepare(
                            "INSERT INTO subjects (name, code) VALUES (?, ?)"
                        )
                        .bind(subject_name, code)
                        .run()
                    )
                    created_row = (
                        await self.env.DB.prepare(
                            "SELECT id FROM subjects WHERE lower(name) = lower(?)"
                        )
                        .bind(subject_name)
                        .first()
                    )
                    subject_id = row_to_dict(created_row).get("id")

                offering_row = (
                    await self.env.DB.prepare(
                        "SELECT id FROM subject_offerings WHERE subject_id = ? AND semester_id = ?"
                    )
                    .bind(subject_id, semester_id)
                    .first()
                )
                offering = row_to_dict(offering_row)

                if offering.get("id"):
                    offering_id = offering["id"]
                else:
                    await (
                        self.env.DB.prepare(
                            "INSERT INTO subject_offerings (subject_id, semester_id) VALUES (?, ?)"
                        )
                        .bind(subject_id, semester_id)
                        .run()
                    )
                    offering_created = (
                        await self.env.DB.prepare(
                            "SELECT id FROM subject_offerings WHERE subject_id = ? AND semester_id = ?"
                        )
                        .bind(subject_id, semester_id)
                        .first()
                    )
                    offering_id = row_to_dict(offering_created).get("id")

                return with_cors(
                    self.env,
                    json_response(
                        {"message": "Subject saved", "offering_id": offering_id},
                        status=201,
                    ),
                )

            if method == "PUT":
                offering_id = parse_int(payload.get("offering_id"))
                subject_name = str(payload.get("name", "") or "").strip()
                code = str(payload.get("code", "N/A") or "N/A").strip() or "N/A"
                semester_id = parse_int(payload.get("semester_id"))

                if not offering_id:
                    return with_cors(
                        self.env,
                        json_response({"error": "offering_id is required"}, status=400),
                    )
                if not subject_name:
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "Subject name is required"}, status=400
                        ),
                    )
                if not semester_id:
                    return with_cors(
                        self.env,
                        json_response({"error": "semester_id is required"}, status=400),
                    )

                current_row = (
                    await self.env.DB.prepare(
                        """
                    SELECT off.id AS offering_id, off.subject_id AS subject_id
                    FROM subject_offerings off
                    WHERE off.id = ?
                    """
                    )
                    .bind(offering_id)
                    .first()
                )
                current = row_to_dict(current_row)
                if not current:
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "Subject offering not found"}, status=404
                        ),
                    )

                duplicate_row = (
                    await self.env.DB.prepare(
                        "SELECT id FROM subjects WHERE lower(name) = lower(?) AND id != ?"
                    )
                    .bind(subject_name, current["subject_id"])
                    .first()
                )
                if row_to_dict(duplicate_row):
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "Another subject with that name exists"},
                            status=400,
                        ),
                    )

                try:
                    await (
                        self.env.DB.prepare(
                            "UPDATE subjects SET name = ?, code = ? WHERE id = ?"
                        )
                        .bind(subject_name, code, current["subject_id"])
                        .run()
                    )
                    await (
                        self.env.DB.prepare(
                            "UPDATE subject_offerings SET semester_id = ? WHERE id = ?"
                        )
                        .bind(semester_id, offering_id)
                        .run()
                    )
                except Exception as error:
                    return with_cors(
                        self.env,
                        json_response(
                            {
                                "error": "Could not update subject offering",
                                "details": str(error),
                            },
                            status=400,
                        ),
                    )

                return with_cors(
                    self.env,
                    json_response({"message": "Subject updated"}),
                )

            if method == "DELETE":
                offering_id = parse_int(payload.get("offering_id"))
                if not offering_id:
                    return with_cors(
                        self.env,
                        json_response({"error": "offering_id is required"}, status=400),
                    )

                offering_row = (
                    await self.env.DB.prepare(
                        "SELECT id, subject_id FROM subject_offerings WHERE id = ?"
                    )
                    .bind(offering_id)
                    .first()
                )
                offering = row_to_dict(offering_row)
                if not offering:
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "Subject offering not found"}, status=404
                        ),
                    )

                await (
                    self.env.DB.prepare("DELETE FROM subject_offerings WHERE id = ?")
                    .bind(offering_id)
                    .run()
                )
                left_row = (
                    await self.env.DB.prepare(
                        "SELECT COUNT(*) AS count FROM subject_offerings WHERE subject_id = ?"
                    )
                    .bind(offering["subject_id"])
                    .first()
                )
                left_count = (
                    parse_int(row_to_dict(left_row).get("count"), default=0) or 0
                )
                if left_count == 0:
                    await (
                        self.env.DB.prepare("DELETE FROM subjects WHERE id = ?")
                        .bind(offering["subject_id"])
                        .run()
                    )

                return with_cors(
                    self.env,
                    json_response({"message": "Subject removed"}),
                )

            return with_cors(
                self.env,
                json_response({"error": "Method not allowed"}, status=405),
            )

        if path == "/admin/streams":
            allowed, reason = is_admin_authorized(self.env, request)
            if not allowed:
                return with_cors(self.env, json_response({"error": reason}, status=401))

            if method in {"POST", "DELETE"}:
                payload, parse_error = await parse_json_payload(request)
                if parse_error:
                    return with_cors(self.env, parse_error)

            if method == "POST":
                name = str(payload.get("label") or payload.get("name") or "").strip()
                if not name:
                    return with_cors(
                        self.env,
                        json_response({"error": "label is required"}, status=400),
                    )
                short_code = (
                    str(payload.get("short_code") or name)
                    .strip()
                    .upper()
                    .replace(" ", "_")
                )

                try:
                    await (
                        self.env.DB.prepare(
                            "INSERT INTO streams (name, short_code) VALUES (?, ?)"
                        )
                        .bind(name, short_code)
                        .run()
                    )
                except Exception as error:
                    return with_cors(
                        self.env,
                        json_response(
                            {
                                "error": "Could not create stream",
                                "details": str(error),
                            },
                            status=400,
                        ),
                    )

                created = (
                    await self.env.DB.prepare(
                        "SELECT id FROM streams WHERE lower(name) = lower(?)"
                    )
                    .bind(name)
                    .first()
                )
                return with_cors(
                    self.env,
                    json_response(
                        {
                            "message": "Stream created",
                            "id": row_to_dict(created).get("id"),
                        },
                        status=201,
                    ),
                )

            if method == "DELETE":
                stream_id = parse_int(payload.get("id"))
                if not stream_id:
                    return with_cors(
                        self.env,
                        json_response({"error": "id is required"}, status=400),
                    )
                await (
                    self.env.DB.prepare("DELETE FROM streams WHERE id = ?")
                    .bind(stream_id)
                    .run()
                )
                return with_cors(
                    self.env,
                    json_response({"message": "Stream removed"}),
                )

            return with_cors(
                self.env,
                json_response({"error": "Method not allowed"}, status=405),
            )

        if path == "/admin/logs" and method == "GET":
            allowed, reason = is_admin_authorized(self.env, request)
            if not allowed:
                return with_cors(self.env, json_response({"error": reason}, status=401))

            params = query_params(request)
            limit = parse_int((params.get("limit") or [50])[0], default=50) or 50
            limit = max(1, min(200, limit))

            logs_result = (
                await self.env.DB.prepare(
                    """
                SELECT
                  created_at AS timestamp,
                  student_name AS name,
                  roll,
                  registration AS reg,
                  subject_name AS subject,
                  stream_label AS stream,
                  semester_label AS semester,
                  subject_code AS code
                FROM generation_logs
                ORDER BY created_at DESC
                LIMIT ?
                """
                )
                .bind(limit)
                .all()
            )
            logs = [row_to_dict(row) for row in (logs_result.results or [])]
            return with_cors(self.env, json_response({"logs": logs}))

        return with_cors(
            self.env,
            json_response({"error": "Not found", "path": path}, status=404),
        )
