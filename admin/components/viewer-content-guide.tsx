import { BookOpenCheck, CircleCheckBig, Eye, Layers3 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import type { ViewerGuide } from "@/lib/viewer-guides";

const sectionIcons = [Layers3, BookOpenCheck, CircleCheckBig, Eye] as const;

export function ViewerContentGuide({ guide }: { guide: ViewerGuide }) {
  return (
    <div className="page-stack viewer-guide-page">
      <PageHeader eyebrow={guide.eyebrow} title={guide.title} description={guide.description} />
      <section className="viewer-guide-notice" role="status">
        <span><Eye size={18} /></span>
        <div>
          <strong>Viewer 안내 모드</strong>
          <p>실제 콘텐츠 값, 원본 위치와 운영 이력은 표시하지 않습니다. 아래에서는 이 화면을 구성하는 정보의 종류만 설명합니다.</p>
        </div>
      </section>
      <section className="viewer-guide-grid" aria-label={`${guide.title} 항목 설명`}>
        {guide.sections.map((section, index) => {
          const Icon = sectionIcons[index % sectionIcons.length];
          return (
            <article className="panel viewer-guide-card" key={section.title}>
              <span className="viewer-guide-icon"><Icon size={20} /></span>
              <p className="eyebrow">CONTENT FIELD {String(index + 1).padStart(2, "0")}</p>
              <h2>{section.title}</h2>
              <p>{section.description}</p>
              <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul>
            </article>
          );
        })}
      </section>
    </div>
  );
}
