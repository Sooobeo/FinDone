export type WorkbookTheoryKind = "section" | "element" | "concept" | "label" | "bullet" | "body";

export interface WorkbookTheoryBlock {
  kind: WorkbookTheoryKind;
  text: string;
}

export interface WorkbookSolutionSegment {
  labelled: boolean;
  text: string;
}

export interface WorkbookQuestion {
  id: string;
  difficulty: number;
  kind: string;
  stem: string;
  choices: [string, string, string, string, string];
  evidence: string;
  answerIndex: 0 | 1 | 2 | 3 | 4;
  solution: WorkbookSolutionSegment[];
}

export interface WorkbookUnitSummary {
  id: string;
  anchor: string;
  title: string;
  questionCount: number;
}

export interface WorkbookSubject {
  id: string;
  title: string;
  units: WorkbookUnitSummary[];
}

export interface WorkbookIndex {
  schemaVersion: 1;
  source: {
    fileName: string;
    sha256: string;
    title: string;
  };
  stats: {
    subjectCount: number;
    unitCount: number;
    questionCount: number;
    conceptElementCount: number;
    glossaryTermCount: number;
  };
  subjects: WorkbookSubject[];
}

export interface WorkbookUnit {
  schemaVersion: 1;
  sourceSha256: string;
  id: string;
  anchor: string;
  subjectId: string;
  subjectTitle: string;
  title: string;
  subtitle: string;
  meta: string[];
  sourceNote: string;
  theory: WorkbookTheoryBlock[];
  questions: WorkbookQuestion[];
}
