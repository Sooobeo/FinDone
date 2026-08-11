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
            <path d="M20 3H44A17 17 0 0 1 61 20V44A17 17 0 0 1 44 61H20A17 17 0 0 1 3 44V20A17 17 0 0 1 20 3Z" fill="#f7f9f8" stroke="#cbd8d5" strokeWidth="1.5" />
            <path d="M20.5 12A3.5 3.5 0 0 1 24 15.5V48.5A3.5 3.5 0 0 1 17 48.5V15.5A3.5 3.5 0 0 1 20.5 12Z" fill="#162321" />
            <path d="M24 14.6C32.1 10.5 42.9 10.9 51 15.7C50.1 26 40.8 31.8 24 29.5Z" fill="#246b65" />
            <path d="M24 31.2C31 27.6 39.7 27.8 45.5 31.7C44.2 39.7 36.4 43.8 24 41Z" fill="#335e85" />
            <path d="M28.2 25.4C33.8 21.1 40.9 18.1 47.9 16.5" fill="none" stroke="#f7f9f8" strokeLinecap="round" strokeWidth="2.35" />
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
