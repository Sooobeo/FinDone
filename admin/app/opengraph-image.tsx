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
            <path
              d="M20 4H44C52.8366 4 60 11.1634 60 20V44C60 52.8366 52.8366 60 44 60H9C6.23858 60 4 57.7614 4 55V20C4 11.1634 11.1634 4 20 4Z"
              fill="#f7fbfa"
              stroke="#cbd8d5"
            />
            <path d="M17 14H48V22H29V29H44V37H29V50H17V14Z" fill="#174e4a" />
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
