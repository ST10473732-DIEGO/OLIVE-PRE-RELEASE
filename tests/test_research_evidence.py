import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock
import unittest

from olive.research.models import ResearchSession, ResearchSource, SearchResult
from olive.research.extraction import extract_page
from olive.research.evidence import extract_evidence, potential_conflicts, rank_sources
from olive.research.citations import validate_findings, render_report, ResearchSynthesizer
from olive.research.orchestrator import ResearchOrchestrator
from olive.research.repository import ResearchRepository
from olive.research.cache import ResearchCache
from olive.research.settings import ResearchSettings
from tests.test_research_core import valid_plan


def source_and_evidence(
    text="Embeddings support local text models and document retrieval.", url="https://example.com/docs"
):
    page = extract_page("<p>" + text + "</p>", url)
    source = ResearchSource(url, "Docs", content_hash=page.content_hash, status="read")
    evidence = extract_evidence(page, source.id, ["Embeddings support local text models"])
    return source, evidence


class EvidenceTests(unittest.TestCase):
    def test_explicit_site_scope_has_domain_boundary(self):
        from olive.research.orchestrator import in_requested_scope

        question = "Research site:docs.example.com"
        self.assertTrue(in_requested_scope("https://docs.example.com/a", question))
        self.assertFalse(in_requested_scope("https://docs.example.com.evil.test/", question))

    def test_untrusted_source_title_cannot_inject_markdown(self):
        source, evidence = source_and_evidence()
        source.title = "[fake](file:///secret) <img src='https://evil.test/'>"
        report = render_report(
            "Question",
            [{"text": evidence[0].quote, "kind": "source_claim", "evidence_ids": [evidence[0].id]}],
            [source],
            evidence,
        )
        self.assertNotIn("<img", report)
        self.assertNotIn("[fake](file:", report)

    def test_future_date_does_not_improve_rank(self):
        future = SearchResult(
            "Embeddings", "https://future.example.com/", rank=1, publication_date="2099-01-01"
        )
        current = SearchResult(
            "Embeddings",
            "https://current.example.com/",
            rank=1,
            publication_date=datetime.now(timezone.utc).isoformat(),
        )
        self.assertEqual(rank_sources([future, current], "Embeddings", "current")[0], current)

    def test_invalid_setting_types_fail_cleanly(self):
        for value in [[], {"depth": []}, {"browser_provider": {}}, {"search_provider": []}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ResearchSettings.validated(value)

    def test_evidence_offsets_map_to_actual_source(self):
        page = extract_page(
            "<h1>Title</h1><p>Embeddings support document retrieval and local search.</p>",
            "https://example.com/",
        )
        evidence = extract_evidence(page, "source", ["Document retrieval"])
        self.assertTrue(evidence)
        for item in evidence:
            self.assertEqual(page.text[item.start : item.end], item.quote)

    def test_citations_only_reference_read_evidence(self):
        source, evidence = source_and_evidence()
        finding = {"text": evidence[0].quote, "kind": "directly_supported", "evidence_ids": [evidence[0].id]}
        self.assertEqual(validate_findings({"findings": [finding]}, [source], evidence), [finding])
        source.status = "visited"
        with self.assertRaisesRegex(ValueError, "unread"):
            validate_findings({"findings": [finding]}, [source], evidence)

    def test_missing_and_duplicate_citations_fail(self):
        source, evidence = source_and_evidence()
        for ids in [["invented"], [], [evidence[0].id, evidence[0].id]]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_findings(
                    {
                        "findings": [
                            {"text": "Embeddings support text", "kind": "source_claim", "evidence_ids": ids}
                        ]
                    },
                    [source],
                    evidence,
                )

    def test_unsupported_statement_is_rejected(self):
        source, evidence = source_and_evidence()
        with self.assertRaisesRegex(ValueError, "support"):
            validate_findings(
                {
                    "findings": [
                        {
                            "text": "The moon consists entirely of cheese",
                            "kind": "source_claim",
                            "evidence_ids": [evidence[0].id],
                        }
                    ]
                },
                [source],
                evidence,
            )

    def test_model_links_and_false_direct_quotes_are_rejected(self):
        source, evidence = source_and_evidence()
        for text in [
            "Embeddings https://invented.example.com/",
            "Embeddings always guarantee perfect accuracy",
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_findings(
                    {
                        "findings": [
                            {"text": text, "kind": "directly_supported", "evidence_ids": [evidence[0].id]}
                        ]
                    },
                    [source],
                    evidence,
                )

    def test_conflict_is_retained_as_uncertain_comparison(self):
        first, a = source_and_evidence()
        second, b = source_and_evidence(
            "Embeddings do not support local text models and document retrieval.",
            "https://second.example.com/docs",
        )
        conflicts = potential_conflicts(a + b)
        self.assertEqual(conflicts[0]["status"], "potential_disagreement")
        self.assertEqual(len(conflicts[0]["evidence_ids"]), 2)

    def test_freshness_prefers_recent_equally_relevant_source(self):
        values = [
            SearchResult("Embeddings", "https://old.example.com/", rank=1, publication_date="2000-01-01"),
            SearchResult(
                "Embeddings",
                "https://new.example.com/",
                rank=1,
                publication_date=datetime.now(timezone.utc).isoformat(),
            ),
        ]
        self.assertEqual(rank_sources(values, "Embeddings", "current")[0].url, "https://new.example.com/")

    def test_report_uses_real_source_urls_only(self):
        source, evidence = source_and_evidence()
        findings = [{"text": evidence[0].quote, "kind": "source_claim", "evidence_ids": [evidence[0].id]}]
        report = render_report("Question", findings, [source], evidence)
        self.assertIn(source.url, report)
        self.assertIn("[S1]", report)


class SynthesisValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_correction_keeps_real_citation_ids(self):
        source, evidence = source_and_evidence()
        session = ResearchSession("Embeddings", sources=[source], evidence=evidence)
        invalid = {"findings": [{"text": "Embeddings are perfect", "kind": "directly_supported", "evidence_ids": ["E1"]}]}
        valid = {"findings": [{"text": evidence[0].quote, "kind": "source_claim", "evidence_ids": ["E1"]}]}
        ollama = SimpleNamespace(chat_once=AsyncMock(side_effect=[json.dumps(invalid), json.dumps(valid)]))
        synthesizer = ResearchSynthesizer(ollama, SimpleNamespace(route=lambda request: SimpleNamespace(name="fixture")))
        findings, report = await synthesizer.synthesize(session)
        self.assertEqual(ollama.chat_once.await_count, 2)
        self.assertEqual(findings[0]["evidence_ids"], [evidence[0].id])
        self.assertEqual(findings[0]["kind"], "directly_supported")
        self.assertIn(source.url, report)

    async def test_failed_citation_correction_does_not_fabricate(self):
        source, evidence = source_and_evidence()
        session = ResearchSession("Embeddings", sources=[source], evidence=evidence)
        invalid = {"findings": [{"text": "Embeddings", "kind": "source_claim", "evidence_ids": ["E999"]}]}
        ollama = SimpleNamespace(chat_once=AsyncMock(return_value=json.dumps(invalid)))
        synthesizer = ResearchSynthesizer(ollama, SimpleNamespace(route=lambda request: SimpleNamespace(name="fixture")))
        with self.assertRaisesRegex(ValueError, "two attempts"):
            await synthesizer.synthesize(session)
        self.assertEqual(ollama.chat_once.await_count, 2)
        self.assertEqual(session.final_report, "")


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.searches, self.reads = [], []
        self.events = []
        self.fail_source = False
        self.fail_synthesis = False
        self.duplicate = False
        self.block = None

        async def search(query, **kwargs):
            self.searches.append(query)
            return [
                SearchResult("Embeddings", f"https://example.com/{query[-1:]}/{i}", rank=i + 1)
                for i in range(5)
            ]

        async def open_page(url):
            self.reads.append(url)
            if self.block:
                await self.block.wait()
            if self.fail_source and url.endswith("/0"):
                raise OSError("Source unavailable")
            suffix = "" if self.duplicate else " Version " + url[-1]
            return extract_page(
                "<p>Embeddings are generated using local text models and support document retrieval."
                + suffix
                + "</p>",
                url,
            )

        async def plan(*args, **kwargs):
            value = valid_plan()
            value["search_queries"] = ["Embeddings query A", "Embeddings query B"]
            return value

        async def chat_once(model, messages, **kwargs):
            if self.fail_synthesis:
                raise ConnectionError("Ollama unavailable")
            item = json.loads(messages[-1]["content"])["untrusted_evidence"][0]
            return json.dumps(
                {"findings": [{"text": item["quote"], "kind": "source_claim", "evidence_ids": [item["id"]]}]}
            )

        synthesizer = ResearchSynthesizer(
            SimpleNamespace(chat_once=chat_once),
            SimpleNamespace(route=lambda request: SimpleNamespace(name="fixture")),
        )
        self.repository = ResearchRepository(self.root / "sessions.json")
        self.orchestrator = ResearchOrchestrator(
            self.repository,
            SimpleNamespace(plan=plan),
            synthesizer,
            SimpleNamespace(search=search, open=open_page),
            ResearchCache(self.root / "cache"),
            lambda topic, value: self.events.append((topic, value)),
        )
        self.session = ResearchSession(
            "Research embeddings",
            settings=ResearchSettings(max_searches=2, max_pages=4, max_link_depth=0).to_dict(),
        )

    async def test_bounded_research_completion_and_citations(self):
        result = await self.orchestrator.run(self.session)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(self.searches), 2)
        self.assertLessEqual(len(self.reads), 4)
        self.assertIn("[S1]", result["final_report"])
        self.assertFalse(any(s.saved_source_id for s in self.session.sources))

    async def test_one_source_failure_does_not_destroy_session(self):
        self.fail_source = True
        await self.orchestrator.run(self.session)
        self.assertEqual(self.session.status, "completed")
        self.assertTrue(any(s.status == "failed" for s in self.session.sources))

    async def test_duplicates_do_not_add_independent_evidence(self):
        self.duplicate = True
        await self.orchestrator.run(self.session)
        self.assertEqual(len({e.source_id for e in self.session.evidence}), 1)
        self.assertTrue(any(s.duplicate_of for s in self.session.sources))

    async def test_ollama_failure_preserves_evidence_and_retry_reuses_reads(self):
        self.fail_synthesis = True
        await self.orchestrator.run(self.session)
        self.assertEqual(self.session.status, "paused")
        count = len(self.reads)
        self.assertTrue(self.session.evidence)
        self.fail_synthesis = False
        await self.orchestrator.run(self.session)
        self.assertEqual(self.session.status, "completed")
        self.assertEqual(len(self.reads), count)

    async def test_pause_and_resume(self):
        self.block = asyncio.Event()
        task = asyncio.create_task(self.orchestrator.run(self.session))
        while not self.reads:
            await asyncio.sleep(0)
        self.orchestrator.pause()
        self.block.set()
        await task
        self.assertEqual(self.session.status, "paused")
        self.block = None
        await self.orchestrator.run(self.session)
        self.assertEqual(self.session.status, "completed")

    async def test_cancel_stops_future_work(self):
        self.block = asyncio.Event()
        task = asyncio.create_task(self.orchestrator.run(self.session))
        while not self.reads:
            await asyncio.sleep(0)
        self.orchestrator.cancel()
        await task
        self.assertEqual(self.session.status, "cancelled")
        self.assertFalse(self.session.final_report)

    async def test_runtime_budget_does_not_reset_on_resume(self):
        self.session.elapsed_seconds = 1000
        await self.orchestrator.run(self.session)
        self.assertEqual(self.session.status, "paused")
        self.assertEqual(self.searches, [])


if __name__ == "__main__":
    unittest.main()
