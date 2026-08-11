import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  ChartNoAxesCombined,
  ClipboardCheck,
  Home,
  ListChecks,
  PanelsTopLeft,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { getIntroNavigation, getIntroSection, introSlugs, type IntroSlug } from "@/lib/app-intro";

const icons = {
  overview: ChartNoAxesCombined,
  today: Home,
  study: BookOpenText,
  quiz: ListChecks,
  records: ClipboardCheck,
  admin: PanelsTopLeft,
} as const;

const appScreenImages = {
  today: "/app-intro/today.svg",
  study: "/app-intro/study.svg",
  quiz: "/app-intro/quiz.svg",
  records: "/app-intro/records.svg",
} as const;

const screenImages: Record<Exclude<IntroSlug, "overview">, string> = {
  ...appScreenImages,
  admin: "/app-intro/admin.svg",
};

function introHref(slug: IntroSlug) {
  return slug === "overview" ? "/about" : `/about/${slug}`;
}

function inlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
      : part,
  );
}

function MarkdownCopy({ source }: { source: string }) {
  const nodes: ReactNode[] = [];
  const lines = source.split(/\r?\n/);
  let paragraph: string[] = [];
  let list: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const value = paragraph.join(" ");
    nodes.push(<p key={`p-${nodes.length}`}>{inlineMarkdown(value)}</p>);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    nodes.push(<ul key={`ul-${nodes.length}`}>{list.map((item, index) => <li key={`${item}-${index}`}>{inlineMarkdown(item)}</li>)}</ul>);
    list = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
    } else if (line.startsWith("## ")) {
      flushParagraph();
      flushList();
      nodes.push(<h2 key={`h2-${nodes.length}`}>{line.slice(3)}</h2>);
    } else if (line.startsWith("### ")) {
      flushParagraph();
      flushList();
      nodes.push(<h3 key={`h3-${nodes.length}`}>{line.slice(4)}</h3>);
    } else if (line.startsWith("- ")) {
      flushParagraph();
      list.push(line.slice(2));
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return <div className="intro-markdown">{nodes}</div>;
}

function AppVisual({ slug, title }: { slug: IntroSlug; title: string }) {
  if (slug === "overview") {
    return (
      <div className="intro-screen-collage" role="img" aria-label="FinDone 앱의 오늘, 학습, 퀴즈, 기록 화면 미리보기">
        {(Object.entries(appScreenImages) as [keyof typeof appScreenImages, string][]).map(([key, src]) => (
          <img key={key} src={src} alt="" />
        ))}
      </div>
    );
  }
  if (slug === "admin") {
    return <img className="intro-admin-image" src={screenImages[slug]} alt={`${title} 관리 및 앱 업데이트 흐름`} />;
  }
  return <img className="intro-phone-image" src={screenImages[slug]} alt={`${title} 앱 화면 미리보기`} />;
}

export async function AppIntroPage({ slug }: { slug: IntroSlug }) {
  const [section, navigation] = await Promise.all([getIntroSection(slug), getIntroNavigation()]);
  const currentIndex = introSlugs.indexOf(slug);
  const previous = currentIndex > 0 ? navigation[currentIndex - 1] : null;
  const next = currentIndex < navigation.length - 1 ? navigation[currentIndex + 1] : null;

  return (
    <main className="intro-page">
      <header className="intro-header">
        <Link className="intro-brand" href="/login" aria-label="로그인 페이지로 돌아가기">
          <img src="/brand/findone-admin-icon.svg" alt="" />
          <span><strong>FinDone</strong><small>APP GUIDE</small></span>
        </Link>
      </header>

      <div className="intro-shell">
        <nav className="intro-nav" aria-label="앱 소개 페이지">
          <p>APP PAGES</p>
          {navigation.map((item) => {
            const Icon = icons[item.slug];
            return (
              <Link key={item.slug} className={item.slug === slug ? "active" : ""} href={introHref(item.slug)} aria-current={item.slug === slug ? "page" : undefined}>
                <Icon size={17} /><span>{item.navLabel}</span>
              </Link>
            );
          })}
        </nav>

        <article className="intro-content">
          <section className="intro-copy-panel">
            {section.eyebrow ? <p className="eyebrow">{section.eyebrow}</p> : null}
            <h1>{section.title}</h1>
            <p className="intro-summary">{section.summary}</p>
            <MarkdownCopy source={section.body} />
            <div className="intro-page-links">
              {previous ? <Link href={introHref(previous.slug)}><ArrowLeft size={15} /> {previous.navLabel}</Link> : <span />}
              {next ? <Link href={introHref(next.slug)}>{next.navLabel} <ArrowRight size={15} /></Link> : <Link href="/login">로그인으로 <ArrowRight size={15} /></Link>}
            </div>
          </section>
          <section className={`intro-visual-panel intro-visual-${slug}`}>
            <AppVisual slug={slug} title={section.title} />
          </section>
        </article>
      </div>
    </main>
  );
}
