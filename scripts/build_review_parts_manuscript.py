"""Revise the working LaTeX draft using observed artifacts, with red changes."""
import argparse
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/extraction'))
from workflow_io import read_json,atomic_json,file_hash


def between(text,start,end,content):
    if text.count(start)!=1 or text.count(end)!=1:raise ValueError('Unexpected manuscript structure')
    left=text.index(start)+len(start);right=text.index(end,left)
    return text[:left]+'\n\n'+content.strip()+'\n\n'+text[right:]


def build(source,pilot,output):
    if output.exists():raise ValueError('Fresh manuscript revision directory required')
    summary=read_json(pilot/'summary.json')
    if summary['status']!='pilot_complete':raise ValueError('Do not describe an incomplete pilot as complete')
    diagnostics=read_json(pilot.parent/'pilot_analysis_final/descriptive_diagnostics.json')
    output.mkdir(parents=True)
    for p in source.iterdir():
        if p.suffix in {'.cls','.sty','.bib','.png','.jpg'} or p.name=='architecture_revision.pdf':shutil.copyfile(p,output/p.name)
    text=(source/'main.tex').read_text(encoding='utf-8')
    text=text.replace('what evidence or sample was used','which identified digital data were used')
    text=text.replace('The online workflow first decides',r'\rev{The following online architecture describes the historical interactive application; the bounded controlled pilot reported later uses Gemini 2.5 Flash and frozen retrieval contexts.} The online workflow first decides',1)
    text=text.replace('Dataset & Named dataset, benchmark, survey sample, or structured experimental collection on which a method was developed or evaluated.',
        r'Dataset & \rev{An identified digital dataset, database or corpus actually used; biological samples and specimens are not datasets.}')
    text=text.replace('Metric & Named quantitative measure or reported indicator used to assess a method or result; numeric values are stored separately.',
        r'Metric & \rev{A numerical measured outcome with explicit endpoint, value, unit, object, condition, uncertainty and report origin. Qualitative high/fast descriptions are excluded.}')
    text=text.replace('The four operational relations describe affiliation, empirical evaluation, measurement, and explicit conceptual association',
        r'\rev{The current strict schema uses five directed relation signatures, distinct from labels in the historical snapshot used for retrieval diagnostics. These cover affiliation, use, evaluation, measured outcomes and domain membership}')
    text=text.replace(r'\relname{EVALUATES}{ON} & Method $\rightarrow$ Dataset & Records the dataset, sample, or benchmark used to train, test, or validate a method.',
        r'\relname{EVALUATED}{ON} & Method $\rightarrow$ Dataset & \rev{Records an explicitly identified digital evaluation dataset.}')
    text=text.replace(r'\relname{MEASURED}{BY} & Method $\rightarrow$ Metric & Links a method or experimental result to the indicator used for quantitative assessment.',
        r'\relname{ACHIEVED}{} & Method $\rightarrow$ Metric & \rev{Links an actual method to a supported numerical outcome.}')
    text=text.replace(r'\relname{RELATED}{TO} & Concept $\rightarrow$ Concept & Represents an explicit scientific or topical association supported by the source section.',
        r'\relname{USED}{FOR} & Method $\rightarrow$ Concept & \rev{Connects a method to its supported task or investigated object.} \\'+'\n'+r'\relname{BELONGS}{TO} & Concept $\rightarrow$ Domain & \rev{Connects a concept to an explicitly supported scientific field.}')
    # ACHIEVED has no underscore, so do not manufacture one with the relation macro.
    text=text.replace(r'\relname{ACHIEVED}{}',r'\texttt{ACHIEVED}')
    text=text.replace(r'\label{tab:relations}'+'\n'+r'\small',r'\label{tab:relations}'+'\n'+r'\small\color{red}')
    text=text.replace(r'\label{alg:offline-kg}'+'\n'+r'\small',r'\label{alg:offline-kg}'+'\n'+r'\small\color{red}')
    text=between(text,r'\subsection{LLM-Based Entity and Relation Extraction}',r'\subsection{Entity Normalization}',r'''
\rev{The historical extraction artifacts and the revised extractor are separate versions. Strict v3.1 uses Gemini 2.5 Flash, temperature zero, no automatic paid retry, and a 16,384-token maximum output. It separates a technical entity identifier from the literal source-preserving name. Relation endpoints use identifiers; author and institution grounding uses names in header evidence. No model self-confidence threshold is treated as source support.}

\rev{The transport returns source-bound evidence identifiers. The code resolves them to text and character offsets and rejects unknown identifiers, unsupported labels, unresolved endpoints and invalid measured values. Each Metric has seven string fields: endpoint, value, unit, object, condition, uncertainty and source report (abstract, prose or table). Units and distinct reports are preserved. Conflicting prose/table values are retained for review rather than reconciled. A syntactically valid record remains pending semantic review.}

\rev{The revised input preserves header, abstract and full-page source text; physical lines containing replacement characters are excluded from quoteable fragments but remain in the original PDF. Coordinate-based extraction has been tested on two development tables only: 45 rice-model outcomes and 12 oil-assay outcomes. Cell coordinates, glyphs, epoch headers and reporting notes are retained. These 57 candidates are neither an independent gold set nor a completed corpus re-extraction. The graph importer does not accept the new coordinate protocol directly.}

\rev{Task-scoped extraction supports bounded continuation and exact paper-local reconciliation. Invalid or incomplete tasks are quarantined. A paper is not imported until source checks, task coverage and a bound human review pass. In the two-paper, 11-task development run, eight tasks were quarantined before subsequent software changes. These failures are retained; no extraction F1 is inferred from validation pass counts.}
''')
    old='GROBID was used to parse the PDFs'
    i=text.index(old);j=text.index(r'\subsection{Scientific Knowledge Schema}',i)
    text=text[:i]+r'''\rev{GROBID supplied the historical section-based metadata/text pipeline \cite{lopez2009grobid,meuschke2023pdfbenchmark}. The revised development extractor additionally preserves full PDF pages and header metadata, with source-quality guards and coordinate evidence for the two explicitly configured development tables. The frozen retrieval comparison corpus remains the historical parsed-text snapshot; newly recovered table cells are not added to one baseline alone. Coordinate layouts are not yet a general table detector. Original PDFs remain authoritative for independent annotation, including text that a parser misses.}

'''+text[j:]
    text=text.replace(r'\State $S_p \gets \Call{GROBIDParse}{p}$',r'\State $S_p \gets \Call{ParseMetadataAndFullPages}{p}$')
    text=text.replace(r'\State $E_s \gets \Call{FilterConfidence}{E_s,0.60}$',r'\State \Call{QuarantineUnsupportedRecords}{$E_s,R_s$}')
    text=text.replace(r'\State \Call{UpsertPaperSubgraph}{$G,p,E_p,R_p$}',r'''\If{\Call{CompleteAndReviewed}{$p,E_p,R_p$}}
    \State \Call{UpsertPaperSubgraph}{$G,p,E_p,R_p$}
    \Else
    \State \Call{RetainPendingOrQuarantined}{$p,E_p,R_p$}
    \EndIf''')
    addition=r'''
\subsection{Matched Retrieval and Ablation Diagnostics}
\rev{A local dense baseline was executed with all-MiniLM-L6-v2: 7,449 source passages from the frozen 482-paper corpus, 384-dimensional unit-normalized vectors and exact in-memory cosine search. BM25 and Vector used shared index/query inputs; model, package and source hashes were retained. No embedding/index time is counted as online QA latency. A later common-context preflight used a pinned o200k\_base proxy tokenizer and a 2,000-token serialized-context cap. This proxy is not Gemini usage accounting.}

\rev{The 45-question preflight produced 360 contexts across eight methods. KG variants used the same query string and token cap. After a query-intent correction, empty context counts were 0 for BM25 and Vector; 4 for KG, raw identities, no semantic signal, no relation signal and KG verified; and 6 for no expansion. These 26 KG empty contexts are retained. They are not independently labelled false refusals. No-expansion now removes degree as well as neighbor connections. It is still entity-anchor search, not a pure text baseline.}

\rev{The raw-identity snapshot had 10,090 nodes versus 8,258 normalized nodes, including provenance nodes. Removing normalization changed selected identity/order on 28 questions in the diagnostic. This is not synonym recall or QA accuracy. The semantic ranking component is a lexical proxy. Removing a coefficient does not remove correlated signals or task-specific filtering; no isolated causal gain is claimed.}

\rev{A released LightRAG 1.5.7 integration test \cite{guo2024lightrag} indexed 100 abstract words from one development paper using one actual Gemini call, producing 11 nodes and 9 edges. Native hybrid and naive retrieval completed on an isolated index copy. This test verifies package integration only; it is not the missing full-corpus SOTA comparison. Native LightRAG prompts/ontology differ from the controlled retrieval track.}

\subsection{Bounded Generation and Paired Claim-Filtering Pilot}
\rev{A new pilot used the first known internal QA question, seven generating methods and a paired filtered KG output, for two repeats. The exact KG draft was reused for the filtered variant; it was not regenerated independently. The total budget was 16 Gemini calls, with temperature zero, a 1,024-token answer limit and a 4,096-token verification limit. Precomputed retrieval is excluded from request timings; intentional throttling is recorded separately. This single-question pilot is not the required 45-question, five-repeat experiment and supplies no independent quality or significance estimate.}

\rev{Claim verification decomposes the KG draft and returns a support decision and exact source quote. The deterministic post-filter accepts only unchanged draft substrings with a valid context index and a quote actually present in the supplied context. This prevents quote fabrication and draft rewriting but does not prove that the quote entails every part of a compound claim. Accepted-claim counts are software diagnostics, not Faithfulness scores. Independent unsupported-claim and false-refusal labels remain necessary.}

\rev{A source-checked error case illustrates a negative trade-off, not an improvement claim. Page 1 of the mango study lists four authors \cite{hau2018uniconazole}. In both pilot repeats, the raw-identity variant returned all four names, whereas the normalized variant omitted Tran Sy Hieu. The raw and normalized contexts retained different numbers of records under the same serialized token cap. This observation does not isolate identity merging from changed topology, ranking and provenance length, and it cannot establish a general normalization effect from one known question.}

\rev{The paired verifier also exposed instability. In repeat 1 it supplied three support records for the same compound author-list claim; two passed the string/quote checks but collapsed to one unique retained text. In repeat 2 all three were rejected and the output became an abstention. The second response inserted punctuation that no longer matched the exact draft substring, and a short name quote failed the minimum quote-length rule. These are concrete over-rejection risks. The first response required read-only removal of a Markdown JSON wrapper; its original response and initial parser failure are preserved. No semantic JSON content was repaired or a paid request silently repeated.}

\rev{The analysis implementation requires the complete declared method--question--repeat grid, explicit generation status, measured attempt duration and score provenance. Failed generation utility is zero under the stated convention; missing runs are rejected, not zero-filled. Conditional-success quality and success/failure attempt timing are separate. Repeats are averaged within question before bootstrap, sign-flip and optional Wilcoxon inference; Holm adjusts the declared comparison family. No empirical p-value or confidence interval is reported from the bounded pilot.}
'''
    marker=r'\subsection{Recovered Historical Logs}'
    timing_rows=[]
    for method,values in diagnostics['provider_timing'].items():
        label=method.replace('_',r'\_')
        timing_rows.append(r'\texttt{'+label+'} & '+f"{values['values'][0]:.3f} & {values['values'][1]:.3f} & {values['mean_seconds']:.3f} & {values['sample_sd_seconds']:.3f}"+r' \\ \hline')
    addition+=r'''
\begin{table}[H]
\caption{\rev{Raw API-adapter request durations in the bounded pilot (seconds; one question, two repeats).}}
\label{tab:bounded-request-times}
\centering\small\color{red}
\begin{tabular}{|l|r|r|r|r|}
\hline Method & Repeat 1 & Repeat 2 & Mean & Sample SD \\ \hline
'''+ '\n'.join(timing_rows)+r'''
\end{tabular}
\par\smallskip\raggedright
\rev{These durations include HTTP and adapter journaling overhead, exclude intentional throttling and frozen retrieval, and are not end-to-end QA latency. The filtered variant allocates the shared KG draft request plus verification. No inferential latency comparison is made from two repeats of one question.}
\end{table}
'''
    text=text.replace(marker,addition+'\n'+marker,1)
    text=text.replace('Vector and SOTA baseline & Actual comparable runs and configuration evidence pending.',
        'Vector and SOTA baseline & Vector retrieval diagnostic completed; released LightRAG excerpt smoke completed; full comparable QA pending.')
    text=text.replace('Ablations and weight sensitivity & Base controls and exploratory runner supplied; complete measurements pending.',
        'Ablations and weight sensitivity & Eight-method context preflight completed; independent quality/repeated-run effects pending.')
    text=text.replace('Claim filtering & Implemented and smoke-tested; independent efficacy assessment pending.',
        'Claim filtering & Paired draft-filter pilot executed; independent efficacy and false-refusal assessment pending.')
    text=text.replace('A completed seven-variant smoke test verifies execution of the portable experiment path.',
        'Matched retrieval preflights, a released LightRAG integration smoke and a bounded paired-generation pilot verify specific execution paths only.')
    text=text.replace(r'\subsection{Limitations and Interpretation}',r'\subsection{Limitations and Interpretation}'+'\n'+r'\rev{The legacy QA questions have been inspected during debugging, and these exploratory runs are not blinded generalization tests. The constrained ontology cannot express every biological object-to-outcome relation; samples must not be relabelled as Methods or Datasets merely to force an edge. Software validation, graph size and context coverage do not substitute for independently adjudicated references.}')
    (output/'main.tex').write_text(text,encoding='utf-8')
    with (output/'references.bib').open('a',encoding='utf-8') as bib:
        bib.write(r'''
@article{hau2018uniconazole,
 author={{Tran Van Hau} and {Phan Van Ut} and {Phan Huynh Anh} and {Tran Sy Hieu}},
 title={The effects of uniconazole dosages and suitable periods for bud break on the flowering of {Dai Loan} mango ({Mangifera indica L.}) grown in {Cho Moi} district, {An Giang} province, 2016},
 journal={Can Tho University Journal of Science},
 year={2018}, volume={54}, number={5}, pages={7--15},
 doi={10.22144/ctu.jen.2018.018}, note={Metadata checked against page 1 of the original PDF}
}
''')
    atomic_json(output/'revision_evidence.json',{'source_tex_sha256':file_hash(source/'main.tex'),'pilot_summary_sha256':file_hash(pilot/'summary.json'),
        'pilot_status':summary['status'],'reserved_api_calls':summary['reserved_api_calls'],'quality_scores_added':False,
        'working_revision_not_submission_ready':True,'changes':'red additions and corrected strict v3.1 schema; historical logs retained separately'})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('source','pilot','output'):parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args();build(**vars(args))
