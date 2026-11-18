"""Dependency-free HTML evidence report. All supplied values are escaped."""
from html import escape
import json

STYLE = '''
:root{color-scheme:light;--ink:#172a3a;--muted:#526579;--paper:#f3f6fa;--line:#d7e0ea;--match:#12665f;--drift:#96500b;--incomparable:#a12c41}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 "Segoe UI",Arial,sans-serif}
a{color:inherit}main{max-width:1120px;margin:0 auto;padding:48px 28px 64px}.brand{font:600 12px "Cascadia Code",Consolas,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
header{padding:28px 0 32px;border-bottom:2px solid var(--ink)}h1{font:600 clamp(32px,5vw,58px)/1.08 Bahnschrift,"Aptos Display","Segoe UI",sans-serif;letter-spacing:-.035em;max-width:780px;margin:18px 0}h2{font-size:21px;margin:0 0 16px}h3{margin:0;font-size:19px;overflow-wrap:anywhere}p{margin:12px 0}.lede{max-width:740px;color:var(--muted)}
.outcome{display:inline-block;font-weight:700;padding:5px 12px;border:1px solid currentColor;border-radius:5px}.match{color:var(--match)}.drift{color:var(--drift)}.incomparable{color:var(--incomparable)}
.pipeline{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin:28px 0;background:white;border:1px solid var(--line);border-radius:8px;overflow:hidden}.step{padding:17px 20px;border-right:1px solid var(--line);position:relative}.step:last-child{border:0}.step small{display:block;font:12px Consolas,monospace;color:var(--muted);margin-bottom:6px}.step.changed{background:#fff3df;border-bottom:3px solid var(--drift)}.step strong{font-size:16px}.step span{display:block;font-size:12px;color:var(--muted);margin-top:5px}
.metrics{display:flex;gap:28px;flex-wrap:wrap;padding:0 0 24px}.metrics strong{font:600 27px Bahnschrift,"Segoe UI",sans-serif;margin-right:6px}.metrics span{color:var(--muted);font-size:14px}
.notice{padding:14px 18px;background:#e9f0f7;border-left:3px solid #607e9a;font-size:14px;margin:8px 0 32px}.notice strong{display:block}section{margin-top:34px}.case{background:#fff;border:1px solid var(--line);border-radius:8px;padding:22px;margin:14px 0}.case-head{display:flex;align-items:center;justify-content:space-between;gap:16px}.case .outcome{font-size:13px;white-space:nowrap}.stages{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0}.stage{font:11px/1.6 "Cascadia Code",Consolas,monospace;padding:3px 7px;background:#eef3f8;border:1px solid var(--line);border-radius:3px;overflow-wrap:anywhere}
.positions{font-size:14px;color:var(--muted)}.lengths{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.lengths div{padding:12px 14px;background:#f6f8fb;border-radius:4px}.lengths small{display:block;color:var(--muted)}code,pre{font:13px/1.55 "Cascadia Code",Consolas,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fb;padding:14px;border-radius:5px;max-height:400px;overflow:auto}summary{cursor:pointer;padding:10px 0;font-weight:600}summary:focus-visible{outline:3px solid #167899;outline-offset:3px}.content-columns{display:grid;grid-template-columns:1fr 1fr;gap:16px;min-width:0}.content-columns>div{min-width:0}
table{width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed;background:#fff}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th{background:#e9eff6;color:var(--muted)}th:first-child{width:28%}.table-wrap{border:1px solid var(--line);border-radius:7px;overflow:hidden}.small{font-size:13px;color:var(--muted)}footer{margin-top:42px;padding-top:20px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
@media(max-width:640px){main{padding:24px 16px 40px}.pipeline{grid-template-columns:1fr 1fr}.step{border-bottom:1px solid var(--line)}.step:nth-child(2){border-right:0}.case{padding:16px}.case-head{align-items:flex-start}.metrics{gap:14px}.content-columns{grid-template-columns:1fr}th,td{padding:9px 7px;font-size:11px}.lengths{gap:8px}.lengths div{padding:9px}}
.case>summary{list-style:none;padding:0}.case>summary::-webkit-details-marker{display:none}.case>summary h3:before{content:'+';display:inline-block;width:20px;color:var(--muted)}.case[open]>summary h3:before{content:'−'}.interpretation{background:#edf4f9;padding:14px 16px;border-left:3px solid #577a98;border-radius:0 5px 5px 0;margin:18px 0}.interpretation p{font-size:14px;margin:7px 0}.window{padding:14px 16px;background:#f5f7fa;border:1px solid var(--line);border-radius:5px;margin:10px 0}.window h4{font-size:13px;margin:0 0 6px}.window pre{margin:4px 0;padding:8px;background:white}.remove{border-left:3px solid #a12c41}.insert{border-left:3px solid #12665f}mark{background:#fff0bd;color:var(--ink)}.window-label{font:11px Consolas,monospace;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}.alignment-note{font-size:12px;color:var(--muted)}
@media print{body{background:white}main{padding:0}.case{break-inside:avoid}details{display:block}pre{max-height:none}}
'''


def e(value):
    return escape(str(value), quote=True)


def position(value):
    return 'none' if value is None else e(value)


def badge(status):
    status = status if status in ('match', 'drift', 'incomparable') else 'incomparable'
    return f'<span class="outcome {status}">{status.title()}</span>'


def _change_html(change, title):
    if change is None:
        return ''
    if not change['total_windows']:
        return f'<p class="small">{e(title)}: no sequence change.</p>'
    mode = ('Enclosing window — alignment budget exceeded; unchanged internal spans may be included.'
            if change['alignment'] == 'enclosing' else
            'Bounded alignment — repeated sequences may have another valid alignment.')
    parts = [f'<h4>{e(title)} · {e(change["total_windows"])} change windows</h4>',
             f'<p class="alignment-note">{mode} Zero-based, half-open ranges.</p>']
    for window in change['windows']:
        parts.append(f'<div class="window"><h4>Baseline [{e(window["baseline_start"])}, {e(window["baseline_end"])}) → Candidate [{e(window["candidate_start"])}, {e(window["candidate_end"])})</h4><p class="small">{e(window["removed_count"])} removed · {e(window["added_count"])} added</p>')
        for side, style in (('baseline', 'remove'), ('candidate', 'insert')):
            preview = window.get(side+'_preview')
            if preview is not None:
                parts.append(f'<div class="window-label">{side}</div><pre class="{style}">{e(json.dumps(preview["before"], ensure_ascii=False))} <mark>{e(json.dumps(preview["changed"], ensure_ascii=False))}</mark> {e(json.dumps(preview["after"], ensure_ascii=False))}</pre>')
                if preview['omitted_items']:
                    parts.append(f'<p class="alignment-note">{e(preview["omitted_items"])} items omitted from this changed-segment preview.</p>')
        parts.append('</div>')
    if change['omitted_windows']:
        parts.append(f'<p class="alignment-note">{e(change["omitted_windows"])} intermediate windows omitted. First two and last are shown.</p>')
    return ''.join(parts)


def render_html(report: dict) -> str:
    status = report['status']
    title, explanation = {
        'match': ('Your input contract holds.', 'The recorded cases agree under the declared contract. This is not a model-quality or universal deployment guarantee.'),
        'drift': ('Same intent. Different input.', 'The captured preprocessing paths differ. Review the stage evidence before accepting a new baseline; drift is not automatically a model defect.'),
        'incomparable': ('Resolve the comparison first.', 'Some cases have different inputs or intent, or are missing. Their absence must not turn into a passing check.')
    }.get(status, ('Comparison requires review.', 'Review the evidence before accepting a baseline.'))
    rows = report['case_results']
    codes = {stage for row in rows for stage in row['stages']}
    enriched = report.get('schema_version') == 2
    partial = any(row['status'] == 'incomparable' for row in rows)
    pipeline = []
    for num, name, related in (
        ('01', 'Messages', {'INPUT_CHANGED', 'MISSING_CASE', 'INTENT_CHANGED'}),
        ('02', 'Template', {'RENDER_CHANGED'}),
        ('03', 'Tokenizer', {'VOCABULARY_CHANGED', 'TOKENIZATION_CHANGED', 'TOKEN_SPELLING_CHANGED'}),
        ('04', 'Postprocess', {'POSTPROCESSING_CHANGED', 'ROUTE_INCONSISTENCY', 'TOKENS_CHANGED'})):
        changed = bool(codes & related)
        if name == 'Tokenizer':
            # Selected spellings also change when only postprocessing adds IDs.
            # Only spelling changes with unchanged selected IDs implicate this stage.
            changed = bool(codes & {'VOCABULARY_CHANGED', 'TOKENIZATION_CHANGED'}) or any(
                'TOKEN_SPELLING_CHANGED' in row['stages'] and row['first_token_difference'] is None
                for row in rows)
        if enriched:
            stages = {'Messages': {'inputs'}, 'Template': {'rendering'},
                      'Tokenizer': {'vocabulary', 'tokenization', 'token_spelling'},
                      'Postprocess': {'postprocessing', 'consistency'}}[name]
            changed = any(row['analysis']['earliest_stage'] in stages for row in rows)
        label = 'Evidence to review' if changed else 'Not comparable for all cases' if partial else 'No reported difference'
        pipeline.append(f'<div class="step{" changed" if changed else ""}"><small>{num} / INPUT PATH</small><strong>{name}</strong><span>{label}</span></div>')
    metrics = ''.join(f'<div><strong>{e(report["summary"][key])}</strong><span>{label}</span></div>'
                      for key, label in (('total', 'cases'), ('match', 'match'), ('drift', 'drift'), ('incomparable', 'incomparable')))
    included = report.get('content_included', False) or any('content' in row for row in rows)
    privacy = ('Content included — keep this report private.' if included else 'Content hidden — a smaller sharing surface.')
    privacy_note = ('Explicit content export is enabled. Rendered prompts, IDs and token spellings may reveal private input.' if included else
                    'Prompt text, token IDs and spellings are omitted. Case names and fingerprints remain visible; review them before sharing. Snapshots are sensitive even when this report is redacted.')
    case_html = []
    for row in rows:
        stage_html = ''.join(f'<span class="stage">{e(s)}</span>' for s in row['stages']) or '<span class="small">No behavioral difference in this case.</span>'
        lens = row['lengths']
        sizes = ''.join(f'<div><small>{side.title()}</small>{e(lens[side+"_tokens"])} tokens · {e(lens[side+"_chars"])} characters</div>' for side in ('baseline', 'candidate'))
        details = ''
        if 'content' in row:
            columns = []
            for side in ('baseline', 'candidate'):
                content = row['content'][side]
                if content is None:
                    text = '<p>Case missing.</p>'
                else:
                    text = f'<pre>{e(content["rendered_text"])}</pre><pre>{e(json.dumps(content["input_ids"]))}</pre><pre>{e(json.dumps(content["tokens"], ensure_ascii=False))}</pre>'
                columns.append(f'<div><h3>{side.title()}</h3>{text}</div>')
            details = '<details><summary>Inspect explicitly included content</summary><div class="content-columns">' + ''.join(columns) + '</div></details>'
        analysis = row.get('analysis')
        if analysis:
            interpretation = f'<div class="interpretation"><strong>First observed: {e(analysis["earliest_stage"] or "no difference")}</strong>' + ''.join(f'<p>{e(note)}</p>' for note in analysis['notes']) + '</div>'
            details = interpretation + _change_html(analysis['token_change'], 'Tokens') + _change_html(analysis['character_change'], 'Characters')
        body = f'<div class="stages">{stage_html}</div><p class="positions">First difference, zero-based: character <strong>{position(row["first_char_difference"])}</strong> · token <strong>{position(row["first_token_difference"])}</strong></p><div class="lengths">{sizes}</div>{details}'
        heading = f'<h3>{e(row["id"])}</h3>{badge(row["status"])}'
        if enriched:
            opened = ' open' if row['status'] != 'match' else ''
            case_html.append(f'<details class="case"{opened}><summary class="case-head">{heading}</summary>{body}</details>')
        else:
            case_html.append(f'<article class="case"><div class="case-head">{heading}</div>{body}</article>')
    changes = report['provenance_changes']
    provenance = ('<p class="small">Recorded artifacts, runtime and options are unchanged.</p>' if not changes else
                  '<div class="table-wrap"><table><thead><tr><th scope="col">Changed field</th><th scope="col">Baseline</th><th scope="col">Candidate</th></tr></thead><tbody>' +
                  ''.join(f'<tr><td><code>{e(c["field"])}</code></td><td><code>{e(c["baseline"])}</code></td><td><code>{e(c["candidate"])}</code></td></tr>' for c in changes) + '</tbody></table></div>')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Input contract · {e(status)}</title><style>{STYLE}</style></head>
<body><main><div class="brand">Chat Input Contract / Evidence report</div><header>{badge(status)}<h1>{title}</h1><p class="lede">{explanation}</p></header>
<div class="pipeline" aria-label="Preprocessing stages">{''.join(pipeline)}</div><div class="metrics">{metrics}</div>
<aside class="notice"><strong>{privacy}</strong>{privacy_note}</aside>
<section aria-label="Case evidence"><h2>Follow the evidence</h2>{''.join(case_html)}</section>
<section aria-label="Provenance"><h2>What changed around the run</h2><p class="small">Provenance changes are context, not automatically a behavioral failure.</p>{provenance}</section>
<footer>Offline · No scripts, external assets or telemetry. A snapshot is recorded evidence, not authenticated proof of origin. Reviewed changes require an explicit baseline decision.</footer>
</main></body></html>'''
