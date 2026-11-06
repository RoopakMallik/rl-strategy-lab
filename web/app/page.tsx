import { AssistantAnswers } from "@/components/AssistantAnswers";
import { Evaluations } from "@/components/Evaluations";
import { HeadlineStats } from "@/components/HeadlineStats";
import { MethodNotes } from "@/components/MethodNotes";
import { ResultsExplorer } from "@/components/ResultsExplorer";
import { SnapshotHeader } from "@/components/SnapshotHeader";
import { loadSnapshot } from "@/lib/loadSnapshot";

export default function DashboardPage() {
  const { dashboard, equityCurves, assistantAnswers } = loadSnapshot();
  return (
    <main className="page">
      <SnapshotHeader dashboard={dashboard} />
      <HeadlineStats dashboard={dashboard} />

      <section className="section" aria-labelledby="results-title">
        <h2 id="results-title">Results</h2>
        <ResultsExplorer strategies={dashboard.strategies} baselines={dashboard.baselines}
          equityCurves={equityCurves} configuration={dashboard.configuration} />
      </section>

      <section className="section" aria-labelledby="assistant-title">
        <h2 id="assistant-title">Ask the results</h2>
        <AssistantAnswers file={assistantAnswers} />
      </section>

      <section className="section" aria-labelledby="evaluations-title">
        <h2 id="evaluations-title">Evaluations</h2>
        <Evaluations evaluations={dashboard.evaluations} />
      </section>

      <section className="section" aria-labelledby="method-title">
        <h2 id="method-title">Method</h2>
        <MethodNotes configuration={dashboard.configuration} />
      </section>

      <footer className="footer">
        A static snapshot: the live system runs on a laptop with PostgreSQL and a local model, which this site
        cannot reach. The data behind this page:{" "}
        <a href="data/dashboard.json">dashboard.json</a>, <a href="data/equity_curves.json">equity_curves.json</a>,{" "}
        <a href="data/assistant_answers.json">assistant_answers.json</a>.
      </footer>
    </main>
  );
}
