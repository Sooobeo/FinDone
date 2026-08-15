#!/usr/bin/env python3
"""Run the v3.1 cross-concept choice experiment without publishing a bank.

This command is intentionally limited to the two ``cross_concept_fact`` slots
in each of the 405 general questions.  It writes experiment evidence and a
human-readable choice review under ``docs/modeling``.  It never writes Admin,
Supabase, Android assets, or the checked-in concept question bank.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from tools import train_concept_question_model as base


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "modeling" / "experiments"
DEFAULT_BUILD_DIR = ROOT / "build" / "concept-model-v3"
CONTRACT_VERSION = "3.1"
GENERAL_QUESTION_TYPES = (
    "term_to_definition",
    "term_to_intuition",
    "term_to_verbal_relation",
)
RETRIEVAL_SIGNALS = (
    "questionWord",
    "questionChar",
    "answerWord",
    "answerChar",
    "sameDomain",
    "sameMode",
    "questionSemantic",
    "answerSemantic",
)


def _v3_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    value = config.get("v3Experiment")
    if not isinstance(value, Mapping):
        raise base.ConceptModelError("v3Experiment is missing from model config")
    if str(value.get("contractVersion")) != CONTRACT_VERSION:
        raise base.ConceptModelError("v3Experiment.contractVersion must be 3.1")
    return value


def _output_policy(output_dir: Path, build_dir: Path) -> tuple[Path, Path]:
    output = base._resolve_repo_path(output_dir)
    build = base._resolve_repo_path(build_dir)
    modeling_root = (ROOT / "docs" / "modeling").resolve()
    build_root = (ROOT / "build").resolve()
    try:
        output.relative_to(modeling_root)
        build.relative_to(build_root)
    except ValueError as error:
        raise base.ConceptModelError(
            "v3 review experiments may write only below docs/modeling and build"
        ) from error
    return output, build


def _weak_profile(config: Mapping[str, Any]) -> Mapping[str, Any]:
    profile_id = str(config.get("canonicalWeakSupervisionProfile", ""))
    profiles = config.get("weakSupervisionProfiles")
    if not isinstance(profiles, list):
        raise base.ConceptModelError("weakSupervisionProfiles is missing")
    for profile in profiles:
        if isinstance(profile, Mapping) and str(profile.get("id")) == profile_id:
            return profile
    raise base.ConceptModelError(f"Unknown canonical weak profile: {profile_id}")


def load_or_run_embedding(
    spec: Mapping[str, Any],
    context: base.FeatureContext,
    cache_root: Path,
    device: str,
) -> base.EmbeddingRun:
    """Load an exact pinned matrix before importing optional model packages."""

    candidate_id = str(spec["id"])
    revision = str(spec["revision"])
    identity = {
        "candidateId": candidate_id,
        "modelId": str(spec["model"]),
        "revision": revision,
        "queryPrefix": str(spec.get("queryPrefix", "")),
        "passagePrefix": str(spec.get("passagePrefix", "")),
        "questions": [item.stem for item in context.questions],
        "elements": [item.semantic_text for item in context.elements],
    }
    matrix_key = base._sha256_bytes(base._stable_json_bytes(identity))
    matrix_path = (
        cache_root
        / candidate_id
        / "findone-similarity-matrices"
        / f"{matrix_key}.npz"
    )
    if matrix_path.is_file():
        with np.load(matrix_path, allow_pickle=False) as cached:
            query_candidate = np.asarray(cached["queryCandidate"], dtype=np.float32)
            answer_candidate = np.asarray(cached["answerCandidate"], dtype=np.float32)
            dimensions = int(np.asarray(cached["dimensions"]).item())
        if query_candidate.shape != (len(context.questions), len(context.elements)):
            raise base.ConceptModelError(f"Invalid cached query matrix: {matrix_path}")
        if answer_candidate.shape != (len(context.elements), len(context.elements)):
            raise base.ConceptModelError(f"Invalid cached answer matrix: {matrix_path}")
        return base.EmbeddingRun(
            candidate_id=candidate_id,
            model_id=str(spec["model"]),
            status="completed",
            revision_requested=revision,
            revision_resolved=revision,
            dimensions=dimensions,
            encode_seconds=0.0,
            artifact_bytes=base._directory_bytes(cache_root / candidate_id),
            error=None,
            cache_hit=True,
            matrix_cache_sha256=base._sha256_file(matrix_path),
            query_candidate_similarity=query_candidate,
            answer_candidate_similarity=answer_candidate,
        )
    return base.run_sentence_transformer(spec, context, cache_root, device)


def build_v3_feature_context(
    elements: list[base.ElementRecord],
    questions: list[base.QuestionGroup],
    weak_profile: Mapping[str, Any],
    rrf_k: int,
    strong_count: int = 2,
    relevant_count: int = 6,
    review_depth: int = 20,
) -> base.FeatureContext:
    """Build the reference weak labels with exactly two strong candidates."""

    if not 0 < strong_count <= relevant_count <= review_depth:
        raise base.ConceptModelError("Invalid v3 weak-label depth contract")
    context = base.build_feature_context(elements, questions, weak_profile, rrf_k)
    weight_names = (
        "questionWord",
        "questionChar",
        "answerWord",
        "answerChar",
        "sameDomain",
        "sameMode",
    )
    weights = {name: float(weak_profile.get(name, -1.0)) for name in weight_names}
    if any(value < 0 for value in weights.values()) or not math.isclose(
        sum(weights.values()), 1.0, abs_tol=1e-6
    ):
        raise base.ConceptModelError("v3 weak-profile weights must sum to 1")

    weak = np.full((len(questions), len(elements)), -1, dtype=np.int8)
    for question_index, question in enumerate(questions):
        answer = elements[question.element_index]
        candidates = base.eligible_candidate_indices(
            elements, question.element_index, question.question_type
        )
        signal_values: dict[str, dict[int, float]] = {
            "questionWord": {
                index: float(context.question_word_similarity[question_index, index])
                for index in candidates
            },
            "questionChar": {
                index: float(context.question_char_similarity[question_index, index])
                for index in candidates
            },
            "answerWord": {
                index: float(context.answer_word_similarity[question.element_index, index])
                for index in candidates
            },
            "answerChar": {
                index: float(context.answer_char_similarity[question.element_index, index])
                for index in candidates
            },
            "sameDomain": {
                index: float(answer.domain_id == elements[index].domain_id)
                for index in candidates
            },
            "sameMode": {
                index: float(answer.mode == elements[index].mode)
                for index in candidates
            },
        }
        ranks = {
            name: base._competition_ranks(values, elements)
            for name, values in signal_values.items()
        }
        scored = []
        for candidate_index in candidates:
            score = sum(
                weights[name] / (rrf_k + ranks[name][candidate_index])
                for name in weight_names
            )
            scored.append((score, elements[candidate_index].element_id, candidate_index))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if len(scored) < review_depth:
            raise base.ConceptModelError(
                f"{question.question_id} has fewer than {review_depth} eligible candidates"
            )
        for rank, (_, _, candidate_index) in enumerate(scored):
            weak[question_index, candidate_index] = (
                3
                if rank < strong_count
                else 2
                if rank < relevant_count
                else 1
                if rank < review_depth
                else 0
            )
    context.weak_relevance = weak
    return context


def ratio_profile(semantic_total: float, metadata_total: float) -> dict[str, Any]:
    """Create a symmetric ratio profile around the equal-weight RRF baseline."""

    lexical_total = 1.0 - semantic_total - metadata_total
    if min(semantic_total, metadata_total, lexical_total) < 0:
        raise base.ConceptModelError("Retrieval ratio totals must be non-negative")
    profile = {
        "id": f"ratio-s{semantic_total:.3f}-m{metadata_total:.3f}",
        "questionWord": lexical_total / 4,
        "questionChar": lexical_total / 4,
        "answerWord": lexical_total / 4,
        "answerChar": lexical_total / 4,
        "sameDomain": metadata_total / 2,
        "sameMode": metadata_total / 2,
        "questionSemantic": semantic_total / 2,
        "answerSemantic": semantic_total / 2,
        "provenance": "v3 validation-only ratio search around equal-weight RRF",
        "semanticTotal": semantic_total,
        "metadataTotal": metadata_total,
        "lexicalTotal": lexical_total,
    }
    base._retrieval_weights(profile)
    return profile


def refinement_profile(
    semantic_total: float,
    metadata_total: float,
    word_fraction: float,
    domain_fraction: float,
) -> dict[str, Any]:
    lexical_total = 1.0 - semantic_total - metadata_total
    if not 0 <= word_fraction <= 1 or not 0 <= domain_fraction <= 1:
        raise base.ConceptModelError("Refinement fractions must be in [0, 1]")
    word_total = lexical_total * word_fraction
    char_total = lexical_total - word_total
    profile = {
        "id": (
            f"refine-s{semantic_total:.3f}-m{metadata_total:.3f}"
            f"-w{word_fraction:.3f}-d{domain_fraction:.3f}"
        ),
        "questionWord": word_total / 2,
        "questionChar": char_total / 2,
        "answerWord": word_total / 2,
        "answerChar": char_total / 2,
        "sameDomain": metadata_total * domain_fraction,
        "sameMode": metadata_total * (1 - domain_fraction),
        "questionSemantic": semantic_total / 2,
        "answerSemantic": semantic_total / 2,
        "provenance": "v3 validation-only lexical/metadata refinement",
        "semanticTotal": semantic_total,
        "metadataTotal": metadata_total,
        "lexicalTotal": lexical_total,
        "wordFraction": word_fraction,
        "domainFraction": domain_fraction,
    }
    base._retrieval_weights(profile)
    return profile


def fine_ratio_profiles(v3: Mapping[str, Any]) -> list[dict[str, Any]]:
    search = v3.get("fineRatioSearch")
    if not isinstance(search, Mapping):
        raise base.ConceptModelError("v3Experiment.fineRatioSearch is missing")
    semantic = [float(value) for value in search.get("semanticTotals", [])]
    metadata = [float(value) for value in search.get("metadataTotals", [])]
    profiles = [ratio_profile(s_value, m_value) for s_value in semantic for m_value in metadata]
    ids = [str(item["id"]) for item in profiles]
    if not profiles or len(ids) != len(set(ids)):
        raise base.ConceptModelError("v3 fine-ratio profiles are empty or duplicated")
    return profiles


def refinement_profiles(
    v3: Mapping[str, Any], selected_profile: Mapping[str, Any]
) -> list[dict[str, Any]]:
    search = v3.get("refinementSearch")
    if not isinstance(search, Mapping):
        raise base.ConceptModelError("v3Experiment.refinementSearch is missing")
    semantic_total = float(selected_profile["semanticTotal"])
    metadata_total = float(selected_profile["metadataTotal"])
    return [
        refinement_profile(semantic_total, metadata_total, float(word), float(domain))
        for word in search.get("wordFractions", [])
        for domain in search.get("domainFractions", [])
    ]


def evaluate_at2(
    context: base.FeatureContext,
    retrieved: Sequence[Sequence[int]],
    ranked: Sequence[Sequence[tuple[int, float]]],
    split: str,
) -> dict[str, Any]:
    recalls: list[float] = []
    ndcgs: list[float] = []
    precisions: list[float] = []
    strong_precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    count = 0
    for question_index, question in enumerate(context.questions):
        if question.split != split:
            continue
        count += 1
        # The weak-label row is -1 for hard-filtered candidates and 0..3 for
        # eligible candidates. Reusing that mask avoids re-running all source
        # role predicates for every ranker evaluation.
        all_relevance = [
            int(value)
            for value in context.weak_relevance[question_index]
            if int(value) >= 0
        ]
        relevant_total = sum(value >= 2 for value in all_relevance)
        retrieved_relevance = [
            int(context.weak_relevance[question_index, candidate_index])
            for candidate_index in retrieved[question_index][:20]
        ]
        recalls.append(sum(value >= 2 for value in retrieved_relevance) / relevant_total)
        ranked_relevance = [
            int(context.weak_relevance[question_index, candidate_index])
            for candidate_index, _ in ranked[question_index]
        ]
        ideal = sorted(all_relevance, reverse=True)
        ideal_dcg = base._dcg(ideal, 2)
        ndcgs.append(base._dcg(ranked_relevance, 2) / ideal_dcg if ideal_dcg else 0.0)
        precisions.append(sum(value >= 2 for value in ranked_relevance[:2]) / 2)
        strong_precisions.append(sum(value == 3 for value in ranked_relevance[:2]) / 2)
        first_relevant = next(
            (position for position, value in enumerate(ranked_relevance, 1) if value >= 2),
            None,
        )
        reciprocal_ranks.append(1 / first_relevant if first_relevant else 0.0)
    return {
        "split": split,
        "questionCount": count,
        "retrievalRecallAt20": round(float(np.mean(recalls)), 6),
        "ndcgAt2": round(float(np.mean(ndcgs)), 6),
        "precisionAt2": round(float(np.mean(precisions)), 6),
        "strongPrecisionAt2": round(float(np.mean(strong_precisions)), 6),
        "mrr": round(float(np.mean(reciprocal_ranks)), 6),
        "labelSource": "v3_equal_weight_weak_rule",
    }


def train_xgboost_at2(
    context: base.FeatureContext,
    embedding: base.EmbeddingRun,
    retrieved: Sequence[Sequence[int]],
    seed: int,
    parameters: Mapping[str, Any],
) -> Any:
    try:
        from xgboost import XGBRanker
    except ImportError as error:
        raise base.ConceptModelError("xgboost is not installed") from error
    train_x, train_y, train_qid, _ = base._training_matrix(
        context, embedding, retrieved, {}, "train"
    )
    validation_x, validation_y, validation_qid, _ = base._training_matrix(
        context, embedding, retrieved, {}, "validation"
    )
    model = XGBRanker(
        objective="rank:ndcg",
        eval_metric="ndcg@2",
        n_estimators=300,
        max_depth=int(parameters.get("maxDepth", 4)),
        learning_rate=float(parameters.get("learningRate", 0.05)),
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=seed,
        tree_method="hist",
        n_jobs=max(1, min(8, os.cpu_count() or 1)),
        early_stopping_rounds=25,
    )
    model.fit(
        train_x,
        train_y,
        qid=train_qid,
        eval_set=[(validation_x, validation_y)],
        eval_qid=[validation_qid],
        verbose=False,
    )
    return model


def _train(
    context: base.FeatureContext,
    embedding: base.EmbeddingRun,
    retrieved: Sequence[Sequence[int]],
    family: str,
    hyperparameters: Mapping[str, Any],
    seed: int,
    max_pairs: int,
) -> Any:
    if family == "pairwise-logistic":
        return base.train_pairwise_logistic(
            context,
            embedding,
            retrieved,
            {},
            seed,
            max_pairs,
            float(hyperparameters["C"]),
        )
    if family == "xgboost":
        return train_xgboost_at2(context, embedding, retrieved, seed, hyperparameters)
    raise base.ConceptModelError(f"Unsupported v3 ranker: {family}")


def _ranker_variants(config: Mapping[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    result = [
        (
            "pairwise-logistic",
            f"pairwise-logistic-c{str(float(value)).replace('.', 'p')}",
            {"C": float(value)},
        )
        for value in config.get("pairwiseLogisticCValues", [])
    ]
    result.extend(
        (
            "xgboost",
            f"xgboost-{str(item.get('id', 'default'))}",
            dict(item),
        )
        for item in config.get("xgboostGrid", [])
        if isinstance(item, Mapping)
    )
    if not result:
        raise base.ConceptModelError("No v3 ranker variants are configured")
    return result


def select_validation_run(
    runs: Sequence[Mapping[str, Any]],
    embedding_priorities: Mapping[str, int] | None = None,
) -> Mapping[str, Any]:
    """Select strictly from validation metrics; test fields are never read."""

    successful = [item for item in runs if item.get("status") == "completed"]
    if not successful:
        raise base.ConceptModelError("No successful v3 validation run is available")
    priorities = embedding_priorities or {}

    def key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        validation = item["validation"]
        assert isinstance(validation, Mapping)
        return (
            -float(validation["ndcgAt2"]),
            -float(validation["strongPrecisionAt2"]),
            -float(validation["precisionAt2"]),
            -float(validation["retrievalRecallAt20"]),
            -float(validation["mrr"]),
            int(priorities.get(str(item["embeddingId"]), 999)),
            0 if item["rankerFamily"] == "pairwise-logistic" else 1,
            str(item["embeddingId"]),
            str(item["retrievalProfileId"]),
            str(item["rankerId"]),
        )

    return min(successful, key=key)


def _run_one(
    *,
    stage: str,
    context: base.FeatureContext,
    embedding: base.EmbeddingRun,
    profile: Mapping[str, Any],
    variant: tuple[str, str, Mapping[str, Any]],
    retrieval_limit: int,
    rrf_k: int,
    seed: int,
    max_pairs: int,
    retrieved: Sequence[Sequence[int]] | None = None,
) -> dict[str, Any]:
    family, ranker_id, hyperparameters = variant
    started = time.perf_counter()
    try:
        active_retrieved = (
            retrieved
            if retrieved is not None
            else base.retrieve_candidates(
                context, embedding, retrieval_limit, profile, rrf_k
            )
        )
        model = _train(
            context,
            embedding,
            active_retrieved,
            family,
            hyperparameters,
            seed,
            max_pairs,
        )
        ranked = base.rank_candidates(context, embedding, active_retrieved, model)
        validation = evaluate_at2(
            context, active_retrieved, ranked, "validation"
        )
        return {
            "stage": stage,
            "embeddingId": embedding.candidate_id,
            "retrievalProfileId": str(profile["id"]),
            "retrievalProfile": {name: profile.get(name) for name in RETRIEVAL_SIGNALS},
            "ratioTotals": {
                key: profile[key]
                for key in (
                    "semanticTotal",
                    "metadataTotal",
                    "lexicalTotal",
                    "wordFraction",
                    "domainFraction",
                )
                if key in profile
            },
            "rankerFamily": family,
            "rankerId": ranker_id,
            "hyperparameters": dict(hyperparameters),
            "status": "completed",
            "trainingSeconds": round(time.perf_counter() - started, 3),
            "validation": validation,
            "test": None,
            "testEvaluated": False,
            "error": None,
        }
    except Exception as error:
        return {
            "stage": stage,
            "embeddingId": embedding.candidate_id,
            "retrievalProfileId": str(profile.get("id", "unknown")),
            "retrievalProfile": {name: profile.get(name) for name in RETRIEVAL_SIGNALS},
            "ratioTotals": {},
            "rankerFamily": family,
            "rankerId": ranker_id,
            "hyperparameters": dict(hyperparameters),
            "status": "failed",
            "trainingSeconds": round(time.perf_counter() - started, 3),
            "validation": None,
            "test": None,
            "testEvaluated": False,
            "error": f"{type(error).__name__}: {str(error)[:500]}",
        }


def _profile_from_run(run: Mapping[str, Any]) -> dict[str, Any]:
    profile = {"id": str(run["retrievalProfileId"]), **dict(run["retrievalProfile"])}
    profile.update(dict(run.get("ratioTotals", {})))
    base._retrieval_weights(profile)
    return profile


def _variant_from_run(run: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    return (
        str(run["rankerFamily"]),
        str(run["rankerId"]),
        dict(run["hyperparameters"]),
    )


def _surface_overlap_hints(target: base.ElementRecord, candidate: base.ElementRecord) -> list[str]:
    target_tokens = {
        token.casefold()
        for token in base.TOKEN_RE.findall(target.semantic_text)
        if len(token) >= 2
    }
    candidate_tokens = {
        token.casefold()
        for token in base.TOKEN_RE.findall(candidate.semantic_text)
        if len(token) >= 2
    }
    return sorted(target_tokens & candidate_tokens, key=lambda value: (-len(value), value))[:8]


def _review_rows(
    context: base.FeatureContext,
    embedding: base.EmbeddingRun,
    ranked: Sequence[Sequence[tuple[int, float]]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for question_index, question in enumerate(context.questions):
        target = context.elements[question.element_index]
        choices = []
        for candidate_index, score in ranked[question_index][:2]:
            candidate = context.elements[candidate_index]
            text = base.display_fact_text(
                candidate, base.fact_type_for_question(question.question_type)
            )
            decision = base.candidate_filter_decision(
                context.elements,
                question.element_index,
                candidate_index,
                question.question_type,
            )
            source_leak = base.text_mentions_title(text, candidate.title)
            target_leak = base.text_mentions_title(text, target.title)
            counters["sourceNameLeakCount"] += int(source_leak)
            counters["targetNameLeakCount"] += int(target_leak)
            if question.question_type == "term_to_definition":
                counters[f"definitionFilter:{decision.reason_id}"] += 1
            choices.append(
                {
                    "sourceElementId": candidate.element_id,
                    "sourceElementTitle": candidate.title,
                    "sourceDomainId": candidate.domain_id,
                    "text": text,
                    "modelScore": round(float(score), 8),
                    "weakRelevance": int(
                        context.weak_relevance[question_index, candidate_index]
                    ),
                    "questionSemanticSimilarity": round(
                        float(embedding.query_candidate_similarity[question_index, candidate_index]),
                        6,
                    )
                    if embedding.query_candidate_similarity is not None
                    else None,
                    "answerSemanticSimilarity": round(
                        float(
                            embedding.answer_candidate_similarity[
                                question.element_index, candidate_index
                            ]
                        ),
                        6,
                    )
                    if embedding.answer_candidate_similarity is not None
                    else None,
                    "surfaceOverlapHints": _surface_overlap_hints(target, candidate),
                    "sharedAnchorIds": [],
                    "anchorReviewStatus": "required",
                    "distinctAxis": None,
                    "distinctAxisReviewStatus": "required",
                    "definitionRoleCompatibility": decision.report_dict()
                    if question.question_type == "term_to_definition"
                    else None,
                    "sourceLocator": candidate.source_locator,
                    "sourceNameLeak": source_leak,
                    "targetNameLeak": target_leak,
                }
            )
        if len(choices) != 2:
            raise base.ConceptModelError(f"{question.question_id} did not produce two choices")
        rows.append(
            {
                "questionId": question.question_id,
                "split": question.split,
                "questionType": question.question_type,
                "targetElementId": target.element_id,
                "targetTitle": target.title,
                "targetDomainId": target.domain_id,
                "stem": question.stem,
                "targetCorrectText": question.correct_answer,
                "crossConceptChoices": choices,
            }
        )
    counters["questionCount"] = len(rows)
    counters["crossConceptChoiceCount"] = sum(
        len(row["crossConceptChoices"]) for row in rows
    )
    counters["anchorReviewRequiredCount"] = counters["crossConceptChoiceCount"]
    counters["distinctAxisReviewRequiredCount"] = counters["crossConceptChoiceCount"]
    return rows, dict(counters)


def _render_choice_review(
    experiment_id: str,
    selection: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    audit: Mapping[str, int],
) -> str:
    lines = [
        f"# {experiment_id} 타개념 선지 사전 검수",
        "",
        "> 이 문서는 Admin 반영 전 검수본이다. 일반 문항의 타개념 참 선지 2개만 표시한다. "
        "대상 개념 변형 오답 2개와 `옳지 않은 것` 문항은 아직 생성하지 않았다.",
        "",
        "## 검수 상태",
        "",
        f"- 일반 문항: {audit['questionCount']}개",
        f"- 타개념 선지: {audit['crossConceptChoiceCount']}개",
        f"- 출처 개념명 노출 감지: {audit.get('sourceNameLeakCount', 0)}건",
        f"- 대상 개념명 노출 감지: {audit.get('targetNameLeakCount', 0)}건",
        f"- 검토된 공유 앵커 필요: {audit['anchorReviewRequiredCount']}건",
        f"- 구별축 검토 필요: {audit['distinctAxisReviewRequiredCount']}건",
        f"- 선택 구성: `{selection['embeddingId']}/{selection['retrievalProfileId']}/{selection['rankerId']}`",
        "",
        "`자동 표면 겹침 힌트`는 검수 편의를 위한 비구속 문자열 교집합이며 "
        "`sharedAnchorIds`가 아니다. 공유 앵커와 구별축을 사람이 확인하기 전에는 이 선지를 문항은행에 넣지 않는다.",
        "",
    ]
    current_domain: str | None = None
    for row in rows:
        domain = str(row["targetDomainId"])
        if domain != current_domain:
            current_domain = domain
            lines.extend((f"## {domain}", ""))
        lines.extend(
            (
                f"### {row['questionId']} · {row['targetTitle']}",
                "",
                f"- 유형: `{row['questionType']}` / 분할: `{row['split']}`",
                f"- 문제: {str(row['stem']).replace(chr(10), ' — ')}",
                f"- 대상 개념의 참 설명: {row['targetCorrectText']}",
                "",
            )
        )
        for position, choice in enumerate(row["crossConceptChoices"], start=1):
            compatibility = choice.get("definitionRoleCompatibility")
            role_line = "해당 없음"
            if isinstance(compatibility, Mapping):
                role_line = str(compatibility.get("reasonId"))
                target_roles = [
                    str(item.get("roleId"))
                    for item in compatibility.get("targetEvidence", [])
                    if isinstance(item, Mapping)
                ]
                candidate_roles = [
                    str(item.get("roleId"))
                    for item in compatibility.get("candidateEvidence", [])
                    if isinstance(item, Mapping)
                ]
                role_line += f" (대상={target_roles or ['근거 부족']}, 후보={candidate_roles or ['근거 부족']})"
            hints = ", ".join(choice["surfaceOverlapHints"]) or "없음"
            lines.extend(
                (
                    f"#### 타개념 선지 {position}",
                    "",
                    f"> {choice['text']}",
                    "",
                    f"- 내부 출처: `{choice['sourceElementId']}` · {choice['sourceElementTitle']} · `{choice['sourceDomainId']}`",
                    f"- 자동 표면 겹침 힌트: {hints}",
                    f"- 정의 역할 호환: `{role_line}`",
                    f"- 랭커 점수/약지도 등급: `{choice['modelScore']}` / `{choice['weakRelevance']}`",
                    f"- 의미 유사도(문제/대상): `{choice['questionSemanticSimilarity']}` / `{choice['answerSemanticSimilarity']}`",
                    f"- 이름 노출 감지(출처/대상): `{choice['sourceNameLeak']}` / `{choice['targetNameLeak']}`",
                    f"- 출처 위치: `{choice['sourceLocator']}`",
                    "- 검수 입력: 공유 앵커 `미확정` / 구별축 `미확정`",
                    "",
                )
            )
    return "\n".join(lines)


def _render_report(report: Mapping[str, Any]) -> str:
    selection = report["selection"]
    evaluation = report["evaluation"]
    dataset = report["dataset"]
    readiness = report["readiness"]
    stage_counts = Counter(
        str(item["stage"])
        for item in report["runs"]
        if item["status"] == "completed"
    )
    lines = [
        f"# {report['experimentId']} 실험 보고서",
        "",
        "## 결론",
        "",
        f"- 상태: `{report['status']}` (Admin 미반영, 릴리스 불가)",
        f"- 선택 구성: `{selection['embeddingId']}/{selection['retrievalProfileId']}/{selection['rankerId']}`",
        f"- validation NDCG@2: `{evaluation['validation']['ndcgAt2']}`",
        f"- test NDCG@2: `{evaluation['test']['ndcgAt2']}`",
        f"- 검수 문서: [{Path(report['artifacts']['choiceReview']).name}]({Path(report['artifacts']['choiceReview']).name})",
        "",
        "이 수치는 독립 사람 라벨이 아니라 동일 가중 RRF 약지도를 얼마나 재현했는지 보여 주는 "
        "bootstrap 진단이다. 교육 품질이나 일반화 성능으로 해석하면 안 된다.",
        "",
        "## 실험 범위",
        "",
        f"- 요소: {dataset['elementCount']}개",
        f"- 일반 문항: {dataset['generalQuestionCount']}개",
        f"- 선택한 타개념 선지: {dataset['selectedCrossConceptChoiceCount']}개",
        f"- 완료 실행: stage 1 {stage_counts['reference-grid']}개, stage 2 {stage_counts['ratio-search']}개, stage 3 {stage_counts['ratio-refinement']}개",
        "- 후보 계약: 일반 문항당 강한 약지도 2개, 관련 약지도 총 6개, Recall@20",
        "- 선택 규칙: validation NDCG@2 → strong Precision@2 → Precision@2 → Recall@20; 정확히 동률일 때만 저비용 구성을 우선",
        "- test 사용: 최종 선택 후 한 구성에만 1회",
        "",
        "## 기준선과 탐색",
        "",
        "1. 저장소 레퍼런스의 동일 가중 RRF 기준선과 6개 임베딩 후보·기존 랭커 그리드에서 시작했다.",
        "2. validation 상위 dense 임베딩 2개에 대해 의미/메타데이터 총비율을 각각 0.15~0.35로 탐색했다.",
        "3. 최상위 비율 주변에서 word/char와 domain/mode 내부 배분을 세분화했다.",
        "4. 정의형 후보에는 출처 정의의 명시적 종결 술어에 근거한 역할 호환 필터를 적용했다.",
        "",
        "## 선택 결과",
        "",
        "| 분할 | Recall@20 | NDCG@2 | Precision@2 | strong Precision@2 | MRR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split in ("validation", "test"):
        metric = evaluation[split]
        lines.append(
            f"| {split} | {metric['retrievalRecallAt20']:.6f} | {metric['ndcgAt2']:.6f} | "
            f"{metric['precisionAt2']:.6f} | {metric['strongPrecisionAt2']:.6f} | {metric['mrr']:.6f} |"
        )
    lines.extend(
        (
            "",
            "## v3.1 준비 상태",
            "",
            f"- 타개념 선지 문장 생성: {readiness['crossConceptChoicesGenerated']}개",
            f"- 검토된 공유 앵커: {readiness['reviewedSharedAnchorCount']}개",
            f"- 검토된 구별축: {readiness['reviewedDistinctAxisCount']}개",
            f"- 출처 개념명 노출: {report['reviewAudit'].get('sourceNameLeakCount', 0)}건",
            f"- 대상 개념명 노출: {report['reviewAudit'].get('targetNameLeakCount', 0)}건",
            f"- 미생성 일반문항 변형 오답 슬롯: {readiness['pendingGeneralMutationSlots']}개",
            f"- 미생성 역문항 변형 오답 슬롯: {readiness['pendingInverseMutationSlots']}개",
            f"- 미생성 `옳지 않은 것` 문항: {readiness['pendingInverseQuestions']}개",
            "",
            "공유 앵커·구별축은 근거 데이터가 없어서 임베딩 유사도나 같은 도메인으로 임의 생성하지 않았다. "
            "따라서 이번 결과는 문장 사전 검수본이며 완성된 v3 문항은행이 아니다.",
            "",
            "## 임베딩 실행",
            "",
            "| 후보 | 상태 | revision | cache | 차원 |",
            "|---|---|---|---:|---:|",
        )
    )
    for embedding in report["embeddings"]:
        lines.append(
            f"| `{embedding['candidateId']}` | {embedding['status']} | "
            f"`{embedding['revisionResolved'] or embedding['revisionRequested']}` | "
            f"{embedding['cacheHit']} | {embedding['dimensions'] or '-'} |"
        )
    lines.extend(
        (
            "",
            "## validation 상위 20개 실행",
            "",
            "| 단계 | 임베딩 | 검색 비율 | 랭커 | NDCG@2 | strong P@2 | P@2 | Recall@20 |",
            "|---|---|---|---|---:|---:|---:|---:|",
        )
    )
    priorities = report["embeddingPriorities"]
    successful = [item for item in report["runs"] if item["status"] == "completed"]
    top_runs: list[Mapping[str, Any]] = []
    remaining = list(successful)
    while remaining and len(top_runs) < 20:
        picked = select_validation_run(remaining, priorities)
        top_runs.append(picked)
        remaining.remove(picked)
    for run in top_runs:
        metric = run["validation"]
        lines.append(
            f"| {run['stage']} | `{run['embeddingId']}` | `{run['retrievalProfileId']}` | "
            f"`{run['rankerId']}` | {metric['ndcgAt2']:.6f} | "
            f"{metric['strongPrecisionAt2']:.6f} | {metric['precisionAt2']:.6f} | "
            f"{metric['retrievalRecallAt20']:.6f} |"
        )
    lines.extend(
        (
            "",
            "## 산출물 및 비반영 확인",
            "",
            f"- 전체 실행 JSON: `{report['artifacts']['jsonReport']}`",
            f"- 검수 Markdown: `{report['artifacts']['choiceReview']}`",
            f"- 선택 모델(빌드 캐시): `{report['artifacts']['selectedModel']}`",
            "- Admin/Supabase 기록: 없음",
            "- 체크인 문항은행 변경: 없음",
            "- Android 콘텐츠 변경: 없음",
            "",
            "## 레퍼런스",
            "",
        )
    )
    for reference in report["methodReferences"]:
        lines.append(f"- [{reference['title']}]({reference['url']})")
    return "\n".join(lines)


def run_experiment(
    *,
    config_path: Path = base.DEFAULT_CONFIG,
    elements_path: Path = base.DEFAULT_ELEMENTS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    build_dir: Path = DEFAULT_BUILD_DIR,
    embedding_ids: Sequence[str] = (),
    device: str = "cpu",
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    output, build = _output_policy(output_dir, build_dir)
    config = base._load_json_object(base._resolve_repo_path(config_path))
    v3 = _v3_config(config)
    elements = base.load_elements(base._resolve_repo_path(elements_path))
    assignments, split_manifest = base.build_split(elements, config)
    _, questions = base.build_facts_and_questions(elements, assignments)
    if {item.question_type for item in questions} != set(GENERAL_QUESTION_TYPES):
        raise base.ConceptModelError("Unexpected general question set for v3 experiment")
    fusion = config.get("fusionBaseline")
    if not isinstance(fusion, Mapping):
        raise base.ConceptModelError("fusionBaseline is missing")
    rrf_k = int(fusion.get("rrfK", 60))
    strong_count = int(v3.get("strongCandidateCount", 2))
    relevant_count = int(v3.get("relevantCandidateCount", 6))
    review_depth = int(v3.get("weakReviewDepth", 20))
    print("[v3] building equal-weight weak-label context", flush=True)
    context = build_v3_feature_context(
        elements,
        questions,
        _weak_profile(config),
        rrf_k,
        strong_count,
        relevant_count,
        review_depth,
    )

    specs = [item for item in config.get("embeddingCandidates", []) if isinstance(item, Mapping)]
    specs_by_id = {str(item.get("id")): item for item in specs}
    requested = list(embedding_ids) or [str(item["id"]) for item in specs]
    unknown = sorted(set(requested) - set(specs_by_id))
    if unknown:
        raise base.ConceptModelError(f"Unknown v3 embedding ids: {unknown}")
    pins = v3.get("embeddingRevisionPins")
    if not isinstance(pins, Mapping):
        raise base.ConceptModelError("v3 embedding revision pins are missing")
    embeddings: list[base.EmbeddingRun] = []
    for index, candidate_id in enumerate(requested, start=1):
        print(f"[v3] embedding {index}/{len(requested)}: {candidate_id}", flush=True)
        if candidate_id == "tfidf-word-char":
            embeddings.append(base.baseline_embedding_run(context))
            continue
        spec = dict(specs_by_id[candidate_id])
        pin = str(pins.get(candidate_id, "")).strip()
        if not pin:
            raise base.ConceptModelError(f"Missing resolved revision pin: {candidate_id}")
        spec["revision"] = pin
        embeddings.append(
            load_or_run_embedding(
                spec, context, base.DEFAULT_BUILD_DIR / "embeddings", device
            )
        )
    completed = {item.candidate_id: item for item in embeddings if item.status == "completed"}
    if "tfidf-word-char" not in completed:
        raise base.ConceptModelError("The reference TF-IDF baseline must be included")

    reference_profiles = [
        item for item in config.get("retrievalProfiles", []) if isinstance(item, Mapping)
    ]
    variants = _ranker_variants(config)
    retrieval_limit = int(config.get("retrievalLimit", 30))
    max_pairs = int(config.get("pairwiseMaxPairsPerQuestion", 80))
    seed = int(config.get("splitSeed", 0))
    runs: list[dict[str, Any]] = []
    expected_stage1 = sum(
        sum(
            embedding.query_candidate_similarity is not None
            or (
                float(profile.get("questionSemantic", 0)) == 0
                and float(profile.get("answerSemantic", 0)) == 0
            )
            for profile in reference_profiles
        )
        * len(variants)
        for embedding in completed.values()
    )
    progress = 0
    for embedding in completed.values():
        for profile in reference_profiles:
            semantic = float(profile.get("questionSemantic", 0)) + float(
                profile.get("answerSemantic", 0)
            )
            if embedding.query_candidate_similarity is None and semantic > 0:
                continue
            shared_retrieved = base.retrieve_candidates(
                context, embedding, retrieval_limit, profile, rrf_k
            )
            for variant in variants:
                runs.append(
                    _run_one(
                        stage="reference-grid",
                        context=context,
                        embedding=embedding,
                        profile=profile,
                        variant=variant,
                        retrieval_limit=retrieval_limit,
                        rrf_k=rrf_k,
                        seed=seed,
                        max_pairs=max_pairs,
                        retrieved=shared_retrieved,
                    )
                )
                progress += 1
                if progress % 10 == 0 or progress == expected_stage1:
                    print(f"[v3] stage 1: {progress}/{expected_stage1}", flush=True)

    priorities = {str(item["id"]): int(item.get("priority", 999)) for item in specs}
    dense_best = []
    for embedding_id, embedding in completed.items():
        if embedding.query_candidate_similarity is None:
            continue
        embedding_runs = [
            item
            for item in runs
            if item["stage"] == "reference-grid" and item["embeddingId"] == embedding_id
        ]
        dense_best.append(select_validation_run(embedding_runs, priorities))
    dense_best_ordered: list[Mapping[str, Any]] = []
    remaining_dense = list(dense_best)
    while remaining_dense:
        selected_dense = select_validation_run(remaining_dense, priorities)
        dense_best_ordered.append(selected_dense)
        remaining_dense.remove(selected_dense)
    top_dense = dense_best_ordered[: int(v3.get("fineSearchEmbeddingCount", 2))]
    fine_profiles = fine_ratio_profiles(v3)
    stage2_total = len(top_dense) * len(fine_profiles)
    progress = 0
    for best in top_dense:
        embedding = completed[str(best["embeddingId"])]
        variant = _variant_from_run(best)
        for profile in fine_profiles:
            runs.append(
                _run_one(
                    stage="ratio-search",
                    context=context,
                    embedding=embedding,
                    profile=profile,
                    variant=variant,
                    retrieval_limit=retrieval_limit,
                    rrf_k=rrf_k,
                    seed=seed,
                    max_pairs=max_pairs,
                )
            )
            progress += 1
            if progress % 10 == 0 or progress == stage2_total:
                print(f"[v3] stage 2: {progress}/{stage2_total}", flush=True)

    stage2_runs = [item for item in runs if item["stage"] == "ratio-search"]
    best_ratio = select_validation_run(stage2_runs, priorities)
    ratio_profile_selected = _profile_from_run(best_ratio)
    stage3_profiles = refinement_profiles(v3, ratio_profile_selected)
    embedding = completed[str(best_ratio["embeddingId"])]
    variant = _variant_from_run(best_ratio)
    for index, profile in enumerate(stage3_profiles, start=1):
        runs.append(
            _run_one(
                stage="ratio-refinement",
                context=context,
                embedding=embedding,
                profile=profile,
                variant=variant,
                retrieval_limit=retrieval_limit,
                rrf_k=rrf_k,
                seed=seed,
                max_pairs=max_pairs,
            )
        )
        if index % 5 == 0 or index == len(stage3_profiles):
            print(f"[v3] stage 3: {index}/{len(stage3_profiles)}", flush=True)

    selected = select_validation_run(runs, priorities)
    selected_embedding = completed[str(selected["embeddingId"])]
    selected_profile = _profile_from_run(selected)
    selected_retrieved = base.retrieve_candidates(
        context, selected_embedding, retrieval_limit, selected_profile, rrf_k
    )
    selected_model = _train(
        context,
        selected_embedding,
        selected_retrieved,
        str(selected["rankerFamily"]),
        selected["hyperparameters"],
        seed,
        max_pairs,
    )
    selected_ranked = base.rank_candidates(
        context, selected_embedding, selected_retrieved, selected_model
    )
    validation = evaluate_at2(context, selected_retrieved, selected_ranked, "validation")
    test = evaluate_at2(context, selected_retrieved, selected_ranked, "test")
    selected["test"] = test
    selected["testEvaluated"] = True
    model_path, model_sha, model_bytes = base._model_artifact(
        build,
        str(selected["embeddingId"]),
        str(selected["retrievalProfileId"]),
        str(selected["rankerId"]),
        selected_model,
    )
    review_rows, review_audit = _review_rows(context, selected_embedding, selected_ranked)

    config_sha = hashlib.sha256(
        base._stable_json_bytes(config)
    ).hexdigest()
    experiment_id = (
        f"cmq-v3-{started_at.strftime('%Y%m%d-%H%M%S')}-{config_sha[:8]}"
    )
    json_path = output / f"{experiment_id}.json"
    markdown_path = output / f"{experiment_id}.md"
    review_path = output / f"{experiment_id}-choice-review.md"
    finished_at = datetime.now(timezone.utc)
    split_counts = Counter(item.split for item in questions)
    report: dict[str, Any] = {
        "experimentId": experiment_id,
        "reportVersion": 3,
        "contractVersion": CONTRACT_VERSION,
        "status": "review_required",
        "releaseReady": False,
        "releaseBlockReason": (
            "공유 앵커·구별축 사람 검수, 변형 오답, 역문항, 독립 평가가 완료되지 않음"
        ),
        "adminWritten": False,
        "questionBankWritten": False,
        "androidContentWritten": False,
        "startedAt": started_at.isoformat(),
        "finishedAt": finished_at.isoformat(),
        "durationSeconds": round(time.perf_counter() - started, 3),
        "dataset": {
            "contentFingerprint": base.content_fingerprint(elements),
            "configSha256": config_sha,
            "splitSha256": split_manifest["splitSha256"],
            "elementCount": len(elements),
            "generalQuestionCount": len(questions),
            "selectedCrossConceptChoiceCount": len(review_rows) * 2,
            "questionSplits": {
                name: split_counts[name] for name in ("train", "validation", "test")
            },
        },
        "weakSupervision": {
            "profileId": str(_weak_profile(config)["id"]),
            "strongCandidateCountPerQuestion": strong_count,
            "relevantCandidateCountPerQuestion": relevant_count,
            "reviewDepth": review_depth,
            "rrfK": rrf_k,
            "humanLabelCount": 0,
            "warning": "v2 승인·반려·수정은 v3에 승계하지 않았고 독립 사람 test 라벨도 없다.",
        },
        "embeddingPriorities": priorities,
        "embeddings": [item.report_dict() for item in embeddings],
        "runs": runs,
        "selection": {
            "embeddingId": selected["embeddingId"],
            "retrievalProfileId": selected["retrievalProfileId"],
            "retrievalProfile": selected["retrievalProfile"],
            "ratioTotals": selected.get("ratioTotals", {}),
            "rankerFamily": selected["rankerFamily"],
            "rankerId": selected["rankerId"],
            "hyperparameters": selected["hyperparameters"],
            "validationNdcgAt2": validation["ndcgAt2"],
            "modelSha256": model_sha,
            "modelBytes": model_bytes,
            "selectionRule": "validation-only strict lexicographic selection; test evaluated once after selection",
        },
        "evaluation": {
            "validation": validation,
            "test": test,
            "interpretation": "equal-weight weak-rule reproduction diagnostic, not independent educational quality",
        },
        "reviewAudit": review_audit,
        "readiness": {
            "crossConceptChoicesGenerated": len(review_rows) * 2,
            "reviewedSharedAnchorCount": 0,
            "reviewedDistinctAxisCount": 0,
            "pendingGeneralMutationSlots": len(questions) * 2,
            "pendingInverseMutationSlots": len(elements),
            "pendingInverseQuestions": len(elements),
            "adminUploadAllowed": False,
        },
        "methodReferences": [
            dict(item)
            for item in config.get("methodReferences", [])
            if isinstance(item, Mapping)
        ],
        "artifacts": {
            "jsonReport": base._report_path(json_path),
            "markdownReport": base._report_path(markdown_path),
            "choiceReview": base._report_path(review_path),
            "selectedModel": base._report_path(model_path),
        },
    }
    base._atomic_json(json_path, report)
    base._atomic_text(markdown_path, _render_report(report))
    base._atomic_text(
        review_path,
        _render_choice_review(experiment_id, report["selection"], review_rows, review_audit),
    )
    print(f"[v3] report: {base._report_path(markdown_path)}", flush=True)
    print(f"[v3] review: {base._report_path(review_path)}", flush=True)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=base.DEFAULT_CONFIG)
    parser.add_argument("--elements", type=Path, default=base.DEFAULT_ELEMENTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--embedding", action="append", default=[])
    parser.add_argument("--device", default="cpu")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    run_experiment(
        config_path=args.config,
        elements_path=args.elements,
        output_dir=args.output_dir,
        build_dir=args.build_dir,
        embedding_ids=args.embedding,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
