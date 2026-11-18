"""Private native-dependency worker. Input travels on stdin, never argv or disk."""
import base64
import sys
from .errors import ContractError
from .io import decode_json, json_bytes


def main():
    try:
        raw = sys.stdin.buffer.read(128 * 1024 * 1024 + 1)
        if len(raw) > 128 * 1024 * 1024:
            raise ContractError('BUDGET_EXCEEDED', 'Transport budget exceeded.')
        payload = decode_json(raw)
        from .capture import execute_capture
        snapshot = execute_capture(payload['manifest'],
                                   base64.b64decode(payload['tokenizer'], validate=True),
                                   base64.b64decode(payload['template'], validate=True))
        output = json_bytes(snapshot)
    except BaseException as exc:
        # PyO3 PanicException inherits BaseException. All diagnostics, including
        # Rust stderr, stay in this worker and are discarded by the parent.
        code = exc.code if isinstance(exc, ContractError) else 'CAPTURE_FAILED'
        output = json_bytes({'error': code})
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
