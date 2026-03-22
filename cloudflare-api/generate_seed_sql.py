import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "admin_config.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "seed.generated.sql"


def sql_text(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def ordinal_text(value: int) -> str:
    suffix = "th"
    if value % 100 not in {11, 12, 13}:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def main() -> None:
    data = json.loads(CONFIG_PATH.read_text())
    subject_codes = data.get("subject_codes", {})
    stream_labels = data.get("stream_labels", {})

    subject_names = []
    seen = set()
    for key in ("subjects", "ece_subjects", "aiml_subjects"):
        for subject_name in data.get(key, []):
            if subject_name in seen:
                continue
            seen.add(subject_name)
            subject_names.append(subject_name)

    lines = [
        "-- Generated from admin_config.json",
        "BEGIN TRANSACTION;",
        "DELETE FROM subject_offerings;",
        "DELETE FROM subjects;",
        "DELETE FROM streams;",
        "DELETE FROM generation_logs;",
        "DELETE FROM semesters;",
        "",
        "INSERT INTO semesters (id, label, order_index) VALUES",
    ]

    semester_rows = []
    for idx in range(1, 9):
        semester_rows.append(f"  ({idx}, {sql_text(ordinal_text(idx))}, {idx})")
    lines.append(",\n".join(semester_rows) + ";")
    lines.append("")

    lines.append("INSERT INTO streams (id, name, short_code) VALUES")
    stream_rows = []
    for raw_id, label in sorted(stream_labels.items(), key=lambda item: int(item[0])):
        short_code = str(label).upper().replace(" ", "_")
        stream_rows.append(
            f"  ({int(raw_id)}, {sql_text(label)}, {sql_text(short_code)})"
        )
    lines.append(",\n".join(stream_rows) + ";")
    lines.append("")

    lines.append("INSERT INTO subjects (id, name, code) VALUES")
    subject_rows = []
    for idx, subject_name in enumerate(subject_names, start=1):
        code = subject_codes.get(subject_name, "N/A") or "N/A"
        subject_rows.append(
            f"  ({idx}, {sql_text(subject_name)}, {sql_text(code)})"
        )
    lines.append(",\n".join(subject_rows) + ";")
    lines.append("")

    lines.append("INSERT INTO subject_offerings (subject_id, semester_id) VALUES")
    offering_rows = [
        f"  ({idx}, 1)" for idx in range(1, len(subject_names) + 1)
    ]
    lines.append(",\n".join(offering_rows) + ";")
    lines.append("")
    lines.append("COMMIT;")
    lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
