"""Executes a code block's typed Python and captures its output.

No sandboxing: this runs with the same permissions as the app itself,
exactly like typing into a local Python REPL. That's fine for your own
code on your own machine, typed by your own hand through the webcam --
but it is not safe to expose to code you didn't type yourself.
"""
import contextlib
import io


def run_code(code: str) -> str:
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            exec(code, {"__name__": "__main__"})
    except Exception as exc:
        buffer.write(f"\n[Erreur] {type(exc).__name__}: {exc}")
    output = buffer.getvalue().strip()
    return output if output else "(pas de sortie -- utilisez print(...))"
