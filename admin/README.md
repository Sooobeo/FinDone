# FinDone Admin

FinDone 앱의 개념 콘텐츠, 원본 자료, 오답 후보, 검수 및 릴리스를 관리하는 Next.js 관리자 화면입니다.

`scripts/start_admin.ps1`은 Supabase 설정이 없을 때만 명시적인 읽기 전용 데모로 실행합니다. 운영 배포는 환경변수가 비어 있으면 fail-closed 설정 오류 화면을 표시하며 실제 앱 fixture를 공개하지 않습니다. Supabase를 연결하려면 `.env.local`에 아래 값을 설정합니다.

```text
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
```

`SUPABASE_SECRET_KEY`는 서버의 `/api/content/stable`이 private 릴리스 파일의 짧은 signed URL을 만들 때만 사용합니다. 브라우저 공개 변수에 넣거나 `NEXT_PUBLIC_` 접두사를 붙이면 안 됩니다.

직접 `npm run dev`로 데모를 열 때만 `NEXT_PUBLIC_FINDONE_ADMIN_DEMO=1`을 설정합니다. 데모는 production 빌드에서 항상 차단되며, 이 값과 Supabase 연결값을 동시에 설정해도 구성 오류로 차단됩니다.

`/signup`에서 이메일 회원가입을 제공하며 새 계정은 DB trigger에 의해 항상 `viewer`로만 생성됩니다. Viewer는 모든 화면을 조회할 수 있지만 편집·업로드·검수·배포 권한은 없습니다. 유일한 `owner`만 전체 작업을 수행합니다.

## 콘텐츠 편집 방식

- 개념 DB 화면에서 현재 앱의 7개 분야·135개 요소와 모든 설명을 검색하고 직접 수정할 수 있습니다.
- `내보내기`는 Excel에서 바로 여는 UTF-8 CSV를 생성합니다. 19개 열과 multiline Markdown을 보존하고, 수식 실행형 셀 값은 중립화합니다.
- `Excel CSV 가져오기`는 ID·분야·모드·상태 같은 고정 열을 잠그고 실제 변경 행만 하나의 트랜잭션으로 저장합니다.
- 랜덤 문제 템플릿은 관리하지 않습니다. 오답 후보 문구와 틀린 이유만 요소별로 관리합니다.

URL과 파일 등록은 비공개 Storage 및 작업 큐까지 구현돼 있습니다. 개념 revision 검증 Worker와 승인본 SQLite 릴리스 Worker는 분리되어 있고, 후자는 기준 DB에 승인 revision을 투영한 뒤 135개 요소·FTS·해시·SQLite 무결성을 재검증합니다. 검증에 성공하면 `stable` 채널까지 자동 공개되며 Android는 다음 실행 때 새 DB를 검증 후 교체합니다. 외부 URL fetch와 파일 파싱 Worker는 아직 별도 경계입니다.

최초 콘텐츠 import 도구는 이 디렉터리의 `.env.local` 또는 `.env`에서 공개 Supabase URL을 자동으로 읽습니다. Secret key는 파일에 저장하지 않고 실행 중인 터미널의 `SUPABASE_SECRET_KEY` 환경변수로만 전달합니다.
