const BLOCKED_HOST_SUFFIXES = [
  ".localhost",
  ".local",
  ".internal",
  ".home.arpa",
  ".nip.io",
  ".sslip.io",
  ".xip.io",
];

export function parsePublicSourceUrl(value: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error("http 또는 https URL을 정확히 입력해 주세요.");
  }
  if (!/^https?:$/.test(parsed.protocol)) {
    throw new Error("http 또는 https URL만 등록할 수 있습니다.");
  }
  if (parsed.username || parsed.password) {
    throw new Error("계정 정보가 포함된 URL은 등록할 수 없습니다.");
  }
  const hostname = parsed.hostname.toLocaleLowerCase("en-US").replace(/\.$/, "");
  if (
    !hostname.includes(".")
    || hostname === "localhost"
    || hostname.startsWith("[")
    || /^[0-9.]+$/.test(hostname)
    || hostname.includes("..")
    || hostname.split(".").some((label) => label.startsWith("-") || label.endsWith("-"))
    || BLOCKED_HOST_SUFFIXES.some((suffix) => hostname.endsWith(suffix))
  ) {
    throw new Error("내부망·로컬·IP 주소는 원본 URL로 등록할 수 없습니다.");
  }
  if (parsed.toString().length > 2048) throw new Error("URL은 2,048자 이하여야 합니다.");
  return parsed;
}
