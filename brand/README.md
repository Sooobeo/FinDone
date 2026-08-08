# FinDone Brand Assets

FinDone은 개인 자산관리·가계부 앱이 아니라, **금융권 취업과 금융 학회 준비를 위한 개인 학습·리서치 도구**입니다.

대표 콘셉트는 **Folio Sprout**입니다. `F`의 세로획은 책등, 위·가운데 획은 펼쳐진 페이지이자 잎을 뜻합니다. 금융 지식과 리서치 역량이 쌓이며 성장한다는 의미를 담습니다. 코인, 지갑, 원화 기호, 저금통, 체크 표시, 단순 우상향 화살표처럼 개인 재무관리 서비스로 오인될 수 있는 요소는 사용하지 않습니다.

## 현재 콘셉트

- 버전: `Concept 01`
- 상태: 컬러와 대표 아이콘을 검토하기 위한 1차 시안
- 색상 비중: Neutral 80% · Research Teal 12% · Analysis Blue 5% · Insight Violet 3%
- 대표 아이콘: `Folio Sprout`
- Figma 원본: [FinDone — Study Brand Concept 01](https://www.figma.com/design/eWpCQT10jgqx0cf3pS2eU9)

## SVG 파일 안내

파일명은 모두 소문자 kebab-case를 사용하고 `findone-` 접두사로 시작합니다.

| 파일 | 상태 | 의미와 용도 | 색상 방식 | 기준 크기 |
|---|---|---|---|---:|
| `logo/findone-mark-brand.svg` | 현재 | 배경이 없는 컬러 대표 마크. 소개 화면, 문서 표지, 브랜드 영역에 사용 | 고정 브랜드 컬러 | `64 × 64` |
| `logo/findone-mark-current.svg` | 현재 | 한 색으로 표시하는 대표 마크. 작은 헤더, 단색 인쇄, UI 내부에 사용 | `currentColor` | `64 × 64` |
| `logo/findone-app-icon.svg` | 현재 | 밝은 타일 위에 대표 마크를 배치한 앱 아이콘 콘셉트 | 고정 브랜드 컬러 | `64 × 64` |
| `preview/findone-brand-concept.svg` | 현재 | 대표 아이콘, 의미, 컬러를 한 화면에서 검토하는 콘셉트 보드 | 고정 브랜드 컬러 | `1200 × 760` |
| `logo/findone-mark-micro.svg` | 예정 | 16–20px에서 잎맥을 제거하고 형태를 단순화한 마이크로 마크 | `currentColor` | `24 × 24` |
| `logo/findone-wordmark-horizontal-brand.svg` | 예정 | 마크와 `FinDone` 이름을 가로로 조합한 기본 로고 | 고정 브랜드 컬러 | 별도 확정 |
| `logo/findone-wordmark-horizontal-current.svg` | 예정 | 문서·인쇄용 단색 가로 로고 | `currentColor` | 별도 확정 |
| `logo/findone-app-icon-master.svg` | 예정 | 플랫폼별 PNG를 만들기 위한 최종 정사각형 마스터 | 고정 브랜드 컬러 | `1024 × 1024` |

`현재`는 지금 바로 검토하거나 사용할 수 있는 파일이고, `예정`은 이번 콘셉트가 확정된 뒤 추가 export할 파일입니다.

Figma에서 최종 확인한 렌더는 `preview/findone-brand-concept.png`에 함께 저장되어 있습니다.

## 컬러

| 역할 | 이름 | HEX | 사용처 |
|---|---|---:|---|
| 최외곽 배경 | Canvas | `#FBFCFB` | 앱 바깥 배경, 넓은 여백 |
| 기본 배경 | Paper | `#F7F9F8` | 학습 화면, 문서형 화면 |
| 보조 표면 | Surface | `#EEF3F2` | 카드, 구분 패널 |
| 기본 글자 | Ink | `#162321` | 제목, 본문, 대표 마크의 책등 |
| 보조 글자 | Ink Secondary | `#435550` | 설명, 보조 정보 |
| 약한 글자 | Muted | `#5A6B67` | 날짜, 출처, 메타데이터 |
| 장식 테두리 | Border | `#CBD8D5` | 카드 구분선 전용 |
| 강한 윤곽 | Strong Outline | `#748B85` | 입력 영역, 선택 윤곽 |
| 대표색 | Research Teal | `#246B65` | 브랜드, 핵심 선택 상태 |
| 대표색 연한 면 | Teal Soft | `#DCECE8` | 선택 배경, 하이라이트 |
| 분석색 | Analysis Blue | `#335E85` | 데이터, 자료, 링크 |
| 분석색 연한 면 | Blue Soft | `#E2EAF2` | 자료 카드, 정보 배경 |
| 인사이트색 | Insight Violet | `#66558B` | 개념 노트, 북마크, 학회 콘텐츠 |
| 인사이트색 연한 면 | Violet Soft | `#EAE5F2` | 인사이트 강조 배경 |

기본 본문 조합인 Ink/Paper 대비는 약 `15.3:1`, 흰색/Research Teal 대비는 약 `6.2:1`입니다. `Border`는 장식용 대비만 가지므로 입력창 경계나 포커스 표시에는 사용하지 않습니다.

실제 코드 토큰은 [`tokens/colors.css`](tokens/colors.css)와 [`tokens/colors.json`](tokens/colors.json)에 동일하게 기록되어 있습니다.

## 색상 방식

### 고정 브랜드 컬러

`*-brand.svg`, `findone-app-icon.svg`, `preview/` 파일은 SVG 내부에 브랜드 컬러가 포함되어 있습니다.

- CSS로 임의 recolor하지 않습니다.
- 채도, 명도, 투명도를 개별적으로 변경하지 않습니다.
- 기본적으로 Paper 또는 흰색 계열 배경에서 사용합니다.

### `currentColor`

`*-current.svg`와 향후 `icons/` 폴더에 들어갈 UI 아이콘은 `currentColor`를 사용합니다. 인라인 SVG나 컴포넌트로 사용할 때 부모의 `color` 값을 상속합니다.

```html
<span style="color: #246B65">
  <!-- inline SVG 권장 -->
</span>
```

`<img>`로 불러온 외부 SVG는 부모의 `color`를 직접 상속하지 않으므로, 동적 색상이 필요하면 인라인 SVG 또는 프레임워크 컴포넌트로 사용합니다.

## 크기와 여백

- 대표 마크 기준 ViewBox: `0 0 64 64`
- 대표 마크 권장 최소 크기: 컬러형 24px, 단색형 20px
- 20px 이하에서는 잎맥이 없는 `findone-mark-micro.svg`를 사용합니다.
- 마크 주위에는 마크 폭의 최소 1/4만큼 빈 공간을 확보합니다.
- SVG 비율을 늘이거나 찌그러뜨리지 않습니다.
- UI에서 실제 터치 영역은 시각적 마크 크기와 별도로 최소 40–44px를 확보합니다.

## 사용 금지

- 그림자, 외곽선, 그라데이션을 임의로 추가하지 않습니다.
- 로고 위에 글자나 다른 아이콘을 겹치지 않습니다.
- 복잡한 사진 위에 대비 없이 배치하지 않습니다.
- 코인, 지갑, 원화 기호, 저금통과 결합하지 않습니다.
- 순수 초록색과 우상향 차트를 결합해 투자 수익 앱처럼 보이게 하지 않습니다.
- Purple, Blue, Teal을 같은 비중의 주색으로 사용하지 않습니다.

## 접근성

- 장식용 SVG는 빈 대체 텍스트 또는 `aria-hidden="true"`를 사용합니다.
- 브랜드를 나타내는 로고에는 `alt="FinDone"`을 사용합니다.
- 아이콘만으로 동작을 전달할 때는 버튼이나 링크에 접근 가능한 이름을 별도로 제공합니다.
- 색만으로 학습 상태나 데이터 범주를 구분하지 않고 레이블·선 스타일·아이콘을 함께 사용합니다.

## 원본과 변경

Figma의 [FinDone — Study Brand Concept 01](https://www.figma.com/design/eWpCQT10jgqx0cf3pS2eU9) 파일을 시각적 원본으로 사용합니다. SVG를 직접 수정한 경우 Figma 원본, 이 문서, `tokens/colors.css`, `tokens/colors.json`을 함께 갱신합니다.
