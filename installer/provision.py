"""Installs the heavy components the setup exe deliberately does not carry.

The wizard ships about 10 MB. The GPU runtime (~4.6 GB installed) and the model
weights (~5.3 GB) are provisioned here instead, and -- the point of the whole design --
each step first asks whether it has already been done:

    deps    skipped when requirements.txt hashes the same as the recorded install
    models  skipped per engine when that engine's weights are already on disk
    both    live outside the program folder, so an upgrade never disturbs them

That is why updating is a few megabytes while a first install is several gigabytes.

Run by Transcriber.iss under the provisioned runtime, never by the user directly.
Every line it prints is a message to the wizard:

    PROGRESS|<0-100>|<text>   move the bar, set the caption
    LOG|<text>                detail for the install log
    WARN|<text>               shown on the final page, does not fail the install
    ERROR|<text>              fails the install, shown to the user

stdout must stay unbuffered (python -u) or the wizard's bar freezes.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

# Child processes must never flash a console window over the wizard.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Set by --progress-file. The wizard cannot read this process's stdout while it runs,
# so the current step is mirrored into a small file it polls instead.
_progress_file = None


def set_progress_file(path):
    global _progress_file
    _progress_file = path


def _write_progress_file(line):
    """Replace the progress file atomically.

    Written whole and swapped into place rather than appended, so the wizard can never
    read a half-written line, and never holds the file open against this process.
    """
    if not _progress_file:
        return
    try:
        directory = os.path.dirname(_progress_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        temporary = _progress_file + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(line)
        os.replace(temporary, _progress_file)
    except OSError:
        # Progress reporting must never be the thing that fails an install.
        pass


def emit(kind, text):
    sys.stdout.write(kind + "|" + str(text) + "\n")
    sys.stdout.flush()


_last_percent = 0


def progress(percent, message):
    """Report a step, never letting the bar run backwards.

    The captions during the dependency install are driven by package names spotted in
    pip's output, and pip does not emit them in the order they finish, so the raw
    numbers arrive out of sequence. Clamping keeps the bar honest-looking; the caption
    still tracks whatever is actually happening.
    """
    global _last_percent

    percent = max(int(percent), _last_percent)
    _last_percent = percent
    emit("PROGRESS", "{0}|{1}".format(percent, message))
    _write_progress_file("{0}|{1}".format(percent, message))


def finish(code, message=""):
    """Final line of the progress file: how the wizard learns this process ended."""
    _write_progress_file("DONE|{0}|{1}".format(int(code), message))


def log(message):
    for line in str(message).splitlines():
        if line.strip():
            emit("LOG", line.rstrip())


def warn(message):
    emit("WARN", message)


class ProvisionError(Exception):
    """A failure the wizard should report and roll back from."""


def stream(command, on_line=None, env=None, cwd=None):
    """Run a command, forwarding its output to the install log as it arrives.

    Output is streamed rather than collected so that a 2.5 GB pip download shows life
    in the wizard instead of looking hung for ten minutes.
    """
    command = [str(part) for part in command]
    log("+ " + " ".join(command))

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
        env=env,
        cwd=cwd,
    )

    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        if not line:
            continue
        log(line)
        if on_line:
            on_line(line)

    return process.wait()


def python_version():
    return ".".join(str(part) for part in sys.version_info[:3])


def torch_importable():
    """Whether the runtime can actually import torch.

    The recorded hash alone is not enough: an interrupted pip run can leave the state
    file claiming success over a broken site-packages.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import torch"],
        capture_output=True,
        creationflags=NO_WINDOW,
    )
    return result.returncode == 0


# --------------------------------------------------------------------------- steps


def step_deps(app_dir, force=False):
    """Install the GPU stack into the runtime, unless it is already the right one."""
    from transcriber import install_state

    requirements = os.path.join(app_dir, "requirements.txt")
    if not os.path.exists(requirements):
        raise ProvisionError("requirements.txt is missing from the install: " + requirements)

    if not force and install_state.runtime_matches(requirements) and torch_importable():
        progress(55, "GPU runtime already installed - keeping it")
        log("requirements.txt is unchanged and torch imports; skipping a ~2.5 GB download.")
        return

    progress(6, "Preparing the GPU runtime")

    # Package names spotted in pip's output, so the caption names what is downloading
    # instead of sitting on one generic message for ten minutes.
    milestones = [
        ("torch-", 30, "Downloading PyTorch with CUDA (about 2.5 GB)"),
        ("nvidia_", 40, "Downloading NVIDIA CUDA libraries"),
        ("transformers-", 46, "Downloading Transformers"),
        ("onnxruntime", 49, "Downloading ONNX Runtime"),
        ("Installing collected packages", 52, "Installing packages"),
    ]

    def watch(line):
        for needle, percent, caption in milestones:
            if needle in line:
                progress(percent, caption)
                return

    code = stream(
        [
            sys.executable, "-m", "pip", "install",
            "--requirement", requirements,
            "--disable-pip-version-check",
            "--no-input",
            "--progress-bar", "off",
        ],
        on_line=watch,
    )
    if code != 0:
        raise ProvisionError(
            "Could not install the GPU runtime. The most common cause is a dropped "
            "internet connection during the PyTorch download; running setup again "
            "resumes from whatever already succeeded."
        )

    install_state.record_runtime(requirements, python_version())
    progress(55, "GPU runtime installed")


# Run in a child process so a model download never shares an interpreter with the pip
# run that just rewrote site-packages underneath it.
DOWNLOAD_SCRIPT = (
    "import sys\n"
    "from transcriber.registry import get_engine\n"
    "engine = get_engine(sys.argv[1])\n"
    "print('Engine: ' + engine.label + ' (' + engine.model_repo + ')')\n"
    "target = engine.ensure_model_downloaded(status_callback=print)\n"
    "print('Model ready in ' + str(target))\n"
)


def step_models(app_dir, wanted=None, force=False):
    """Download each engine's weights, skipping any already on disk."""
    from transcriber import install_state

    rows = install_state.model_status()
    if not rows:
        raise ProvisionError("No transcription engines are registered in this build.")

    if wanted:
        rows = [row for row in rows if row[0] in wanted]

    engines = {name: engine for name, _label, engine in install_state._engine_instances()}
    span = 40.0 / max(1, len(rows))

    # The download runs in a child interpreter, which does not inherit this process's
    # sys.path, so the app folder has to be handed over explicitly or the child cannot
    # import transcriber at all.
    child_env = dict(os.environ)
    inherited = child_env.get("PYTHONPATH")
    child_env["PYTHONPATH"] = app_dir + (os.pathsep + inherited if inherited else "")

    for index, (name, label, installed, location) in enumerate(rows):
        base = 55 + span * index

        if installed and not force:
            progress(base + span, label + " weights already installed - keeping them")
            log("Found existing weights for " + name + " in " + str(location) + "; not downloading again.")
            install_state.record_model(name, location)
            continue

        progress(base, "Downloading " + label + " weights")

        # Keep the child's last line so the failure reports what actually went wrong
        # rather than blaming the network for every possible cause.
        last_line = {"text": ""}

        def remember(line, store=last_line):
            if line.strip():
                store["text"] = line.strip()

        code = stream(
            [sys.executable, "-u", "-c", DOWNLOAD_SCRIPT, name],
            on_line=remember,
            env=child_env,
            cwd=app_dir,
        )
        if code != 0:
            detail = last_line["text"]
            raise ProvisionError(
                "Could not download the weights for " + label + ". "
                + (detail + " " if detail else "")
                + "Finished downloads are kept, so running setup again resumes where "
                "it stopped."
            )

        engine = engines.get(name)
        found = install_state.find_model_dir(engine) if engine else None
        if found:
            install_state.record_model(name, found)

    progress(95, "Model weights ready")


def step_launcher(runtime_dir):
    """Give the installed app its own process name.

    The shortcut points at a copy of pythonw.exe named Transcriber.exe, so the taskbar
    and Task Manager show "Transcriber" rather than a generic Python process. Copying
    works because the interpreter finds its standard library relative to the
    executable's own folder, which the copy does not change.
    """
    source = os.path.join(runtime_dir, "pythonw.exe")
    target = os.path.join(runtime_dir, "Transcriber.exe")

    if not os.path.exists(source):
        raise ProvisionError("The runtime is missing pythonw.exe: " + source)

    try:
        shutil.copy2(source, target)
    except (PermissionError, OSError):
        # Locked because a copy is running: the existing file is the same interpreter,
        # so this is not worth failing an install over.
        log("Could not replace " + target + "; keeping the existing launcher.")

    progress(96, "Launcher ready")
    return target


CUDA_SCRIPT = (
    "import torch\n"
    "print('torch ' + torch.__version__)\n"
    "if not torch.cuda.is_available():\n"
    "    raise SystemExit('CUDA is not available to torch')\n"
    "print('CUDA device: ' + torch.cuda.get_device_name(0))\n"
    "print('CUDA build: ' + str(torch.version.cuda))\n"
)


def step_verify():
    """Report, but do not enforce, CUDA visibility.

    A missing driver is worth telling the user about, but failing the install over it
    would leave them with nothing installed to fix it with.
    """
    progress(97, "Checking the GPU")
    result = subprocess.run(
        [sys.executable, "-c", CUDA_SCRIPT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    log(result.stdout)
    log(result.stderr)

    if result.returncode != 0:
        warn(
            "No CUDA GPU is visible to PyTorch. Transcriber is installed, but it needs "
            "an up-to-date NVIDIA driver to transcribe. Install the latest driver from "
            "nvidia.com and restart the computer."
        )
        return False
    return True


def step_finalize(app_version, install_dir):
    from transcriber import install_state

    install_state.record_app(app_version, install_dir)
    progress(100, "Setup complete")


# --------------------------------------------------------------------------- entry


def do_check(app_dir):
    """Print the current install state as JSON, for the wizard's components page."""
    from transcriber import install_state

    requirements = os.path.join(app_dir, "requirements.txt")
    payload = {
        "app_version": install_state.installed_app_version(),
        "runtime_installed": install_state.runtime_is_installed(),
        "runtime_current": install_state.runtime_matches(requirements),
        "models": [
            {"name": name, "label": label, "installed": installed, "path": location}
            for name, label, installed, location in install_state.model_status()
        ],
    }
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Provision Transcriber's runtime and models.")
    parser.add_argument("--app-dir", required=True, help="Folder holding the installed app source.")
    parser.add_argument("--runtime-dir", help="Folder holding the private Python runtime.")
    parser.add_argument("--install-dir", help="Folder the wizard installed the program into.")
    parser.add_argument("--app-version", default="", help="Version being installed.")
    parser.add_argument("--models", default="", help="Comma-separated engines to install; default all.")
    parser.add_argument("--force-deps", action="store_true", help="Reinstall dependencies even if unchanged.")
    parser.add_argument("--force-models", action="store_true", help="Re-download weights even if present.")
    parser.add_argument("--check", action="store_true", help="Print install state as JSON and exit.")
    parser.add_argument("--progress-file", help="File the wizard polls for the current step.")
    args = parser.parse_args()

    app_dir = os.path.abspath(args.app_dir)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    if args.check:
        do_check(app_dir)
        return 0

    set_progress_file(args.progress_file)
    runtime_dir = args.runtime_dir or os.path.dirname(sys.executable)
    wanted = [name.strip() for name in args.models.split(",") if name.strip()]

    try:
        progress(2, "Starting setup")
        step_deps(app_dir, force=args.force_deps)
        step_models(app_dir, wanted=wanted or None, force=args.force_models)
        step_launcher(runtime_dir)
        step_verify()
        step_finalize(args.app_version, args.install_dir or app_dir)
    except ProvisionError as exc:
        emit("ERROR", str(exc))
        finish(1, str(exc))
        return 1
    except Exception as exc:  # the wizard needs a sentence, not a traceback
        message = "Unexpected setup failure: " + str(exc)
        emit("ERROR", message)
        log(repr(exc))
        finish(1, message)
        return 1

    finish(0, "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
