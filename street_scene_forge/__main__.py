import argparse
import signal
import sys
from . import __version__
from .core import ForgeError, Limits, convert


def main(argv=None):
    parser = argparse.ArgumentParser(description='Convert bounded local OSM XML into an offline 3D scene. Never accesses the network.')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('input', help='local UTF-8 OSM 0.6 XML file')
    parser.add_argument('--bbox', required=True, type=float, nargs=4, metavar=('WEST', 'SOUTH', 'EAST', 'NORTH'))
    parser.add_argument('--output', required=True, help='new output directory; parent must exist')
    args = parser.parse_args(argv)
    limits = Limits()
    def cancel(signum, frame):
        raise KeyboardInterrupt
    def timeout(signum, frame):
        raise ForgeError('runtime_limit')
    # Unix wall-clock deadline also covers parser/serializer and filesystem calls.
    previous = {}
    if hasattr(signal, 'SIGALRM'):
        for sig, handler in ((signal.SIGALRM, timeout), (signal.SIGTERM, cancel), (signal.SIGINT, cancel)):
            previous[sig] = signal.signal(sig, handler)
        signal.setitimer(signal.ITIMER_REAL, limits.seconds)
    try:
        manifest = convert(args.input, args.output, args.bbox, limits)
        print(f"Exported {manifest['totals']['features']} features; {len(manifest['diagnostics'])} omissions. Open {args.output}/index.html")
        return 0
    except KeyboardInterrupt:
        print('Cancelled; owned partial output removed.', file=sys.stderr)
        return 130
    except (ForgeError, OSError, ValueError) as exc:
        print('street-scene-forge: '+str(exc), file=sys.stderr)
        return 2
    finally:
        if previous:
            signal.setitimer(signal.ITIMER_REAL, 0)
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == '__main__':
    sys.exit(main())
