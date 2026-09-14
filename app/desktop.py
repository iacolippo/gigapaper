"""Runs gigapaper as a desktop app.

The server is still a server — it just stops being the interface. uvicorn
binds an ephemeral port on the loopback address and a native webview window
(WKWebView on macOS) is pointed at it, so there is no tab, no URL bar, and no
port to remember. Closing the window ends the process.

Without pywebview installed, or with --browser, it falls back to opening the
default browser instead.
"""

import argparse
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

WINDOW_TITLE = "gigapaper"


def free_port() -> int:
    """A port the OS says is free right now.

    Racy in principle; in practice nothing else claims it in the microseconds
    before uvicorn binds it, and the alternative — a fixed port — collides
    with a second copy of the app.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(port: int) -> uvicorn.Server:
    """Starts the API on a daemon thread and returns once it accepts requests."""
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("the gigapaper server did not start")
    return server


def main() -> int:
    parser = argparse.ArgumentParser(prog="gigapaper", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--browser",
        action="store_true",
        help="open in the default browser instead of a desktop window",
    )
    parser.add_argument(
        "--port", type=int, default=0, help="serve on this port instead of a free one"
    )
    args = parser.parse_args()

    port = args.port or free_port()
    serve(port)
    url = f"http://127.0.0.1:{port}"

    if not args.browser:
        try:
            import webview
        except ImportError:
            print("pywebview not installed; opening a browser instead.", file=sys.stderr)
        else:
            webview.create_window(
                WINDOW_TITLE,
                url,
                width=1400,
                height=900,
                min_size=(900, 600),
                # pywebview defaults this to False, which injects
                # `body { -webkit-user-select: none }` into the page. That
                # makes the whole reader unselectable, and selecting text is
                # how every highlight gets made.
                text_select=True,
            )
            webview.start()
            return 0

    print(f"gigapaper on {url}")
    webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
