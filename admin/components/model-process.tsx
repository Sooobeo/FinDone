import { ArrowDown, CheckCircle2, CircleDot, Database, FlaskConical, PackageCheck, ScanSearch } from "lucide-react";
import type { SectionedMarkdownSection } from "@/lib/sectioned-markdown";
import { markdownToPlainText, splitMarkdownSubsections } from "@/lib/sectioned-markdown";

const processIcons = [Database, ScanSearch, FlaskConical, PackageCheck, CheckCircle2];

export function ModelProcess({ section, viewer = false }: { section: SectionedMarkdownSection; viewer?: boolean }) {
  const steps = splitMarkdownSubsections(section.body);
  return (
    <section className={`panel model-process-panel ${viewer ? "viewer-model-process" : ""}`}>
      <div className="model-process-heading">
        <span><CircleDot size={20} /></span>
        <div>
          <p className="eyebrow">END-TO-END PIPELINE</p>
          {viewer ? <h1>{section.title}</h1> : <h2>{section.title}</h2>}
          <p>{section.lead}</p>
        </div>
      </div>
      <ol className="model-process-steps">
        {steps.map((step, index) => {
          const Icon = processIcons[index] ?? CircleDot;
          return (
            <li key={step.title}>
              <span className="model-process-icon"><Icon size={18} /></span>
              <div><strong>{step.title}</strong><p className="model-process-copy">{markdownToPlainText(step.body)}</p></div>
              {index < steps.length - 1 ? <ArrowDown className="model-process-arrow" size={14} aria-hidden="true" /> : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
