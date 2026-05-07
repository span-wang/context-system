from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx


DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123456"


class RegressionError(RuntimeError):
    pass


@dataclass(slots=True)
class RegressionContext:
    api_base: str
    username: str
    password: str
    timeout: float
    token: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify question review write APIs through real HTTP.")
    parser.add_argument("--api-base", required=True, help="API base URL, for example http://127.0.0.1:8000")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    context = RegressionContext(
        api_base=args.api_base.rstrip("/"),
        username=args.username,
        password=args.password,
        timeout=args.timeout,
    )

    try:
        summary = run_regression(context)
    except Exception as exc:
        print(f"QUESTION_REVIEW_HTTP_REGRESSION_FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Question review HTTP regression passed.")
    return 0


def run_regression(context: RegressionContext) -> dict[str, Any]:
    with httpx.Client(timeout=context.timeout) as client:
        wait_for_health(client, context)
        context.token = login(client, context)
        headers = auth_headers(context)

        subject_id, point_payloads = choose_subject_and_points(client, context)
        marker = f"http-review-{int(time.time())}-{uuid4().hex[:8]}"
        paper_id = upload_paper(client, context, headers, subject_id, point_payloads, marker)
        parse_payload = parse_paper(client, context, headers, paper_id)
        if parse_payload.get("question_count", 0) < 2:
            raise RegressionError(f"expected parser to create at least 2 questions, got {parse_payload}")
        if parse_payload.get("tagged_count", 0) < 1:
            raise RegressionError(f"expected parser to create at least 1 knowledge candidate, got {parse_payload}")

        questions = request_json(client, "GET", f"{context.api_base}/platform/api/questions?paper_id={paper_id}")
        if len(questions) < 2:
            raise RegressionError(f"expected at least 2 questions for paper {paper_id}, got {len(questions)}")

        first_question_id = int(questions[0]["id"])
        second_question_id = int(questions[1]["id"])

        patch_note = f"{marker}-patch"
        patched = request_json(
            client,
            "PATCH",
            f"{context.api_base}/platform/api/questions/{first_question_id}",
            headers=headers,
            json={"review_status": "needs_revision", "review_note": patch_note},
        )
        assert_equal(patched.get("review_status"), "needs_revision", "patched review_status")
        assert_equal(patched.get("review_note"), patch_note, "patched review_note")

        batch_note = f"{marker}-batch"
        batch_payload = request_json(
            client,
            "POST",
            f"{context.api_base}/platform/api/questions/batch-review",
            headers=headers,
            json={
                "question_ids": [first_question_id, second_question_id],
                "review_status": "approved",
                "review_note": batch_note,
            },
        )
        assert_equal(batch_payload.get("updated_count"), 2, "batch-review updated_count")
        assert_equal(batch_payload.get("review_status"), "approved", "batch-review review_status")

        reviewed_questions = request_json(client, "GET", f"{context.api_base}/platform/api/questions?paper_id={paper_id}")
        reviewed_by_id = {int(item["id"]): item for item in reviewed_questions}
        for question_id in (first_question_id, second_question_id):
            question = reviewed_by_id.get(question_id)
            if not question:
                raise RegressionError(f"question {question_id} disappeared after batch-review")
            assert_equal(question.get("review_status"), "approved", f"question {question_id} review_status")
            assert_equal(question.get("review_note"), batch_note, f"question {question_id} review_note")

        first_detail = request_json(client, "GET", f"{context.api_base}/platform/api/questions/{first_question_id}")
        links = list(first_detail.get("links") or [])
        if not links:
            raise RegressionError(f"question {first_question_id} has no knowledge candidates")

        primary_link_id = int(links[0]["id"])
        reviewed_link = request_json(
            client,
            "POST",
            f"{context.api_base}/platform/api/questions/{first_question_id}/knowledge-links/review",
            headers=headers,
            json={
                "link_ids": [primary_link_id],
                "review_status": "approved",
                "primary_link_id": primary_link_id,
            },
        )
        assert_equal(reviewed_link.get("updated_count"), 1, "knowledge review updated_count")
        assert_equal(reviewed_link.get("review_status"), "approved", "knowledge review review_status")
        assert_equal(reviewed_link.get("primary_link_id"), primary_link_id, "knowledge review primary_link_id")

        detail_after_link_review = request_json(client, "GET", f"{context.api_base}/platform/api/questions/{first_question_id}")
        primary_after_review = find_link(detail_after_link_review, primary_link_id)
        assert_equal(primary_after_review.get("review_status"), "approved", "primary link review_status")
        assert_equal(primary_after_review.get("is_primary"), True, "primary link is_primary")

        retag_payload = request_json(
            client,
            "POST",
            f"{context.api_base}/platform/api/questions/{first_question_id}/retag",
            headers=headers,
        )
        assert_equal(retag_payload.get("question_id"), first_question_id, "retag question_id")
        if retag_payload.get("total_links", 0) < 1:
            raise RegressionError(f"retag should leave at least one link, got {retag_payload}")

        detail_after_retag = request_json(client, "GET", f"{context.api_base}/platform/api/questions/{first_question_id}")
        primary_after_retag = find_link(detail_after_retag, primary_link_id)
        assert_equal(primary_after_retag.get("review_status"), "approved", "approved link after retag")
        if not any(link.get("tag_source") == "rule_keyword" for link in detail_after_retag.get("links") or []):
            raise RegressionError("retag did not leave any rule_keyword link on the question")

        audit_actions = audit_actions_for_question(client, context, headers, first_question_id)
        missing_actions = {"update", "batch_review", "review_knowledge_links", "retag"} - audit_actions
        if missing_actions:
            raise RegressionError(f"missing audit log action(s): {sorted(missing_actions)}")

        return {
            "api_base": context.api_base,
            "paper_id": paper_id,
            "question_ids": [first_question_id, second_question_id],
            "primary_link_id": primary_link_id,
            "parse": {
                "question_count": parse_payload.get("question_count"),
                "tagged_count": parse_payload.get("tagged_count"),
                "provider": parse_payload.get("provider"),
            },
            "batch_review": batch_payload,
            "knowledge_review": reviewed_link,
            "retag": retag_payload,
            "audit_actions": sorted(audit_actions),
        }


def wait_for_health(client: httpx.Client, context: RegressionContext) -> None:
    deadline = time.monotonic() + context.timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{context.api_base}/api/system/healthz")
            if response.status_code < 500:
                return
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as exc:  # noqa: BLE001 - include final connection error in regression output.
            last_error = str(exc)
        time.sleep(0.5)
    raise RegressionError(f"API did not become healthy at {context.api_base}: {last_error}")


def login(client: httpx.Client, context: RegressionContext) -> str:
    payload = request_json(
        client,
        "POST",
        f"{context.api_base}/platform/api/auth/login",
        json={"username": context.username, "password": context.password},
    )
    token = str(payload.get("access_token") or "")
    if not token:
        raise RegressionError("login did not return access_token")
    return token


def choose_subject_and_points(client: httpx.Client, context: RegressionContext) -> tuple[int, list[dict[str, Any]]]:
    subjects = request_json(client, "GET", f"{context.api_base}/platform/api/knowledge/subjects")
    if not subjects:
        raise RegressionError("no subjects returned from knowledge API")

    fallback_points = []
    fallback_subject_id = int(subjects[0]["id"])
    for subject in subjects:
        subject_id = int(subject["id"])
        points = request_json(client, "GET", f"{context.api_base}/platform/api/knowledge/points?subject_id={subject_id}")
        if points and not fallback_points:
            fallback_subject_id = subject_id
            fallback_points = points
        if len(points) >= 2:
            return subject_id, points[:3]

    if fallback_points:
        return fallback_subject_id, fallback_points[:3]
    raise RegressionError("no knowledge points returned from knowledge API")


def upload_paper(
    client: httpx.Client,
    context: RegressionContext,
    headers: dict[str, str],
    subject_id: int,
    points: list[dict[str, Any]],
    marker: str,
) -> int:
    sample_text = build_sample_text(points, marker)
    files = {"file": (f"{marker}.txt", sample_text.encode("utf-8"), "text/plain")}
    data = {
        "paper_name": f"HTTP regression paper {marker}",
        "subject_id": str(subject_id),
        "exam_year": "2026",
        "exam_month": "5",
        "exam_region": "HTTP",
        "exam_type": "regression",
        "paper_type": "regression",
        "paper_code": marker,
    }
    payload = request_json(
        client,
        "POST",
        f"{context.api_base}/platform/api/papers/upload",
        headers=headers,
        data=data,
        files=files,
    )
    paper_id = int(payload.get("id") or 0)
    if paper_id <= 0:
        raise RegressionError(f"upload did not return paper id: {payload}")
    return paper_id


def parse_paper(client: httpx.Client, context: RegressionContext, headers: dict[str, str], paper_id: int) -> dict[str, Any]:
    return request_json(
        client,
        "POST",
        f"{context.api_base}/platform/api/papers/{paper_id}/parse",
        headers=headers,
        data={"preset": "auto"},
    )


def build_sample_text(points: list[dict[str, Any]], marker: str) -> str:
    terms = []
    for point in points:
        name = str(point.get("name") or "").strip()
        if name:
            terms.append(name)
        for keyword in point.get("keywords_json") or []:
            keyword_text = str(keyword).strip()
            if keyword_text:
                terms.append(keyword_text)

    unique_terms = list(dict.fromkeys(terms))
    if not unique_terms:
        unique_terms = [marker]

    first_terms = " ".join(unique_terms[:6])
    second_terms = " ".join(unique_terms[-6:])
    return (
        f"1. {marker} question one covers {first_terms} for candidate recall.\n"
        "A. option one\n"
        "B. option two\n"
        "Answer: A\n"
        f"Analysis: verify knowledge candidate recall with {first_terms}.\n\n"
        f"2. {marker} question two covers {second_terms} for review workflows.\n"
        "A. option one\n"
        "B. option two\n"
        "Answer: B\n"
        f"Analysis: verify batch-review and stable readback with {second_terms}.\n"
    )


def audit_actions_for_question(
    client: httpx.Client,
    context: RegressionContext,
    headers: dict[str, str],
    question_id: int,
) -> set[str]:
    logs = request_json(client, "GET", f"{context.api_base}/platform/api/system/audit-logs?limit=100", headers=headers)
    question_id_text = str(question_id)
    actions: set[str] = set()
    for row in logs:
        action = str(row.get("action") or "")
        target_id = str(row.get("target_id") or "")
        payload = row.get("payload_json") or {}
        payload_ids = {str(item) for item in payload.get("link_ids", [])} if isinstance(payload, dict) else set()
        if row.get("target_type") != "question":
            continue
        if target_id == question_id_text or question_id_text in target_id.split(",") or question_id_text in payload_ids:
            actions.add(action)
    return actions


def request_json(client: httpx.Client, method: str, url: str, **kwargs: Any) -> Any:
    response = client.request(method, url, **kwargs)
    if response.status_code >= 400:
        raise RegressionError(f"{method} {url} failed: HTTP {response.status_code}: {response.text[:1000]}")
    try:
        return response.json()
    except ValueError as exc:
        raise RegressionError(f"{method} {url} did not return JSON: {response.text[:1000]}") from exc


def auth_headers(context: RegressionContext) -> dict[str, str]:
    if not context.token:
        raise RegressionError("auth token is missing")
    return {"Authorization": f"Bearer {context.token}"}


def find_link(question_detail: dict[str, Any], link_id: int) -> dict[str, Any]:
    for link in question_detail.get("links") or []:
        if int(link.get("id")) == link_id:
            return link
    raise RegressionError(f"link {link_id} not found on question {question_detail.get('id')}")


def assert_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise RegressionError(f"{label}: expected {expected!r}, got {actual!r}")


if __name__ == "__main__":
    raise SystemExit(main())
