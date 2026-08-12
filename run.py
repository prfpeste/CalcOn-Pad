import sys
import threading
import time
import webbrowser

from app import app


def run_server(open_browser: bool, debug: bool):
    if open_browser:
        def _run():
            app.run(host="127.0.0.1", port=5000, debug=debug)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        time.sleep(1)
        webbrowser.open("http://127.0.0.1:5000")
        thread.join()
    else:
        app.run(host="127.0.0.1", port=5000, debug=debug)


if __name__ == "__main__":
    frozen = getattr(sys, "frozen", False)
    if frozen:
        run_server(open_browser=True, debug=False)
    else:
        run_server(open_browser=False, debug=False)
