"""Offline CLI. Match=0, drift=1, incomparable or rejected input=2."""
import argparse
import sys
from .core import compare_snapshots
from .errors import ContractError
from .io import check_output, load_json, write_bytes, write_json
from .report import render_html


def parser():
    result = argparse.ArgumentParser(prog='chat-input-contract',
        description='Capture and compare local chat preprocessing evidence. No model or API key needed.')
    sub = result.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture', help='Capture a local tokenizer/template manifest (sensitive snapshot).')
    capture.add_argument('manifest'); capture.add_argument('--out', required=True)
    capture.add_argument('--force', action='store_true', help='Replace existing output, never input files.')
    compare = sub.add_parser('compare', help='Compare declared input contracts; no tokenizer dependency required.')
    compare.add_argument('baseline'); compare.add_argument('candidate')
    compare.add_argument('--json', required=True, dest='json_output')
    compare.add_argument('--html', dest='html_output')
    compare.add_argument('--include-content', action='store_true', help='Explicitly include sensitive rendered prompts and token details.')
    compare.add_argument('--force', action='store_true', help='Replace existing outputs, never input files.')
    demo = sub.add_parser('demo', help='Run actual good/bad/repaired paths on original tiny fixtures.')
    demo.add_argument('--out', required=True, help='New or empty output directory.')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'capture':
            from .capture import capture_manifest, manifest_inputs
            _, protected = manifest_inputs(args.manifest)
            check_output(args.out, force=args.force, protected=protected)
            snapshot = capture_manifest(args.manifest)
            write_json(args.out, snapshot, force=args.force, protected=protected)
            print(f'Captured {len(snapshot["cases"])} cases. Snapshot contains sensitive prompt material.')
            return 0
        if args.command == 'demo':
            from .demo import run_demo
            result = run_demo(args.out)
            print(f'Demo verified: safe={result["safe"]}, broken={result["broken"]}, cases={result["cases"]}.')
            return 0
        baseline, candidate = load_json(args.baseline), load_json(args.candidate)
        report = compare_snapshots(baseline, candidate, include_content=args.include_content)
        inputs = (args.baseline, args.candidate)
        check_output(args.json_output, force=args.force,
                     protected=inputs + ((args.html_output,) if args.html_output else ()))
        html = None
        if args.html_output:
            check_output(args.html_output, force=args.force, protected=inputs + (args.json_output,))
            html = render_html(report).encode('utf-8')
        write_json(args.json_output, report, force=args.force, protected=inputs)
        if html is not None:
            write_bytes(args.html_output, html, force=args.force, protected=inputs + (args.json_output,))
        s = report['summary']
        print(f'{report["status"].upper()}: {s["total"]} cases; {s["match"]} match, {s["drift"]} drift, {s["incomparable"]} incomparable.')
        return {'match': 0, 'drift': 1, 'incomparable': 2}[report['status']]
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError, RecursionError):
        print('EXECUTION_FAILED: Local input/output operation failed; no success is claimed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
