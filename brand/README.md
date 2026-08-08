# FinDone Brand Assets

FinDone은 개인 자산관리 앱이 아니라, 금융권 취업·금융 학회·산업 리서치를 준비하기 위한 개인 학습 도구입니다.

현재 대표 아이콘 콘셉트는 **Folio Sprout · Mono**입니다. 처음 제안한 세로 줄기와 두 장의 잎 형태로 돌아가되, 모든 요소를 `Research Teal #246B65` 한 색으로 통일했습니다. 동전, 지갑, 통화 기호, 상승 차트처럼 자산관리 앱으로 오해될 만한 요소는 사용하지 않습니다.

## 현재 콘셉트

- 버전: `Concept 03`
- 대표 아이콘: `Folio Sprout · Mono`
- 의미: 안정적인 학습 축 + 리서치를 통해 자라는 지식
- 아이콘 유채색: `Research Teal #246B65` 한 가지
- 표현 방식: 평면 단색, 그라데이션·그림자·반사광 없음
- Figma 원본: [FinDone · Study Brand Concept](https://www.figma.com/design/eWpCQT10jgqx0cf3pS2eU9)

## SVG 파일 안내

| 파일 | 상태 | 용도 | 색상 방식 | 기준 크기 |
|---|---|---|---|---:|
| `logo/findone-mark-brand.svg` | 현재 | 배경이 없는 고정 컬러 대표 마크. 소개 화면, 문서 표지, 브랜드 영역에 사용 | `#246B65` | `64 × 64` |
| `logo/findone-app-icon.svg` | 현재 | 밝은 Paper 타일 위에 단색 대표 마크를 배치한 앱 아이콘 | `#246B65` + 중립 배경 | `64 × 64` |
| `logo/findone-mark-current.svg` | 현재 | 같은 형태의 동적 단색 마크. UI, 단색 인쇄, 테마 대응에 사용 | `currentColor` | `64 × 64` |
| `logo/findone-mark-micro.svg` | 현재 | 16–20px에서도 형태가 유지되도록 축소한 버전 | `currentColor` | `24 × 24` |
| `preview/findone-brand-concept.svg` | 현재 | 대표 아이콘과 기존 제품 팔레트를 함께 확인하는 콘셉트 보드 | 고정 브랜드 컬러 | `1200 × 760` |
| `logo/findone-wordmark-horizontal-brand.svg` | 예정 | 마크와 `FinDone` 이름을 가로로 조합한 기본 로고 | 고정 브랜드 컬러 | 추후 확정 |
| `logo/findone-wordmark-horizontal-current.svg` | 예정 | 문서·인쇄용 단색 가로 로고 | `currentColor` | 추후 확정 |
| `logo/findone-app-icon-master.svg` | 예정 | 스토어 및 PWA용 PNG를 만들기 위한 1024px 마스터 | 고정 브랜드 컬러 | `1024 × 1024` |

`현재` 파일은 바로 사용할 수 있고, `예정` 파일은 대표 아이콘 확정 후 추가로 export할 파일입니다. Figma 미리보기는 `preview/findone-brand-concept.png`에도 저장합니다.

## 아이콘 색상 원칙

- 고정 컬러 아이콘의 유채색은 `#246B65`만 사용합니다.
- 줄기와 두 장의 잎에 색상 차이를 두지 않습니다.
- 위·아래 잎은 줄기에는 각각 붙지만 서로 맞닿지 않도록 일정한 세로 간격을 둡니다.
- 그라데이션, 반사광, 드롭 섀도, 입체 외곽선을 사용하지 않습니다.
- Paper 배경과 중립 테두리는 앱 타일의 표면이며 아이콘 색상에 포함하지 않습니다.
- 다른 색이 필요한 UI에서는 `findone-mark-current.svg`에 부모의 `color`를 상속합니다.

## 제품 팔레트

대표 아이콘은 단일 Teal이지만, 앱 화면에 사용할 기존 제품 팔레트는 유지합니다.

| 역할 | 이름 | HEX |
|---|---|---:|
| 최외곽 배경 | Canvas | `#FBFCFB` |
| 기본 배경 | Paper | `#F7F9F8` |
| 보조 표면 | Surface | `#EEF3F2` |
| 기본 글자 | Ink | `#162321` |
| 보조 글자 | Ink Secondary | `#435550` |
| 약한 글자 | Muted | `#5A6B67` |
| 장식 테두리 | Border | `#CBD8D5` |
| 강한 외곽선 | Strong Outline | `#748B85` |
| 브랜드·핵심 상태 | Research Teal | `#246B65` |
| 데이터·자료 | Analysis Blue | `#335E85` |
| 개념 노트·인사이트 | Insight Violet | `#66558B` |

실제 코드용 전체 토큰은 [`tokens/colors.css`](tokens/colors.css)와 [`tokens/colors.json`](tokens/colors.json)에 있습니다.

## 크기와 사용

- 고정 컬러 마크 권장 최소 크기: `24px`
- `20px` 이하: `findone-mark-micro.svg` 사용
- 마크 주변에는 마크 폭의 최소 1/4만큼 여백 확보
- 클릭·탭 영역은 시각적 아이콘과 별도로 최소 `40–44px` 확보
- 고정 컬러 SVG는 `<img>`로 사용하고, 동적 단색 아이콘은 인라인 SVG로 사용

## 금지 사항

- 아이콘 비율을 늘이거나 찌그러뜨리지 않습니다.
- 줄기와 잎에 서로 다른 유채색을 사용하지 않습니다.
- 그라데이션, 그림자, 광택, 입체 효과를 추가하지 않습니다.
- 동전, 지갑, 통화 기호, 상승 화살표와 결합하지 않습니다.
- 복잡한 사진 위에 대비 없이 배치하지 않습니다.

## 접근성

- 장식용 마크는 빈 대체 텍스트 또는 `aria-hidden="true"`를 사용합니다.
- 브랜드를 식별하는 로고에는 `alt="FinDone"`을 사용합니다.
- 아이콘만 있는 버튼은 버튼 자체에 접근 가능한 이름을 제공합니다.
- 상태와 데이터는 색상만으로 구분하지 않고 라벨·선 스타일을 함께 사용합니다.
