from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx
from selectolax.parser import HTMLParser

from kairos_report.config import Settings
from kairos_report.errors import (
    TutoryAuthenticationError,
    TutoryContractChanged,
    TutoryGenerationUncertain,
    TutoryRetryPaused,
    TutoryTemporaryError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportDocument:
    key: str
    html: str


@dataclass(frozen=True)
class ReportBundle:
    key: str
    documents: dict[str, str]


@dataclass(frozen=True)
class TutoryStudent:
    id: str
    name: str
    status: str = "active"
    raw_phone: str | None = None


class TutoryClient:
    BASE_URL = "https://admin.tutory.com.br"
    GENERATE_PATH = "/intent/cadastrar-relatorio-coach"
    DOCUMENT_PATH = "/documentos/relatorios/desempenho"
    DOCUMENT_PATHS = {
        "desempenho": "/documentos/relatorios/desempenho",
        "questoes": "/documentos/relatorios/questoes",
        "aluno": "/documentos/relatorios/aluno",
        "horas-liquidas": "/documentos/relatorios/horas-liquidas",
        "progresso": "/documentos/relatorios/progresso",
    }
    LOGIN_PATH = "/intent/login"
    DASHBOARD_PATH = "/index"
    COACHING_PATH = "/alunos/coaching"
    STUDENT_SEARCH_PATH = "/alunos/consulta"
    STUDENT_DETAIL_PATH = "/alunos/index"
    RESULT_LIMIT = 50

    def __init__(
        self,
        settings: Settings,
        *,
        sleep: Callable[[float], object] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._token = (
            settings.tutory_api_token.get_secret_value()
            if settings.tutory_api_token is not None
            else None
        )
        self._account = settings.tutory_account
        self._static_token = settings.tutory_api_token is not None
        self._password = settings.tutory_password.get_secret_value()
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_attempts: int = settings.tutory_http_max_attempts
        self._request_spacing: float = settings.tutory_request_spacing_seconds
        self._retry_base: float = settings.tutory_retry_base_seconds
        self._retry_max: float = settings.tutory_retry_max_seconds
        self._last_request_at: datetime | None = None
        self._started_at = self._clock()
        self._calls = 0
        self._retries = 0
        self._wait_seconds = 0.0
        self._statuses: dict[str, int] = {}

    @property
    def stats(self) -> dict[str, object]:
        elapsed = max(0.0, (self._clock() - self._started_at).total_seconds())
        return {
            "http_calls": self._calls,
            "http_retries": self._retries,
            "wait_seconds": round(self._wait_seconds, 3),
            "elapsed_seconds": round(elapsed, 3),
            "statuses": dict(sorted(self._statuses.items())),
        }

    def list_active_students(
        self,
        *,
        student_ids: Sequence[str] | None = None,
        include_phones: bool = False,
    ) -> list[TutoryStudent]:
        requested_ids: set[str] | None = None
        if student_ids is not None:
            if not student_ids or any(not student_id.strip() for student_id in student_ids):
                raise ValueError("Selected student IDs must not be empty")
            requested_ids = set(student_ids)
        with httpx.Client(base_url=self.BASE_URL, timeout=30) as client:
            self._login(client)
            dashboard = self._request(client, "GET", self.DASHBOARD_PATH)
            expected_count = self._parse_active_count(dashboard.text)
            if self._token is None:
                self._token = self._discover_api_token(client, dashboard.text)
            search_page = self._request(
                client, "GET", self.STUDENT_SEARCH_PATH, params={"status": "ativos"}
            )
            course_ids = self._parse_course_ids(search_page.text)

            students_by_id: dict[str, TutoryStudent] = {}
            saturated_courses: list[str] = []
            for course_id in course_ids:
                page = self._request(
                    client,
                    "GET",
                    self.STUDENT_SEARCH_PATH,
                    params={"status": "ativos", "curso": course_id},
                )
                students = self._parse_students(page.text)
                self._merge_students(students_by_id, students)
                if len(students) == self.RESULT_LIMIT:
                    saturated_courses.append(course_id)

            for course_id in saturated_courses:
                for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    page = self._request(
                        client,
                        "GET",
                        self.STUDENT_SEARCH_PATH,
                        params={"status": "ativos", "curso": course_id, "nome": letter},
                    )
                    self._merge_students(students_by_id, self._parse_students(page.text))
                    if len(students_by_id) == expected_count:
                        break

            if len(students_by_id) != expected_count:
                raise TutoryContractChanged(
                    "Active-student enumeration did not match the dashboard total: "
                    f"expected {expected_count}, found {len(students_by_id)}"
                )
            students = sorted(students_by_id.values(), key=lambda student: student.id)
            if requested_ids is not None:
                unknown_ids = requested_ids - students_by_id.keys()
                if unknown_ids:
                    raise ValueError("Requested students are not in the active-student list")
                students = [student for student in students if student.id in requested_ids]
            if include_phones:
                students = [self._student_with_phone(client, student) for student in students]
            return students

    def _student_with_phone(self, client: httpx.Client, student: TutoryStudent) -> TutoryStudent:
        page = self._request(
            client,
            "GET",
            self.STUDENT_DETAIL_PATH,
            params={"aid": student.id},
        )
        tree = HTMLParser(page.text)
        area_node = tree.css_first('select[name="ddd"] option[selected]')
        if area_node is None:
            area_node = tree.css_first('input[name="ddd"]')
        phone_node = tree.css_first('input[name="celular"]')
        area = area_node.attributes.get("value", "") if area_node is not None else ""
        phone = phone_node.attributes.get("value", "") if phone_node is not None else ""
        raw_phone = f"{area}{phone}" if area and phone else None
        return replace(student, raw_phone=raw_phone)

    def _login(self, client: httpx.Client) -> httpx.Response:
        return self._request(
            client,
            "POST",
            self.LOGIN_PATH,
            data={"account": self._account, "password": self._password},
        )

    @staticmethod
    def _parse_active_count(html: str) -> int:
        node = HTMLParser(html).css_first('[role="progressbar"]')
        if node is None:
            logger.warning("Tutory session login could not be confirmed")
            raise TutoryAuthenticationError("Tutory session login could not be confirmed")
        match = re.search(r"\b(\d+)\s*\(", node.text(strip=True))
        if match is None:
            raise TutoryContractChanged("Tutory dashboard is missing the active-student total")
        return int(match.group(1))

    @staticmethod
    def _parse_course_ids(html: str) -> list[str]:
        tree = HTMLParser(html)
        select = tree.css_first('select[name="curso"]')
        if select is None:
            raise TutoryContractChanged("Tutory student search is missing the course filter")
        course_ids = [
            value
            for option in select.css("option")
            if (value := option.attributes.get("value", ""))
        ]
        if not course_ids:
            raise TutoryContractChanged("Tutory student search returned no course identifiers")
        return list(dict.fromkeys(course_ids))

    @staticmethod
    def _parse_students(html: str) -> list[TutoryStudent]:
        students: list[TutoryStudent] = []
        for card in HTMLParser(html).css(".pesquisa-aluno-container"):
            name_node = card.css_first(".pesquisa-aluno-nome")
            id_node = card.css_first('form.form_visualizar_aluno input[name="id"]')
            student_id = id_node.attributes.get("value", "") if id_node is not None else ""
            name = name_node.text(strip=True) if name_node is not None else ""
            if not student_id or not name:
                raise TutoryContractChanged("Tutory student result is missing ID or name")
            students.append(TutoryStudent(id=student_id, name=name))
        return students

    @staticmethod
    def _merge_students(target: dict[str, TutoryStudent], students: list[TutoryStudent]) -> None:
        for student in students:
            existing = target.get(student.id)
            if existing is not None and existing.name != student.name:
                raise TutoryContractChanged("Tutory returned conflicting data for a student ID")
            target[student.id] = student

    def generate_report(
        self, student_id: str, period_start: date, period_end: date
    ) -> ReportDocument:
        bundle = self.generate_report_bundle(
            student_id,
            period_start,
            period_end,
            models=("desempenho",),
        )
        return ReportDocument(key=bundle.key, html=bundle.documents["desempenho"])

    def generate_report_bundle(
        self,
        student_id: str,
        period_start: date,
        period_end: date,
        *,
        models: tuple[str, ...] = ("desempenho", "questoes", "aluno"),
    ) -> ReportBundle:
        if period_end < period_start:
            raise ValueError("period_end must not precede period_start")
        unknown_models = set(models) - self.DOCUMENT_PATHS.keys()
        if unknown_models:
            raise ValueError(f"Unsupported Tutory report models: {sorted(unknown_models)}")
        with httpx.Client(base_url=self.BASE_URL, timeout=30) as client:
            token = self._authorized_token(client)
            client.headers["Authorization"] = f"Bearer {token}"
            generation_data = {
                "alunos[]": student_id,
                "dt_ini": period_start.strftime("%d/%m/%Y"),
                "dt_fim": period_end.strftime("%d/%m/%Y"),
                "agrupamento": "semana",
            }
            try:
                response = self._request(
                    client,
                    "POST",
                    self.GENERATE_PATH,
                    data=generation_data,
                    ambiguous_write=True,
                )
            except TutoryAuthenticationError:
                if self._static_token or self._token is None:
                    raise
                self._token = None
                token = self._authorized_token(client)
                client.headers["Authorization"] = f"Bearer {token}"
                response = self._request(
                    client,
                    "POST",
                    self.GENERATE_PATH,
                    data=generation_data,
                    ambiguous_write=True,
                )
            key = self._extract_report_key(response)
            try:
                documents = {
                    model: self._request(
                        client,
                        "GET",
                        self.DOCUMENT_PATHS[model],
                        params={"key": key},
                    ).text
                    for model in models
                }
            except (TutoryAuthenticationError, TutoryTemporaryError) as exc:
                retry_after_seconds = (
                    exc.retry_after_seconds if isinstance(exc, TutoryRetryPaused) else None
                )
                stop_reason: Literal["upstream", "auth", "retry_paused"]
                if isinstance(exc, TutoryAuthenticationError):
                    stop_reason = "auth"
                elif isinstance(exc, TutoryRetryPaused):
                    stop_reason = "retry_paused"
                else:
                    stop_reason = "upstream"
                raise TutoryGenerationUncertain(
                    "Tutory report generation completed but document retrieval is uncertain; "
                    "manual reconciliation is required",
                    retry_after_seconds=retry_after_seconds,
                    stop_reason=stop_reason,
                ) from exc

        if any("relat" not in html.lower() for html in documents.values()):
            raise TutoryContractChanged("Tutory report document has an unexpected shape")
        return ReportBundle(key=key, documents=documents)

    def _authorized_token(self, client: httpx.Client) -> str:
        token = self._token
        if token is None:
            self._login(client)
            dashboard = self._request(client, "GET", self.DASHBOARD_PATH)
            token = self._discover_api_token(client, dashboard.text)
            self._token = token
        return token

    @staticmethod
    def _extract_api_token(html: str) -> str:
        tree = HTMLParser(html)
        for script in tree.css("script"):
            text = script.text()
            if "adminUser" not in text:
                continue
            match = re.search(
                r'(?:["\']token["\']|\btoken)\s*:\s*["\']([^"\']+)["\']',
                text,
            )
            if match is None:
                match = re.search(r'adminUser\.token\s*=\s*["\']([^"\']+)["\']', text)
            if match is not None:
                return match.group(1)
        raise TutoryAuthenticationError(
            "Tutory login succeeded but API authorization was not found"
        )

    def _discover_api_token(self, client: httpx.Client, authenticated_html: str) -> str:
        try:
            return self._extract_api_token(authenticated_html)
        except TutoryAuthenticationError:
            coaching = self._request(client, "GET", self.COACHING_PATH)
            return self._extract_api_token(coaching.text)

    def _request(
        self,
        client: httpx.Client,
        method: str,
        path: str,
        *,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        ambiguous_write: bool = False,
    ) -> httpx.Response:
        for attempt in range(1, self._max_attempts + 1):
            self._pace_request()
            self._calls += 1
            try:
                response = client.request(method, path, data=data, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                self._record_status("network_error")
                if ambiguous_write:
                    raise TutoryGenerationUncertain(
                        "Tutory report generation is uncertain; manual reconciliation is required"
                    ) from exc
                if attempt == self._max_attempts:
                    raise TutoryTemporaryError(
                        "Tutory unavailable after the configured attempts"
                    ) from exc
                self._wait_before_retry(attempt, None)
                continue

            self._last_request_at = self._clock()
            self._record_status(str(response.status_code))
            if response.status_code in {401, 403}:
                logger.warning("Tutory authentication was rejected")
                raise TutoryAuthenticationError("Tutory authentication was rejected")
            if response.status_code >= 500 and ambiguous_write:
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    delay = self._retry_delay(attempt, retry_after)
                    raise TutoryGenerationUncertain(
                        "Tutory report generation is uncertain; manual reconciliation is "
                        "required",
                        retry_after_seconds=delay,
                        stop_reason="retry_paused",
                    )
                raise TutoryGenerationUncertain(
                    "Tutory report generation is uncertain; manual reconciliation is required"
                )
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    delay = self._retry_delay(attempt, retry_after)
                    if attempt == self._max_attempts or delay > self._retry_max:
                        raise TutoryRetryPaused(
                            "Tutory requested a retry delay that must be preserved",
                            retry_after_seconds=delay,
                        )
                if attempt == self._max_attempts:
                    raise TutoryTemporaryError("Tutory unavailable after the configured attempts")
                self._wait_before_retry(attempt, retry_after)
                continue
            if response.is_error:
                raise TutoryContractChanged(
                    f"Unexpected Tutory HTTP status: {response.status_code}"
                )
            return response

        raise AssertionError("bounded retry loop ended unexpectedly")

    def _pace_request(self) -> None:
        if self._last_request_at is None or self._request_spacing <= 0:
            return
        elapsed = max(0.0, (self._clock() - self._last_request_at).total_seconds())
        remaining = self._request_spacing - elapsed
        if remaining > 0:
            self._sleep(remaining)
            self._wait_seconds += remaining

    def _wait_before_retry(self, attempt: int, retry_after: str | None) -> None:
        delay = self._retry_delay(attempt, retry_after)
        if delay > self._retry_max:
            raise TutoryRetryPaused(
                "Tutory requested a delay longer than the configured allowed wait",
                retry_after_seconds=delay,
            )
        self._retries += 1
        if delay > 0:
            self._sleep(delay)
            self._wait_seconds += delay

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    seconds = (retry_at - self._clock()).total_seconds()
                    return max(0.0, float(seconds))
                except (TypeError, ValueError, OverflowError):
                    pass
        return float(min(self._retry_max, self._retry_base * (2 ** (attempt - 1))))

    def _record_status(self, status: str) -> None:
        self._statuses[status] = self._statuses.get(status, 0) + 1

    @staticmethod
    def _extract_report_key(response: httpx.Response) -> str:
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise TutoryContractChanged("Tutory generation response is not JSON") from exc

        if not isinstance(payload, dict) or payload.get("result") is not True:
            raise TutoryContractChanged("Tutory generation response has an unexpected shape")
        data = payload.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise TutoryContractChanged("Tutory generation response has an unexpected shape")
        key = data[0].get("token")
        if not isinstance(key, str) or not key:
            raise TutoryContractChanged("Tutory generation response is missing the report key")
        return key
