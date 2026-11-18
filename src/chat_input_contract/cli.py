"""Offline CLI. Match=0, drift=1, incomparable or rejected input=2."""
import argparse
import sys
from . import __version__
from .core import compare_snapshots
from .errors import ContractError
from .io import check_output, load_json, write_bytes, write_json
from .report import render_html


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ContractError('INVALID_ARGUMENTS', 'Invalid command arguments; use --help for syntax.')


def _outputs(command, *, required=False):
    command.add_argument('--json', required=required, dest='json_output')
    command.add_argument('--html', dest='html_output')
    command.add_argument('--include-content', action='store_true', help='Explicitly export sensitive content to reports, not the terminal.')
    command.add_argument('--force', action='store_true', help='Replace existing outputs, never input files.')


def parser():
    result = SafeParser(prog='chat-input-contract',
        description='Capture and check local chat preprocessing evidence. No model or API key needed.')
    result.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = result.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture', help='Capture a local manifest (sensitive baseline snapshot).')
    capture.add_argument('manifest'); capture.add_argument('--out', required=True)
    capture.add_argument('--force', action='store_true', help='Replace existing output, never input files.')
    compare = sub.add_parser('compare', help='Compare saved snapshots; core dependencies only.')
    compare.add_argument('baseline'); compare.add_argument('candidate')
    compare.add_argument('--explain', action='store_true', help='Opt into report v2 with bounded difference windows.')
    _outputs(compare, required=True)
    check = sub.add_parser('check', help='Check a live local manifest against a reviewed baseline without writing a candidate.')
    check.add_argument('manifest'); check.add_argument('--baseline', required=True)
    _outputs(check)
    demo = sub.add_parser('demo', help='Execute good/bad/repaired paths on original tiny fixtures.')
    demo.add_argument('--out', required=True, help='New or empty output directory.')
    return result


def _preflight(args, protected):
    outputs = [p for p in (args.json_output, args.html_output) if p]
    for index, output in enumerate(outputs):
        check_output(output, force=args.force,
                     protected=(*protected, *outputs[:index], *outputs[index+1:]))


def _publish(args, report, protected):
    # Compute all requested representations before any output is published.
    from .io import json_bytes
    raw_json = json_bytes(report) if args.json_output else None
    raw_html = render_html(report).encode('utf-8') if args.html_output else None
    if raw_json is not None:
        write_bytes(args.json_output, raw_json, force=args.force, protected=protected)
    if raw_html is not None:
        write_bytes(args.html_output, raw_html, force=args.force,
                    protected=(*protected, *((args.json_output,) if args.json_output else ())))


def terminal_summary(report):
    s = report['summary']
    lines = [f'{report["status"].upper()}: {s["total"]} cases; {s["match"]} match, {s["drift"]} drift, {s["incomparable"]} incomparable.']
    if report['schema_version'] == 2:
        findings = [(i, row) for i, row in enumerate(report['case_results'], 1) if row['status'] != 'match']
        for i, row in findings[:10]:
            analysis = row['analysis']
            chars, tokens = row['first_char_difference'], row['first_token_difference']
            lines.append(f'  case[{i}] {row["status"]}: {analysis["earliest_stage"]}; first character={chars}, token={tokens}')
        if len(findings) > 10:
            lines.append(f'  {len(findings)-10} further nonmatching cases omitted from terminal; see the report.')
    return '\n'.join(lines)


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        if args.command == 'capture':
            from .capture import capture_prepared, prepare_capture
            prepared = prepare_capture(args.manifest)
            check_output(args.out, force=args.force, protected=prepared.protected)
            snapshot = capture_prepared(prepared)
            write_json(args.out, snapshot, force=args.force, protected=prepared.protected)
            print(f'Captured {len(snapshot["cases"])} cases. Snapshot contains sensitive prompt material.')
            return 0
        if args.command == 'demo':
            from .demo import run_demo
            result = run_demo(args.out)
            print(f'Demo verified: safe={result["safe"]}, broken={result["broken"]}, cases={result["cases"]}.')
            return 0
        if args.command == 'check':
            from .check import prepare_check, check_prepared
            prepared = prepare_check(args.manifest, args.baseline)
            inputs = prepared.protected
            _preflight(args, inputs)
            report = check_prepared(prepared, include_content=args.include_content)
        else:
            inputs = (args.baseline, args.candidate)
            _preflight(args, inputs)
            baseline, candidate = load_json(args.baseline), load_json(args.candidate)
            if args.explain:
                from .explain import explain_snapshots
                report = explain_snapshots(baseline, candidate, include_content=args.include_content)
            else:
                report = compare_snapshots(baseline, candidate, include_content=args.include_content)
        _publish(args, report, inputs)
        print(terminal_summary(report))
        return {'match': 0, 'drift': 1, 'incomparable': 2}[report['status']]
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError, RecursionError):
        print('EXECUTION_FAILED: Local input/output operation failed; no success is claimed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
