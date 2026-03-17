from __future__ import annotations

import argparse
import sys

from offline_agents.agents.card_agent import CardAgent
from offline_agents.agents.rules_agent import RulesAgent


def _print_response(backend: str | None, response: str) -> None:
    print(f"backend: {backend or 'unknown'}")
    print()
    print(response.strip())


def _run_rules(
    question: str,
    use_rag: bool,
    backend: str,
    ollama_model: str | None,
) -> int:
    prefer_ollama = backend == "ollama"
    agent = RulesAgent(
        use_rag=use_rag,
        prefer_ollama=prefer_ollama,
        ollama_model=ollama_model or "fab-rules-ft-q4ks",
    )
    response = agent.ask(question)
    _print_response(agent.last_backend, response)
    return 0


def _run_cards(
    question: str,
    slug: str | None,
    use_rag: bool,
    backend: str,
    ollama_model: str | None,
) -> int:
    prefer_ollama = backend == "ollama"
    agent = CardAgent(
        use_rag=use_rag,
        prefer_ollama=prefer_ollama,
        ollama_model=ollama_model or "fab-cards-ft-q4ks",
    )
    response = agent.ask(question, slug=slug)
    _print_response(agent.last_backend, response)
    return 0


def _run_smoke_test(use_rag: bool) -> int:
    rules_agent = RulesAgent(use_rag=use_rag)
    rules_response = rules_agent.ask("What does Arcane Barrier N do per CR 8.3.8?")
    if rules_agent.last_backend != "local-transformers":
        raise RuntimeError(
            f"Rules smoke test used unexpected backend: {rules_agent.last_backend!r}"
        )

    card_agent = CardAgent(use_rag=use_rag)
    resolved_slug = card_agent.resolve_card_slug("big_bully")
    if resolved_slug != "big_bully_red":
        raise RuntimeError(
            f"Card smoke test resolved 'big_bully' to unexpected slug: {resolved_slug!r}"
        )
    card_response = card_agent.ask(
        "When does Big Bully's effect trigger?",
        slug="big_bully",
    )
    if card_agent.last_backend != "local-transformers":
        raise RuntimeError(
            f"Card smoke test used unexpected backend: {card_agent.last_backend!r}"
        )

    print("PASS rules backend=local-transformers")
    print(rules_response.strip().splitlines()[0])
    print()
    print(f"PASS cards slug={resolved_slug} backend=local-transformers")
    print(card_response.strip().splitlines()[0])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PowerShell-friendly CLI for the local FAB rules/card agents.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    rules_parser = subparsers.add_parser("rules", help="Ask the rules agent a question")
    rules_parser.add_argument("question", nargs="+", help="Question to ask the rules agent")
    rules_parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Skip ChromaDB retrieval and query the fine-tuned model directly",
    )
    rules_parser.add_argument(
        "--backend",
        choices=["auto", "ollama"],
        default="auto",
        help="Backend preference: auto (local first) or ollama (quantized first)",
    )
    rules_parser.add_argument(
        "--ollama-model",
        help="Override Ollama model name (default: fab-rules-ft-q4ks)",
    )

    cards_parser = subparsers.add_parser("cards", help="Ask the card agent a question")
    cards_parser.add_argument("question", nargs="+", help="Question to ask the card agent")
    cards_parser.add_argument("--slug", help="Optional card slug to include official card text")
    cards_parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Skip ChromaDB retrieval and query the fine-tuned model directly",
    )
    cards_parser.add_argument(
        "--backend",
        choices=["auto", "ollama"],
        default="auto",
        help="Backend preference: auto (local first) or ollama (quantized first)",
    )
    cards_parser.add_argument(
        "--ollama-model",
        help="Override Ollama model name (default: fab-cards-ft-q4ks)",
    )

    smoke_parser = subparsers.add_parser(
        "smoke-test",
        help="Verify both agents answer using the local fine-tuned backend",
    )
    smoke_parser.add_argument(
        "--with-rag",
        action="store_true",
        help="Include ChromaDB retrieval in the smoke test instead of model-only checks",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "rules":
        return _run_rules(
            " ".join(args.question),
            use_rag=not args.no_rag,
            backend=args.backend,
            ollama_model=args.ollama_model,
        )
    if args.command == "cards":
        return _run_cards(
            " ".join(args.question),
            slug=args.slug,
            use_rag=not args.no_rag,
            backend=args.backend,
            ollama_model=args.ollama_model,
        )
    if args.command == "smoke-test":
        return _run_smoke_test(use_rag=args.with_rag)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
