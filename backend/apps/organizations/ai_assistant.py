"""Tenant-scoped explanatory AI service for reconciliation investigations."""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from django.conf import settings
from rest_framework.exceptions import APIException

from apps.ingestion.models import ImportRecord
from apps.reconciliation.models import (
    MatchCandidate,
    ReconciliationRun,
    TransactionReconciliation,
    TransactionState,
)


class AssistantUnavailable(APIException):
    status_code = 503
    default_detail = "AI Assistant is not configured for this environment."
    default_code = "assistant_unavailable"


class AssistantProviderError(APIException):
    status_code = 502
    default_detail = "AI Assistant could not generate a response right now."
    default_code = "assistant_provider_error"


ATTENTION_STATES = (
    TransactionState.CONFLICT,
    TransactionState.EXCEPTION,
    TransactionState.CANDIDATE,
    TransactionState.UNMATCHED,
)
REFERENCE_PATTERN = re.compile(r"\b[A-Za-z]{2,}[A-Za-z0-9-]*\d[A-Za-z0-9-]*\b")


def _transaction_label(state: TransactionReconciliation) -> str:
    transaction = state.transaction
    return transaction.reference or transaction.external_id or f"row {transaction.source_row_number}"


def _money(transaction) -> str:
    return f"{transaction.currency or 'currency not supplied'} {transaction.amount}"


def _method(method: str | None) -> str:
    labels = {
        "exact": "exact match",
        "normalized": "normalized match",
        "within_tolerance": "within configured tolerance",
        "partial_tolerance": "partial tolerance match",
        "out_of_tolerance": "outside configured tolerance",
        "similarity": "similarity comparison",
        "none": "different",
        "one_empty": "one value is empty",
        "both_empty": "both values are empty",
    }
    return labels.get(method or "", "not available")


def _candidate_for_state(state: TransactionReconciliation):
    candidates = MatchCandidate.objects.select_related(
        "source_transaction", "target_transaction"
    ).filter(run=state.run)
    if state.side == "SOURCE":
        candidates = candidates.filter(source_transaction=state.transaction)
    else:
        candidates = candidates.filter(target_transaction=state.transaction)
    return candidates.order_by("-score").first()


def _candidate_answer(state: TransactionReconciliation, candidate: MatchCandidate) -> str:
    source = candidate.source_transaction
    target = candidate.target_transaction
    evidence = candidate.evidence or {}
    reference = evidence.get("reference", {})
    amount = evidence.get("amount", {})
    date = evidence.get("date", {})
    counterparty = evidence.get("counterparty", {})
    lines = [f"{_transaction_label(state)} is a candidate because:"]
    lines.extend([
        f"• Amount: {_money(source)} ↔ {_money(target)} — {_method(amount.get('method'))}.",
        f"• Counterparty: {source.counterparty or 'not supplied'} ↔ {target.counterparty or 'not supplied'} — {_method(counterparty.get('method'))}.",
        f"• Date: {source.transaction_date.isoformat()} ↔ {target.transaction_date.isoformat()} — {_method(date.get('method'))}.",
        f"• Reference: {source.reference or 'not supplied'} ↔ {target.reference or 'not supplied'} — {_method(reference.get('method'))}.",
        f"Composite candidate score: {float(candidate.score) * 100:.2f}%.",
    ])
    if state.state == TransactionState.CANDIDATE:
        lines.append("Reviewer confirmation is required because this transaction remains in the candidate state.")
    elif candidate.review_status == "CONFIRMED":
        lines.append("This candidate has been confirmed by a reviewer.")
    elif candidate.review_status == "REJECTED":
        lines.append("This candidate was rejected by a reviewer.")
    return "\n".join(lines)


def _unmatched_answer(state: TransactionReconciliation) -> str:
    transaction = state.transaction
    candidate = _candidate_for_state(state)
    lines = [
        f"{_transaction_label(state)} is currently {state.state.lower().replace('_', ' ')}.",
        f"Transaction: {_money(transaction)} on {transaction.transaction_date.isoformat()} with {transaction.counterparty or 'no counterparty supplied'}.",
    ]
    if candidate:
        lines.append(
            f"The strongest recorded candidate is {candidate.target_transaction.reference or candidate.target_transaction.external_id or 'an unreferenced transaction'} at {float(candidate.score) * 100:.2f}%."
        )
        lines.append("It did not become an accepted match under the current reconciliation state and review outcome.")
    else:
        lines.append("No candidate was recorded above the configured minimum matching threshold.")
    return "\n".join(lines)


def _source_states(run: ReconciliationRun):
    return TransactionReconciliation.objects.select_related("transaction").filter(
        run=run, side="SOURCE"
    )


def _run_counts(run: ReconciliationRun) -> dict[str, int]:
    states = _source_states(run)
    return {
        "matched": states.filter(state=TransactionState.MATCHED).count(),
        "candidates": states.filter(state=TransactionState.CANDIDATE).count(),
        "unmatched": states.filter(state=TransactionState.UNMATCHED).count(),
        "conflicts": states.filter(state=TransactionState.CONFLICT).count(),
        "exceptions": states.filter(state=TransactionState.EXCEPTION).count(),
    }


def _run_summary(run: ReconciliationRun) -> str:
    counts = _run_counts(run)
    attention = counts["candidates"] + counts["unmatched"] + counts["conflicts"] + counts["exceptions"]
    if counts["conflicts"]:
        next_action = "Investigate conflicts first, then review candidates and exceptions."
    elif counts["exceptions"]:
        next_action = "Resolve exceptions first, then review candidate matches."
    elif counts["candidates"]:
        next_action = "Review candidate matches before closing this run."
    elif counts["unmatched"]:
        next_action = "Review unmatched source transactions."
    else:
        next_action = "No source transaction is currently awaiting reconciliation review."
    return "\n".join([
        f"Run status: {run.status.title()}.",
        f"Source records: {run.total_source}; target records: {run.total_target}.",
        f"Matched: {counts['matched']}; candidates: {counts['candidates']}; unmatched: {counts['unmatched']}; conflicts: {counts['conflicts']}; exceptions: {counts['exceptions']}.",
        f"Interpretation: {attention} source transaction(s) currently need attention.",
        f"Recommended: {next_action}",
    ])


def _attention_answer(run: ReconciliationRun) -> str:
    counts = _run_counts(run)
    states = list(_source_states(run).filter(state__in=ATTENTION_STATES))
    order = {
        TransactionState.CONFLICT: 0,
        TransactionState.EXCEPTION: 1,
        TransactionState.CANDIDATE: 2,
        TransactionState.UNMATCHED: 3,
    }
    states.sort(key=lambda state: order[state.state])
    total = len(states)
    lines = [f"{total} source transaction(s) need attention."]
    lines.extend([
        f"• Conflicts: {counts['conflicts']}",
        f"• Exceptions: {counts['exceptions']}",
        f"• Candidates: {counts['candidates']}",
        f"• Unmatched: {counts['unmatched']}",
    ])
    if states:
        priority = states[0]
        transaction = priority.transaction
        lines.append(
            f"Highest priority: {_transaction_label(priority)}, {_money(transaction)}, {transaction.counterparty or 'counterparty not supplied'} ({priority.state.lower().replace('_', ' ')})."
        )
        lines.append("Recommended: Investigate the highest-priority item first, then continue by state priority.")
    else:
        lines.append("There are no source transactions currently in conflict, exception, candidate, or unmatched states.")
    return "\n".join(lines)


def _conflict_answer(run: ReconciliationRun) -> str:
    conflicts = list(_source_states(run).filter(state=TransactionState.CONFLICT)[:5])
    if not conflicts:
        return "There are 0 source transactions in the conflict state for this run."
    lines = [f"There are {len(conflicts)} conflict(s) shown from this run."]
    for state in conflicts:
        candidate = _candidate_for_state(state)
        detail = f"{_transaction_label(state)} — {_money(state.transaction)}"
        if candidate:
            detail += f"; strongest recorded candidate score {float(candidate.score) * 100:.2f}%"
        lines.append(f"• {detail}")
    lines.append("Conflicts indicate competing or ambiguous candidate outcomes and should be investigated before approval.")
    return "\n".join(lines)


def _latest_import_answer(organization) -> str:
    latest = ImportRecord.objects.filter(organization=organization).order_by("-created_at").first()
    if latest is None:
        return "There are no imports in this organization yet."
    return "\n".join([
        f"Latest import: {latest.original_filename} ({latest.source}).",
        f"Status: {latest.status.title()}; rows: {latest.total_rows}; valid: {latest.valid_rows}; rejected: {latest.rejected_rows}.",
        f"Uploaded at: {latest.created_at.isoformat()} UTC.",
    ])


def _history_answer(organization, *, changed: bool) -> str:
    runs = list(ReconciliationRun.objects.filter(organization=organization).order_by("-created_at")[:5])
    if not runs:
        return "There are no reconciliation runs in this organization yet."
    if changed:
        if len(runs) < 2:
            return "Only one reconciliation run is available, so there is no previous run to compare."
        latest, previous = runs[0], runs[1]
        current_counts, previous_counts = _run_counts(latest), _run_counts(previous)
        return "\n".join([
            "Change from the previous run:",
            f"• Matched: {current_counts['matched'] - previous_counts['matched']:+d}",
            f"• Candidates: {current_counts['candidates'] - previous_counts['candidates']:+d}",
            f"• Unmatched: {current_counts['unmatched'] - previous_counts['unmatched']:+d}",
            f"• Conflicts: {current_counts['conflicts'] - previous_counts['conflicts']:+d}",
            f"• Exceptions: {current_counts['exceptions'] - previous_counts['exceptions']:+d}",
        ])
    lines = ["Recent reconciliation runs:"]
    for run in runs:
        counts = _run_counts(run)
        lines.append(
            f"• {run.created_at.date().isoformat()} — {run.status.title()}: {counts['matched']} matched, {counts['candidates']} candidates, {counts['unmatched']} unmatched."
        )
    return "\n".join(lines)


def _find_referenced_state(organization, question: str, run_id=None):
    references = REFERENCE_PATTERN.findall(question)
    if not references:
        return None
    states = TransactionReconciliation.objects.select_related("transaction", "run").filter(
        run__organization=organization,
        transaction__reference__iexact=references[0],
    )
    if run_id:
        states = states.filter(run_id=run_id)
    return states.order_by("-run__created_at").first()


def answer_known_question(
    *, question: str, organization, run_id=None,
    transaction_reconciliation_id=None, conversation=None,
) -> str | None:
    """Answer high-value reconciliation questions directly from authoritative records."""
    normalized = question.lower().strip()
    run = None
    if run_id:
        run = ReconciliationRun.objects.filter(id=run_id, organization=organization).first()
    if run is None:
        run = ReconciliationRun.objects.filter(organization=organization).order_by("-created_at").first()

    state = None
    if transaction_reconciliation_id and run:
        state = TransactionReconciliation.objects.select_related("transaction", "run").filter(
            id=transaction_reconciliation_id, run=run
        ).first()
    state = state or _find_referenced_state(organization, question, run_id)

    if state and ("candidate" in normalized or "explain" in normalized):
        candidate = _candidate_for_state(state)
        if candidate:
            return _candidate_answer(state, candidate)
    if state and ("unmatched" in normalized or "fail to match" in normalized or "why" in normalized):
        return _unmatched_answer(state)

    previous_user_questions = " ".join(
        item.get("content", "").lower()
        for item in (conversation or [])
        if item.get("role") == "user"
    )

    if run and ("what needs attention" in normalized or "transactions need attention" in normalized or "needs attention" in normalized or "highest-risk" in normalized or "highest risk" in normalized or "how many exceptions" in normalized):
        return _attention_answer(run)
    if run and ("conflict" in normalized):
        return _conflict_answer(run)
    if run and ("summarize this run" in normalized or "summary of the latest run" in normalized or "summary" in normalized and "run" in normalized):
        return _run_summary(run)
    if "import" in normalized and ("latest" in normalized or "time" in normalized):
        return _latest_import_answer(organization)
    if "time" in normalized and "latest import" in previous_user_questions:
        return _latest_import_answer(organization)
    if "what changed" in normalized or "previous run" in normalized:
        return _history_answer(organization, changed=True)
    if "audit" in normalized or "history" in normalized or "latest reconciliation run" in normalized:
        return _history_answer(organization, changed=False)
    return None


def _transaction_context(state: TransactionReconciliation) -> dict[str, Any]:
    transaction = state.transaction
    candidates = MatchCandidate.objects.filter(run=state.run).filter(
        source_transaction=transaction
    ) if state.side == "SOURCE" else MatchCandidate.objects.filter(
        run=state.run, target_transaction=transaction
    )
    return {
        "transaction": {
            "date": transaction.transaction_date.isoformat(),
            "amount": str(transaction.amount),
            "currency": transaction.currency,
            "reference": transaction.reference,
            "counterparty": transaction.counterparty,
            "description": transaction.description,
            "source_row": transaction.source_row_number,
        },
        "reconciliation": {"side": state.side, "state": state.state},
        "candidates": [
            {
                "score": str(candidate.score),
                "review_status": candidate.review_status,
                "selected": candidate.is_selected,
                "reference_score": str(candidate.reference_score),
                "amount_score": str(candidate.amount_score),
                "date_score": str(candidate.date_score),
                "counterparty_score": str(candidate.counterparty_score),
                "evidence": candidate.evidence,
            }
            for candidate in candidates[:5]
        ],
    }


def build_context(*, organization, run_id=None, transaction_reconciliation_id=None) -> dict[str, Any]:
    """Return only data authorized for the requested organization."""
    context: dict[str, Any] = {
        "organization": organization.name,
        "recent_runs": [],
    }
    runs = ReconciliationRun.objects.filter(organization=organization).order_by("-created_at")
    context["recent_runs"] = [
        {
            "id": str(run.id),
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "total_source": run.total_source,
            "total_target": run.total_target,
            "matched": run.matched_count,
            "unmatched": run.unmatched_count,
            "conflicts": run.conflict_count,
            "exceptions": run.exception_count,
        }
        for run in runs[:5]
    ]

    if run_id:
        run = runs.filter(id=run_id).first()
        if run is None:
            raise ValueError("Reconciliation run was not found.")
        context["selected_run"] = {
            "id": str(run.id),
            "status": run.status,
            "summary": {
                "matched": run.matched_count,
                "unmatched": run.unmatched_count,
                "conflicts": run.conflict_count,
                "exceptions": run.exception_count,
            },
        }

        if transaction_reconciliation_id:
            state = TransactionReconciliation.objects.select_related("transaction").filter(
                id=transaction_reconciliation_id,
                run=run,
            ).first()
            if state is None:
                raise ValueError("Transaction reconciliation was not found.")
            context["selected_transaction"] = _transaction_context(state)
    elif transaction_reconciliation_id:
        raise ValueError("A reconciliation run is required for a transaction explanation.")

    return context


def _provider_url() -> str:
    if settings.AI_PROVIDER.lower() == "groq":
        return "https://api.groq.com/openai/v1/chat/completions"
    if settings.AI_PROVIDER.lower() == "openrouter":
        return "https://openrouter.ai/api/v1/chat/completions"
    raise AssistantUnavailable("AI Assistant provider is not supported.")


def answer_question(*, question: str, context: dict[str, Any]) -> str:
    """Request an explanation without exposing secrets or giving the model write access."""
    if not settings.AI_API_KEY:
        raise AssistantUnavailable()

    messages = [
        {
            "role": "system",
            "content": (
                "You are FinAudit Copilot, an explanation assistant for financial "
                "reconciliation. Use only the supplied organization-scoped context. "
                "Explain deterministic results, evidence, states, and audit summaries. "
                "Never claim that you changed records or performed reconciliation. "
                "Never invent transaction data. If the context lacks an answer, say so "
                "and suggest the relevant FinAudit view. Be concise and professional."
            ),
        },
        {"role": "system", "content": f"Authorized context:\n{json.dumps(context, default=str)}"},
        {"role": "user", "content": question},
    ]
    try:
        response = requests.post(
            _provider_url(),
            headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
            json={"model": settings.AI_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 450},
            timeout=20,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AssistantProviderError() from exc

    if not answer:
        raise AssistantProviderError("AI Assistant returned an empty response.")
    return answer
