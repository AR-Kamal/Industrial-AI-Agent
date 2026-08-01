import json
from argparse import ArgumentParser
from dataclasses import asdict
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.chatbot.grounded import GroundedAnswerRequest, GroundedAnswerService


class Command(BaseCommand):
    help = "Answer one text question using validated retrieval and grounded generation."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("query")
        parser.add_argument("--document")
        parser.add_argument("--top-k", type=int)
        parser.add_argument("--threshold", type=float)
        parser.add_argument("--show-diagnostics", action="store_true")
        parser.add_argument("--output-json", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        typed: dict[str, Any] = options
        try:
            result = GroundedAnswerService().answer(
                GroundedAnswerRequest(
                    typed["query"],
                    typed["document"],
                    typed["top_k"],
                    typed["threshold"],
                )
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        payload = asdict(result)
        if not typed["show_diagnostics"]:
            payload.pop("diagnostics", None)
        if typed["output_json"]:
            self.stdout.write(json.dumps(payload, indent=2, default=str))
            return
        self.stdout.write(f"STATUS\n{result.status}\n\nANSWER\n{result.answer}")
        if result.safety_notice:
            self.stdout.write(f"\n\nSAFETY NOTICE\n{result.safety_notice}")
        self.stdout.write("\n\nCITATIONS")
        for citation in result.citations:
            pages = (
                citation.page_start
                if citation.page_start == citation.page_end
                else f"{citation.page_start}-{citation.page_end}"
            )
            self.stdout.write(
                f"\n{citation.evidence_label}: {citation.document_id}; "
                f"{citation.chapter}; {citation.section}; pages {pages}"
            )
        if typed["show_diagnostics"]:
            self.stdout.write(
                "\n\nDIAGNOSTICS\n"
                + json.dumps(
                    asdict(result.diagnostics) if result.diagnostics else {}, indent=2
                )
            )
