import { ImageResponse } from "next/og";

export const alt = "FinDone Content Admin";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          alignItems: "center",
          background:
            "radial-gradient(circle at 72% 18%, rgba(79, 132, 122, 0.34), transparent 34%), linear-gradient(135deg, #315f5a 0%, #183a37 100%)",
          color: "#f7f9f8",
          display: "flex",
          flexDirection: "column",
          height: "100%",
          justifyContent: "center",
          width: "100%",
        }}
      >
        <div style={{ alignItems: "center", display: "flex" }}>
          <svg
            aria-hidden="true"
            height={156}
            viewBox="0 0 64 64"
            width={156}
          >
            <rect
              fill="#f7f9f8"
              height="56"
              rx="16"
              stroke="#cbd8d5"
              width="56"
              x="4"
              y="4"
            />
            <g fill="#246b65">
              <rect height="38" rx="3.5" width="7" x="18" y="13" />
              <path d="M25 15.5C32.5 11.5 42.5 11.8 50 16.2C49.2 24.8 40.5 29.2 25 27.6V15.5Z" />
              <path d="M25 33.6C31.5 30.5 39.5 30.8 45 34.1C43.8 41.2 36.5 44.8 25 42.3V33.6Z" />
            </g>
          </svg>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              marginLeft: "38px",
            }}
          >
            <div
              style={{
                fontSize: "104px",
                fontWeight: 700,
                letterSpacing: "-5px",
                lineHeight: 1,
              }}
            >
              FinDone
            </div>
            <div
              style={{
                fontSize: "25px",
                fontWeight: 600,
                letterSpacing: "11px",
                marginLeft: "5px",
                marginTop: "18px",
                opacity: 0.76,
              }}
            >
              CONTENT ADMIN
            </div>
          </div>
        </div>
        <div
          style={{
            borderTop: "1px solid rgba(247, 249, 248, 0.22)",
            fontSize: "27px",
            letterSpacing: "2px",
            marginTop: "68px",
            paddingTop: "28px",
            textAlign: "center",
            width: "760px",
          }}
        >
          학습 콘텐츠 제작 · 검수 · 배포
        </div>
      </div>
    ),
    size,
  );
}
