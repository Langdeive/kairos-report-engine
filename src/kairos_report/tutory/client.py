from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import httpx
from selectolax.parser import HTMLParser

from kairos_report.config import Settings
from kairos_report.errors import (
    TutoryAuthenticationError,
    TutoryContractChanged,
    TutoryTemporaryError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportDocument:
    key: str
    html: str


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
    LOGIN_PATH = "/intent/login"
    DASHBOARD_PATH = "/index"
    STUDENT_SEARCH_PATH = "/alunos/consulta"
    STUDENT_DETAIL_PATH = "/alunos/index"
    RESULT_LIMIT = 50

    def __init__(
        self,
        settings: Settings,
        *,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        self._token = settings.tutory_api_token.get_secret_value()
        self._account = settings.tutory_account
        self._password = settings.tutory_password.get_secret_value()
        self._sleep = sleep

    def list_active_students(self, *, include_phones: bool = False) -> list[TutoryStudent]:
        with httpx.Client(base_url=self.BASE_URL, timeout=30) as client:
            self._login(client)
            dashboard = self._request(client, "GET", self.DASHBOARD_PATH)
            expected_count = self._parse_active_count(dashboard.text)
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
            if include_phones:
                students = [self._student_with_phone(client, student) for student in students]
            return students

    def _student_with_phone(
        self, client: httpx.Client, student: TutoryStudent
    ) -> TutoryStudent:
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

    def _login(self, client: httpx.Client) -> None:
        self._request(
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
    def _merge_students(
        target: dict[str, TutoryStudent], students: list[TutoryStudent]
    ) -> None:
        for student in students:
            existing = target.get(student.id)
            if existing is not None and existing.name != student.name:
                raise TutoryContractChanged("Tutory returned conflicting data for a student ID")
            target[student.id] = student

    def generate_report(
        self, student_id: str, period_start: date, period_end: date
    ) -> ReportDocument:
        headers = {"Authorization": f"Bearer {self._token}"}
        with httpx.Client(base_url=self.BASE_URL, headers=headers, timeout=30) as client:
            response = self._request(
                client,
                "POST",
                self.GENERATE_PATH,
                data={
                    "alunos[]": student_id,
                    "dt_ini": period_start.strftime("%d/%m/%Y"),
                    "dt_fim": period_end.strftime("%d/%m/%Y"),
                    "agrupamento": "semana",
                },
            )
            key = self._extract_report_key(response)
            document = self._request(
                client,
                "GET",
                self.DOCUMENT_PATH,
                params={"key": key},
            )

        if "relatório" not in document.text.lower():
            raise TutoryContractChanged("Tutory report document has an unexpected shape")
        return ReportDocument(key=key, html=document.text)

    def _request(
        self,
        client: httpx.Client,
        method: str,
        path: str,
        *,
        data: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        for attempt in range(1, 4):
            try:
                response = client.request(method, path, data=data, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 3:
                    raise TutoryTemporaryError("Tutory unavailable after three attempts") from exc
                self._sleep(float(attempt))
                continue

            if response.status_code in {401, 403}:
                logger.warning("Tutory authentication was rejected")
                raise TutoryAuthenticationError("Tutory authentication was rejected")
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 3:
                    raise TutoryTemporaryError("Tutory unavailable after three attempts")
                self._sleep(float(attempt))
                continue
            if response.is_error:
                raise TutoryContractChanged(
                    f"Unexpected Tutory HTTP status: {response.status_code}"
                )
            return response

        raise AssertionError("bounded retry loop ended unexpectedly")

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
