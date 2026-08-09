package com.findone.app.ui

/**
 * Returns an intentionally authored list summary instead of clipping the element body or formula.
 * The title is repeated as a label so every row remains specific even within the same domain.
 */
internal fun learningElementSummary(domainId: String, title: String): String {
    val subject = title.trim().ifEmpty { "이 학습요소" }
    val summary = when (domainId.trim().uppercase()) {
        "ACC" -> "재무제표 수치와 회계 판단의 연결을 익힙니다."
        "CF" -> "현금흐름의 원인과 기업가치 영향을 판단하는 방법을 익힙니다."
        "INV" -> "투자 의사결정에 필요한 위험·수익 분석을 익힙니다."
        "FI" -> "금리·채권·신용위험의 변화를 해석하는 방법을 익힙니다."
        "DER" -> "파생상품의 구조와 손익·헤지 효과를 익힙니다."
        "EQV" -> "기업가치와 주식가치 산정에 적용하는 방법을 익힙니다."
        "IBT" -> "면접 답변과 금융 실무 커뮤니케이션에 활용하는 방법을 익힙니다."
        else -> "핵심 원리와 실무 적용 기준을 익힙니다."
    }
    return "$subject: $summary"
}
