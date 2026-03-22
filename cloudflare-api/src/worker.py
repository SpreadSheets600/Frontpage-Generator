import html
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint, env, fetch


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
        "Access-Control-Allow-Headers": "Content-Type",
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


def sanitize_text(value):
    return html.escape(str(value or "").strip())


def require_fields(payload, names):
    missing = [name for name in names if not str(payload.get(name, "")).strip()]
    return missing


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


def render_frontpage_html(payload, env):
    template_url = env_value(env, "PUBLIC_TEMPLATE_URL", "")
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

    row_markup = "\n".join(
        f'<div class="line line-{index}">{value}</div>'
        for index, value in enumerate(rows)
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

    html, body {{
      margin: 0;
      padding: 0;
      background: white;
      font-family: "FrontpageSans", Arial, sans-serif;
    }}

    .page {{
      position: relative;
      width: 1414px;
      height: 2000px;
      overflow: hidden;
    }}

    .background {{
      position: absolute;
      left: 0;
      top: 0;
      width: 1414px;
      height: 2000px;
    }}

    .line {{
      position: absolute;
      left: 530px;
      color: #000;
      font-size: 45px;
      line-height: 1;
      white-space: nowrap;
    }}

    .line-0 {{ top: 1060px; }}
    .line-1 {{ top: 1147px; }}
    .line-2 {{ top: 1234px; }}
    .line-3 {{ top: 1321px; }}
    .line-4 {{ top: 1408px; }}
    .line-5 {{ top: 1495px; }}
    .line-6 {{ top: 1582px; }}

    .line-6 {{
      max-width: 760px;
      white-space: normal;
    }}
  </style>
</head>
<body>
  <div class="page">
    <img class="background" src="{template_url}" alt="" />
    {row_markup}
  </div>
</body>
</html>
"""


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = path_for(request)
        method = request.method.upper()

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
            offerings_result = await self.env.DB.prepare(
                """
                SELECT
                  off.id AS offering_id,
                  off.semester_id AS semester_id,
                  sub.id AS subject_id,
                  sub.name AS subject_name,
                  sub.code AS subject_code
                FROM subject_offerings off
                JOIN subjects sub ON sub.id = off.subject_id
                ORDER BY off.semester_id, sub.name
                """
            ).all()

            semesters = [row_to_dict(row) for row in (semesters_result.results or [])]
            streams = [row_to_dict(row) for row in (streams_result.results or [])]
            offerings = [row_to_dict(row) for row in (offerings_result.results or [])]

            catalog = []
            for semester in semesters:
                semester_id = semester["id"]
                semester_subjects = []
                for offering in offerings:
                    if offering["semester_id"] != semester_id:
                        continue
                    semester_subjects.append(
                        {
                            "offering_id": offering["offering_id"],
                            "subject_id": offering["subject_id"],
                            "name": offering["subject_name"],
                            "code": offering["subject_code"],
                        }
                    )
                catalog.append(
                    {
                        "semester": {"id": semester_id, "label": semester["label"]},
                        "subjects": semester_subjects,
                    }
                )

            return with_cors(
                self.env,
                json_response({"catalog": catalog, "streams": streams}),
            )

        if path == "/api/generate-pdf" and method == "POST":
            payload = await request.json()
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
                template_url = env_value(self.env, "PUBLIC_TEMPLATE_URL", "")

                if not browser_account_id or not browser_token:
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "Browser Rendering credentials are not configured."},
                            status=500,
                        ),
                    )

                if not template_url:
                    return with_cors(
                        self.env,
                        json_response(
                            {"error": "PUBLIC_TEMPLATE_URL is not configured."},
                            status=500,
                        ),
                    )

                wants_pdf = bool(payload.get("as_pdf", True))
                endpoint = "pdf" if wants_pdf else "screenshot"
                request_body = {"html": html_document}
                if wants_pdf:
                    request_body["pdfOptions"] = {
                        "width": "1414px",
                        "height": "2000px",
                        "margin": {"top": "0", "right": "0", "bottom": "0", "left": "0"},
                        "printBackground": True,
                    }
                else:
                    request_body["viewport"] = {
                        "width": 1414,
                        "height": 2000,
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
                    return with_cors(
                        self.env,
                        json_response(
                            {
                                "error": "Browser Rendering PDF request failed.",
                                "details": error_text,
                            },
                            status=502,
                        ),
                    )

                created_at = datetime.now(timezone.utc).isoformat()
                await (
                    self.env.DB.prepare(
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

        return with_cors(
            self.env,
            json_response({"error": "Not found", "path": path}, status=404),
        )
